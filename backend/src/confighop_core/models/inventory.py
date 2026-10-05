from pydantic import BaseModel, Field

from .common import ParserWarning
from .interface import AggregateInterface, LoopbackInterface, PhysicalInterface, Subinterface, VlanInterface, Zone
from .objects import AddressObject, ServiceObject
from .platform import DeviceEntry, PlatformMetadata
from .policy import NatRule, SecurityRule
from .routing import StaticRoute, VirtualRouter


class PaloAltoInventory(BaseModel):
    platform: PlatformMetadata
    device_entries: list[DeviceEntry] = Field(default_factory=list)
    vsys_names: list[str] = Field(default_factory=list)
    physical_interfaces: list[PhysicalInterface] = Field(default_factory=list)
    subinterfaces: list[Subinterface] = Field(default_factory=list)
    aggregate_interfaces: list[AggregateInterface] = Field(default_factory=list)
    vlan_interfaces: list[VlanInterface] = Field(default_factory=list)
    loopback_interfaces: list[LoopbackInterface] = Field(default_factory=list)
    zones: list[Zone] = Field(default_factory=list)
    virtual_routers: list[VirtualRouter] = Field(default_factory=list)
    static_routes: list[StaticRoute] = Field(default_factory=list)
    address_objects: list[AddressObject] = Field(default_factory=list)
    service_objects: list[ServiceObject] = Field(default_factory=list)
    security_rules: list[SecurityRule] = Field(default_factory=list)
    nat_rules: list[NatRule] = Field(default_factory=list)
    warnings: list[ParserWarning] = Field(default_factory=list)
