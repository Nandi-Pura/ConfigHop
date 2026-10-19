from defusedxml import ElementTree as SafeET

from confighop_core.models.firewall import (
    Address, Finding, FirewallIR, Group, Interface, Nat, Policy, Route, Schedule, Service, Zone,
)
from confighop_core.firewall_ir import finalize_ir
from confighop_core.parsers.palo_alto.parser import parse_palo_alto_xml_bytes


def _members(entry, path: str) -> list[str]:
    return [item.text.strip() for item in entry.findall(path) if item.text and item.text.strip()]


def _text(entry, path: str, default: str = '') -> str:
    value = entry.findtext(path)
    return value.strip() if value and value.strip() else default


def parse_panos_firewall(source: str, version: str) -> FirewallIR:
    data = source.encode('utf-8')
    inventory = parse_palo_alto_xml_bytes(data)
    root = SafeET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    ir = FirewallIR(source_vendor='panos', source_version=version or inventory.platform.config_version or '')
    if len(inventory.vsys_names) != 1 or len(inventory.device_entries) != 1:
        ir.findings.append(Finding(severity='BLOCKED', code='PANOS_SCOPE', message='Exactly one device and VSYS must be selected for cross-vendor translation.'))
    if root.find('./devices/entry/device-group') is not None or root.find('./devices/entry/vsys/entry/import') is not None:
        ir.findings.append(Finding(severity='BLOCKED', code='PANORAMA_SCOPE', message='Managed or imported object scope requires separate migration design.'))
    for device in root.findall('./devices/entry'):
        network = device.find('network')
        if network is not None:
            for child in network:
                if child.tag not in {'interface', 'virtual-router'}:
                    ir.findings.append(Finding(severity='BLOCKED', code='UNSUPPORTED_SECTION', message=f'Unsupported PAN-OS network section {child.tag}.'))
            for router in network.findall('./virtual-router/entry'):
                for child in router:
                    if child.tag not in {'interface', 'routing-table'}:
                        ir.findings.append(Finding(severity='BLOCKED', code='UNSUPPORTED_SECTION', message=f'Unsupported PAN-OS virtual-router section {child.tag}.', entity=router.get('name', '')))
        for vsys in device.findall('./vsys/entry'):
            for child in vsys:
                if child.tag not in {'address', 'address-group', 'service', 'service-group', 'zone', 'rulebase', 'schedule'}:
                    ir.findings.append(Finding(severity='BLOCKED', code='UNSUPPORTED_SECTION', message=f'Unsupported PAN-OS VSYS section {child.tag}.', entity=vsys.get('name', '')))
            for rulebase in vsys.findall('rulebase'):
                for child in rulebase:
                    if child.tag not in {'security', 'nat'}:
                        ir.findings.append(Finding(severity='BLOCKED', code='UNSUPPORTED_SECTION', message=f'Unsupported PAN-OS rulebase section {child.tag}.', entity=vsys.get('name', '')))
    ir.source_scope = inventory.vsys_names[0] if inventory.vsys_names else 'vsys1'
    for obj in inventory.address_objects:
        ir.addresses.append(Address(name=obj.name, scope=obj.scope.name or obj.scope.type, kind=obj.kind, value=obj.value or ''))
    for obj in inventory.service_objects:
        ir.services.append(Service(name=obj.name, scope=obj.scope.name or obj.scope.type, protocol=obj.protocol,
            port=obj.destination_port or '', source_port=obj.source_port))
    for obj in inventory.physical_interfaces:
        ir.interfaces.append(Interface(name=obj.name, kind='physical', address=obj.ip_addresses[0] if obj.ip_addresses else None))
    for obj in inventory.aggregate_interfaces:
        ir.interfaces.append(Interface(name=obj.name, kind='aggregate', address=obj.ip_addresses[0] if obj.ip_addresses else None,
            members=obj.member_interfaces))
    for obj in inventory.subinterfaces:
        ir.interfaces.append(Interface(name=obj.name, kind='vlan', address=obj.ip_addresses[0] if obj.ip_addresses else None,
            parent=obj.parent_interface, vlan=obj.tag))
    for obj in inventory.zones:
        ir.zones.append(Zone(name=obj.name, scope=obj.vsys, interfaces=obj.interface_members))
        if obj.zone_type != 'layer3':
            ir.findings.append(Finding(severity='BLOCKED', code='ZONE_TYPE', message='Only Layer 3 zones are supported.', entity=obj.name))
    for obj in inventory.static_routes:
        ir.routes.append(Route(name=obj.name, destination=obj.destination or '', gateway=obj.next_hop_value if obj.next_hop_type == 'ip-address' else None,
            interface=obj.egress_interface, router=obj.virtual_router))
        if obj.next_hop_type not in (None, 'ip-address'):
            ir.findings.append(Finding(severity='BLOCKED', code='ROUTE_NEXT_HOP', message='Route next-hop type is unsupported.', entity=obj.name))
    for container in [root.find('shared'), *root.findall('./devices/entry/vsys/entry')]:
        if container is None:
            continue
        scope = 'shared' if container.tag == 'shared' else container.get('name', 'vsys1')
        if scope == 'shared':
            for child in container:
                if child.tag not in {'address', 'address-group', 'service', 'service-group', 'schedule'}:
                    ir.findings.append(Finding(severity='BLOCKED', code='UNSUPPORTED_SECTION', message=f'Unsupported PAN-OS shared section {child.tag}.'))
        for kind, path in [('address', './address-group/entry'), ('service', './service-group/entry')]:
            for entry in container.findall(path):
                group = Group(name=entry.get('name', ''), scope=scope, members=_members(entry, './static/member') if kind == 'address' else _members(entry, './members/member'))
                (ir.address_groups if kind == 'address' else ir.service_groups).append(group)
                if kind == 'address' and entry.find('./dynamic') is not None:
                    ir.findings.append(Finding(severity='BLOCKED', code='DYNAMIC_GROUP', message='Dynamic address groups require manual migration.', entity=group.name))
        for entry in container.findall('./schedule/entry'):
            ir.schedules.append(Schedule(name=entry.get('name', ''), scope=scope, kind='panos'))
            ir.findings.append(Finding(severity='BLOCKED', code='SCHEDULE_SEMANTICS', message='PAN-OS schedule translation requires manual design.', entity=entry.get('name', '')))
        for entry in container.findall('./rulebase/security/rules/entry'):
            name = entry.get('name', '')
            for key in ('disabled', 'log-end', 'negate-source', 'negate-destination'):
                if entry.find(key) is not None and _text(entry, key) not in {'yes', 'no'}:
                    ir.findings.append(Finding(severity='BLOCKED', code='POLICY_ENUM', message=f'Unsupported {key} value.', entity=name))
            supported_policy_fields = {'from', 'to', 'source', 'destination', 'application', 'service', 'action',
                'disabled', 'description', 'log-end', 'schedule', 'profile-setting', 'source-user',
                'negate-source', 'negate-destination', 'category'}
            for child in entry:
                if child.tag not in supported_policy_fields:
                    ir.findings.append(Finding(severity='BLOCKED', code='UNSUPPORTED_POLICY_FIELD', message=f'Unsupported policy field {child.tag}.', entity=name))
            policy = Policy(name=name, scope=scope, source_zones=_members(entry, './from/member'),
                destination_zones=_members(entry, './to/member'), sources=_members(entry, './source/member'),
                destinations=_members(entry, './destination/member'), services=_members(entry, './service/member'),
                applications=_members(entry, './application/member'), action=_text(entry, 'action', 'deny'),
                disabled=_text(entry, 'disabled') == 'yes', schedule=_text(entry, 'schedule', 'always'),
                log=_text(entry, 'log-end') == 'yes', description=_text(entry, 'description'))
            ir.policies.append(policy)
            if entry.find('profile-setting') is not None:
                ir.findings.append(Finding(severity='BLOCKED', code='SECURITY_PROFILE', message='Security profile references need manual migration.', entity=name))
            if entry.find('source-user') is not None and _members(entry, './source-user/member') != ['any']:
                ir.findings.append(Finding(severity='BLOCKED', code='USER_ID', message='User identity matching needs manual migration.', entity=name))
            if _text(entry, 'negate-source') == 'yes' or _text(entry, 'negate-destination') == 'yes' or _members(entry, './category/member') not in ([], ['any']):
                ir.findings.append(Finding(severity='BLOCKED', code='POLICY_MATCH', message='Negated or category-based matching needs manual migration.', entity=name))
        for entry in container.findall('./rulebase/nat/rules/entry'):
            name = entry.get('name', '')
            if entry.find('disabled') is not None and _text(entry, 'disabled') not in {'yes', 'no'}:
                ir.findings.append(Finding(severity='BLOCKED', code='NAT_ENUM', message='Unsupported NAT disabled value.', entity=name))
            for child in entry:
                if child.tag not in {'from', 'to', 'source', 'destination', 'service', 'source-translation', 'destination-translation', 'disabled'}:
                    ir.findings.append(Finding(severity='BLOCKED', code='UNSUPPORTED_NAT_FIELD', message=f'Unsupported NAT field {child.tag}.', entity=name))
            if _text(entry, 'disabled') == 'yes':
                ir.findings.append(Finding(severity='BLOCKED', code='NAT_DISABLED', message='Disabled NAT rules require explicit target handling.', entity=name))
            common = dict(name=name, scope=scope, source_zones=_members(entry, './from/member'),
                destination_zones=_members(entry, './to/member'), sources=_members(entry, './source/member'),
                destinations=_members(entry, './destination/member'), service=_text(entry, 'service', 'any'))
            dipp = entry.find('./source-translation/dynamic-ip-and-port')
            dnat = entry.find('./destination-translation')
            if dipp is not None:
                addresses = _members(dipp, './translated-address/member')
                if len(addresses) == 1 and dnat is None:
                    ir.nat.append(Nat(kind='dipp', translated_address=addresses[0], **common))
                else:
                    ir.findings.append(Finding(severity='BLOCKED', code='PANOS_SNAT', message='Only one translated address and no combined NAT is supported.', entity=name))
            elif dnat is not None and _text(dnat, 'translated-address') and entry.find('source-translation') is None:
                ir.nat.append(Nat(kind='dnat', translated_address=_text(dnat, 'translated-address'),
                    translated_port=_text(dnat, 'translated-port') or None, **common))
            else:
                ir.findings.append(Finding(severity='BLOCKED', code='PANOS_NAT', message='NAT form requires manual migration.', entity=name))
    for warning in inventory.warnings:
        ir.findings.append(Finding(severity='BLOCKED', code=warning.code, message=warning.message, entity=warning.object_name))
    for nat in ir.nat:
        matches = []
        for policy in ir.policies:
            def destination_match(value: str) -> bool:
                if value in nat.destinations:
                    return True
                address = next((item for item in ir.addresses if item.name == value), None)
                return bool(address and any(address.value == original or address.value == original + '/32' for original in nat.destinations))
            if (nat.source_zones == policy.source_zones and (nat.kind == 'dnat' or nat.destination_zones == policy.destination_zones)
                    and nat.sources == policy.sources and any(destination_match(value) for value in policy.destinations)):
                matches.append(policy)
        if len(matches) == 1:
            nat.related_policy = matches[0].name
        else:
            ir.findings.append(Finding(severity='BLOCKED', code='NAT_POLICY_LINK', message='NAT rule has no unique equivalent security policy.', entity=nat.name))
    return finalize_ir(ir)
