import asyncio
import ntpath
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import Request

from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.compatibility import CompatibilityAssessment, assess
from confighop_core.deployment import DeploymentPlan, build_deployment_plan
from confighop_core.hardware.registry import get_profile
from confighop_core.hardware.palo_alto import SYNTHETIC
from confighop_core.dependencies import build_dependency_index
from confighop_core.errors import ConfigParseError
from confighop_core.models.dependency import ReferenceType
from confighop_core.models.hardware import HardwareProfile, ProfileStatus
from confighop_core.models.inventory import PaloAltoInventory
from confighop_core.models.mapping import InterfaceMapping, MigrationPreview, PreviewStatus
from confighop_core.models.transformation import CandidateRenderResult
from confighop_core.parsers.palo_alto.parser import MAX_XML_BYTES

from .schemas import (
    CandidateMetadata, DependencySummary, InventorySummary, InventoryView, PhysicalInterfaceView,
    DeviceIdentityView, PlatformView, ProfileDetail, ProfileSummary, ProjectView,
    SourceConnectionTestView, SourceProvenance, SourceView,
)
from .panos_xml import XmlApiError, create_source_client, export_configuration, read_system_info
from .project_state import (
    DeploymentPackage, DeviceIdentity, ProjectDatabase, SourceSnapshot, mapping_hash,
    package_input_hash, sha256_file,
)


PROFILE_ID = "paloalto-synthetic-64"
SYNTHETIC_PROFILE = SYNTHETIC


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def xml_api_service_error(exc: XmlApiError) -> ServiceError:
    status = {
        "XML_API_ENDPOINT_INVALID": 400,
        "XML_API_KEY_REQUIRED": 400,
        "XML_API_TLS_REQUIRED": 400,
        "XML_API_CA_INVALID": 400,
        "XML_API_ENDPOINT_NOT_ALLOWED": 403,
        "XML_API_EXPORT_TOO_LARGE": 413,
        "XML_API_TRANSPORT_ERROR": 502,
        "XML_API_TLS_FAILED": 502,
        "XML_API_HTTP_ERROR": 502,
        "XML_API_REDIRECT": 502,
        "XML_API_TIMEOUT": 504,
    }.get(exc.code, 422)
    return ServiceError(exc.code, str(exc), status)


@dataclass
class ProjectSession:
    project_id: str
    workspace: Path
    database: ProjectDatabase | None = field(default=None, repr=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    deleted: bool = False
    source_filename: str | None = None
    source_size_bytes: int | None = None
    source_provenance: SourceProvenance | None = None
    inventory: PaloAltoInventory | None = None
    profile_id: str | None = None
    source_profile_id: str | None = None
    source_panos_train: str | None = None
    target_panos_train: str | None = None
    compatibility: CompatibilityAssessment | None = None
    mappings: list[InterfaceMapping] = field(default_factory=list)
    preview: MigrationPreview | None = None
    candidate: CandidateRenderResult | None = None
    active_snapshot_id: str | None = None
    active_package_id: str | None = None
    integrity_error: bool = False

    @property
    def source_path(self) -> Path:
        return self.workspace / "snapshots" / (self.active_snapshot_id or "unavailable") / "source.xml"

    @property
    def candidate_path(self) -> Path:
        return self.workspace / "candidate.xml"

    def export_state(self) -> dict:
        return dict(project_id=self.project_id, source_filename=self.source_filename,
            source_size_bytes=self.source_size_bytes,
            source_provenance=self.source_provenance.model_dump(mode="json") if self.source_provenance else None,
            active_snapshot_id=self.active_snapshot_id, active_package_id=self.active_package_id,
            profile_id=self.profile_id, source_profile_id=self.source_profile_id,
            source_panos_train=self.source_panos_train, target_panos_train=self.target_panos_train,
            mappings=[item.model_dump(mode="json") for item in self.mappings],
            compatibility=self.compatibility.model_dump(mode="json") if self.compatibility else None,
            preview=self.preview.model_dump(mode="json") if self.preview else None,
            candidate=self.candidate.model_dump(mode="json") if self.candidate else None)

    def persist(self) -> None:
        if self.database:
            self.database.save_project(self.project_id, self.export_state())

    def verify_source(self) -> None:
        snapshot = self.database.snapshot(self.active_snapshot_id) if self.active_snapshot_id and self.database else None
        if self.integrity_error or not self.active_snapshot_id or not self.source_provenance or (
            not snapshot or snapshot.project_id != self.project_id or snapshot.sha256 != self.source_provenance.sha256 or
            not self.source_path.is_file() or sha256_file(self.source_path) != self.source_provenance.sha256
        ):
            self.integrity_error = True
            raise ServiceError("SOURCE_INTEGRITY_FAILED", "Source snapshot integrity check failed.", 409)

    def invalidate(self, reason: str = "INPUT_CHANGED", *, persist: bool = True) -> None:
        if self.active_package_id and self.database:
            self.database.invalidate_package(self.active_package_id, reason)
        self.active_package_id = None
        self.compatibility = None
        self.mappings = []
        self.preview = None
        self.candidate = None
        if persist:
            self.persist()
        self.candidate_path.unlink(missing_ok=True)


class ProjectStore:
    def __init__(self, data_dir: Path | None = None):
        self.root = tempfile.TemporaryDirectory(prefix="confighop-") if data_dir is None else None
        self.data_dir = Path(self.root.name) if self.root else Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = ProjectDatabase(self.data_dir)
        self.projects: dict[str, ProjectSession] = {}
        self.lock = asyncio.Lock()
        self.max_source_bytes = MAX_XML_BYTES
        for state in self.database.projects():
            project_id = state["project_id"]
            project = ProjectSession(project_id, self.data_dir / project_id, database=self.database)
            project.source_filename = state.get("source_filename")
            project.source_size_bytes = state.get("source_size_bytes")
            project.source_provenance = SourceProvenance.model_validate(state["source_provenance"]) if state.get("source_provenance") else None
            project.active_snapshot_id = state.get("active_snapshot_id")
            project.active_package_id = state.get("active_package_id")
            project.profile_id = state.get("profile_id")
            project.source_profile_id = state.get("source_profile_id")
            project.source_panos_train = state.get("source_panos_train")
            project.target_panos_train = state.get("target_panos_train")
            project.mappings = [InterfaceMapping.model_validate(item) for item in state.get("mappings", [])]
            project.compatibility = CompatibilityAssessment.model_validate(state["compatibility"]) if state.get("compatibility") else None
            project.preview = MigrationPreview.model_validate(state["preview"]) if state.get("preview") else None
            project.candidate = CandidateRenderResult.model_validate(state["candidate"]) if state.get("candidate") else None
            if project.active_snapshot_id:
                snapshot = self.database.snapshot(project.active_snapshot_id)
                if not project.source_provenance or not snapshot or snapshot.project_id != project.project_id or (
                    snapshot.sha256 != project.source_provenance.sha256 or not project.source_path.is_file() or
                    sha256_file(project.source_path) != project.source_provenance.sha256):
                    project.integrity_error = True
                else:
                    try:
                        project.inventory = parse_palo_alto_xml(project.source_path)
                    except ConfigParseError:
                        project.integrity_error = True
            if project.integrity_error:
                if project.active_package_id:
                    self.database.invalidate_package(project.active_package_id, "SOURCE_INTEGRITY_FAILED")
                project.active_package_id = None
                project.candidate = None
                project.preview = None
                project.compatibility = None
                project.persist()
            if project.candidate and project.candidate.validation.valid and (
                not project.candidate_path.is_file() or sha256_file(project.candidate_path) != project.candidate.candidate_sha256
            ):
                if project.active_package_id:
                    self.database.invalidate_package(project.active_package_id, "CANDIDATE_INTEGRITY_FAILED")
                project.candidate = None
                project.preview = None
                project.compatibility = None
                project.active_package_id = None
                project.persist()
            self.projects[project_id] = project

    async def create(self) -> ProjectSession:
        async with self.lock:
            project_id = str(uuid4())
            workspace = self.data_dir / project_id
            workspace.mkdir(mode=0o700)
            project = ProjectSession(project_id, workspace, database=self.database)
            project.persist()
            self.projects[project_id] = project
            return project

    def get(self, project_id: str) -> ProjectSession:
        project = self.projects.get(project_id)
        if project is None or project.deleted:
            raise ServiceError("PROJECT_NOT_FOUND", "Project session was not found.", 404)
        return project

    async def delete(self, project_id: str) -> None:
        project = self.get(project_id)
        async with project.lock:
            project.deleted = True
            async with self.lock:
                self.projects.pop(project_id, None)
            self.database.delete_project(project_id)
            shutil.rmtree(project.workspace)

    def close(self) -> None:
        self.database.close()
        if self.root:
            self.root.cleanup()


def sanitize_filename(value: str | None) -> str:
    name = ntpath.basename((value or "source.xml").replace("/", "\\"))
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:100].strip("._")
    return name or "source.xml"


def project_view(project: ProjectSession) -> ProjectView:
    state = "EMPTY"
    if project.integrity_error:
        state = "SOURCE_INTEGRITY_FAILED"
    elif project.inventory:
        state = "SOURCE_READY"
    if project.preview and not project.integrity_error:
        state = {PreviewStatus.READY: "PREVIEW_READY", PreviewStatus.REVIEW_REQUIRED: "PREVIEW_REVIEW_REQUIRED",
            PreviewStatus.BLOCKED: "PREVIEW_BLOCKED"}[project.preview.status]
    if project.candidate and project.candidate.validation.valid and not project.integrity_error:
        state = "CANDIDATE_READY"
    return ProjectView(project_id=project.project_id, state=state,
        source_available=project.inventory is not None and not project.integrity_error,
        source_filename=project.source_filename,
        source_size_bytes=project.source_size_bytes, source_provenance=project.source_provenance,
        active_snapshot_id=project.active_snapshot_id, active_package_id=project.active_package_id,
        target_profile_id=project.profile_id,
        source_profile_id=project.source_profile_id, source_panos_train=project.source_panos_train,
        target_panos_train=project.target_panos_train,
        latest_platform_assessment=project.compatibility.platform if project.compatibility and not project.integrity_error else None,
        latest_hardware_assessment=project.compatibility.hardware if project.compatibility and not project.integrity_error else None,
        preview_available=project.preview is not None and not project.integrity_error,
        preview_status=project.preview.status if project.preview and not project.integrity_error else None,
        candidate_available=bool(project.candidate and project.candidate.validation.valid and not project.integrity_error),
        candidate_sha256=project.candidate.candidate_sha256 if project.candidate and project.candidate.validation.valid and not project.integrity_error else None,
        candidate_size_bytes=project.candidate.candidate_size_bytes if project.candidate and project.candidate.validation.valid and not project.integrity_error else None)


def inventory_summary(inventory: PaloAltoInventory) -> InventorySummary:
    return InventorySummary(physical_interfaces=len(inventory.physical_interfaces), subinterfaces=len(inventory.subinterfaces),
        aggregate_interfaces=len(inventory.aggregate_interfaces), vlan_interfaces=len(inventory.vlan_interfaces),
        loopbacks=len(inventory.loopback_interfaces), zones=len(inventory.zones),
        virtual_routers=len(inventory.virtual_routers), static_routes=len(inventory.static_routes),
        address_objects=len(inventory.address_objects), service_objects=len(inventory.service_objects),
        security_rules=len(inventory.security_rules), nat_rules=len(inventory.nat_rules),
        parser_warnings=len(inventory.warnings))


def inventory_view(inventory: PaloAltoInventory) -> InventoryView:
    index = build_dependency_index(inventory)
    rows = []
    for physical in inventory.physical_interfaces:
        children = [child.name for child in inventory.subinterfaces if child.parent_interface == physical.name]
        references = [ref for name in [physical.name, *children] for ref in index.get(name, [])]
        counts = {kind: sum(ref.reference_type == kind for ref in references) for kind in ReferenceType}
        summary = DependencySummary(zone_references=counts[ReferenceType.ZONE_INTERFACE],
            virtual_router_references=counts[ReferenceType.VIRTUAL_ROUTER_INTERFACE],
            static_route_references=counts[ReferenceType.STATIC_ROUTE_EGRESS_INTERFACE],
            nat_references=counts[ReferenceType.NAT_INTERFACE_REFERENCE],
            aggregate_memberships=counts[ReferenceType.AGGREGATE_MEMBERSHIP], child_count=len(children))
        rows.append(PhysicalInterfaceView(name=physical.name, mode=physical.mode,
            link_state=physical.link_state, link_speed=physical.link_speed, link_duplex=physical.link_duplex,
            link_speed_explicit=physical.link_speed_explicit, link_duplex_explicit=physical.link_duplex_explicit,
            ip_addresses=physical.ip_addresses, management_profile=physical.management_profile,
            aggregate_group=physical.aggregate_group, subinterface_count=len(children), subinterface_names=children,
            zone_names=list(dict.fromkeys(f"{ref.scope}/{ref.object_name}" for ref in references
                if ref.reference_type == ReferenceType.ZONE_INTERFACE)),
            dependency_count=len(references), dependency_summary=summary))
    return InventoryView(platform=PlatformView.model_validate(inventory.platform.model_dump()),
        summary=inventory_summary(inventory), physical_interfaces=rows, parser_warnings=inventory.warnings)


def profile_summary(profile_id: str = PROFILE_ID) -> ProfileSummary:
    profile = get_profile(profile_id)
    if profile is None:
        raise ServiceError("TARGET_PROFILE_NOT_FOUND", "Target profile was not found.", 404)
    return ProfileSummary(id=profile_id, vendor=profile.vendor, model=profile.model,
        domain=profile.domain.value, software_family=profile.software_family.value,
        target_render_support=profile.target_render_support.value,
        profile_status=profile.profile_status.value, interface_count=len(profile.interfaces), series=profile.series,
        verified_at=profile.verified_at,
        native_interface_count=sum(item.availability.value == "NATIVE" for item in profile.interfaces),
        conditional_interface_count=sum(item.availability.value == "NATIVE_CONDITIONAL" for item in profile.interfaces),
        breakout_interface_count=sum(item.availability.value == "BREAKOUT_CHILD" for item in profile.interfaces),
        candidate_ready_interface_count=sum(item.candidate_support.value == "SUPPORTED" for item in profile.interfaces),
        supported_panos_trains=profile.supported_panos_trains, evidence_ids=profile.evidence_ids)


def profile_detail(profile_id: str) -> ProfileDetail:
    profile = get_profile(profile_id)
    if profile is None:
        raise ServiceError("TARGET_PROFILE_NOT_FOUND", "Target profile was not found.", 404)
    return ProfileDetail(**profile_summary(profile_id).model_dump(), interfaces=[item.name for item in profile.interfaces],
        port_details=[item.model_dump(mode="json") for item in profile.interfaces],
        interface_groups=profile.interface_groups, first_supported_release=profile.first_supported_release, notes=profile.notes,
        software_support_rules=[rule.model_dump(mode="json") for rule in profile.software_support_rules])


async def upload_source(store: ProjectStore, project: ProjectSession, request: Request, filename: str | None) -> SourceView:
    async with project.lock:
        if project.deleted:
            raise ServiceError("PROJECT_NOT_FOUND", "Project session was not found.", 404)
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > store.max_source_bytes:
                    raise ServiceError("SOURCE_TOO_LARGE", "Source exceeds the upload limit.", 413)
            except ValueError as exc:
                raise ServiceError("INVALID_REQUEST", "Invalid content length.", 400) from exc
        temporary = project.workspace / f"upload-{uuid4().hex}.tmp"
        size = 0
        try:
            with temporary.open("xb") as stream:
                os.chmod(temporary, 0o600)
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > store.max_source_bytes:
                        raise ServiceError("SOURCE_TOO_LARGE", "Source exceeds the upload limit.", 413)
                    stream.write(chunk)
            return await ingest_source_file(store, project, temporary, filename=filename,
                origin="FILE_UPLOADED", snapshot_kind="UNVERIFIED")
        finally:
            temporary.unlink(missing_ok=True)


async def ingest_source_file(store: ProjectStore, project: ProjectSession, temporary: Path, *,
    filename: str | None, origin: str, snapshot_kind: str, serial: str | None = None,
    model: str | None = None, panos_version: str | None = None,
    hostname: str | None = None) -> SourceView:
    size = temporary.stat().st_size
    if size > store.max_source_bytes:
        raise ServiceError("SOURCE_TOO_LARGE", "Source exceeds the upload limit.", 413)
    try:
        inventory = await asyncio.to_thread(parse_palo_alto_xml, temporary)
    except ConfigParseError as exc:
        raise ServiceError("SOURCE_PARSE_FAILED", "Source is not valid supported PAN-OS XML.", 422) from exc
    digest = sha256_file(temporary)
    provenance = SourceProvenance(origin=origin, snapshot_kind=snapshot_kind, sha256=digest,
        received_at_utc=datetime.now(timezone.utc), serial=serial, model=model,
        panos_version=panos_version, hostname=hostname)
    snapshot_id = str(uuid4())
    snapshot_dir = project.workspace / "snapshots" / snapshot_id
    snapshot_dir.mkdir(parents=True, mode=0o700)
    snapshot_path = snapshot_dir / "source.xml"
    source_filename = sanitize_filename(filename)
    identity = DeviceIdentity(hostname=hostname, serial=serial, model=model,
        panos_version=panos_version, observed_at_utc=provenance.received_at_utc) if all(
        value is not None for value in (hostname, serial, model, panos_version)) else None
    snapshot = SourceSnapshot(snapshot_id=snapshot_id, project_id=project.project_id,
        filename=source_filename, size_bytes=size, sha256=digest, origin=origin,
        snapshot_kind=snapshot_kind, received_at_utc=provenance.received_at_utc, identity=identity)
    state = project.export_state()
    state.update(source_filename=source_filename, source_size_bytes=size,
        source_provenance=provenance.model_dump(mode="json"), active_snapshot_id=snapshot_id,
        active_package_id=None, compatibility=None, mappings=[], preview=None, candidate=None)
    try:
        os.replace(temporary, snapshot_path)
        project.database.save_snapshot(snapshot, state)
    except Exception:
        snapshot_path.unlink(missing_ok=True)
        snapshot_dir.rmdir()
        raise
    project.inventory = inventory
    project.source_filename = source_filename
    project.source_size_bytes = size
    project.source_provenance = provenance
    project.active_snapshot_id = snapshot_id
    project.active_package_id = None
    project.integrity_error = False
    project.invalidate(persist=False)
    return SourceView(project_id=project.project_id, filename=project.source_filename, size_bytes=size,
        platform=PlatformView.model_validate(inventory.platform.model_dump()),
        inventory_summary=inventory_summary(inventory), provenance=provenance)


async def collect_source_from_client(store: ProjectStore, project: ProjectSession,
    client: httpx.AsyncClient, api_key: str, *, operation_timeout_seconds: float = 60.0) -> SourceView:
    async with project.lock:
        require_live(project)
        try:
            async with asyncio.timeout(operation_timeout_seconds):
                identity_before = await read_system_info(client, api_key)
                first = await export_configuration(client, api_key, max_bytes=store.max_source_bytes)
                second = await export_configuration(client, api_key, max_bytes=store.max_source_bytes)
                identity_after = await read_system_info(client, api_key)
        except TimeoutError:
            raise ServiceError("XML_API_OPERATION_TIMEOUT", "The source collection operation timed out.", 504) from None
        except XmlApiError as exc:
            raise xml_api_service_error(exc) from None
        if identity_before != identity_after:
            raise ServiceError("SOURCE_IDENTITY_CHANGED", "The source device identity changed during collection.", 409)
        if first != second:
            raise ServiceError("SOURCE_CONFIG_CHANGED", "The source configuration changed during collection.", 409)

        temporary = project.workspace / f"collect-{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as stream:
                os.chmod(temporary, 0o600)
                stream.write(first)
            return await ingest_source_file(store, project, temporary,
                filename=f"{identity_before.serial}-configuration.xml", origin="API_COLLECTED",
                snapshot_kind="UNVERIFIED", serial=identity_before.serial,
                model=identity_before.model, panos_version=identity_before.panos_version,
                hostname=identity_before.hostname)
        finally:
            temporary.unlink(missing_ok=True)


async def collect_source(store: ProjectStore, project: ProjectSession, *, host: str, port: int,
    api_key: str, ca_pem: str | None, allowed_endpoints: set[tuple[str, int]]) -> SourceView:
    try:
        client = create_source_client(host, port, allowed_endpoints=allowed_endpoints, ca_pem=ca_pem)
    except XmlApiError as exc:
        raise xml_api_service_error(exc) from None
    async with client:
        return await collect_source_from_client(store, project, client, api_key)


async def test_source_connection(*, host: str, port: int, api_key: str, ca_pem: str | None,
    allowed_endpoints: set[tuple[str, int]], operation_timeout_seconds: float = 15.0) -> SourceConnectionTestView:
    try:
        client = create_source_client(host, port, allowed_endpoints=allowed_endpoints, ca_pem=ca_pem)
    except XmlApiError as exc:
        raise xml_api_service_error(exc) from None
    try:
        async with client:
            async with asyncio.timeout(operation_timeout_seconds):
                identity = await read_system_info(client, api_key)
    except TimeoutError:
        raise ServiceError("XML_API_OPERATION_TIMEOUT", "The source connection test timed out.", 504) from None
    except XmlApiError as exc:
        raise xml_api_service_error(exc) from None
    return SourceConnectionTestView(host=host, port=port, tested_at_utc=datetime.now(timezone.utc),
        identity=DeviceIdentityView(hostname=identity.hostname, serial=identity.serial,
            model=identity.model, panos_version=identity.panos_version))


def require_inventory(project: ProjectSession) -> PaloAltoInventory:
    require_live(project)
    if project.integrity_error:
        raise ServiceError("SOURCE_INTEGRITY_FAILED", "Source snapshot integrity check failed.", 409)
    if project.inventory is None:
        raise ServiceError("SOURCE_REQUIRED", "Upload a valid PAN-OS XML source first.", 409)
    return project.inventory


def require_profile(project: ProjectSession) -> HardwareProfile:
    require_live(project)
    if project.profile_id is None:
        raise ServiceError("TARGET_PROFILE_REQUIRED", "Select an available target profile first.", 409)
    profile = get_profile(project.profile_id)
    if profile is None:
        raise ServiceError("TARGET_PROFILE_NOT_FOUND", "Target profile was not found.", 404)
    return profile


def require_live(project: ProjectSession) -> None:
    if project.deleted:
        raise ServiceError("PROJECT_NOT_FOUND", "Project session was not found.", 404)


def select_profile(project: ProjectSession, profile_id: str | None, panos_train: str | None = None) -> ProjectView:
    require_live(project)
    if profile_id:
        profile_detail(profile_id)
    project.profile_id = profile_id
    project.target_panos_train = panos_train
    project.invalidate("TARGET_PROFILE_CHANGED")
    return project_view(project)


def select_source_profile(project: ProjectSession, profile_id: str | None, panos_train: str | None) -> ProjectView:
    require_live(project)
    if profile_id:
        profile_detail(profile_id)
    project.source_profile_id = profile_id
    project.source_panos_train = panos_train
    project.invalidate("SOURCE_PROFILE_CHANGED")
    return project_view(project)


def assess_project(project: ProjectSession, mappings: list[InterfaceMapping]) -> CompatibilityAssessment:
    inventory = require_inventory(project)
    project.invalidate("MAPPING_CHANGED")
    project.mappings = mappings
    project.compatibility = assess(inventory, project.source_profile_id, project.source_panos_train,
        project.profile_id, project.target_panos_train, mappings)
    project.persist()
    return project.compatibility


async def update_preview(project: ProjectSession, mappings: list[InterfaceMapping]) -> MigrationPreview:
    inventory = require_inventory(project)
    profile = require_profile(project)
    project.invalidate("MAPPING_CHANGED")
    project.mappings = mappings
    if profile.profile_status == ProfileStatus.VERIFIED:
        project.compatibility = assess(inventory, project.source_profile_id, project.source_panos_train,
            project.profile_id, project.target_panos_train, mappings)
    project.preview = await asyncio.to_thread(preview_interface_mappings, inventory, mappings, profile)
    project.persist()
    return project.preview


def candidate_metadata(project: ProjectSession) -> CandidateMetadata:
    result = project.candidate
    if result is None and project.compatibility and project.compatibility.status.value == "BLOCKED":
        return CandidateMetadata(status=PreviewStatus.BLOCKED, candidate_available=False,
            candidate_sha256=None, candidate_size_bytes=None,
            preview_status=project.preview.status if project.preview else PreviewStatus.BLOCKED,
            plan_status=PreviewStatus.BLOCKED,
            findings=[{"code": item.code, "severity": item.severity, "message": item.message} for item in project.compatibility.findings],
            source_profile_id=project.source_profile_id, target_profile_id=project.profile_id,
            source_profile_status=get_profile(project.source_profile_id).profile_status.value if get_profile(project.source_profile_id or "") else None,
            target_profile_status=get_profile(project.profile_id).profile_status.value if get_profile(project.profile_id or "") else None,
            target_render_support=get_profile(project.profile_id).target_render_support.value if get_profile(project.profile_id or "") else None,
            effective_panos_version=project.compatibility.platform.effective_source_version,
            platform_assessment_status=project.compatibility.platform.status.value,
            hardware_assessment_status=project.compatibility.hardware.status.value,
            evidence_ids=project.compatibility.evidence_ids,
            deployment_plan=project_deployment_plan(project))
    if result is None or project.preview is None:
        raise ServiceError("CANDIDATE_NOT_AVAILABLE", "Candidate result is not available.", 409)
    overall = result.status
    if project.compatibility and project.compatibility.status.value == "REVIEW_REQUIRED" and overall == PreviewStatus.READY:
        overall = PreviewStatus.REVIEW_REQUIRED
    return CandidateMetadata(status=overall, candidate_available=result.validation.valid,
        candidate_sha256=result.candidate_sha256, candidate_size_bytes=result.candidate_size_bytes,
        preview_status=project.preview.status, plan_status=result.plan.status, validation=result.validation,
        semantic_diff=result.semantic_diff, findings=result.plan.findings, plan=result.plan,
        summary=project.preview.summary.model_dump(), source_profile_id=project.source_profile_id,
        target_profile_id=project.profile_id,
        source_profile_status=get_profile(project.source_profile_id).profile_status.value if get_profile(project.source_profile_id or "") else None,
        target_profile_status=get_profile(project.profile_id).profile_status.value if get_profile(project.profile_id or "") else None,
        target_render_support=get_profile(project.profile_id).target_render_support.value if get_profile(project.profile_id or "") else None,
        effective_panos_version=project.compatibility.platform.effective_source_version if project.compatibility else None,
        platform_assessment_status=project.compatibility.platform.status.value if project.compatibility else None,
        hardware_assessment_status=project.compatibility.hardware.status.value if project.compatibility else None,
        evidence_ids=project.compatibility.evidence_ids if project.compatibility else [],
        deployment_plan=project_deployment_plan(project))


def project_deployment_plan(project: ProjectSession) -> DeploymentPlan | None:
    if (project.inventory is None or project.preview is None or project.compatibility is None
            or not project.source_profile_id or not project.source_panos_train or not project.target_panos_train):
        return None
    profile = get_profile(project.profile_id or "")
    if profile is None:
        return None
    return build_deployment_plan(project.inventory, project.source_profile_id, project.source_panos_train,
        profile, project.target_panos_train, project.mappings, project.preview, project.compatibility,
        project.candidate)


async def generate_candidate(project: ProjectSession, mappings: list[InterfaceMapping], allow_review: bool) -> CandidateMetadata:
    inventory = require_inventory(project)
    profile = require_profile(project)
    project.verify_source()
    project.invalidate("MAPPING_CHANGED")
    project.mappings = mappings
    if profile.profile_status == ProfileStatus.VERIFIED:
        project.compatibility = assess(inventory, project.source_profile_id, project.source_panos_train,
            project.profile_id, project.target_panos_train, mappings)
    project.preview = await asyncio.to_thread(preview_interface_mappings, inventory, mappings, profile)
    if project.compatibility and (project.compatibility.status.value == "BLOCKED" or
            project.compatibility.status.value == "REVIEW_REQUIRED" and not allow_review):
        project.persist()
        return candidate_metadata(project) if project.compatibility.status.value == "BLOCKED" else blocked_review_metadata(project)
    if project.preview.status == PreviewStatus.BLOCKED or project.preview.status == PreviewStatus.REVIEW_REQUIRED and not allow_review:
        project.persist()
        return blocked_review_metadata(project)
    project.candidate = await asyncio.to_thread(render_panos_candidate, project.source_path, inventory,
        project.preview, profile, project.candidate_path, allow_review=allow_review,
        source_profile_id=project.source_profile_id, source_panos_train=project.source_panos_train,
        target_panos_train=project.target_panos_train)
    if project.candidate.validation.valid:
        package = DeploymentPackage(package_id=str(uuid4()), project_id=project.project_id,
            source_snapshot_id=project.active_snapshot_id, source_sha256=project.source_provenance.sha256,
            input_sha256=package_input_hash(source_sha256=project.source_provenance.sha256,
                source_profile_id=project.source_profile_id, target_profile_id=project.profile_id,
                source_panos_train=project.source_panos_train, target_panos_train=project.target_panos_train,
                mapping_sha256=mapping_hash(project.mappings), target_baseline_sha256=None),
            mapping_sha256=mapping_hash(project.mappings), source_profile_id=project.source_profile_id,
            target_profile_id=project.profile_id, source_panos_train=project.source_panos_train,
            target_panos_train=project.target_panos_train,
            candidate_sha256=project.candidate.candidate_sha256)
        project.database.save_package(package)
        project.active_package_id = package.package_id
    project.persist()
    return candidate_metadata(project)


def blocked_review_metadata(project: ProjectSession) -> CandidateMetadata:
    compatibility = project.compatibility
    blocked = (compatibility and compatibility.status.value == "BLOCKED") or (project.preview and project.preview.status == PreviewStatus.BLOCKED)
    return CandidateMetadata(status=PreviewStatus.BLOCKED if blocked else PreviewStatus.REVIEW_REQUIRED,
        candidate_available=False, candidate_sha256=None, candidate_size_bytes=None,
        preview_status=project.preview.status if project.preview else PreviewStatus.BLOCKED,
        plan_status=PreviewStatus.BLOCKED,
        findings=[{"code": item.code, "severity": item.severity, "message": item.message} for item in compatibility.findings] if compatibility else [],
        source_profile_id=project.source_profile_id, target_profile_id=project.profile_id,
        source_profile_status=get_profile(project.source_profile_id).profile_status.value if get_profile(project.source_profile_id or "") else None,
        target_profile_status=get_profile(project.profile_id).profile_status.value if get_profile(project.profile_id or "") else None,
        target_render_support=get_profile(project.profile_id).target_render_support.value if get_profile(project.profile_id or "") else None,
        effective_panos_version=compatibility.platform.effective_source_version if compatibility else None,
        platform_assessment_status=compatibility.platform.status.value if compatibility else None,
        hardware_assessment_status=compatibility.hardware.status.value if compatibility else None,
        evidence_ids=compatibility.evidence_ids if compatibility else [],
        deployment_plan=project_deployment_plan(project))
