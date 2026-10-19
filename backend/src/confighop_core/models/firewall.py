from typing import Literal

from pydantic import BaseModel, Field


Vendor = Literal['fortios', 'panos']
Severity = Literal['INFO', 'REVIEW_REQUIRED', 'BLOCKED']


class Finding(BaseModel):
    severity: Severity
    code: str
    message: str
    entity: str = ''
    line: int | None = None


class Resource(BaseModel):
    name: str
    scope: str = 'root'
    line: int | None = None
    source_name: str | None = None
    identity: str = ''
    source_location: str = ''
    dependencies: list[str] = Field(default_factory=list)
    translation_status: Literal['PARSED', 'REVIEW_REQUIRED', 'UNSUPPORTED', 'BLOCKED'] = 'PARSED'
    findings: list[Finding] = Field(default_factory=list)


class Interface(Resource):
    kind: str = 'physical'
    address: str | None = None
    parent: str | None = None
    vlan: int | None = None
    members: list[str] = Field(default_factory=list)


class Zone(Resource):
    interfaces: list[str] = Field(default_factory=list)


class Address(Resource):
    kind: str
    value: str


class Group(Resource):
    members: list[str] = Field(default_factory=list)


class Service(Resource):
    protocol: str
    port: str
    source_port: str | None = None


class Schedule(Resource):
    kind: str
    start: str = ''
    end: str = ''
    days: list[str] = Field(default_factory=list)


class Policy(Resource):
    source_zones: list[str] = Field(default_factory=list)
    destination_zones: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    destinations: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
    action: str = 'deny'
    disabled: bool = False
    schedule: str = 'always'
    log: bool = False
    description: str = ''
    nat: bool = False
    nat_pool: str | None = None


class Nat(Resource):
    kind: str
    source_zones: list[str] = Field(default_factory=list)
    destination_zones: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    destinations: list[str] = Field(default_factory=list)
    translated_address: str = ''
    original_port: str | None = None
    translated_port: str | None = None
    interface: str | None = None
    related_policy: str | None = None


class Route(Resource):
    destination: str
    gateway: str | None = None
    interface: str | None = None
    router: str = 'default'


class FirewallIR(BaseModel):
    source_vendor: Vendor
    source_version: str = ''
    source_scope: str = 'root'
    routing_context: str = 'default'
    hardware_context: str | None = None
    interfaces: list[Interface] = Field(default_factory=list)
    zones: list[Zone] = Field(default_factory=list)
    addresses: list[Address] = Field(default_factory=list)
    address_groups: list[Group] = Field(default_factory=list)
    services: list[Service] = Field(default_factory=list)
    service_groups: list[Group] = Field(default_factory=list)
    schedules: list[Schedule] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
    nat: list[Nat] = Field(default_factory=list)
    routes: list[Route] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class Coverage(BaseModel):
    category: str
    parsed: int
    translated: int
    rendered: int
    validated: int
    review_required: int
    unsupported: int
    blocked: int


class FirewallCandidate(BaseModel):
    source_os: Vendor
    source_version: str
    target_os: Vendor
    target_version: str
    status: Literal['INCOMPLETE', 'BLOCKED', 'REVIEW_REQUIRED', 'READY_FOR_REVIEW']
    revision: int
    sha256: str
    syntax: Literal['xml', 'cli']
    text: str
    findings: list[Finding]
    coverage: list[Coverage]
