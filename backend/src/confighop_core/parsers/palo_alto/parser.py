from pathlib import Path
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from confighop_core.errors import ConfigParseError, ConfigTooLargeError, MalformedXmlError, UnsupportedConfigFormatError
from confighop_core.models.common import ObjectScope, ParserWarning
from confighop_core.models.interface import AggregateInterface, LoopbackInterface, PhysicalInterface, Subinterface, VlanInterface, Zone
from confighop_core.models.inventory import PaloAltoInventory
from confighop_core.models.objects import AddressObject, ServiceObject
from confighop_core.models.platform import DeviceEntry, PlatformMetadata
from confighop_core.models.policy import NatRule, SecurityRule
from confighop_core.models.routing import StaticRoute, VirtualRouter

from .helpers import child_tag, interface_mode, ip_addresses, members, optional_bool, optional_int, text

MAX_XML_BYTES = 100 * 1024 * 1024


def parse_palo_alto_xml(path: str | Path) -> PaloAltoInventory:
    """Read a local PAN-OS XML export and return inventory without changing it."""
    source = Path(path)
    try:
        if source.stat().st_size > MAX_XML_BYTES:
            raise ConfigTooLargeError("Configuration exceeds the 100 MiB limit.")
        data = source.read_bytes()
    except OSError as exc:
        raise ConfigParseError("Configuration file could not be read.") from exc
    if len(data) > MAX_XML_BYTES:
        raise ConfigTooLargeError("Configuration exceeds the 100 MiB limit.")
    try:
        root = SafeET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (SafeET.ParseError, DefusedXmlException) as exc:
        raise MalformedXmlError("Configuration is malformed or contains prohibited XML constructs.") from exc
    if root.tag != "config":
        raise UnsupportedConfigFormatError("Expected a Palo Alto config XML root.")

    return _inventory_from_root(root)


def parse_palo_alto_xml_bytes(data: bytes) -> PaloAltoInventory:
    if len(data) > MAX_XML_BYTES:
        raise ConfigTooLargeError("Configuration exceeds the 100 MiB limit.")
    try:
        root = SafeET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (SafeET.ParseError, DefusedXmlException) as exc:
        raise MalformedXmlError("Configuration is malformed or contains prohibited XML constructs.") from exc
    if root.tag != "config":
        raise UnsupportedConfigFormatError("Expected a Palo Alto config XML root.")
    return _inventory_from_root(root)


def _inventory_from_root(root: Element) -> PaloAltoInventory:

    inventory = PaloAltoInventory(platform=PlatformMetadata(config_version=root.get("version"), detail_version=root.get("detail-version")))
    _parse_objects(root.find("shared"), ObjectScope(type="shared"), inventory)
    for device in root.findall("./devices/entry"):
        inventory.device_entries.append(DeviceEntry(name=device.get("name") or ""))
        _parse_interfaces(device, inventory)
        _parse_routing(device, inventory)
        for vsys in device.findall("./vsys/entry"):
            inventory.vsys_names.append(vsys.get("name") or "")
            _parse_vsys(vsys, inventory)
    return inventory


def _parse_interfaces(device: Element, inventory: PaloAltoInventory) -> None:
    members_by_aggregate: dict[str, list[str]] = {}
    for entry in device.findall("./network/interface/ethernet/entry"):
        name = entry.get("name") or ""
        mode = interface_mode(entry)
        group = text(entry, "aggregate-group")
        if group:
            members_by_aggregate.setdefault(group, []).append(name)
        interface = PhysicalInterface(
            name=name, mode=mode, comment=text(entry, "comment"), link_state=text(entry, "link-state"),
            link_state_explicit=entry.find("link-state") is not None,
            link_speed=text(entry, "link-speed"), link_duplex=text(entry, "link-duplex"), aggregate_group=group,
            link_speed_explicit=entry.find("link-speed") is not None,
            link_duplex_explicit=entry.find("link-duplex") is not None,
            ip_addresses=ip_addresses(entry, "./layer3/ip/entry", "physical_interface", name, inventory.warnings),
            management_profile=text(entry, "./layer3/interface-management-profile"),
        )
        for mode_name in ("layer3", "layer2"):
            for unit in entry.findall(f"./{mode_name}/units/entry"):
                unit_name = unit.get("name") or ""
                interface.subinterface_names.append(unit_name)
                inventory.subinterfaces.append(Subinterface(
                    name=unit_name, parent_interface=name, mode=mode_name,
                    tag=optional_int(unit, "tag", "subinterface", unit_name, inventory.warnings),
                    ip_addresses=ip_addresses(unit, "./ip/entry", "subinterface", unit_name, inventory.warnings),
                    management_profile=text(unit, "interface-management-profile"), comment=text(unit, "comment"),
                    adjust_tcp_mss_enabled=optional_bool(unit, "./adjust-tcp-mss/enable"),
                ))
        inventory.physical_interfaces.append(interface)

    for entry in device.findall("./network/interface/aggregate-ethernet/entry"):
        name = entry.get("name") or ""
        inventory.aggregate_interfaces.append(AggregateInterface(
            name=name, mode=interface_mode(entry), comment=text(entry, "comment"),
            ip_addresses=ip_addresses(entry, "./layer3/ip/entry", "aggregate_interface", name, inventory.warnings),
            management_profile=text(entry, "./layer3/interface-management-profile"),
            member_interfaces=members_by_aggregate.get(name, []),
        ))

    for kind, model in (("vlan", VlanInterface), ("loopback", LoopbackInterface)):
        output = inventory.vlan_interfaces if kind == "vlan" else inventory.loopback_interfaces
        for entry in device.findall(f"./network/interface/{kind}/units/entry"):
            name = entry.get("name") or ""
            output.append(model(
                name=name, ip_addresses=ip_addresses(entry, "./ip/entry", f"{kind}_interface", name, inventory.warnings),
                management_profile=text(entry, "interface-management-profile"), comment=text(entry, "comment"),
            ))


def _parse_routing(device: Element, inventory: PaloAltoInventory) -> None:
    for entry in device.findall("./network/virtual-router/entry"):
        name = entry.get("name") or ""
        router = VirtualRouter(name=name, interface_members=members(entry, "./interface/member"))
        for route in entry.findall("./routing-table/ip/static-route/entry"):
            route_name = route.get("name") or ""
            router.static_route_names.append(route_name)
            next_hop_type = child_tag(route, "nexthop")
            next_hop_value = text(route, f"./nexthop/{next_hop_type}") if next_hop_type else None
            if next_hop_type not in (None, "ip-address", "next-vr", "discard"):
                inventory.warnings.append(ParserWarning(code="UNSUPPORTED_ROUTE_NEXTHOP", object_type="static_route", object_name=route_name, field="nexthop", message="Next-hop structure was retained by type but is not interpreted."))
            inventory.static_routes.append(StaticRoute(
                name=route_name, virtual_router=name, destination=text(route, "destination"),
                egress_interface=text(route, "interface"),
                metric=optional_int(route, "metric", "static_route", route_name, inventory.warnings),
                next_hop_type=next_hop_type, next_hop_value=next_hop_value, bfd_profile=text(route, "bfd/profile"),
            ))
        inventory.virtual_routers.append(router)


def _parse_objects(container: Element | None, scope: ObjectScope, inventory: PaloAltoInventory) -> None:
    if container is None:
        return
    for entry in container.findall("./address/entry"):
        name = entry.get("name") or ""
        kind = next((tag for tag in ("ip-netmask", "ip-range", "fqdn") if entry.find(tag) is not None), "unknown")
        if kind == "unknown":
            inventory.warnings.append(ParserWarning(code="MALFORMED_OBJECT", object_type="address_object", object_name=name, field="kind", message="Address object form is not supported; value was omitted."))
        inventory.address_objects.append(AddressObject(name=name, scope=scope, kind=kind, value=text(entry, kind) if kind != "unknown" else None, description=text(entry, "description")))
    for entry in container.findall("./service/entry"):
        name = entry.get("name") or ""
        protocol = next((tag for tag in ("tcp", "udp") if entry.find(f"./protocol/{tag}") is not None), "unknown")
        if protocol == "unknown":
            inventory.warnings.append(ParserWarning(code="MALFORMED_OBJECT", object_type="service_object", object_name=name, field="protocol", message="Service protocol is not supported; ports were omitted."))
        inventory.service_objects.append(ServiceObject(
            name=name, scope=scope, protocol=protocol,
            destination_port=text(entry, f"./protocol/{protocol}/port") if protocol != "unknown" else None,
            source_port=text(entry, f"./protocol/{protocol}/source-port") if protocol != "unknown" else None,
            description=text(entry, "description"),
        ))


def _parse_vsys(vsys: Element, inventory: PaloAltoInventory) -> None:
    name = vsys.get("name") or ""
    _parse_objects(vsys, ObjectScope(type="vsys", name=name), inventory)
    for entry in vsys.findall("./zone/entry"):
        zone_name = entry.get("name") or ""
        zone_type = next((mode for tag, mode in (("layer3", "layer3"), ("layer2", "layer2"), ("virtual-wire", "virtual_wire")) if entry.find(f"./network/{tag}") is not None), "unknown")
        inventory.zones.append(Zone(name=zone_name, vsys=name, zone_type=zone_type, interface_members=members(entry, f"./network/{zone_type.replace('_', '-')}/member") if zone_type != "unknown" else []))

    for entry in vsys.findall("./rulebase/security/rules/entry"):
        inventory.security_rules.append(SecurityRule(
            name=entry.get("name") or "", uuid=entry.get("uuid"), vsys=name,
            from_zones=members(entry, "./from/member"), to_zones=members(entry, "./to/member"),
            sources=members(entry, "./source/member"), destinations=members(entry, "./destination/member"),
            applications=members(entry, "./application/member"), services=members(entry, "./service/member"),
            action=text(entry, "action"), disabled=optional_bool(entry, "disabled"), description=text(entry, "description"),
        ))

    for entry in vsys.findall("./rulebase/nat/rules/entry"):
        refs = [interface.text.strip() for path in ("./source-translation//interface-address/interface", "./destination-translation//interface-address/interface") for interface in entry.findall(path) if interface.text and interface.text.strip()]
        inventory.nat_rules.append(NatRule(
            name=entry.get("name") or "", uuid=entry.get("uuid"), vsys=name,
            from_zones=members(entry, "./from/member"), to_zones=members(entry, "./to/member"),
            sources=members(entry, "./source/member"), destinations=members(entry, "./destination/member"),
            service=text(entry, "service"), source_translation_type=child_tag(entry, "source-translation"),
            destination_translation_type=child_tag(entry, "destination-translation"),
            interface_references=list(dict.fromkeys(refs)), disabled=optional_bool(entry, "disabled"),
        ))
