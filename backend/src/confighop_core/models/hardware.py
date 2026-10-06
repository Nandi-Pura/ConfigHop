from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class ProfileStatus(StrEnum):
    SYNTHETIC = "synthetic"
    USER_SUPPLIED = "user_supplied"
    VERIFIED = "verified"


class HardwareKind(StrEnum):
    PHYSICAL_ETHERNET = "physical_ethernet"
    AGGREGATE_ETHERNET = "aggregate_ethernet"
    LOOPBACK = "loopback"
    VLAN = "vlan"


class PortAvailability(StrEnum):
    NATIVE = "NATIVE"
    NATIVE_CONDITIONAL = "NATIVE_CONDITIONAL"
    BREAKOUT_CHILD = "BREAKOUT_CHILD"


class MappingSupport(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONDITIONAL = "CONDITIONAL"
    UNSUPPORTED = "UNSUPPORTED"


class CandidateSupport(StrEnum):
    SUPPORTED = "SUPPORTED"
    BLOCKED = "BLOCKED"


class RequiredCondition(StrEnum):
    NONE = "NONE"
    BREAKOUT_MODE = "BREAKOUT_MODE"
    MANUAL_NATIVE_PORT_SPEED = "MANUAL_NATIVE_PORT_SPEED"


class HardwareInterfaceGroup(BaseModel):
    id: str
    label: str
    interface_names: list[str]
    media_capabilities: list[str]
    speed_capabilities: list[str]
    availability: PortAvailability = PortAvailability.NATIVE
    mapping_support: MappingSupport = MappingSupport.SUPPORTED
    candidate_support: CandidateSupport = CandidateSupport.SUPPORTED
    required_condition: RequiredCondition = RequiredCondition.NONE
    evidence_ids: list[str] = Field(default_factory=list)
    notes: str | None = None


class HardwareInterface(BaseModel):
    name: str
    kind: HardwareKind
    supported_modes: list[str] = Field(default_factory=list)
    speed_capabilities: list[str] = Field(default_factory=list)
    media: str | None = None
    media_capabilities: list[str] = Field(default_factory=list)
    availability: PortAvailability = PortAvailability.NATIVE
    mapping_support: MappingSupport = MappingSupport.SUPPORTED
    candidate_support: CandidateSupport = CandidateSupport.SUPPORTED
    required_condition: RequiredCondition = RequiredCondition.NONE
    parent_interface: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    ztp_capable: bool = False
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("interface name must be nonblank and unpadded")
        return value


class HardwareProfile(BaseModel):
    id: str | None = None
    vendor: str
    model: str
    series: str | None = None
    profile_status: ProfileStatus
    interfaces: list[HardwareInterface]
    interface_groups: list[HardwareInterfaceGroup] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    supported_panos_trains: list[str] = Field(default_factory=list)
    verified_unsupported_panos_trains: list[str] = Field(default_factory=list)
    first_supported_release: str | None = None
    verified_at: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def unique_interfaces(self) -> "HardwareProfile":
        names = [interface.name for interface in self.interfaces]
        if len(names) != len(set(names)):
            raise ValueError("duplicate hardware interface names")
        return self
