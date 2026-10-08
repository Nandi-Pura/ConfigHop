from enum import StrEnum
from ipaddress import ip_network

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import ParserWarning
from .hardware import SoftwareFamily


def vlan_id(value: int) -> int:
    if not 1 <= value <= 4094:
        raise ValueError("VLAN ID must be between 1 and 4094")
    return value


class SwitchportMode(StrEnum):
    ACCESS = "ACCESS"
    TRUNK = "TRUNK"
    ROUTED = "ROUTED"
    UNKNOWN = "UNKNOWN"


class LagProtocol(StrEnum):
    LACP = "LACP"
    STATIC = "STATIC"
    UNKNOWN = "UNKNOWN"


class LagMode(StrEnum):
    ACTIVE = "ACTIVE"
    PASSIVE = "PASSIVE"
    ON = "ON"
    UNKNOWN = "UNKNOWN"


class StpMode(StrEnum):
    PVST = "PVST"
    RAPID_PVST = "RAPID_PVST"
    MSTP = "MSTP"
    RSTP = "RSTP"
    UNKNOWN = "UNKNOWN"


class SwitchPlatform(BaseModel):
    vendor: str
    software_family: SoftwareFamily
    software_version: str
    hardware_profile_id: str


class VendorExtension(BaseModel):
    vendor: str
    scope: str
    object_name: str | None = None
    feature: str
    raw_value: str
    reason: str


class Vlan(BaseModel):
    id: int
    name: str | None = None

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: int) -> int:
        return vlan_id(value)


class VlanReferences(BaseModel):
    access_vlan: int | None = None
    native_vlan: int | None = None
    allowed_vlans: list[int] = Field(default_factory=list)

    @field_validator("access_vlan", "native_vlan")
    @classmethod
    def valid_reference(cls, value: int | None) -> int | None:
        return vlan_id(value) if value is not None else None

    @field_validator("allowed_vlans")
    @classmethod
    def normalized_allowed(cls, values: list[int]) -> list[int]:
        return sorted({vlan_id(value) for value in values})


class SwitchPhysicalInterface(VlanReferences):
    name: str
    description: str | None = None
    admin_enabled: bool | None = None
    switchport_mode: SwitchportMode = SwitchportMode.UNKNOWN
    voice_vlan: int | None = None
    lag_id: int | None = None
    ip_addresses: list[str] = Field(default_factory=list)
    speed: str | None = None
    stp_edge: bool = False
    vendor_extensions: list[VendorExtension] = Field(default_factory=list)

    @field_validator("voice_vlan")
    @classmethod
    def valid_voice(cls, value: int | None) -> int | None:
        return vlan_id(value) if value is not None else None


class SwitchLag(VlanReferences):
    id: int
    name: str
    description: str | None = None
    admin_enabled: bool | None = None
    protocol: LagProtocol = LagProtocol.UNKNOWN
    mode: LagMode = LagMode.UNKNOWN
    members: list[str] = Field(default_factory=list)
    switchport_mode: SwitchportMode = SwitchportMode.UNKNOWN
    ip_addresses: list[str] = Field(default_factory=list)
    vendor_extensions: list[VendorExtension] = Field(default_factory=list)


class SwitchSvi(BaseModel):
    vlan_id: int
    name: str
    description: str | None = None
    admin_enabled: bool | None = None
    ip_addresses: list[str] = Field(default_factory=list)
    vrf: str | None = None
    vendor_extensions: list[VendorExtension] = Field(default_factory=list)

    @field_validator("vlan_id")
    @classmethod
    def valid_svi(cls, value: int) -> int:
        return vlan_id(value)


class RoutedInterface(BaseModel):
    name: str
    description: str | None = None
    admin_enabled: bool | None = None
    ip_addresses: list[str] = Field(default_factory=list)
    vrf: str | None = None
    vendor_extensions: list[VendorExtension] = Field(default_factory=list)


class SwitchStaticRoute(BaseModel):
    destination: str
    next_hop: str | None = None
    egress_interface: str | None = None
    metric: int | None = None
    vrf: str | None = None

    @field_validator("destination")
    @classmethod
    def valid_destination(cls, value: str) -> str:
        return str(ip_network(value, strict=False))


class SwitchStp(BaseModel):
    global_mode: StpMode = StpMode.UNKNOWN
    edge_interfaces: list[str] = Field(default_factory=list)


class SwitchConfig(BaseModel):
    platform: SwitchPlatform
    hostname: str | None = None
    vlans: list[Vlan] = Field(default_factory=list)
    physical_interfaces: list[SwitchPhysicalInterface] = Field(default_factory=list)
    lags: list[SwitchLag] = Field(default_factory=list)
    svis: list[SwitchSvi] = Field(default_factory=list)
    routed_interfaces: list[RoutedInterface] = Field(default_factory=list)
    static_routes: list[SwitchStaticRoute] = Field(default_factory=list)
    stp: SwitchStp = Field(default_factory=SwitchStp)
    parser_warnings: list[ParserWarning] = Field(default_factory=list)
    vendor_extensions: list[VendorExtension] = Field(default_factory=list)

    @model_validator(mode="after")
    def deterministic(self) -> "SwitchConfig":
        self.vlans.sort(key=lambda item: item.id)
        self.physical_interfaces.sort(key=lambda item: item.name)
        self.lags.sort(key=lambda item: item.id)
        self.svis.sort(key=lambda item: item.vlan_id)
        self.routed_interfaces.sort(key=lambda item: item.name)
        self.static_routes.sort(key=lambda item: (item.destination, item.vrf or "", item.next_hop or "", item.egress_interface or ""))
        for lag in self.lags:
            lag.members = sorted(set(lag.members))
        self.stp.edge_interfaces = sorted(set(self.stp.edge_interfaces))
        self.parser_warnings.sort(key=lambda item: (item.code, item.object_type, item.object_name or "", item.field, item.message))
        self.vendor_extensions.sort(key=lambda item: (item.vendor, item.scope, item.object_name or "", item.feature, item.raw_value))
        return self
