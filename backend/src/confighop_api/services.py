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
from confighop_core.dependencies import build_dependency_index
from confighop_core.errors import ConfigParseError
from confighop_core.models.dependency import ReferenceType
from confighop_core.models.hardware import HardwareInterface, HardwareKind, HardwareProfile, ProfileStatus
from confighop_core.models.inventory import PaloAltoInventory
from confighop_core.models.mapping import InterfaceMapping, MigrationPreview, PreviewStatus
from confighop_core.models.transformation import CandidateRenderResult
from confighop_core.parsers.palo_alto.parser import MAX_XML_BYTES

from .schemas import (
    CandidateMetadata, DependencySummary, InventorySummary, InventoryView, PhysicalInterfaceView,
    PlatformView, ProfileDetail, ProfileSummary, ProjectView, SourceView,
)


PROFILE_ID = "paloalto-synthetic-64"
SYNTHETIC_PROFILE = HardwareProfile(vendor="palo_alto", model="synthetic-panos-target-64",
    profile_status=ProfileStatus.SYNTHETIC,
    interfaces=[HardwareInterface(name=f"ethernet1/{number}", kind=HardwareKind.PHYSICAL_ETHERNET)
        for number in range(1, 65)], notes="Development profile only; no real hardware compatibility claim.")


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
            ip_addresses=physical.ip_addresses, management_profile=physical.management_profile,
            aggregate_group=physical.aggregate_group, subinterface_count=len(children), subinterface_names=children,
            zone_names=list(dict.fromkeys(f"{ref.scope}/{ref.object_name}" for ref in references
                if ref.reference_type == ReferenceType.ZONE_INTERFACE)),
            dependency_count=len(references), dependency_summary=summary))
    return InventoryView(platform=PlatformView.model_validate(inventory.platform.model_dump()),
        summary=inventory_summary(inventory), physical_interfaces=rows, parser_warnings=inventory.warnings)


def profile_summary() -> ProfileSummary:
    return ProfileSummary(id=PROFILE_ID, vendor=SYNTHETIC_PROFILE.vendor, model=SYNTHETIC_PROFILE.model,
        profile_status=SYNTHETIC_PROFILE.profile_status.value, interface_count=len(SYNTHETIC_PROFILE.interfaces))


def profile_detail(profile_id: str) -> ProfileDetail:
    if profile_id != PROFILE_ID:
        raise ServiceError("TARGET_PROFILE_NOT_FOUND", "Target profile was not found.", 404)
    return ProfileDetail(**profile_summary().model_dump(), interfaces=[item.name for item in SYNTHETIC_PROFILE.interfaces])


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
    return SYNTHETIC_PROFILE


def require_live(project: ProjectSession) -> None:
    if project.deleted:
        raise ServiceError("PROJECT_NOT_FOUND", "Project session was not found.", 404)


def select_profile(project: ProjectSession, profile_id: str | None) -> ProjectView:
    require_live(project)
    if profile_id:
        profile_detail(profile_id)
    project.profile_id = profile_id
    project.invalidate()
    return project_view(project)


async def update_preview(project: ProjectSession, mappings: list[InterfaceMapping]) -> MigrationPreview:
    inventory = require_inventory(project)
    profile = require_profile(project)
    project.invalidate()
    project.mappings = mappings
    project.preview = await asyncio.to_thread(preview_interface_mappings, inventory, mappings, profile)
    return project.preview


def candidate_metadata(project: ProjectSession) -> CandidateMetadata:
    result = project.candidate
    if result is None or project.preview is None:
        raise ServiceError("CANDIDATE_NOT_AVAILABLE", "Candidate result is not available.", 409)
    return CandidateMetadata(status=result.status, candidate_available=result.validation.valid,
        candidate_sha256=result.candidate_sha256, candidate_size_bytes=result.candidate_size_bytes,
        preview_status=project.preview.status, plan_status=result.plan.status, validation=result.validation,
        semantic_diff=result.semantic_diff, findings=result.plan.findings, plan=result.plan,
        summary=project.preview.summary.model_dump())


async def generate_candidate(project: ProjectSession, mappings: list[InterfaceMapping], allow_review: bool) -> CandidateMetadata:
    inventory = require_inventory(project)
    profile = require_profile(project)
    project.invalidate()
    project.mappings = mappings
    project.preview = await asyncio.to_thread(preview_interface_mappings, inventory, mappings, profile)
    project.candidate = await asyncio.to_thread(render_panos_candidate, project.source_path, inventory,
        project.preview, profile, project.candidate_path, allow_review=allow_review)
    return candidate_metadata(project)
