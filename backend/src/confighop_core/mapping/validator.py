from collections import Counter

from ..palo_alto_constants import NATIVE_QSFP_SPEED_XML
from ..models.hardware import HardwareKind, HardwareProfile, RequiredCondition
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
        chosen = mapping.target_settings.link_speed if mapping.target_settings else None
        if target and target.required_condition == RequiredCondition.MANUAL_NATIVE_PORT_SPEED:
            if chosen is None:
                error("TARGET_NATIVE_PORT_MODE_REQUIRED", "Select 40G or 100G for the native QSFP target.")
            elif chosen not in NATIVE_QSFP_SPEED_XML:
                error("TARGET_LINK_SPEED_UNSUPPORTED", "The selected speed cannot configure this native QSFP target.")
            else:
                findings.append(MigrationFinding(code="PHYSICAL_LINK_CHANGE_REQUIRED", severity=Severity.WARNING,
                    source_interface=mapping.source_interface, target_interface=mapping.target_interface,
                    message="Verify optics, cabling and peer compatibility before deployment."))
        elif target and target.required_condition == RequiredCondition.AUTO_ONLY_LINK_FIELDS_ABSENT and chosen is not None:
            error("TARGET_AUTO_ONLY_LINK_SETTING_NOT_APPLICABLE", "Scoped auto-only RJ45 rendering cannot set target link speed.")
        elif mapping.target_settings is not None and chosen is not None:
            error("TARGET_INTERFACE_SETTING_NOT_APPLICABLE", "Native QSFP target speed does not apply to this interface.")
    return findings
