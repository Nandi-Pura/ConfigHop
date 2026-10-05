from copy import deepcopy
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element

from ..models.inventory import PaloAltoInventory
from ..models.transformation import OperationType, TransformationPlan


def expected_inventory(source: PaloAltoInventory, plan: TransformationPlan) -> PaloAltoInventory:
    expected = source.model_copy(deep=True)
    physical = {op.source_value: op.target_value for op in plan.operations
        if op.operation_type == OperationType.RENAME_PHYSICAL_INTERFACE}
    children = {op.source_value: op.target_value for op in plan.operations
        if op.operation_type == OperationType.RENAME_SUBINTERFACE}

    def mapped(value: str) -> str:
        return children.get(value, physical.get(value, value))

    for item in expected.physical_interfaces:
        item.name = physical.get(item.name, item.name)
        item.subinterface_names = [mapped(name) for name in item.subinterface_names]
    for item in expected.subinterfaces:
        item.name = children.get(item.name, item.name)
        item.parent_interface = physical.get(item.parent_interface, item.parent_interface)
    for item in expected.aggregate_interfaces:
        item.member_interfaces = [physical.get(name, name) for name in item.member_interfaces]
    for item in expected.zones:
        item.interface_members = [mapped(name) for name in item.interface_members]
    for item in expected.virtual_routers:
        item.interface_members = [mapped(name) for name in item.interface_members]
    for item in expected.static_routes:
        if item.egress_interface:
            item.egress_interface = mapped(item.egress_interface)
    for item in expected.nat_rules:
        item.interface_references = list(dict.fromkeys(mapped(name) for name in item.interface_references))
    for warning in expected.warnings:
        if warning.object_name:
            warning.object_name = mapped(warning.object_name)
    return expected


def element_path(root: Element, target: Element) -> tuple[int, ...]:
    def walk(node: Element, path: tuple[int, ...]) -> tuple[int, ...] | None:
        if node is target:
            return path
        for index, child in enumerate(node):
            found = walk(child, path + (index,))
            if found is not None:
                return found
        return None

    found = walk(root, ())
    if found is None:
        raise ValueError("Mutation node is detached from the source tree")
    return found


def preservation_audit(
    source_root: Element, candidate_root: Element,
    inverse: list[tuple[tuple[int, ...], str, str]],
) -> bool:
    restored = deepcopy(candidate_root)
    for path, field, old in inverse:
        node = restored
        for index in path:
            node = node[index]
        if field == "name":
            node.set("name", old)
        else:
            node.text = old
    source_xml = ET.canonicalize(ET.tostring(source_root, encoding="unicode"), with_comments=True)
    restored_xml = ET.canonicalize(ET.tostring(restored, encoding="unicode"), with_comments=True)
    return source_xml == restored_xml
