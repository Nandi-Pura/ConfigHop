import hashlib
import ipaddress
import re
from collections import Counter
from xml.etree import ElementTree as ET

from pydantic import BaseModel, Field

from confighop_core.models.firewall import Coverage, Finding, FirewallCandidate, FirewallIR, Resource, Vendor


class FirewallMappings(BaseModel):
    interfaces: dict[str, str] = Field(default_factory=dict)
    zones: dict[str, str] = Field(default_factory=dict)
    addresses: dict[str, str] = Field(default_factory=dict)
    services: dict[str, str] = Field(default_factory=dict)
    policies: dict[str, str] = Field(default_factory=dict)
    nat: dict[str, str] = Field(default_factory=dict)


_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_. -]{0,62}$')
_INTERFACE_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_./-]{0,62}$')


def _finding(code: str, message: str, entity: str = '', severity: str = 'BLOCKED') -> Finding:
    return Finding(severity=severity, code=code, message=message, entity=entity)


def _name(source: str, mapping: dict[str, str]) -> str:
    return mapping.get(source, source)


def _refs(values: list[str], mapping: dict[str, str], wildcard: str) -> list[str]:
    return [wildcard if value.lower() in {'any', 'all'} else _name(value, mapping) for value in values]


def validate_firewall(ir: FirewallIR, target: Vendor, mappings: FirewallMappings) -> list[Finding]:
    findings = list(ir.findings)
    categories = [ir.interfaces, ir.zones, ir.addresses + ir.address_groups, ir.services + ir.service_groups,
        ir.schedules, ir.policies, ir.nat, ir.routes]
    for category in categories:
        counts = Counter((item.scope, item.name) for item in category)
        for (scope, name), count in counts.items():
            if count > 1:
                findings.append(_finding('DUPLICATE_IDENTITY', f'Duplicate identity in {scope}.', name))
    for label, mapping, source in [('interface', mappings.interfaces, ir.interfaces), ('zone', mappings.zones, ir.zones),
            ('address', mappings.addresses, ir.addresses + ir.address_groups),
            ('service', mappings.services, ir.services + ir.service_groups),
            ('policy', mappings.policies, ir.policies), ('NAT', mappings.nat, ir.nat)]:
        source_names = {item.name for item in source}
        if set(mapping) - source_names:
            findings.append(_finding('UNKNOWN_MAPPING', f'{label} mapping refers to unknown source identities.'))
        assigned = [_name(item.name, mapping) for item in source]
        for name, count in Counter(assigned).items():
            if count > 1:
                findings.append(_finding('NAME_COLLISION', f'{label} target name is repeated.', name))
            if not (_INTERFACE_NAME if label == 'interface' else _NAME).fullmatch(name):
                findings.append(_finding('INVALID_NAME', f'{label} target name is outside the conservative portable subset.', name))
    interface_names = {item.name for item in ir.interfaces}
    zone_names = {item.name for item in ir.zones}
    address_names = {item.name for item in ir.addresses + ir.address_groups}
    service_names = {item.name for item in ir.services + ir.service_groups}
    schedules = {item.name for item in ir.schedules}
    for zone in ir.zones:
        for member in zone.interfaces:
            if member not in interface_names:
                findings.append(_finding('MISSING_INTERFACE', 'Zone references a missing interface.', zone.name))
            elif member not in mappings.interfaces:
                findings.append(_finding('UNMAPPED_INTERFACE', 'Explicit target interface mapping is required.', member))
    for item in ir.interfaces:
        if item.name not in mappings.interfaces:
            findings.append(_finding('UNMAPPED_INTERFACE', 'Every source interface requires an explicit target mapping.', item.name))
        if item.parent and item.parent not in interface_names:
            findings.append(_finding('MISSING_PARENT', 'Subinterface parent is missing.', item.name))
        if item.parent and item.parent not in mappings.interfaces:
            findings.append(_finding('UNMAPPED_PARENT', 'Subinterface parent needs an explicit target mapping.', item.name))
        if item.kind not in {'physical', 'vlan', 'aggregate'}:
            findings.append(_finding('INTERFACE_KIND', 'Interface kind is unsupported.', item.name))
        if item.kind == 'vlan' and (item.vlan is None or not 1 <= item.vlan <= 4094):
            findings.append(_finding('VLAN_TAG', 'VLAN interface requires a valid tag.', item.name))
        if item.kind == 'aggregate' and (not item.members or any(member not in mappings.interfaces for member in item.members)):
            findings.append(_finding('AGGREGATE_MEMBER', 'Aggregate members need explicit target mappings.', item.name))
        if item.address:
            try:
                if ipaddress.ip_interface(item.address).version != 4:
                    raise ValueError()
            except ValueError:
                findings.append(_finding('INTERFACE_IP', 'Only IPv4 interface addresses are supported.', item.name))
    def check_group(groups, names, code):
        graph = {group.name: group.members for group in groups}
        def visit(name, ancestors):
            if len(ancestors) >= 64:
                findings.append(_finding('GROUP_DEPTH', f'{code} group nesting exceeds the supported limit.', name))
                return
            if name in ancestors:
                findings.append(_finding('CYCLIC_GROUP', f'{code} group has a cycle.', name))
                return
            for member in graph.get(name, []):
                if member not in names:
                    findings.append(_finding('MISSING_REFERENCE', f'{code} group member is missing.', member))
                elif member in graph:
                    visit(member, ancestors | {name})
        for group in groups:
            visit(group.name, set())
    check_group(ir.address_groups, address_names, 'Address')
    check_group(ir.service_groups, service_names, 'Service')
    for policy in ir.policies:
        for label, values, valid in [('source zone', policy.source_zones, zone_names), ('destination zone', policy.destination_zones, zone_names),
                ('source address', policy.sources, address_names), ('destination address', policy.destinations, address_names),
                ('service', policy.services, service_names)]:
            if not values:
                findings.append(_finding('EMPTY_POLICY_MATCH', f'{label} is empty; no default is inferred.', policy.name))
            for value in values:
                if value.lower() not in {'any', 'all'} and value not in valid:
                    findings.append(_finding('MISSING_REFERENCE', f'{label} reference is unresolved: {value}.', policy.name))
        if any(value.lower() in {'any', 'all'} for value in policy.source_zones + policy.destination_zones):
            findings.append(_finding('ANY_ZONE', 'Unrestricted zone matching needs manual review.', policy.name))
        if policy.action not in {'accept', 'allow', 'deny', 'drop'}:
            findings.append(_finding('ACTION', 'Policy action has no verified equivalent.', policy.name))
        if policy.applications and policy.applications != ['any']:
            findings.append(_finding('APP_ID', 'Application-aware policy cannot be safely converted to service-only matching.', policy.name))
        if policy.schedule != 'always':
            findings.append(_finding('SCHEDULE', 'Restricted schedule requires manual equivalence verification.', policy.name))
            if policy.schedule not in schedules:
                findings.append(_finding('MISSING_REFERENCE', 'Policy schedule is missing.', policy.name))
        if 'application-default' in policy.services:
            findings.append(_finding('APPLICATION_DEFAULT', 'Application-default service cannot be replaced with ANY.', policy.name))
        if policy.nat and not any(n.related_policy == policy.name for n in ir.nat):
            findings.append(_finding('NAT_DEPENDENCY', 'Policy SNAT has no safe translated NAT rule.', policy.name))
    for nat in ir.nat:
        if nat.kind not in {'dipp', 'dnat'}:
            findings.append(_finding('NAT_KIND', 'NAT kind is unsupported.', nat.name))
        if not nat.translated_address:
            findings.append(_finding('NAT_TRANSLATION', 'Translated address is missing.', nat.name))
        if nat.service.lower() not in {'any', 'all'} and nat.service not in service_names:
            findings.append(_finding('NAT_SERVICE', 'NAT service reference is unresolved.', nat.name))
        if nat.service in {group.name for group in ir.service_groups}:
            findings.append(_finding('NAT_SERVICE', 'NAT group service matching is not in the supported subset.', nat.name))
        if nat.related_policy:
            related = next((policy for policy in ir.policies if policy.name == nat.related_policy), None)
            if related is None:
                findings.append(_finding('NAT_POLICY_LINK', 'NAT references a missing security policy.', nat.name))
            else:
                groups = {group.name: group.members for group in ir.service_groups}
                values = related.services
                seen = set()
                while len(values) == 1 and values[0] in groups and values[0] not in seen:
                    seen.add(values[0]); values = groups[values[0]]
                related_service = values[0] if len(values) == 1 else None
                if not related_service or (nat.service.lower() in {'any', 'all'}) != (related_service.lower() in {'any', 'all'}) or (nat.service.lower() not in {'any', 'all'} and nat.service != related_service):
                    findings.append(_finding('NAT_SERVICE_MISMATCH', 'NAT and linked security policy have different service matches.', nat.name))
        translated = next((address.value for address in ir.addresses if address.name == nat.translated_address), nat.translated_address)
        try:
            translated_ip = ipaddress.ip_network(translated, strict=False)
            if translated_ip.version != 4 or translated_ip.prefixlen != 32:
                raise ValueError()
        except ValueError:
            findings.append(_finding('NAT_TRANSLATION', 'Only a single IPv4 translated address is supported.', nat.name))
        if nat.kind == 'dnat' and len(nat.destinations) != 1:
            findings.append(_finding('DNAT_MATCH', 'DNAT requires exactly one original destination.', nat.name))
        if nat.kind == 'dnat' and len(nat.destinations) == 1:
            original = next((address.value for address in ir.addresses if address.name == nat.destinations[0]), nat.destinations[0])
            try:
                if ipaddress.ip_network(original, strict=False).prefixlen != 32:
                    raise ValueError()
            except ValueError:
                findings.append(_finding('DNAT_MATCH', 'DNAT original destination must be one IPv4 address.', nat.name))
        if nat.kind == 'dnat' and target == 'fortios':
            ingress = [zone for zone in ir.zones if zone.name in nat.destination_zones]
            if len(ingress) != 1 or len(ingress[0].interfaces) != 1 or ingress[0].interfaces[0] not in mappings.interfaces:
                findings.append(_finding('VIP_INGRESS', 'DNAT requires one explicitly mapped original destination interface.', nat.name))
        if target == 'fortios' and not nat.related_policy:
            findings.append(_finding('NAT_POLICY_LINK', 'FortiOS NAT requires a uniquely linked firewall policy.', nat.name))
        for zone in nat.source_zones + nat.destination_zones:
            if zone.lower() != 'any' and zone not in zone_names:
                findings.append(_finding('MISSING_REFERENCE', 'NAT zone is unresolved.', nat.name))
        findings.append(_finding('NAT_REVIEW', 'Verify packet-flow, pre/post-NAT zone lookup and policy order on target hardware.', nat.name, 'REVIEW_REQUIRED'))
    for route in ir.routes:
        if route.interface and route.interface not in interface_names:
            findings.append(_finding('MISSING_INTERFACE', 'Static route interface is missing.', route.name))
        elif route.interface and route.interface not in mappings.interfaces:
            findings.append(_finding('UNMAPPED_INTERFACE', 'Static route interface needs an explicit mapping.', route.name))
        try:
            ipaddress.ip_network(route.destination, strict=False)
            if route.gateway:
                ipaddress.ip_address(route.gateway)
        except ValueError:
            findings.append(_finding('ROUTE_IP', 'Static route address is invalid.', route.name))
    for address in ir.addresses:
        try:
            if address.kind in {'ipmask', 'ip-netmask'}:
                if ipaddress.ip_network(address.value, strict=False).version != 4:
                    raise ValueError()
            elif address.kind in {'iprange', 'ip-range'}:
                start, end = address.value.split('-', 1)
                first, last = ipaddress.ip_address(start), ipaddress.ip_address(end)
                if first.version != 4 or last.version != 4 or first > last:
                    raise ValueError()
            elif address.kind != 'fqdn' or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?', address.value):
                raise ValueError()
        except ValueError:
            findings.append(_finding('ADDRESS_VALUE', 'Address value or kind is unsupported.', address.name))
    for service in ir.services:
        port_match = re.fullmatch(r'(\d{1,5})(?:-(\d{1,5}))?', service.port)
        if (service.protocol not in {'tcp', 'udp'} or not port_match or int(port_match[1]) > 65535
                or (port_match[2] is not None and (int(port_match[2]) > 65535 or int(port_match[1]) > int(port_match[2])))):
            findings.append(_finding('SERVICE_VALUE', 'Only one TCP or UDP destination port or range is supported.', service.name))
        if service.source_port:
            findings.append(_finding('SOURCE_PORT', 'Service source-port constraints need manual verification.', service.name))
    if ir.schedules:
        findings.append(_finding('SCHEDULE_TRANSLATION', 'Schedule rendering is not yet verified for this pair.'))
    return findings


def _add(parent: ET.Element, path: str, value: str | None = None) -> ET.Element:
    node = parent
    for tag in path.split('/'):
        existing = node.find(tag)
        node = existing if existing is not None else ET.SubElement(node, tag)
    if value is not None:
        node.text = value
    return node


def _members(parent: ET.Element, path: str, values: list[str]) -> None:
    node = _add(parent, path)
    for value in values:
        _add(node, 'member', value)


def _ordered_groups(groups):
    by_name = {group.name: group for group in groups}
    ordered, seen = [], set()
    def visit(name):
        if name in seen:
            return
        seen.add(name)
        for member in by_name[name].members:
            if member in by_name:
                visit(member)
        ordered.append(by_name[name])
    for group in groups:
        visit(group.name)
    return ordered


def _render_panos(ir: FirewallIR, mappings: FirewallMappings) -> str:
    root = ET.Element('config', {'version': '11.1.0'})
    device = ET.SubElement(_add(root, 'devices'), 'entry', {'name': 'localhost.localdomain'})
    network = _add(device, 'network')
    ethernet = _add(network, 'interface/ethernet')
    aggregate_member = {member: item.name for item in ir.interfaces if item.kind == 'aggregate' for member in item.members}
    physical_entries: dict[str, ET.Element] = {}
    for interface in ir.interfaces:
        if interface.name not in mappings.interfaces:
            continue
        target = mappings.interfaces[interface.name]
        if interface.kind == 'vlan':
            continue
        destination = ethernet if interface.kind == 'physical' else _add(network, 'interface/aggregate-ethernet')
        entry = ET.SubElement(destination, 'entry', {'name': target})
        physical_entries[interface.name] = entry
        if interface.name in aggregate_member:
            _add(entry, 'aggregate-group', _name(aggregate_member[interface.name], mappings.interfaces))
        else:
            _add(entry, 'layer3')
            if interface.address:
                ET.SubElement(_add(entry.find('layer3'), 'ip'), 'entry', {'name': interface.address})
    for interface in ir.interfaces:
        if interface.kind != 'vlan' or interface.name not in mappings.interfaces:
            continue
        parent = physical_entries[interface.parent or '']
        unit = ET.SubElement(_add(parent.find('layer3'), 'units'), 'entry', {'name': mappings.interfaces[interface.name]})
        _add(unit, 'tag', str(interface.vlan))
        if interface.address:
            ET.SubElement(_add(unit, 'ip'), 'entry', {'name': interface.address})
    vr = ET.SubElement(_add(network, 'virtual-router'), 'entry', {'name': 'default'})
    _members(vr, 'interface', list(dict.fromkeys(mappings.interfaces[item.name] for item in ir.interfaces
        if item.name in mappings.interfaces and item.name not in aggregate_member)))
    for route in ir.routes:
        entry = ET.SubElement(_add(vr, 'routing-table/ip/static-route'), 'entry', {'name': route.name})
        _add(entry, 'destination', route.destination)
        if route.gateway:
            _add(entry, 'nexthop/ip-address', route.gateway)
        if route.interface:
            _add(entry, 'interface', _name(route.interface, mappings.interfaces))
    vsys = ET.SubElement(_add(device, 'vsys'), 'entry', {'name': 'vsys1'})
    for zone in ir.zones:
        entry = ET.SubElement(_add(vsys, 'zone'), 'entry', {'name': _name(zone.name, mappings.zones)})
        _members(entry, 'network/layer3', [_name(value, mappings.interfaces) for value in zone.interfaces])
    for address in ir.addresses:
        entry = ET.SubElement(_add(vsys, 'address'), 'entry', {'name': _name(address.name, mappings.addresses)})
        kind = {'ipmask': 'ip-netmask', 'iprange': 'ip-range'}.get(address.kind, address.kind)
        _add(entry, kind, address.value)
    for group in _ordered_groups(ir.address_groups):
        entry = ET.SubElement(_add(vsys, 'address-group'), 'entry', {'name': _name(group.name, mappings.addresses)})
        _members(entry, 'static', _refs(group.members, mappings.addresses, 'any'))
    for service in ir.services:
        entry = ET.SubElement(_add(vsys, 'service'), 'entry', {'name': _name(service.name, mappings.services)})
        _add(entry, f'protocol/{service.protocol}/port', service.port)
    for group in _ordered_groups(ir.service_groups):
        entry = ET.SubElement(_add(vsys, 'service-group'), 'entry', {'name': _name(group.name, mappings.services)})
        _members(entry, 'members', _refs(group.members, mappings.services, 'any'))
    for policy in ir.policies:
        entry = ET.SubElement(_add(vsys, 'rulebase/security/rules'), 'entry', {'name': _name(policy.name, mappings.policies)})
        for path, values, mapping in [('from', policy.source_zones, mappings.zones), ('to', policy.destination_zones, mappings.zones),
                ('source', policy.sources, mappings.addresses), ('destination', policy.destinations, mappings.addresses),
                ('service', policy.services, mappings.services)]:
            _members(entry, path, _refs(values, mapping, 'any'))
        _members(entry, 'application', ['any'])
        _add(entry, 'action', 'allow' if policy.action in {'accept', 'allow'} else 'deny')
        _add(entry, 'disabled', 'yes' if policy.disabled else 'no')
        _add(entry, 'log-end', 'yes' if policy.log else 'no')
        if policy.description:
            _add(entry, 'description', policy.description)
    for nat in ir.nat:
        entry = ET.SubElement(_add(vsys, 'rulebase/nat/rules'), 'entry', {'name': _name(nat.name, mappings.nat)})
        for path, values, mapping in [('from', nat.source_zones, mappings.zones), ('to', nat.destination_zones, mappings.zones),
                ('source', nat.sources, mappings.addresses), ('destination', nat.destinations, mappings.addresses)]:
            _members(entry, path, _refs(values, mapping, 'any'))
        _add(entry, 'service', 'any' if nat.service.lower() in {'any', 'all'} else _name(nat.service, mappings.services))
        if nat.kind == 'dipp':
            _members(entry, 'source-translation/dynamic-ip-and-port/translated-address', [nat.translated_address])
        else:
            _add(entry, 'destination-translation/translated-address', nat.translated_address)
            if nat.translated_port:
                _add(entry, 'destination-translation/translated-port', nat.translated_port)
    ET.indent(root)
    return ET.tostring(root, encoding='unicode') + '\n'


def _quote(value: str) -> str:
    if re.fullmatch(r'[0-9.]+', value):
        return value
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ') + '"'


def _set(key: str, value: str | list[str]) -> str:
    values = value if isinstance(value, list) else [value]
    return f'        set {key} ' + ' '.join(_quote(item) for item in values) + '\n'


def _block(section: str, records: list[tuple[str, list[tuple[str, str | list[str]]]]]) -> str:
    if not records:
        return ''
    text = f'config {section}\n'
    for name, fields in records:
        text += f'    edit {_quote(name)}\n'
        for key, value in fields:
            text += _set(key, value)
        text += '    next\n'
    return text + 'end\n\n'


def _render_fortios(ir: FirewallIR, mappings: FirewallMappings) -> str:
    output = '# ConfigHop migration candidate: review before deployment\n'
    interfaces = []
    for item in ir.interfaces:
        if item.name not in mappings.interfaces:
            continue
        fields = []
        if item.address:
            network = ipaddress.ip_interface(item.address)
            fields.append(('ip', [str(network.ip), str(network.network.netmask)]))
        if item.kind == 'vlan':
            fields += [('type', 'vlan'), ('interface', _name(item.parent or '', mappings.interfaces)), ('vlanid', str(item.vlan))]
        elif item.kind == 'aggregate':
            fields += [('type', 'aggregate'), ('member', [_name(member, mappings.interfaces) for member in item.members])]
        interfaces.append((mappings.interfaces[item.name], fields))
    output += _block('system interface', interfaces)
    output += _block('system zone', [(_name(item.name, mappings.zones), [('interface', [_name(value, mappings.interfaces) for value in item.interfaces])]) for item in ir.zones])
    addresses = []
    for item in ir.addresses:
        if item.kind in {'ipmask', 'ip-netmask'}:
            network = ipaddress.ip_network(item.value, strict=False)
            fields = [('subnet', [str(network.network_address), str(network.netmask)])]
        elif item.kind in {'iprange', 'ip-range'}:
            start, end = item.value.split('-', 1)
            fields = [('type', 'iprange'), ('start-ip', start), ('end-ip', end)]
        else:
            fields = [('type', 'fqdn'), ('fqdn', item.value)]
        addresses.append((_name(item.name, mappings.addresses), fields))
    output += _block('firewall address', addresses)
    output += _block('firewall addrgrp', [(_name(item.name, mappings.addresses), [('member', _refs(item.members, mappings.addresses, 'all'))]) for item in _ordered_groups(ir.address_groups)])
    output += _block('firewall service custom', [(_name(item.name, mappings.services), [('protocol', 'TCP/UDP/SCTP'), (f'{item.protocol}-portrange', item.port)]) for item in ir.services])
    output += _block('firewall service group', [(_name(item.name, mappings.services), [('member', _refs(item.members, mappings.services, 'ALL'))]) for item in _ordered_groups(ir.service_groups)])
    output += _block('router static', [(item.name if item.name.isdigit() else str(index + 1),
        [('dst', [str(ipaddress.ip_network(item.destination, strict=False).network_address), str(ipaddress.ip_network(item.destination, strict=False).netmask)]),
            *([('gateway', item.gateway)] if item.gateway else []), *([('device', _name(item.interface, mappings.interfaces))] if item.interface else [])]) for index, item in enumerate(ir.routes)])
    def destination_for_policy(policy, value):
        dnat = next((nat for nat in ir.nat if nat.kind == 'dnat' and nat.related_policy == policy.name), None)
        if dnat and (value in dnat.destinations or any(address.name == value and address.value.removesuffix('/32') in dnat.destinations for address in ir.addresses)):
            return _name(dnat.name, mappings.nat)
        return _refs([value], mappings.addresses, 'all')[0]

    def translated_ip(value):
        address = next((item.value for item in ir.addresses if item.name == value), value)
        return str(ipaddress.ip_network(address, strict=False).network_address)

    pools = [(f'pool-{item.name}', [('type', 'overload'), ('startip', translated_ip(item.translated_address)), ('endip', translated_ip(item.translated_address))]) for item in ir.nat if item.kind == 'dipp']
    output += _block('firewall ippool', pools)
    output += _block('firewall vip', [(_name(item.name, mappings.nat),
        [('extintf', _name(next(zone.interfaces[0] for zone in ir.zones if zone.name in item.destination_zones), mappings.interfaces)),
            ('extip', translated_ip(item.destinations[0])), ('mappedip', translated_ip(item.translated_address))])
        for item in ir.nat if item.kind == 'dnat'])
    output += _block('firewall policy', [(str(index + 1), [('name', _name(item.name, mappings.policies)),
        ('srcintf', _refs(item.source_zones, mappings.zones, 'any')),
        ('dstintf', _refs(item.destination_zones, mappings.zones, 'any')),
        ('srcaddr', _refs(item.sources, mappings.addresses, 'all')),
        ('dstaddr', [destination_for_policy(item, value) for value in item.destinations]),
        ('service', _refs(item.services, mappings.services, 'ALL')),
        ('action', 'accept' if item.action in {'accept', 'allow'} else 'deny'), ('schedule', item.schedule),
        ('status', 'disable' if item.disabled else 'enable'), ('logtraffic', 'all' if item.log else 'disable'),
        *([('comments', item.description)] if item.description else []),
        *([('nat', 'enable'), ('ippool', 'enable'), ('poolname', f'pool-{next(nat.name for nat in ir.nat if nat.kind == "dipp" and nat.related_policy == item.name)}')]
            if any(nat.kind == 'dipp' and nat.related_policy == item.name for nat in ir.nat) else [])])
        for index, item in enumerate(ir.policies)])
    return output.rstrip() + '\n'


def generate_firewall(ir: FirewallIR, target: Vendor, mappings: FirewallMappings, revision: int, target_version: str = '') -> FirewallCandidate:
    findings = validate_firewall(ir, target, mappings)
    blocked = any(item.severity == 'BLOCKED' for item in findings)
    status = 'BLOCKED' if blocked else 'REVIEW_REQUIRED' if any(item.severity == 'REVIEW_REQUIRED' for item in findings) else 'READY_FOR_REVIEW'
    try:
        text = '' if blocked else (_render_panos(ir, mappings) if target == 'panos' else _render_fortios(ir, mappings))
    except (ValueError, KeyError, TypeError):
        findings.append(_finding('RENDER_UNSUPPORTED', 'Candidate rendering encountered an unsupported source combination.'))
        blocked, status, text = True, 'BLOCKED', ''
    if text:
        if target == 'panos':
            from defusedxml import ElementTree as SafeET
            SafeET.fromstring(text.encode('utf-8'), forbid_dtd=True, forbid_entities=True, forbid_external=True)
        else:
            from confighop_core.parsers.fortios import parse_fortios_tree
            parse_fortios_tree(text)
    counts = {'Objects': ir.addresses + ir.address_groups, 'Services': ir.services + ir.service_groups,
        'Interfaces': ir.interfaces, 'Zones': ir.zones, 'Policies': ir.policies, 'NAT': ir.nat,
        'Routes': ir.routes, 'Schedules': ir.schedules, 'VPN': [], 'Security profiles': []}
    coverage = []
    for category, items in counts.items():
        names = {item.name for item in items}
        review_names = {finding.entity for finding in findings if finding.entity in names and finding.severity == 'REVIEW_REQUIRED'}
        blocked_names = {finding.entity for finding in findings if finding.entity in names and finding.severity == 'BLOCKED'}
        unsupported_names = {finding.entity for finding in findings if finding.entity in names and finding.code.startswith(('UNSUPPORTED', 'SERVICE_PROTOCOL', 'ADDRESS_TYPE'))}
        extra = 0
        blocked_extra = 0
        if category == 'VPN':
            extra = sum(finding.code == 'UNSUPPORTED_SECTION' and any(word in finding.message.lower() for word in ('vpn', 'tunnel', 'ipsec')) for finding in findings)
        elif category == 'Security profiles':
            extra = sum(finding.code == 'SECURITY_PROFILE' for finding in findings)
        elif category == 'Schedules' and ir.schedules:
            blocked_extra = len(ir.schedules)
        coverage.append(Coverage(category=category, parsed=len(items) + extra, translated=0 if blocked else len(items),
            rendered=0 if blocked else len(items), validated=0 if blocked else len(items) - len(review_names | blocked_names),
            review_required=len(review_names), unsupported=len(unsupported_names) + extra + blocked_extra, blocked=len(blocked_names) + extra + blocked_extra))
    return FirewallCandidate(source_os=ir.source_vendor, source_version=ir.source_version, target_os=target,
        target_version=target_version or ('7.4' if target == 'fortios' else '11.1'),
        status=status, revision=revision, sha256=hashlib.sha256(text.encode()).hexdigest(),
        syntax='xml' if target == 'panos' else 'cli', text=text, findings=findings, coverage=coverage)
