from xml.etree.ElementTree import Element

from ...models.transformation import OperationType, TransformationPlan


_DECLARATIONS = {OperationType.RENAME_PHYSICAL_INTERFACE, OperationType.RENAME_SUBINTERFACE}
_NON_SEMANTIC = {"comment", "description"}


def unmodeled_interface_references(
    root: Element, plan: TransformationPlan, resolved: list[tuple],
) -> list[str]:
    """Find exact changed identities outside the nodes resolved by modeled operations."""
    changed = {op.source_value for op in plan.operations if op.operation_type in _DECLARATIONS}
    known = {(id(node), "name" if field == "name" else "text")
             for _, node, field in resolved if field in {"name", "text"}}
    findings: list[str] = []

    pending = [(root, "")]
    while pending:
        node, path = pending.pop()
        if not isinstance(node.tag, str):
            continue
        segment = node.tag + (f"[@name='{node.get('name')}']" if node.get("name") else "")
        here = f"{path}/{segment}"
        if node.tag not in _NON_SEMANTIC:
            for key, value in node.attrib.items():
                if value in changed and (id(node), key) not in known:
                    findings.append(f"{value} at {here}/@{key}")
            value = (node.text or "").strip()
            if value in changed and (id(node), "text") not in known:
                findings.append(f"{value} at {here}/text()")
        pending.extend((child, here) for child in reversed(node))
    return findings
