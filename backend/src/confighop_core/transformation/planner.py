from collections import Counter
from hashlib import sha256

from ..mapping import preview_interface_mappings
from ..models.dependency import ReferenceType
from ..models.hardware import HardwareProfile
from ..models.inventory import PaloAltoInventory
from ..models.mapping import ChangeAction, MigrationPreview, PreviewStatus, Severity
from ..models.transformation import OperationType, RenderFinding, TransformationOperation, TransformationPlan


_REF_OPERATIONS = {
    ReferenceType.ZONE_INTERFACE: OperationType.UPDATE_ZONE_INTERFACE_REFERENCE,
    ReferenceType.VIRTUAL_ROUTER_INTERFACE: OperationType.UPDATE_VIRTUAL_ROUTER_INTERFACE_REFERENCE,
    ReferenceType.STATIC_ROUTE_EGRESS_INTERFACE: OperationType.UPDATE_STATIC_ROUTE_EGRESS_REFERENCE,
    ReferenceType.NAT_INTERFACE_REFERENCE: OperationType.UPDATE_NAT_INTERFACE_REFERENCE,
    ReferenceType.AGGREGATE_MEMBERSHIP: OperationType.ASSERT_AGGREGATE_MEMBERSHIP,
    ReferenceType.SUBINTERFACE_PARENT: OperationType.ASSERT_SUBINTERFACE_PARENT,
}


def inventory_digest(inventory: PaloAltoInventory) -> str:
    return sha256(inventory.model_dump_json().encode("utf-8")).hexdigest()


def build_transformation_plan(
    source_bytes: bytes, inventory: PaloAltoInventory, preview: MigrationPreview,
    target_profile: HardwareProfile, *, allow_review: bool = False,
) -> TransformationPlan:
    findings: list[RenderFinding] = []

    def error(code: str, message: str) -> None:
        findings.append(RenderFinding(code=code, severity=Severity.ERROR, message=message))

    fresh = preview_interface_mappings(inventory, preview.mappings, target_profile)
    if fresh.model_dump() != preview.model_dump():
        error("PREVIEW_MISMATCH", "Submitted preview differs from a fresh preview.")
    if preview.status == PreviewStatus.BLOCKED:
        error("PREVIEW_BLOCKED", "Blocked preview cannot be rendered.")
    if preview.status == PreviewStatus.REVIEW_REQUIRED and not allow_review:
        error("REVIEW_APPROVAL_REQUIRED", "Explicit review override is required.")

    physical_map = {impact.source_interface: impact.target_interface for impact in preview.impacts
        if impact.mapping_status.value in ("MAPPED", "REVIEW")}
    final_physical = [physical_map.get(item.name, item.name) for item in inventory.physical_interfaces]
    if any(count > 1 for count in Counter(final_physical).values()):
        error("TARGET_PHYSICAL_NAME_COLLISION", "Final physical interface names collide.")
    child_map = {child.source_interface: child.target_interface for impact in preview.impacts
        for child in impact.derived_subinterfaces}
    final_children = [child_map.get(item.name, item.name) for item in inventory.subinterfaces]
    if any(count > 1 for count in Counter(final_children).values()):
        error("TARGET_SUBINTERFACE_NAME_COLLISION", "Final subinterface names collide.")

    operations: list[TransformationOperation] = []

    def add(kind: OperationType, old: str, new: str, obj_type: str, obj_name: str, scope: str, field: str) -> None:
        operations.append(TransformationOperation(sequence=len(operations) + 1, operation_type=kind,
            source_value=old, target_value=new, object_type=obj_type, object_name=obj_name, scope=scope, field=field))

    if not findings:
        for impact in preview.impacts:
            if impact.source_interface != impact.target_interface:
                add(OperationType.RENAME_PHYSICAL_INTERFACE, impact.source_interface, impact.target_interface,
                    "physical_interface", impact.source_interface, "network", "name")
            for child in impact.derived_subinterfaces:
                if child.source_interface != child.target_interface:
                    add(OperationType.RENAME_SUBINTERFACE, child.source_interface, child.target_interface,
                        "subinterface", child.source_parent, "network", "name")
            for change in impact.reference_changes:
                if change.action != ChangeAction.UPDATE_REFERENCE:
                    continue
                add(_REF_OPERATIONS[change.reference_type], change.old_value, change.new_value,
                    change.object_type, change.object_name, change.scope, change.field)
    status = PreviewStatus.BLOCKED if findings else preview.status
    return TransformationPlan(source_sha256=sha256(source_bytes).hexdigest(),
        source_inventory_sha256=inventory_digest(inventory), target_profile_vendor=target_profile.vendor,
        target_profile_model=target_profile.model, target_profile_status=target_profile.profile_status.value,
        preview_status=preview.status, operations=operations, findings=findings, status=status)
