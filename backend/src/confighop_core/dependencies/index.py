from collections import defaultdict

from ..models.dependency import DependencyReference, ReferenceType
from ..models.inventory import PaloAltoInventory


def build_dependency_index(inventory: PaloAltoInventory) -> dict[str, list[DependencyReference]]:
    index: dict[str, list[DependencyReference]] = defaultdict(list)

    def add(identity: str, kind: ReferenceType, object_type: str, name: str, scope: str, field: str) -> None:
        index[identity].append(DependencyReference(
            reference_type=kind, object_type=object_type, object_name=name,
            scope=scope, field=field, referenced_interface=identity,
        ))

    for child in inventory.subinterfaces:
        add(child.parent_interface, ReferenceType.SUBINTERFACE_PARENT, "subinterface", child.name, "network", "parent_interface")
    for zone in inventory.zones:
        for member in zone.interface_members:
            add(member, ReferenceType.ZONE_INTERFACE, "zone", zone.name, zone.vsys, "interface_members")
    for router in inventory.virtual_routers:
        for member in router.interface_members:
            add(member, ReferenceType.VIRTUAL_ROUTER_INTERFACE, "virtual_router", router.name, router.name, "interface_members")
    for route in inventory.static_routes:
        if route.egress_interface:
            add(route.egress_interface, ReferenceType.STATIC_ROUTE_EGRESS_INTERFACE, "static_route", route.name, route.virtual_router, "egress_interface")
    for rule in inventory.nat_rules:
        for interface in rule.interface_references:
            add(interface, ReferenceType.NAT_INTERFACE_REFERENCE, "nat_rule", rule.name, rule.vsys, "interface_references")
    for interface in inventory.physical_interfaces:
        if interface.aggregate_group:
            add(interface.name, ReferenceType.AGGREGATE_MEMBERSHIP, "aggregate_interface", interface.aggregate_group, "network", "member_interfaces")
    return dict(index)
