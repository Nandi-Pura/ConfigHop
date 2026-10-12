from .dependencies import build_dependency_index
from .models.hardware import HardwareProfile, RequiredCondition, TargetRenderSupport
from .models.inventory import PaloAltoInventory
from .models.mapping import InterfaceMapping, MigrationFinding, Severity


def scoped_render_findings(
    inventory: PaloAltoInventory, mappings: list[InterfaceMapping], target: HardwareProfile,
) -> list[MigrationFinding]:
    if target.target_render_support != TargetRenderSupport.SCOPED:
        return []
    references = build_dependency_index(inventory)
    decisions = {item.source_interface: item for item in mappings}
    ports = {item.name: item for item in target.interfaces}
    groups = {name: group.id for group in target.interface_groups for name in group.interface_names}
    findings: list[MigrationFinding] = []

    def error(code: str, message: str, source: str, destination: str | None = None) -> None:
        findings.append(MigrationFinding(code=code, severity=Severity.ERROR, message=message,
            source_interface=source, target_interface=destination))

    for interface in inventory.physical_interfaces:
        active = bool(interface.mode != "unknown" or interface.aggregate_group or interface.ip_addresses
            or interface.management_profile or interface.subinterface_names or interface.link_state_explicit
            or interface.link_speed_explicit or interface.link_duplex_explicit or references.get(interface.name))
        mapping = decisions.get(interface.name)
        destination = mapping.target_interface if mapping else interface.name
        if active and mapping is None:
            error("SCOPED_TARGET_ACTIVE_INTERFACE_MAPPING_REQUIRED",
                "Every active source physical interface requires an explicit mapping for a scoped target.", interface.name, destination)
        if not active and mapping is None and destination not in ports:
            error("TARGET_INTERFACE_NOT_FOUND",
                "Preserved inactive source interface is absent from the target hardware profile.", interface.name, destination)
        if not active and mapping is None:
            continue
        port = ports.get(destination)
        if port is None:
            continue
        if interface.mode in {"layer2", "virtual_wire", "aggregate_member"} or interface.aggregate_group:
            error("SCOPED_TARGET_DEPENDENCY_COVERAGE_INSUFFICIENT",
                "This interface mode has unqualified dependency coverage for scoped rendering.", interface.name, destination)
        if port.required_condition == RequiredCondition.TARGET_LINK_SERIALIZATION_UNVERIFIED:
            error("TARGET_INTERFACE_GROUP_RENDERING_UNQUALIFIED",
                f"Target group {groups.get(destination, destination)} has unqualified link or optic serialization.", interface.name, destination)
        elif port.required_condition == RequiredCondition.AUTO_ONLY_LINK_FIELDS_ABSENT:
            if interface.link_speed_explicit or interface.link_duplex_explicit:
                error("TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED",
                    "Auto-negotiation-only hardware is documented, but explicit speed or duplex XML serialization is unqualified.", interface.name, destination)
            if mapping and mapping.target_settings and mapping.target_settings.link_speed is not None:
                error("TARGET_AUTO_ONLY_LINK_SETTING_NOT_APPLICABLE",
                    "Scoped auto-only RJ45 rendering cannot set target link speed.", interface.name, destination)
        else:
            error("TARGET_INTERFACE_GROUP_RENDERING_UNQUALIFIED",
                f"Target group {groups.get(destination, destination)} is outside the scoped render policy.", interface.name, destination)
    return findings
