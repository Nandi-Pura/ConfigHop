from typing import Literal

from pydantic import BaseModel, Field


TranslationStatus = Literal['TRANSLATED', 'PRESERVED', 'REVIEW_REQUIRED', 'MANUAL_REQUIRED', 'UNSUPPORTED', 'BLOCKED']


class SwitchStatement(BaseModel):
    line: int
    source: str
    scope: str = 'global'
    feature: str
    values: list[str] = Field(default_factory=list)
    explicit: bool = True
    status: TranslationStatus = 'TRANSLATED'
    render_supported: bool = True
    dependencies: list[str] = Field(default_factory=list)


class SwitchInterface(BaseModel):
    name: str
    kind: Literal['Physical', 'LAG', 'SVI', 'Loopback', 'Other']
    line: int


class SwitchMigrationIR(BaseModel):
    schema_version: Literal['1'] = '1'
    source_os: Literal['IOS_XE', 'AOS_CX'] = 'IOS_XE'
    source_version: str
    interfaces: list[SwitchInterface] = Field(default_factory=list)
    statements: list[SwitchStatement] = Field(default_factory=list)


class SwitchFinding(BaseModel):
    severity: Literal['INFO', 'REVIEW_REQUIRED', 'BLOCKED']
    code: str
    message: str
    line: int | None = None
    scope: str = 'global'


class SwitchDependency(BaseModel):
    source: str
    target: str
    relation: str
    line: int
    resolved: bool


class SwitchCoverage(BaseModel):
    source_vendor: str
    source_os: str
    source_version: str
    target_vendor: str
    target_os: str
    target_version: str
    meaningful_constructs: int
    translated_constructs: int
    preserved_for_review_constructs: int
    review_required_constructs: int
    manual_required_constructs: int = 0
    unsupported_constructs: int = 0
    blocked_constructs: int
    unsupported_feature_families: list[str]
    unresolved_dependencies: int
    interface_mapping_complete: bool
    version_limitations: list[str]
    hardware_compatibility_status: Literal['PROFILE_CHECKED', 'NOT_VERIFIED']
    output_validation_status: Literal['CHECKED_SUBSET', 'BLOCKED']


class SwitchCandidate(BaseModel):
    text: str
    sha256: str
    status: Literal['READY', 'REVIEW_REQUIRED', 'BLOCKED']
    findings: list[SwitchFinding]
    dependencies: list[SwitchDependency]
    report: list[SwitchStatement]
    coverage: dict[str, int]
    translation_summary: SwitchCoverage
    resolved_interfaces: dict[str, str]
    syntax_compatible: bool
    hardware_context: str | None
    deployment_verified: bool = False
