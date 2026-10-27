import asyncio
import hashlib
from collections import deque
import ntpath
import os
import re
import shutil
import tempfile
from time import monotonic
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

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
from confighop_core.renderers.palo_alto.renderer import CandidateLimitExceeded

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
    touched: float = 0.0
    clock: Callable[[], float] = monotonic
    expired: bool = False
    cleanup_debt: bool = False
    cleanup_debt_bytes: int = 0

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
        try:
            self.candidate_path.unlink(missing_ok=True)
        except OSError:
            self.cleanup_debt = True  # The file remains counted; candidate metadata is already invalidated.

    def touch(self) -> None:
        self.touched = self.clock()


class ProjectStore:
    def __init__(self, *, clock: Callable[[], float] = monotonic,
                 max_projects: int = 2, aggregate_bytes: int = 640 * 1024 * 1024,
                 project_bytes: int = 320 * 1024 * 1024,
                 max_candidate_bytes: int = 100 * 1024 * 1024,
                 idle_seconds: int = 24 * 60 * 60,
                 free_floor_bytes: int = 1024 * 1024 * 1024):
        self.root = tempfile.TemporaryDirectory(prefix="confighop-")
        self.projects: dict[str, ProjectSession] = {}
        self.expired_ids: deque[str] = deque(maxlen=1024)
        self.lock = asyncio.Lock()  # Acquire before a project lock for file-adding operations.
        self.clock = clock
        self.max_projects = max_projects
        self.aggregate_bytes = aggregate_bytes
        self.project_bytes = project_bytes
        self.max_candidate_bytes = max_candidate_bytes
        self.idle_seconds = idle_seconds
        self.free_floor_bytes = free_floor_bytes
        self.reservations: dict[str, int] = {}
        self.max_source_bytes = MAX_XML_BYTES
        self._process_file = None

    def acquire_process_lock(self) -> None:
        if self._process_file is not None:
            return
        key = hashlib.sha256(str(Path(__file__).resolve().parents[3]).encode()).hexdigest()[:16]
        lock_path = Path(tempfile.gettempdir()) / f"confighop-worker-{key}.lock"
        lock_file = lock_path.open("a+b")
        try:
            lock_file.seek(0)
            lock_file.write(b"\0")
            lock_file.flush()
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            lock_file.close()
            raise RuntimeError("Only one ConfigHop backend worker may run for this checkout.") from exc
        self._process_file = lock_file

    @staticmethod
    def _bytes(path: Path) -> int:
        return sum(file.stat().st_size for file in path.rglob("*") if file.is_file()) if path.exists() else 0

    def reserve(self, project: ProjectSession, additional: int, base_total: int, base_project: int,
                disk_needed: int) -> None:
        try:
            if base_project + additional > self.project_bytes:
                raise ServiceError("PROJECT_CAPACITY_EXCEEDED", "This project has reached its temporary storage limit.", 507)
            if base_total + additional > self.aggregate_bytes:
                raise ServiceError("STORE_CAPACITY_EXCEEDED", "Temporary storage is full. Delete an unused project.", 507)
            if shutil.disk_usage(self.root.name).free - disk_needed < self.free_floor_bytes:
                raise ServiceError("TEMP_STORAGE_UNAVAILABLE", "Not enough free temporary disk space.", 507)
        except OSError as exc:
            raise ServiceError("QUOTA_RESERVATION_UNAVAILABLE", "Temporary storage could not be checked.", 503) from exc
        self.reservations[project.project_id] = additional

    def usage(self) -> tuple[int, dict[str, int]]:
        try:
            total = self._bytes(Path(self.root.name))
            by_project = {key: self._bytes(p.workspace) for key, p in self.projects.items()}
            for key, project in self.projects.items():
                debt = max(0, project.cleanup_debt_bytes - by_project[key])
                total += debt
                by_project[key] += debt
            return total, by_project
        except OSError as exc:
            raise ServiceError("QUOTA_RESERVATION_UNAVAILABLE", "Temporary storage could not be checked.", 503) from exc

    async def reap_expired(self) -> None:
        async with self.lock:
            for project in list(self.projects.values()):
                if project.lock.locked() or (not project.deleted and self.clock() - project.touched < self.idle_seconds):
                    continue
                async with project.lock:
                    if not project.deleted and self.clock() - project.touched < self.idle_seconds:
                        continue
                    if not project.deleted:
                        project.expired = True
                        project.deleted = True
                        self.expired_ids.append(project.project_id)
                    try:
                        self._remove_owned(project)
                    except OSError:
                        project.cleanup_debt = True
                        continue  # Files remain under the store root and still count toward its budget.

    def _remove_owned(self, project: ProjectSession) -> None:
        project.cleanup_debt_bytes = max(project.cleanup_debt_bytes, self._bytes(project.workspace))
        try:
            shutil.rmtree(project.workspace)
        except FileNotFoundError:
            if project.workspace.exists():
                raise
        self.projects.pop(project.project_id, None)

    async def create(self) -> ProjectSession:
        await self.reap_expired()
        async with self.lock:
            if sum(not p.deleted for p in self.projects.values()) >= self.max_projects:
                raise ServiceError("PROJECT_LIMIT_REACHED", "Close a project before creating another.", 429)
            project_id = str(uuid4())
            workspace = Path(self.root.name) / project_id
            try:
                workspace.mkdir(mode=0o700)
            except OSError as exc:
                raise ServiceError("TEMP_STORAGE_UNAVAILABLE", "Temporary storage could not create this project.", 507) from exc
            project = ProjectSession(project_id, workspace, touched=self.clock(), clock=self.clock)
            self.projects[project_id] = project
            return project

    def get(self, project_id: str) -> ProjectSession:
        project = self.projects.get(project_id)
        if project is None:
            if project_id in self.expired_ids:
                raise ServiceError("PROJECT_EXPIRED", "Project session expired. Upload the source again.", 404)
            raise ServiceError("PROJECT_NOT_FOUND", "Project session was not found.", 404)
        if project.expired:
            raise ServiceError("PROJECT_EXPIRED", "Project session expired. Upload the source again.", 404)
        if project.deleted:
            raise ServiceError("PROJECT_NOT_FOUND", "Project session was not found.", 404)
        if not project.lock.locked() and self.clock() - project.touched >= self.idle_seconds:
            project.expired = True
            raise ServiceError("PROJECT_EXPIRED", "Project session expired. Upload the source again.", 404)
        project.touch()
        return project

    async def delete(self, project_id: str) -> None:
        async with self.lock:
            project = self.projects.get(project_id)
            if project is None or (project.deleted and not project.cleanup_debt):
                raise ServiceError("PROJECT_NOT_FOUND", "Project session was not found.", 404)
            async with project.lock:
                project.deleted = True
                try:
                    self._remove_owned(project)
                except OSError as exc:
                    project.cleanup_debt = True
                    raise ServiceError("TEMP_STORAGE_UNAVAILABLE", "Project files could not be removed; storage remains reserved.", 507) from exc

    def close(self) -> None:
        try:
            self.root.cleanup()
        finally:
            if self._process_file is not None:
                if os.name == "nt":
                    import msvcrt
                    self._process_file.seek(0)
                    msvcrt.locking(self._process_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._process_file.fileno(), fcntl.LOCK_UN)
                self._process_file.close()
                self._process_file = None


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
    async with store.lock, project.lock:
        require_live(project)
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > store.max_source_bytes:
                    raise ServiceError("SOURCE_TOO_LARGE", "Source exceeds the upload limit.", 413)
            except ValueError as exc:
                raise ServiceError("INVALID_REQUEST", "Invalid content length.", 400) from exc
        temporary = project.workspace / f"upload-{uuid4().hex}.tmp"
        size = 0
        base_total, by_project = store.usage()
        try:
            with temporary.open("xb") as stream:
                os.chmod(temporary, 0o600)
                async for chunk in request.stream():
                    next_size = size + len(chunk)
                    if next_size > store.max_source_bytes:
                        raise ServiceError("SOURCE_TOO_LARGE", "Source exceeds the upload limit.", 413)
                    store.reserve(project, next_size, base_total, by_project[project.project_id], len(chunk))
                    stream.write(chunk)
                    size = next_size
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
        except OSError as exc:
            raise ServiceError("TEMP_STORAGE_UNAVAILABLE", "Temporary storage could not accept this source; the previous source is retained.", 507) from exc
        finally:
            store.reservations.pop(project.project_id, None)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                project.cleanup_debt = True
            project.touch()


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
    project.touch()
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
    project.touch()
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


async def generate_candidate(project: ProjectSession, mappings: list[InterfaceMapping], allow_review: bool,
                             store: ProjectStore | None = None) -> CandidateMetadata:
    inventory = require_inventory(project)
    profile = require_profile(project)
    project.invalidate()
    project.mappings = mappings
    if profile.profile_status == ProfileStatus.VERIFIED:
        project.compatibility = assess(inventory, project.source_profile_id, project.source_panos_train,
            project.profile_id, project.target_panos_train, mappings)
    project.preview = await asyncio.to_thread(preview_interface_mappings, inventory, mappings, profile)
    if project.compatibility and (project.compatibility.status.value == "BLOCKED" or
            project.compatibility.status.value == "REVIEW_REQUIRED" and not allow_review):
        return candidate_metadata(project) if project.compatibility.status.value == "BLOCKED" else blocked_review_metadata(project)
    if project.preview.status == PreviewStatus.BLOCKED or project.preview.status == PreviewStatus.REVIEW_REQUIRED and not allow_review:
        return blocked_review_metadata(project)
    base_total, by_project = store.usage() if store else (0, {})
    def reserve_output(size: int) -> None:
        if store:
            store.reserve(project, size, base_total, by_project[project.project_id], size)
    try:
        render = asyncio.create_task(asyncio.to_thread(render_panos_candidate, project.source_path, inventory,
            project.preview, profile, project.candidate_path, allow_review=allow_review,
            source_profile_id=project.source_profile_id, source_panos_train=project.source_panos_train,
            target_panos_train=project.target_panos_train,
            validation_dir=project.workspace if store else None,
            max_output_bytes=store.max_candidate_bytes if store else None,
            reserve_output=reserve_output if store else None))
        try:
            project.candidate = await asyncio.shield(render)
        except asyncio.CancelledError:
            try:
                await render  # Keep the reservation and project lock until the worker stops writing.
            finally:
                project.candidate_path.unlink(missing_ok=True)
            raise
    except CandidateLimitExceeded as exc:
        raise ServiceError("CANDIDATE_CAPACITY_EXCEEDED", "Candidate exceeds the 100 MiB output limit.", 507) from exc
    except OSError as exc:
        project.cleanup_debt = True
        raise ServiceError("TEMP_STORAGE_UNAVAILABLE", "Temporary storage could not accept the candidate.", 507) from exc
    finally:
        if store:
            store.reservations.pop(project.project_id, None)
            project.touch()
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
