import asyncio
import ntpath
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from fastapi import Request

from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.compatibility import CompatibilityAssessment, assess
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
    PlatformView, ProfileDetail, ProfileSummary, ProjectView, SourceView,
)


PROFILE_ID = "paloalto-synthetic-64"
SYNTHETIC_PROFILE = SYNTHETIC


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass
class ProjectSession:
    project_id: str
    workspace: Path
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    deleted: bool = False
    source_filename: str | None = None
    source_size_bytes: int | None = None
    inventory: PaloAltoInventory | None = None
    profile_id: str | None = None
    source_profile_id: str | None = None
    source_panos_train: str | None = None
    target_panos_train: str | None = None
    compatibility: CompatibilityAssessment | None = None
    mappings: list[InterfaceMapping] = field(default_factory=list)
    preview: MigrationPreview | None = None
    candidate: CandidateRenderResult | None = None

    @property
    def source_path(self) -> Path:
        return self.workspace / "source.xml"

    @property
    def candidate_path(self) -> Path:
        return self.workspace / "candidate.xml"

    def invalidate(self) -> None:
        self.compatibility = None
        self.mappings = []
        self.preview = None
        self.candidate = None
        self.candidate_path.unlink(missing_ok=True)


class ProjectStore:
    def __init__(self):
        self.root = tempfile.TemporaryDirectory(prefix="confighop-")
        self.projects: dict[str, ProjectSession] = {}
        self.lock = asyncio.Lock()
        self.max_source_bytes = MAX_XML_BYTES

    async def create(self) -> ProjectSession:
        async with self.lock:
            project_id = str(uuid4())
            workspace = Path(self.root.name) / project_id
            workspace.mkdir(mode=0o700)
            project = ProjectSession(project_id, workspace)
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
            shutil.rmtree(project.workspace)

    def close(self) -> None:
        self.root.cleanup()


def sanitize_filename(value: str | None) -> str:
    name = ntpath.basename((value or "source.xml").replace("/", "\\"))
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:100].strip("._")
    return name or "source.xml"


def project_view(project: ProjectSession) -> ProjectView:
    state = "EMPTY"
    if project.inventory:
        state = "SOURCE_READY"
    if project.preview:
        state = {PreviewStatus.READY: "PREVIEW_READY", PreviewStatus.REVIEW_REQUIRED: "PREVIEW_REVIEW_REQUIRED",
            PreviewStatus.BLOCKED: "PREVIEW_BLOCKED"}[project.preview.status]
    if project.candidate and project.candidate.validation.valid:
        state = "CANDIDATE_READY"
    return ProjectView(project_id=project.project_id, state=state,
        source_available=project.inventory is not None, source_filename=project.source_filename,
        source_size_bytes=project.source_size_bytes, target_profile_id=project.profile_id,
        source_profile_id=project.source_profile_id, source_panos_train=project.source_panos_train,
        target_panos_train=project.target_panos_train,
        latest_platform_assessment=project.compatibility.platform if project.compatibility else None,
        latest_hardware_assessment=project.compatibility.hardware if project.compatibility else None,
        preview_available=project.preview is not None,
        preview_status=project.preview.status if project.preview else None,
        candidate_available=bool(project.candidate and project.candidate.validation.valid),
        candidate_sha256=project.candidate.candidate_sha256 if project.candidate and project.candidate.validation.valid else None,
        candidate_size_bytes=project.candidate.candidate_size_bytes if project.candidate and project.candidate.validation.valid else None)


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
            try:
                inventory = await asyncio.to_thread(parse_palo_alto_xml, temporary)
            except ConfigParseError as exc:
                raise ServiceError("SOURCE_PARSE_FAILED", "Source is not valid supported PAN-OS XML.", 422) from exc
            os.replace(temporary, project.source_path)
            project.inventory = inventory
            project.source_filename = sanitize_filename(filename)
            project.source_size_bytes = size
            project.invalidate()
            return SourceView(project_id=project.project_id, filename=project.source_filename, size_bytes=size,
                platform=PlatformView.model_validate(inventory.platform.model_dump()),
                inventory_summary=inventory_summary(inventory))
        finally:
            temporary.unlink(missing_ok=True)


def require_inventory(project: ProjectSession) -> PaloAltoInventory:
    require_live(project)
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
    project.invalidate()
    return project_view(project)


def select_source_profile(project: ProjectSession, profile_id: str | None, panos_train: str | None) -> ProjectView:
    require_live(project)
    if profile_id:
        profile_detail(profile_id)
    project.source_profile_id = profile_id
    project.source_panos_train = panos_train
    project.invalidate()
    return project_view(project)


def assess_project(project: ProjectSession, mappings: list[InterfaceMapping]) -> CompatibilityAssessment:
    inventory = require_inventory(project)
    project.invalidate()
    project.mappings = mappings
    project.compatibility = assess(inventory, project.source_profile_id, project.source_panos_train,
        project.profile_id, project.target_panos_train, mappings)
    return project.compatibility


async def update_preview(project: ProjectSession, mappings: list[InterfaceMapping]) -> MigrationPreview:
    inventory = require_inventory(project)
    profile = require_profile(project)
    project.invalidate()
    project.mappings = mappings
    if profile.profile_status == ProfileStatus.VERIFIED:
        project.compatibility = assess(inventory, project.source_profile_id, project.source_panos_train,
            project.profile_id, project.target_panos_train, mappings)
    project.preview = await asyncio.to_thread(preview_interface_mappings, inventory, mappings, profile)
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
            evidence_ids=project.compatibility.evidence_ids)
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
        evidence_ids=project.compatibility.evidence_ids if project.compatibility else [])


async def generate_candidate(project: ProjectSession, mappings: list[InterfaceMapping], allow_review: bool) -> CandidateMetadata:
    inventory = require_inventory(project)
    profile = require_profile(project)
    project.invalidate()
    project.mappings = mappings
    if profile.profile_status == ProfileStatus.VERIFIED:
        project.compatibility = assess(inventory, project.source_profile_id, project.source_panos_train,
            project.profile_id, project.target_panos_train, mappings)
        if project.compatibility.status.value == "BLOCKED" or (project.compatibility.status.value == "REVIEW_REQUIRED" and not allow_review):
            return candidate_metadata(project) if project.compatibility.status.value == "BLOCKED" else blocked_review_metadata(project)
    project.preview = await asyncio.to_thread(preview_interface_mappings, inventory, mappings, profile)
    if project.preview.status == PreviewStatus.BLOCKED or project.preview.status == PreviewStatus.REVIEW_REQUIRED and not allow_review:
        return blocked_review_metadata(project)
    project.candidate = await asyncio.to_thread(render_panos_candidate, project.source_path, inventory,
        project.preview, profile, project.candidate_path, allow_review=allow_review,
        source_profile_id=project.source_profile_id, source_panos_train=project.source_panos_train,
        target_panos_train=project.target_panos_train)
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
        evidence_ids=compatibility.evidence_ids if compatibility else [])
