from xml.etree.ElementTree import Element

from ...models.transformation import OperationType, TransformationOperation


def _named(parents: list[Element], path: str, name: str) -> list[Element]:
    return [entry for parent in parents for entry in parent.findall(path) if entry.get("name") == name]


def locate(root: Element, operation: TransformationOperation) -> list[tuple[Element, str]]:
    """Resolve original nodes only; the second tuple item is 'name', 'text', or 'assert'."""
    devices = root.findall("./devices/entry")
    kind = operation.operation_type
    if kind == OperationType.RENAME_PHYSICAL_INTERFACE:
        return [(item, "name") for item in _named(devices, "./network/interface/ethernet/entry", operation.source_value)]
    if kind in (OperationType.RENAME_SUBINTERFACE, OperationType.ASSERT_SUBINTERFACE_PARENT):
        parent_name = operation.object_name if kind == OperationType.RENAME_SUBINTERFACE else operation.source_value
        child_name = operation.source_value if kind == OperationType.RENAME_SUBINTERFACE else operation.object_name
        parents = _named(devices, "./network/interface/ethernet/entry", parent_name)
        children = [child for parent in parents for mode in ("layer3", "layer2")
            for child in parent.findall(f"./{mode}/units/entry") if child.get("name") == child_name]
        return [(child, "assert" if kind == OperationType.ASSERT_SUBINTERFACE_PARENT else "name") for child in children]
    if kind == OperationType.ASSERT_AGGREGATE_MEMBERSHIP:
        return [(item, "assert") for item in _named(devices, "./network/interface/ethernet/entry", operation.source_value)
            if item.findtext("aggregate-group") == operation.object_name]
    if kind == OperationType.UPDATE_ZONE_INTERFACE_REFERENCE:
        vsys = _named(devices, "./vsys/entry", operation.scope)
        zones = _named(vsys, "./zone/entry", operation.object_name)
        return [(member, "text") for zone in zones for mode in ("layer3", "layer2", "virtual-wire")
            for member in zone.findall(f"./network/{mode}/member") if (member.text or "").strip() == operation.source_value]
    if kind in (OperationType.UPDATE_VIRTUAL_ROUTER_INTERFACE_REFERENCE, OperationType.UPDATE_STATIC_ROUTE_EGRESS_REFERENCE):
        routers = _named(devices, "./network/virtual-router/entry",
            operation.object_name if kind == OperationType.UPDATE_VIRTUAL_ROUTER_INTERFACE_REFERENCE else operation.scope)
        if kind == OperationType.UPDATE_VIRTUAL_ROUTER_INTERFACE_REFERENCE:
            return [(member, "text") for router in routers for member in router.findall("./interface/member")
                if (member.text or "").strip() == operation.source_value]
        routes = _named(routers, "./routing-table/ip/static-route/entry", operation.object_name)
        return [(interface, "text") for route in routes for interface in route.findall("./interface")
            if (interface.text or "").strip() == operation.source_value]
    if kind == OperationType.UPDATE_NAT_INTERFACE_REFERENCE:
        vsys = _named(devices, "./vsys/entry", operation.scope)
        rules = _named(vsys, "./rulebase/nat/rules/entry", operation.object_name)
        return [(interface, "text") for rule in rules for translation in ("source-translation", "destination-translation")
            for parent in rule.findall(f"./{translation}") for address in parent.iter("interface-address")
            for interface in address.findall("./interface") if (interface.text or "").strip() == operation.source_value]
    raise ValueError("Unsupported operation type")
