from enum import StrEnum

from pydantic import BaseModel, Field

from .mapping import PreviewStatus, Severity


class OperationType(StrEnum):
    RENAME_PHYSICAL_INTERFACE = "RENAME_PHYSICAL_INTERFACE"
    SET_INTERFACE_LINK_SPEED = "SET_INTERFACE_LINK_SPEED"
    RENAME_SUBINTERFACE = "RENAME_SUBINTERFACE"
    UPDATE_ZONE_INTERFACE_REFERENCE = "UPDATE_ZONE_INTERFACE_REFERENCE"
    UPDATE_VIRTUAL_ROUTER_INTERFACE_REFERENCE = "UPDATE_VIRTUAL_ROUTER_INTERFACE_REFERENCE"
    UPDATE_STATIC_ROUTE_EGRESS_REFERENCE = "UPDATE_STATIC_ROUTE_EGRESS_REFERENCE"
    UPDATE_NAT_INTERFACE_REFERENCE = "UPDATE_NAT_INTERFACE_REFERENCE"
    ASSERT_AGGREGATE_MEMBERSHIP = "ASSERT_AGGREGATE_MEMBERSHIP"
    ASSERT_SUBINTERFACE_PARENT = "ASSERT_SUBINTERFACE_PARENT"


class RenderFinding(BaseModel):
    code: str
    severity: Severity
    message: str


class TransformationOperation(BaseModel):
    sequence: int
    operation_type: OperationType
    source_value: str
    target_value: str
    object_type: str
    object_name: str
    scope: str
    field: str
    expected_occurrences: int = 1


class TransformationPlan(BaseModel):
    source_sha256: str
    source_inventory_sha256: str
    target_profile_vendor: str
    target_profile_model: str
    target_profile_status: str
    preview_status: PreviewStatus
    operations: list[TransformationOperation] = Field(default_factory=list)
    findings: list[RenderFinding] = Field(default_factory=list)
    status: PreviewStatus


class CandidateValidationReport(BaseModel):
    source_sha256: str
    candidate_sha256: str | None = None
    candidate_parse_ok: bool = False
    expected_inventory_match: bool = False
    preservation_audit_ok: bool = False
    operations_planned: int = 0
    operations_applied: int = 0
    postconditions_passed: bool = False
    findings: list[RenderFinding] = Field(default_factory=list)
    valid: bool = False


class SemanticChange(BaseModel):
    category: str
    object_type: str
    object_name: str
    scope: str
    old_value: str
    new_value: str
    status: str = "APPLIED"


class SemanticMigrationDiff(BaseModel):
    changes: list[SemanticChange] = Field(default_factory=list)


class CandidateRenderResult(BaseModel):
    plan: TransformationPlan
    validation: CandidateValidationReport
    semantic_diff: SemanticMigrationDiff
    candidate_sha256: str | None = None
    candidate_size_bytes: int | None = None
    output_path: str | None = None
    status: PreviewStatus
