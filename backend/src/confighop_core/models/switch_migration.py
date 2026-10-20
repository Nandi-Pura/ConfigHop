from typing import Literal

from pydantic import BaseModel, Field


TranslationStatus = Literal['TRANSLATED', 'PRESERVED', 'REVIEW_REQUIRED', 'UNSUPPORTED', 'BLOCKED']


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
    source_os: Literal['IOS_XE'] = 'IOS_XE'
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


class SwitchCandidate(BaseModel):
    text: str
    sha256: str
    status: Literal['READY', 'REVIEW_REQUIRED', 'BLOCKED']
    findings: list[SwitchFinding]
    dependencies: list[SwitchDependency]
    report: list[SwitchStatement]
    coverage: dict[str, int]
    resolved_interfaces: dict[str, str]
    syntax_compatible: bool
    hardware_context: str | None
    deployment_verified: bool = False
