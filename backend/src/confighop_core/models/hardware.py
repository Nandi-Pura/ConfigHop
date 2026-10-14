from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class ProfileStatus(StrEnum):
    SYNTHETIC = "synthetic"
    USER_SUPPLIED = "user_supplied"
    VERIFIED = "verified"


class PlatformDomain(StrEnum):
    FIREWALL = "firewall"
    SWITCH = "switch"


class SoftwareFamily(StrEnum):
    PAN_OS = "pan_os"
    IOS_XE = "ios_xe"
    AOS_CX = "aos_cx"


class TargetRenderSupport(StrEnum):
    SUPPORTED = "SUPPORTED"
    SCOPED = "SCOPED"
    ANALYSIS_ONLY = "ANALYSIS_ONLY"


class SoftwareSupportStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"


class SoftwareSupportRule(BaseModel):
    train: str
    status: SoftwareSupportStatus
    minimum_version: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


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
    CONDITIONAL = "CONDITIONAL"
    BLOCKED = "BLOCKED"


class RequiredCondition(StrEnum):
    NONE = "NONE"
    BREAKOUT_MODE = "BREAKOUT_MODE"
    MANUAL_NATIVE_PORT_SPEED = "MANUAL_NATIVE_PORT_SPEED"
    AUTO_ONLY_LINK_FIELDS_ABSENT = "AUTO_ONLY_LINK_FIELDS_ABSENT"
    OPTIC_CONTEXT_LINK_FIELDS_ABSENT = "OPTIC_CONTEXT_LINK_FIELDS_ABSENT"
    TARGET_LINK_SERIALIZATION_UNVERIFIED = "TARGET_LINK_SERIALIZATION_UNVERIFIED"


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
    domain: PlatformDomain = PlatformDomain.FIREWALL
    software_family: SoftwareFamily = SoftwareFamily.PAN_OS
    target_render_support: TargetRenderSupport = TargetRenderSupport.SUPPORTED
    profile_status: ProfileStatus
    interfaces: list[HardwareInterface]
    interface_groups: list[HardwareInterfaceGroup] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    supported_panos_trains: list[str] = Field(default_factory=list)
    verified_unsupported_panos_trains: list[str] = Field(default_factory=list)
    software_support_rules: list[SoftwareSupportRule] = Field(default_factory=list)
    first_supported_release: str | None = None
    verified_at: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def unique_interfaces(self) -> "HardwareProfile":
        names = [interface.name for interface in self.interfaces]
        if len(names) != len(set(names)):
            raise ValueError("duplicate hardware interface names")
        if len({rule.train for rule in self.software_support_rules}) != len(self.software_support_rules):
            raise ValueError("duplicate software support train")
        if self.software_family == SoftwareFamily.PAN_OS and self.software_support_rules:
            self.supported_panos_trains = [rule.train for rule in self.software_support_rules if rule.status == SoftwareSupportStatus.SUPPORTED]
            self.verified_unsupported_panos_trains = [rule.train for rule in self.software_support_rules if rule.status == SoftwareSupportStatus.UNSUPPORTED]
        known = set(names)
        for group in self.interface_groups:
            if not set(group.interface_names) <= known:
                raise ValueError("interface group references unknown interface")
        grouped = [name for group in self.interface_groups for name in group.interface_names]
        if len(grouped) != len(set(grouped)):
            raise ValueError("interface assigned to multiple groups")
        for interface in self.interfaces:
            if interface.parent_interface and interface.parent_interface not in known:
                raise ValueError("breakout child references unknown parent")
        return self
