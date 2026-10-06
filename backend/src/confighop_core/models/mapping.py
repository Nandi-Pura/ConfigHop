from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .dependency import ReferenceType


class MappingStatus(StrEnum):
    MAPPED = "MAPPED"
    REVIEW = "REVIEW"
    CONFLICT = "CONFLICT"
    UNSUPPORTED = "UNSUPPORTED"
    UNMAPPED = "UNMAPPED"


class PreviewStatus(StrEnum):
    READY = "READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class CoverageStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"


class ChangeAction(StrEnum):
    UPDATE_REFERENCE = "UPDATE_REFERENCE"
    PRESERVE = "PRESERVE"
    REVIEW = "REVIEW"


class TargetLinkSpeed(StrEnum):
    FORTY_G = "40G"
    HUNDRED_G = "100G"
    AUTO = "auto"
    TEN_G = "10G"
    TWENTY_FIVE_G = "25G"


class TargetInterfaceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    link_speed: TargetLinkSpeed | str | None = None


class InterfaceMapping(BaseModel):
    source_interface: str
    target_interface: str
    notes: str | None = None
    target_settings: TargetInterfaceSettings | None = None


class DerivedSubinterfaceMapping(BaseModel):
    source_interface: str
    target_interface: str
    source_parent: str
    target_parent: str
    unit_suffix: str
    tag: int | None = None
    status: MappingStatus = MappingStatus.MAPPED


class MigrationFinding(BaseModel):
    code: str
    severity: Severity
    scope: str = "mapping"
    source_interface: str | None = None
    target_interface: str | None = None
    object_type: str | None = None
    object_name: str | None = None
    message: str


class DependencyCoverage(BaseModel):
    status: CoverageStatus
    covered_reference_types: list[ReferenceType]
    known_gaps: list[str] = Field(default_factory=list)


class ReferenceChange(BaseModel):
    reference_type: ReferenceType
    object_type: str
    object_name: str
    scope: str
    field: str
    old_value: str
    new_value: str
    action: ChangeAction
    status: MappingStatus


class InterfaceMigrationImpact(BaseModel):
    source_interface: str
    target_interface: str
    mapping_status: MappingStatus
    derived_subinterfaces: list[DerivedSubinterfaceMapping] = Field(default_factory=list)
    reference_changes: list[ReferenceChange] = Field(default_factory=list)
    findings: list[MigrationFinding] = Field(default_factory=list)
    coverage: DependencyCoverage


class MigrationSummary(BaseModel):
    submitted_mappings: int
    valid_mappings: int
    derived_subinterface_mappings: int
    zone_reference_changes: int
    virtual_router_reference_changes: int
    static_route_reference_changes: int
    nat_reference_changes: int
    aggregate_membership_changes: int
    review_findings: int
    blocking_findings: int


class MigrationPreview(BaseModel):
    mappings: list[InterfaceMapping]
    impacts: list[InterfaceMigrationImpact]
    findings: list[MigrationFinding]
    summary: MigrationSummary
    status: PreviewStatus
    coverage: DependencyCoverage
