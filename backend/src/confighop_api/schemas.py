from typing import Literal

from pydantic import BaseModel, Field

from confighop_core.models.common import ParserWarning
from confighop_core.compatibility import CompatibilityAssessment, HardwareAssessment, PlatformAssessment
from confighop_core.models.hardware import HardwareInterfaceGroup
from confighop_core.models.mapping import InterfaceMapping, MigrationPreview, PreviewStatus
from confighop_core.models.transformation import (
    CandidateValidationReport, RenderFinding, SemanticMigrationDiff, TransformationPlan,
)


class InventorySummary(BaseModel):
    physical_interfaces: int
    subinterfaces: int
    aggregate_interfaces: int
    vlan_interfaces: int
    loopbacks: int
    zones: int
    virtual_routers: int
    static_routes: int
    address_objects: int
    service_objects: int
    security_rules: int
    nat_rules: int
    parser_warnings: int


class PlatformView(BaseModel):
    vendor: str
    config_version: str | None
    detail_version: str | None
    source_format: str


class DependencySummary(BaseModel):
    zone_references: int = 0
    virtual_router_references: int = 0
    static_route_references: int = 0
    nat_references: int = 0
    aggregate_memberships: int = 0
    child_count: int = 0


class PhysicalInterfaceView(BaseModel):
    name: str
    mode: str
    ip_addresses: list[str]
    management_profile: str | None
    aggregate_group: str | None
    subinterface_count: int
    subinterface_names: list[str]
    zone_names: list[str]
    dependency_count: int
    dependency_summary: DependencySummary


class InventoryView(BaseModel):
    platform: PlatformView
    summary: InventorySummary
    physical_interfaces: list[PhysicalInterfaceView]
    parser_warnings: list[ParserWarning]


class SourceView(BaseModel):
    project_id: str
    filename: str
    size_bytes: int
    platform: PlatformView
    inventory_summary: InventorySummary


ProjectStatus = Literal["EMPTY", "SOURCE_READY", "PREVIEW_READY", "PREVIEW_REVIEW_REQUIRED", "PREVIEW_BLOCKED", "CANDIDATE_READY"]


class ProjectView(BaseModel):
    project_id: str
    state: ProjectStatus
    source_available: bool
    source_filename: str | None
    source_size_bytes: int | None
    target_profile_id: str | None
    source_profile_id: str | None = None
    source_panos_train: str | None = None
    target_panos_train: str | None = None
    latest_platform_assessment: PlatformAssessment | None = None
    latest_hardware_assessment: HardwareAssessment | None = None
    preview_available: bool
    preview_status: PreviewStatus | None
    candidate_available: bool
    candidate_sha256: str | None
    candidate_size_bytes: int | None


class ProfileSummary(BaseModel):
    id: str
    vendor: str
    model: str
    domain: str = "firewall"
    software_family: str = "pan_os"
    target_render_support: str = "SUPPORTED"
    profile_status: str
    interface_count: int
    series: str | None = None
    verified_at: str | None = None
    native_interface_count: int = 0
    conditional_interface_count: int = 0
    breakout_interface_count: int = 0
    candidate_ready_interface_count: int = 0
    supported_panos_trains: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ProfileDetail(ProfileSummary):
    interfaces: list[str]
    port_details: list[dict] = Field(default_factory=list)
    interface_groups: list[HardwareInterfaceGroup] = Field(default_factory=list)
    first_supported_release: str | None = None
    notes: str | None = None
    software_support_rules: list[dict] = Field(default_factory=list)


class SelectProfileRequest(BaseModel):
    profile_id: str | None
    panos_train: str | None = None


class PreviewView(MigrationPreview):
    platform_assessment: PlatformAssessment | None = None
    hardware_assessment: HardwareAssessment | None = None
    overall_status: str | None = None


class PreviewRequest(BaseModel):
    mappings: list[InterfaceMapping] = Field(default_factory=list)


class CandidateRequest(PreviewRequest):
    allow_review: bool = False


class CandidateMetadata(BaseModel):
    status: PreviewStatus
    candidate_available: bool
    candidate_sha256: str | None
    candidate_size_bytes: int | None
    preview_status: PreviewStatus
    plan_status: PreviewStatus
    validation: CandidateValidationReport | None = None
    semantic_diff: SemanticMigrationDiff | None = None
    findings: list[RenderFinding] = Field(default_factory=list)
    plan: TransformationPlan | None = None
    summary: dict[str, int] = Field(default_factory=dict)
    source_profile_id: str | None = None
    target_profile_id: str | None = None
    source_profile_status: str | None = None
    target_profile_status: str | None = None
    target_render_support: str | None = None
    effective_panos_version: str | None = None
    platform_assessment_status: str | None = None
    hardware_assessment_status: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class HealthView(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["confighop-api"] = "confighop-api"
    api_version: Literal["v1"] = "v1"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorView(BaseModel):
    error: ErrorDetail
