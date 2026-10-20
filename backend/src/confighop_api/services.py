import asyncio
import hashlib
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
from confighop_core.models.hardware import HardwareProfile, ProfileStatus, TargetRenderSupport
from confighop_core.models.inventory import PaloAltoInventory
from confighop_core.models.mapping import InterfaceMapping, MigrationPreview, PreviewStatus
from confighop_core.models.transformation import CandidateRenderResult
from confighop_core.parsers.palo_alto.parser import MAX_XML_BYTES

from .schemas import (
    CandidateMetadata, DependencySummary, InventorySummary, InventoryView, PhysicalInterfaceView,
    DeviceIdentityView, PlatformView, ProfileDetail, ProfileSummary, ProjectView,
    SourceConnectionTestView, SourceProvenance, SourceView, TargetPreflightView,
)
from .artifacts import (
    ARTIFACT_FORMAT, ArtifactIntegrityError, ArtifactKeyError, EncryptedArtifactStore,
)
from .panos_xml import (
    XmlApiError, create_source_client, create_target_client, export_configuration,
    read_candidate_configuration, read_preflight_probe, read_running_configuration,
    read_system_info,
)
from .project_state import (
    DeploymentPackage, DeviceIdentity, ProjectDatabase, SourceSnapshot, TargetBaseline,
    make_review_decision, mapping_hash, package_input_hash, sha256_file,
)
from .target_package import TargetPackageError, analyze_target_safety, build_target_package


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
    target_baseline: TargetBaseline | None = None
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
            target_baseline=self.target_baseline.model_dump(mode="json") if self.target_baseline else None,
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
    def __init__(self, data_dir: Path | None = None, *, artifact_key: bytes | None = None):
        self.root = tempfile.TemporaryDirectory(prefix="confighop-") if data_dir is None else None
        self.data_dir = Path(self.root.name) if self.root else Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.artifacts = EncryptedArtifactStore(self.data_dir, artifact_key)
        self.database = ProjectDatabase(self.data_dir, artifacts=self.artifacts)
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
            project.target_baseline = TargetBaseline.model_validate(state["target_baseline"]) if state.get("target_baseline") else None
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
            if project.active_package_id:
                package = self.database.package(project.active_package_id)
                try:
                    if package is None:
                        raise ValueError("Package metadata is unavailable")
                    self.database.verify_package_artifacts(package)
                except ValueError:
                    if package is not None:
                        self.database.invalidate_package(package.package_id, "PACKAGE_INTEGRITY_FAILED")
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
    if (project.profile_id, project.target_panos_train) != (profile_id, panos_train):
        project.target_baseline = None
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


def record_target_baseline(project: ProjectSession, baseline: TargetBaseline) -> None:
    require_live(project)
    source_serial = project.source_provenance.serial if project.source_provenance else None
    if source_serial and source_serial == baseline.serial:
        raise ServiceError("SOURCE_TARGET_SAME_SERIAL", "Source and target serial must differ.", 409)
    previous = project.target_baseline
    identity = lambda item: (item.serial, item.model, item.hostname, item.panos_version, item.sha256)
    changed = previous is None or identity(previous) != identity(baseline)
    reason = "TARGET_BASELINE_CHANGED" if changed else None
    state = project.export_state()
    state["target_baseline"] = baseline.model_dump(mode="json")
    project.database.bind_target_baseline(project.project_id, state, reason)
    project.target_baseline = baseline
    if changed:
        project.active_package_id = None


async def collect_target_baseline_from_client(store: ProjectStore, project: ProjectSession,
    client: httpx.AsyncClient, api_key: str, *, expected_serial: str, expected_model: str,
    operation_timeout_seconds: float = 60.0) -> TargetBaseline:
    async with project.lock:
        require_inventory(project)
        project.verify_source()
        profile = require_profile(project)
        source_serial = project.source_provenance.serial if project.source_provenance else None
        if not source_serial:
            raise ServiceError("SOURCE_SERIAL_UNVERIFIED",
                "Collect the source device identity through the API before binding a target baseline.", 409)
        if expected_serial == source_serial:
            raise ServiceError("SOURCE_TARGET_SAME_SERIAL", "Source and target serial must differ.", 409)
        if expected_model != profile.model:
            raise ServiceError("TARGET_MODEL_MISMATCH", "Expected target model differs from the selected profile.", 409)
        try:
            store.artifacts.require_key()
        except ArtifactKeyError:
            raise ServiceError("ARTIFACT_KEY_REQUIRED",
                "Configure CONFIGHOP_ARTIFACT_KEY_B64 before collecting a target configuration.", 503) from None
        try:
            async with asyncio.timeout(operation_timeout_seconds):
                identity_before = await read_system_info(client, api_key)
                first = await read_running_configuration(client, api_key, max_bytes=store.max_source_bytes)
                second = await read_running_configuration(client, api_key, max_bytes=store.max_source_bytes)
                identity_after = await read_system_info(client, api_key)
        except TimeoutError:
            raise ServiceError("XML_API_OPERATION_TIMEOUT", "Target baseline collection timed out.", 504) from None
        except XmlApiError as exc:
            raise xml_api_service_error(exc) from None
        if identity_before != identity_after:
            raise ServiceError("TARGET_IDENTITY_CHANGED", "Target identity changed during baseline collection.", 409)
        if first != second:
            raise ServiceError("TARGET_CONFIG_CHANGED", "Target active configuration changed during baseline collection.", 409)
        if identity_before.serial != expected_serial or identity_before.serial == source_serial:
            raise ServiceError("TARGET_SERIAL_MISMATCH", "Target serial differs from the confirmed device.", 409)
        if identity_before.model != expected_model:
            raise ServiceError("TARGET_MODEL_MISMATCH", "Target model differs from the selected profile.", 409)
        if project.target_panos_train and not identity_before.panos_version.startswith(
            project.target_panos_train + "."):
            raise ServiceError("TARGET_PANOS_TRAIN_MISMATCH",
                "Target PAN-OS version differs from the selected train.", 409)
        baseline = TargetBaseline(serial=identity_before.serial, model=identity_before.model,
            hostname=identity_before.hostname, panos_version=identity_before.panos_version,
            multi_vsys=identity_before.multi_vsys,
            operational_mode=identity_before.operational_mode,
            sha256=hashlib.sha256(first).hexdigest(), artifact_format=ARTIFACT_FORMAT,
            artifact_size_bytes=len(first))
        previous = project.target_baseline
        try:
            store.artifacts.write_target_baseline(project.project_id, baseline.baseline_id,
                first, baseline.sha256)
            record_target_baseline(project, baseline)
        except (ArtifactIntegrityError, ArtifactKeyError) as exc:
            store.artifacts.delete_target_baseline(project.project_id, baseline.baseline_id)
            raise ServiceError("TARGET_BASELINE_ARTIFACT_FAILED",
                "Target baseline could not be stored securely.", 500) from exc
        except Exception:
            store.artifacts.delete_target_baseline(project.project_id, baseline.baseline_id)
            raise
        if previous and previous.baseline_id != baseline.baseline_id:
            store.artifacts.delete_target_baseline(project.project_id, previous.baseline_id)
        return baseline


async def collect_target_baseline(store: ProjectStore, project: ProjectSession, *,
    host: str, port: int, api_key: str, ca_pem: str | None, expected_serial: str,
    expected_model: str, allowed_endpoints: set[tuple[str, int]]) -> TargetBaseline:
    try:
        client = create_target_client(host, port, allowed_endpoints=allowed_endpoints, ca_pem=ca_pem)
    except XmlApiError as exc:
        raise xml_api_service_error(exc) from None
    async with client:
        return await collect_target_baseline_from_client(store, project, client, api_key,
            expected_serial=expected_serial, expected_model=expected_model)


async def build_target_deployment_package(store: ProjectStore,
    project: ProjectSession) -> DeploymentPackage:
    async with project.lock:
        require_inventory(project)
        project.verify_source()
        baseline = project.target_baseline
        if baseline is None:
            raise ServiceError("TARGET_BASELINE_REQUIRED", "Collect a target baseline first.", 409)
        if not project.active_package_id:
            raise ServiceError("PACKAGE_NOT_AVAILABLE", "Generate a source candidate after collecting the target baseline.", 409)
        package = store.database.package(project.active_package_id)
        if package is None or package.status != "DRAFT_UNDEPLOYABLE":
            raise ServiceError("PACKAGE_NOT_BUILDABLE", "The active package cannot be rebuilt.", 409)
        if package.target_baseline_sha256 != baseline.sha256 or package.target_serial != baseline.serial:
            raise ServiceError("TARGET_BASELINE_MISMATCH", "The package is not bound to the current target baseline.", 409)
        if package.review_id or package.deployable_candidate_sha256:
            raise ServiceError("TARGET_PACKAGE_ALREADY_BUILT",
                "The active target package is already built. Regenerate the source candidate to replace it.", 409)
        try:
            store.database.verify_package_artifacts(package)
            target_xml = store.artifacts.read_target_baseline(project.project_id,
                baseline.baseline_id, baseline.sha256, max_plaintext_bytes=store.max_source_bytes)
        except ArtifactKeyError:
            raise ServiceError("ARTIFACT_KEY_REQUIRED",
                "Configure CONFIGHOP_ARTIFACT_KEY_B64 before building a target package.", 503) from None
        except (ArtifactIntegrityError, ValueError):
            raise ServiceError("TARGET_BASELINE_ARTIFACT_INTEGRITY_FAILED",
                "The encrypted target baseline failed integrity verification.", 409) from None
        candidate_path = project.workspace / "packages" / package.package_id / "candidate.xml"
        try:
            result = await asyncio.to_thread(build_target_package, target_xml, candidate_path.read_bytes())
        except (OSError, TargetPackageError) as exc:
            raise ServiceError("TARGET_PACKAGE_BUILD_BLOCKED", str(exc), 409) from None
        if not result.changes:
            raise ServiceError("TARGET_PACKAGE_EMPTY", "No migration-owned changes were found for the target.", 409)
        deployable_sha256 = hashlib.sha256(result.xml).hexdigest()
        try:
            store.artifacts.write_deployable(project.project_id, package.package_id,
                result.xml, deployable_sha256)
            updated = package.model_copy(update={
                "deployable_candidate_sha256": deployable_sha256,
                "target_changes": result.changes,
                "target_preservation": result.preservation,
                "target_findings": result.findings,
            })
            store.database.update_draft_package(updated,
                expected_input_sha256=package.input_sha256, action="TARGET_PACKAGE_BUILT",
                evidence_sha256=deployable_sha256)
        except (ArtifactIntegrityError, ArtifactKeyError) as exc:
            store.artifacts.delete_deployable(project.project_id, package.package_id)
            raise ServiceError("TARGET_PACKAGE_ARTIFACT_FAILED",
                "The deployable package could not be stored securely.", 500) from exc
        except Exception:
            store.artifacts.delete_deployable(project.project_id, package.package_id)
            raise
        return updated


async def review_target_deployment_package(store: ProjectStore, project: ProjectSession, *,
    confirmed_target_hostname: str, accepted_finding_codes: list[str],
    actor_sha256: str) -> DeploymentPackage:
    async with project.lock:
        baseline = project.target_baseline
        if baseline is None or not project.active_package_id:
            raise ServiceError("TARGET_PACKAGE_NOT_AVAILABLE", "Build a target package first.", 409)
        package = store.database.package(project.active_package_id)
        if package is None or not package.deployable_candidate_sha256:
            raise ServiceError("TARGET_PACKAGE_NOT_AVAILABLE", "Build a target package first.", 409)
        if package.review_id:
            raise ServiceError("TARGET_PACKAGE_ALREADY_REVIEWED", "The target package is already reviewed.", 409)
        if confirmed_target_hostname != baseline.hostname:
            raise ServiceError("TARGET_HOSTNAME_CONFIRMATION_MISMATCH",
                "The confirmed hostname does not match the collected target.", 409)
        blocking = [item.code for item in package.target_findings if item.severity == "ERROR"]
        if blocking:
            raise ServiceError("TARGET_PACKAGE_FINDINGS_BLOCKED",
                "Resolve blocking target package findings before review.", 409)
        required = {item.code for item in package.target_findings if item.requires_acceptance}
        accepted = set(accepted_finding_codes)
        if accepted - required:
            raise ServiceError("TARGET_PACKAGE_REVIEW_INVALID",
                "Review contains finding codes that are not present in the package.", 400)
        if required - accepted:
            raise ServiceError("TARGET_PACKAGE_REVIEW_INCOMPLETE",
                "Accept every required target package finding before review.", 409)
        try:
            store.database.verify_package_artifacts(package)
        except ValueError:
            raise ServiceError("PACKAGE_INTEGRITY_FAILED",
                "Deployment package artifact integrity check failed.", 409) from None
        decision = make_review_decision(project_id=project.project_id,
            source_package_id=package.package_id, input_sha256=package.input_sha256,
            candidate_sha256=package.candidate_sha256 or "",
            deployable_candidate_sha256=package.deployable_candidate_sha256,
            accepted_finding_codes=sorted(accepted), actor_sha256=actor_sha256)
        try:
            store.database.save_review(decision)
            reviewed_input = package_input_hash(source_sha256=package.source_sha256,
                source_profile_id=package.source_profile_id,
                target_profile_id=package.target_profile_id,
                source_panos_train=package.source_panos_train,
                target_panos_train=package.target_panos_train,
                mapping_sha256=package.mapping_sha256,
                target_baseline_sha256=package.target_baseline_sha256,
                candidate_sha256=package.candidate_sha256,
                review_sha256=decision.decision_sha256,
                deployable_candidate_sha256=package.deployable_candidate_sha256,
                renderer_version=package.renderer_version)
            reviewed = package.model_copy(update={"review_id": decision.review_id,
                "review_sha256": decision.decision_sha256, "input_sha256": reviewed_input})
            store.database.update_draft_package(reviewed,
                expected_input_sha256=package.input_sha256, action="TARGET_PACKAGE_REVIEWED",
                evidence_sha256=decision.decision_sha256)
        except ValueError as exc:
            raise ServiceError("TARGET_PACKAGE_REVIEW_STALE",
                "Project inputs changed before the review could be recorded.", 409) from exc
        return reviewed


def _release_tuple(value: str | None) -> tuple[int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)", value or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


async def check_target_preflight_from_client(store: ProjectStore, project: ProjectSession,
    client: httpx.AsyncClient, api_key: str, *, expected_serial: str, expected_model: str,
    recovery_path_confirmed: bool = False,
    operation_timeout_seconds: float = 90.0) -> TargetPreflightView:
    async with project.lock:
        require_inventory(project)
        project.verify_source()
        profile = require_profile(project)
        baseline = project.target_baseline
        if baseline is None:
            raise ServiceError("TARGET_BASELINE_REQUIRED", "Collect a target baseline first.", 409)
        if (expected_serial, expected_model) != (baseline.serial, baseline.model):
            raise ServiceError("TARGET_CONFIRMATION_MISMATCH",
                "Confirmed target identity differs from the collected baseline.", 409)
        package = store.database.package(project.active_package_id) if project.active_package_id else None
        try:
            async with asyncio.timeout(operation_timeout_seconds):
                identity_before = await read_system_info(client, api_key)
                if (identity_before.serial, identity_before.model) != (baseline.serial, baseline.model):
                    project.database.detach_active_package(project.project_id, "TARGET_IDENTITY_DRIFT")
                    project.active_package_id = None
                    raise ServiceError("TARGET_IDENTITY_DRIFT", "Target identity differs from the collected baseline.", 409)
                running = await read_running_configuration(client, api_key, max_bytes=store.max_source_bytes)
                candidate = await read_candidate_configuration(client, api_key, max_bytes=store.max_source_bytes)
                change_summary_clear = await read_preflight_probe(client, api_key, "change_summary")
                commit_locks_clear = await read_preflight_probe(client, api_key, "commit_locks")
                pending_jobs_clear = await read_preflight_probe(client, api_key, "pending_jobs")
                running_again = await read_running_configuration(client, api_key, max_bytes=store.max_source_bytes)
                identity_after = await read_system_info(client, api_key)
        except TimeoutError:
            raise ServiceError("XML_API_OPERATION_TIMEOUT", "Target preflight check timed out.", 504) from None
        except XmlApiError as exc:
            raise xml_api_service_error(exc) from None
        if identity_before != identity_after or running != running_again:
            project.database.detach_active_package(project.project_id, "TARGET_CHANGED_DURING_PREFLIGHT")
            project.active_package_id = None
            raise ServiceError("TARGET_CHANGED_DURING_PREFLIGHT",
                "Target identity or active configuration changed during preflight.", 409)
        try:
            safety = analyze_target_safety(running, multi_vsys=identity_before.multi_vsys)
        except TargetPackageError:
            raise ServiceError("TARGET_TOPOLOGY_UNRECOGNIZED",
                "Target HA, Panorama, or virtual-system topology could not be evaluated.", 422) from None
        current_sha256 = hashlib.sha256(running).hexdigest()
        baseline_clear = (current_sha256 == baseline.sha256 and
            (identity_before.serial, identity_before.model, identity_before.hostname,
                identity_before.panos_version) ==
            (baseline.serial, baseline.model, baseline.hostname, baseline.panos_version))
        if not baseline_clear:
            project.database.detach_active_package(project.project_id, "TARGET_BASELINE_DRIFT")
            project.active_package_id = None
        source_serial = project.source_provenance.serial if project.source_provenance else None
        train = project.target_panos_train
        profile_clear = (profile.profile_status == ProfileStatus.VERIFIED and
            profile.target_render_support == TargetRenderSupport.SUPPORTED and
            profile.model == identity_before.model and train is not None and
            train in profile.supported_panos_trains and
            identity_before.panos_version.startswith(train + "."))
        current_release = _release_tuple(identity_before.panos_version)
        minimum_release = _release_tuple(profile.first_supported_release)
        minimum_release_clear = bool(current_release and minimum_release and
            current_release >= minimum_release)
        package_preserved = bool(package and package.deployable_candidate_sha256 and
            package.target_preservation and
            set(package.target_preservation.values()) == {"PRESERVED"} and
            not any(item.severity == "ERROR" for item in package.target_findings))
        review_clear = bool(package and package.review_id and package.review_sha256)
        package_status_clear = bool(package and package.status in {
            "DRAFT_UNDEPLOYABLE", "PREFLIGHT_PASSED"})
        checks = {
            "source_target_serial": "CLEAR" if source_serial and source_serial != baseline.serial else "BLOCKED",
            "profile_identity_and_train": "CLEAR" if profile_clear else "BLOCKED",
            "baseline_unchanged": "CLEAR" if baseline_clear else "BLOCKED",
            "candidate_matches_running": "CLEAR" if candidate == running else "BLOCKED",
            "change_summary_empty": "CLEAR" if change_summary_clear else "BLOCKED",
            "commit_locks_empty": "CLEAR" if commit_locks_clear else "BLOCKED",
            "pending_jobs_empty": "CLEAR" if pending_jobs_clear else "BLOCKED",
            "ha_state": "CLEAR" if safety.ha_clear else "BLOCKED",
            "panorama_ownership": "CLEAR" if safety.panorama_clear else "BLOCKED",
            "multi_vsys": "CLEAR" if safety.multi_vsys_clear else "BLOCKED",
            "minimum_software_release": "CLEAR" if minimum_release_clear else "BLOCKED",
            "capability_matrix": "CLEAR" if profile_clear else "BLOCKED",
            "recovery_path": "CLEAR" if recovery_path_confirmed else "BLOCKED",
            "target_local_preservation": "CLEAR" if package_preserved else "BLOCKED",
            "manual_review": "CLEAR" if review_clear else "BLOCKED",
            "package_state": "CLEAR" if package_status_clear else "BLOCKED",
        }
        blockers = [name for name, status in checks.items() if status != "CLEAR"]
        if not blockers and package is not None and package.status == "DRAFT_UNDEPLOYABLE":
            try:
                package = store.database.transition_package(package.package_id,
                    "PREFLIGHT_PASSED", expected_input_sha256=package.input_sha256)
            except ValueError as exc:
                raise ServiceError("TARGET_PREFLIGHT_STALE",
                    "Package inputs changed before preflight could pass.", 409) from exc
        passed = not blockers and package is not None and package.status == "PREFLIGHT_PASSED"
        return TargetPreflightView(target_serial=baseline.serial,
            package_id=package.package_id if package else None,
            observed_at_utc=datetime.now(timezone.utc),
            status="PASSED" if passed else "BLOCKED",
            checks=checks, blockers=blockers, deployment_allowed=passed)


async def check_target_preflight(store: ProjectStore, project: ProjectSession, *,
    host: str, port: int, api_key: str, ca_pem: str | None, expected_serial: str,
    expected_model: str, recovery_path_confirmed: bool,
    allowed_endpoints: set[tuple[str, int]]) -> TargetPreflightView:
    try:
        client = create_target_client(host, port, allowed_endpoints=allowed_endpoints, ca_pem=ca_pem)
    except XmlApiError as exc:
        raise xml_api_service_error(exc) from None
    async with client:
        return await check_target_preflight_from_client(store, project, client, api_key,
            expected_serial=expected_serial, expected_model=expected_model,
            recovery_path_confirmed=recovery_path_confirmed)


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
                mapping_sha256=mapping_hash(project.mappings),
                target_baseline_sha256=project.target_baseline.sha256 if project.target_baseline else None,
                candidate_sha256=project.candidate.candidate_sha256),
            mapping_sha256=mapping_hash(project.mappings), source_profile_id=project.source_profile_id,
            target_profile_id=project.profile_id, source_panos_train=project.source_panos_train,
            target_panos_train=project.target_panos_train,
            target_baseline_sha256=project.target_baseline.sha256 if project.target_baseline else None,
            target_serial=project.target_baseline.serial if project.target_baseline else None,
            candidate_sha256=project.candidate.candidate_sha256)
        package_dir = project.workspace / "packages" / package.package_id
        package_dir.mkdir(parents=True, mode=0o700)
        package_artifact = package_dir / "candidate.xml"
        try:
            shutil.copyfile(project.candidate_path, package_artifact)
            os.chmod(package_artifact, 0o600)
            if sha256_file(package_artifact) != package.candidate_sha256:
                raise ServiceError("CANDIDATE_INTEGRITY_FAILED", "Candidate artifact integrity check failed.", 409)
            state = project.export_state()
            state["active_package_id"] = package.package_id
            project.database.save_package(package, state=state)
        except Exception:
            package_artifact.unlink(missing_ok=True)
            package_dir.rmdir()
            project.candidate = None
            project.persist()
            raise
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
