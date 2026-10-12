from typing import Literal

from pydantic import BaseModel, Field


InterfaceMode = Literal["layer3", "layer2", "virtual_wire", "aggregate_member", "unknown"]


class PhysicalInterface(BaseModel):
    name: str
    mode: InterfaceMode
    comment: str | None = None
    link_state: str | None = None
    link_state_explicit: bool = False
    link_speed: str | None = None
    link_speed_explicit: bool = False
    link_duplex: str | None = None
    link_duplex_explicit: bool = False
    aggregate_group: str | None = None
    ip_addresses: list[str] = Field(default_factory=list)
    management_profile: str | None = None
    subinterface_names: list[str] = Field(default_factory=list)


class Subinterface(BaseModel):
    name: str
    parent_interface: str
    mode: Literal["layer3", "layer2"]
    tag: int | None = None
    ip_addresses: list[str] = Field(default_factory=list)
    management_profile: str | None = None
    comment: str | None = None
    adjust_tcp_mss_enabled: bool | None = None


class AggregateInterface(BaseModel):
    name: str
    mode: InterfaceMode
    comment: str | None = None
    ip_addresses: list[str] = Field(default_factory=list)
    management_profile: str | None = None
    member_interfaces: list[str] = Field(default_factory=list)


class VlanInterface(BaseModel):
    name: str
    ip_addresses: list[str] = Field(default_factory=list)
    management_profile: str | None = None
    comment: str | None = None


class LoopbackInterface(VlanInterface):
    pass


class Zone(BaseModel):
    name: str
    vsys: str
    zone_type: Literal["layer3", "layer2", "virtual_wire", "unknown"]
    interface_members: list[str] = Field(default_factory=list)
