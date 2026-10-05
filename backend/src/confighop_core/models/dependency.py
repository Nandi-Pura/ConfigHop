from enum import StrEnum

from pydantic import BaseModel


class ReferenceType(StrEnum):
    SUBINTERFACE_PARENT = "SUBINTERFACE_PARENT"
    ZONE_INTERFACE = "ZONE_INTERFACE"
    VIRTUAL_ROUTER_INTERFACE = "VIRTUAL_ROUTER_INTERFACE"
    STATIC_ROUTE_EGRESS_INTERFACE = "STATIC_ROUTE_EGRESS_INTERFACE"
    NAT_INTERFACE_REFERENCE = "NAT_INTERFACE_REFERENCE"
    AGGREGATE_MEMBERSHIP = "AGGREGATE_MEMBERSHIP"


class DependencyReference(BaseModel):
    reference_type: ReferenceType
    object_type: str
    object_name: str
    scope: str
    field: str
    referenced_interface: str
