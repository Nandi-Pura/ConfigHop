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


class HardwareInterface(BaseModel):
    name: str
    kind: HardwareKind
    supported_modes: list[str] = Field(default_factory=list)
    speed_capabilities: list[str] = Field(default_factory=list)
    media: str | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("interface name must be nonblank and unpadded")
        return value


class HardwareProfile(BaseModel):
    vendor: str
    model: str
    profile_status: ProfileStatus
    interfaces: list[HardwareInterface]
    notes: str | None = None

    @model_validator(mode="after")
    def unique_interfaces(self) -> "HardwareProfile":
        names = [interface.name for interface in self.interfaces]
        if len(names) != len(set(names)):
            raise ValueError("duplicate hardware interface names")
        return self
