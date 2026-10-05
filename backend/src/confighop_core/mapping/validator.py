from collections import Counter

from ..models.hardware import HardwareKind, HardwareProfile
from ..models.inventory import PaloAltoInventory
from ..models.mapping import InterfaceMapping, MigrationFinding, Severity


def validate_mappings(
    inventory: PaloAltoInventory, mappings: list[InterfaceMapping], target_profile: HardwareProfile,
) -> list[MigrationFinding]:
    findings: list[MigrationFinding] = []
    if len(inventory.device_entries) > 1:
        findings.append(MigrationFinding(code="MULTI_DEVICE_INVENTORY_UNSUPPORTED", severity=Severity.ERROR,
            message="Interface ownership is ambiguous across multiple devices."))
    sources = {interface.name for interface in inventory.physical_interfaces}
    unsupported_sources = {interface.name for interface in inventory.subinterfaces}
    unsupported_sources.update(interface.name for interface in inventory.aggregate_interfaces)
    unsupported_sources.update(interface.name for interface in inventory.vlan_interfaces)
    unsupported_sources.update(interface.name for interface in inventory.loopback_interfaces)
    targets = {interface.name: interface for interface in target_profile.interfaces}
    source_counts = Counter(mapping.source_interface for mapping in mappings)
    target_counts = Counter(mapping.target_interface for mapping in mappings)
    for mapping in mappings:
        def error(code: str, message: str) -> None:
            findings.append(MigrationFinding(code=code, severity=Severity.ERROR,
                source_interface=mapping.source_interface, target_interface=mapping.target_interface, message=message))

        if source_counts[mapping.source_interface] > 1:
            error("DUPLICATE_SOURCE_MAPPING", "Source interface has multiple submitted mappings.")
        if target_counts[mapping.target_interface] > 1:
            error("DUPLICATE_TARGET_MAPPING", "Target interface has multiple submitted mappings.")
        if mapping.source_interface in unsupported_sources:
            error("UNSUPPORTED_MAPPING_OBJECT", "Only physical Ethernet source interfaces can be mapped directly.")
        elif mapping.source_interface not in sources:
            error("SOURCE_INTERFACE_NOT_FOUND", "Source physical interface was not found.")
        target = targets.get(mapping.target_interface)
        if target is None:
            error("TARGET_INTERFACE_NOT_FOUND", "Target interface was not found in the hardware profile.")
        elif target.kind != HardwareKind.PHYSICAL_ETHERNET:
            error("TARGET_INTERFACE_TYPE_UNSUPPORTED", "Target interface is not physical Ethernet.")
    return findings
