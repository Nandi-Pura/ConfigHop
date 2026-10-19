import ipaddress
import shlex
from dataclasses import dataclass, field

from confighop_core.models.firewall import (
    Address, Finding, FirewallIR, Group, Interface, Nat, Policy, Route, Schedule, Service, Zone,
)
from confighop_core.firewall_ir import finalize_ir

MAX_FIREWALL_BYTES = 2 * 1024 * 1024


@dataclass
class Node:
    name: str
    line: int
    values: dict[str, list[str]] = field(default_factory=dict)
    children: list['Node'] = field(default_factory=list)

    def get(self, key: str, default: str = '') -> str:
        return ' '.join(self.values.get(key, [])) or default

    def items(self, path: str) -> list['Node']:
        return [entry for section in self.children if section.name == path for entry in section.children]


def _tokens(line: str) -> list[str]:
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = '#'
    return list(lexer)


def parse_fortios_tree(source: str) -> Node:
    if len(source.encode('utf-8')) > MAX_FIREWALL_BYTES or source.count('\n') > 20000:
        raise ValueError('FortiOS source exceeds the 2 MB or 20,000-line limit.')
    root = Node('root', 0)
    stack = [root]
    for number, raw in enumerate(source.splitlines(), 1):
        try:
            parts = _tokens(raw.strip())
        except ValueError as exc:
            raise ValueError(f'Malformed FortiOS quoting on line {number}.') from exc
        if not parts:
            continue
        command, *args = parts
        if command == 'config' and args:
            node = Node('config ' + ' '.join(args), number)
            stack[-1].children.append(node)
            stack.append(node)
        elif command == 'edit' and len(args) == 1 and len(stack) > 1:
            node = Node(args[0], number)
            stack[-1].children.append(node)
            stack.append(node)
        elif command == 'set' and len(args) >= 2 and len(stack) > 1:
            stack[-1].values[args[0]] = args[1:]
        elif command == 'unset' and len(args) == 1 and len(stack) > 1:
            stack[-1].values.pop(args[0], None)
        elif command == 'next' and len(stack) > 2:
            stack.pop()
        elif command == 'end' and len(stack) > 1:
            stack.pop()
        else:
            # Unknown commands remain visible to the adapter as unsupported input.
            stack[-1].children.append(Node(f'!unsupported:{command}', number, {'args': args}))
    if len(stack) != 1:
        raise ValueError(f'FortiOS source has an unclosed {stack[-1].name} block.')
    return root


def _network(address: str, mask: str) -> str:
    return str(ipaddress.ip_network(f'{address}/{mask}', strict=False))


def _interface_address(address: str, mask: str) -> str:
    return str(ipaddress.ip_interface(f'{address}/{mask}'))


def parse_fortios(source: str, version: str) -> FirewallIR:
    tree = parse_fortios_tree(source)
    ir = FirewallIR(source_vendor='fortios', source_version=version)
    contexts = [tree]
    for vdom in tree.items('config vdom'):
        contexts.append(vdom)
    if len(contexts) > 2:
        ir.findings.append(Finding(severity='BLOCKED', code='MULTI_VDOM', message='Multiple VDOMs require separate migrations.'))
    for context in contexts:
        scope = context.name if context is not tree else 'root'
        for item in context.items('config system interface'):
            kind = item.get('type', 'physical')
            if kind not in {'physical', 'vlan', 'aggregate', 'loopback'}:
                ir.findings.append(Finding(severity='BLOCKED', code='INTERFACE_TYPE', message=f'Unsupported interface type {kind}.', entity=item.name, line=item.line))
            address = None
            if item.values.get('ip'):
                try:
                    address = _interface_address(*item.values['ip'][:2])
                except (ValueError, TypeError):
                    ir.findings.append(Finding(severity='BLOCKED', code='INTERFACE_IP', message='Invalid interface IP.', entity=item.name, line=item.line))
            ir.interfaces.append(Interface(name=item.name, scope=scope, line=item.line, kind=kind, address=address,
                parent=item.get('interface') or None, vlan=int(item.get('vlanid')) if item.get('vlanid').isdigit() else None,
                members=item.values.get('member', [])))
        for item in context.items('config system zone'):
            ir.zones.append(Zone(name=item.name, scope=scope, line=item.line, interfaces=item.values.get('interface', [])))
        for item in context.items('config firewall address'):
            kind = item.get('type', 'ipmask')
            value = ''
            try:
                if kind == 'ipmask' and item.values.get('subnet'):
                    value = _network(*item.values['subnet'][:2])
                elif kind in {'iprange', 'fqdn'}:
                    value = item.get('start-ip') + '-' + item.get('end-ip') if kind == 'iprange' else item.get('fqdn')
                else:
                    raise ValueError('unsupported address form')
            except (ValueError, TypeError):
                ir.findings.append(Finding(severity='BLOCKED', code='ADDRESS_TYPE', message=f'Unsupported or invalid address type {kind}.', entity=item.name, line=item.line))
            ir.addresses.append(Address(name=item.name, scope=scope, line=item.line, kind=kind, value=value))
        for item in context.items('config firewall addrgrp'):
            ir.address_groups.append(Group(name=item.name, scope=scope, line=item.line, members=item.values.get('member', [])))
        for item in context.items('config firewall service custom'):
            choices = [(protocol, item.get(f'{protocol.lower()}-portrange')) for protocol in ('TCP', 'UDP') if item.get(f'{protocol.lower()}-portrange')]
            if len(choices) != 1 or item.get('protocol', 'TCP/UDP/SCTP') not in {'TCP/UDP/SCTP', choices[0][0] if choices else ''}:
                ir.findings.append(Finding(severity='BLOCKED', code='SERVICE_PROTOCOL', message='Only a single TCP or UDP port range is supported.', entity=item.name, line=item.line))
            protocol, port = choices[0] if choices else ('unknown', '')
            ir.services.append(Service(name=item.name, scope=scope, line=item.line, protocol=protocol.lower(), port=port))
        for item in context.items('config firewall service group'):
            ir.service_groups.append(Group(name=item.name, scope=scope, line=item.line, members=item.values.get('member', [])))
        for item in context.items('config firewall schedule recurring'):
            ir.schedules.append(Schedule(name=item.name, scope=scope, line=item.line, kind='recurring', start=item.get('start'), end=item.get('end'), days=item.values.get('day', [])))
        for item in context.items('config firewall schedule onetime'):
            ir.findings.append(Finding(severity='BLOCKED', code='SCHEDULE_ONETIME', message='One-time schedule translation is unsupported.', entity=item.name, line=item.line))
        pools = {item.name: item for item in context.items('config firewall ippool')}
        vips = {item.name: item for item in context.items('config firewall vip')}
        for order, item in enumerate(context.items('config firewall policy')):
            policy = Policy(name=item.get('name', item.name), source_name=item.name, scope=scope, line=item.line,
                source_zones=item.values.get('srcintf', []), destination_zones=item.values.get('dstintf', []),
                sources=item.values.get('srcaddr', []), destinations=item.values.get('dstaddr', []),
                services=item.values.get('service', []), action=item.get('action', 'deny'),
                disabled=item.get('status', 'enable') == 'disable', schedule=item.get('schedule', 'always'),
                log=item.get('logtraffic', 'disable') != 'disable', description=item.get('comments'),
                nat=item.get('nat') == 'enable', nat_pool=item.get('poolname') or None)
            for reference in policy.source_zones + policy.destination_zones:
                if reference in {interface.name for interface in ir.interfaces} and reference not in {zone.name for zone in ir.zones}:
                    ir.zones.append(Zone(name=reference, scope=scope, line=item.line, interfaces=[reference]))
            ir.policies.append(policy)
            if policy.nat:
                if item.get('ippool') != 'enable' or not policy.nat_pool or policy.nat_pool not in pools:
                    ir.findings.append(Finding(severity='BLOCKED', code='SNAT_INTERFACE', message='Interface SNAT or missing pool cannot be translated without a verified egress address.', entity=policy.name, line=item.line))
                else:
                    pool = pools[policy.nat_pool]
                    if pool.get('startip') != pool.get('endip') or pool.get('type', 'overload') != 'overload':
                        ir.findings.append(Finding(severity='BLOCKED', code='SNAT_POOL_TYPE', message='Only a single-address overload pool is supported.', entity=pool.name, line=pool.line))
                    else:
                        ir.nat.append(Nat(name=f'snat-{item.name}', kind='dipp', scope=scope, line=item.line,
                            source_zones=policy.source_zones, destination_zones=policy.destination_zones,
                            sources=policy.sources, destinations=policy.destinations, translated_address=pool.get('startip'), related_policy=policy.name))
            for destination in policy.destinations:
                if destination in vips:
                    vip = vips[destination]
                    if not vip.get('extip') or not vip.get('mappedip') or vip.get('portforward', 'disable') != 'disable':
                        ir.findings.append(Finding(severity='BLOCKED', code='VIP_COMPLEX', message='Only one-to-one VIP without port forwarding is supported.', entity=vip.name, line=vip.line))
                    else:
                        ingress = [zone.name for zone in ir.zones if vip.get('extintf') in zone.interfaces]
                        if len(ingress) != 1:
                            ir.findings.append(Finding(severity='BLOCKED', code='VIP_INGRESS', message='VIP requires an explicit external interface in exactly one zone.', entity=vip.name, line=vip.line))
                        if not any(address.name == vip.name for address in ir.addresses):
                            ir.addresses.append(Address(name=vip.name, scope=scope, line=vip.line,
                                kind='ipmask', value=f"{vip.get('extip')}/32"))
                        ir.nat.append(Nat(name=f'dnat-{vip.name}', kind='dnat', scope=scope, line=vip.line,
                            source_zones=policy.source_zones, destination_zones=ingress,
                            sources=policy.sources, destinations=[vip.get('extip')], translated_address=vip.get('mappedip'),
                            related_policy=policy.name))
        linked_vips = {nat.name.removeprefix('dnat-') for nat in ir.nat if nat.kind == 'dnat'}
        for name, item in vips.items():
            if name not in linked_vips:
                ir.findings.append(Finding(severity='BLOCKED', code='UNLINKED_VIP', message='VIP has no supported policy reference.', entity=name, line=item.line))
        linked_pools = {policy.nat_pool for policy in ir.policies if policy.nat_pool}
        for name, item in pools.items():
            if name not in linked_pools:
                ir.findings.append(Finding(severity='BLOCKED', code='UNLINKED_POOL', message='IP pool has no supported policy reference.', entity=name, line=item.line))
        for item in context.items('config router static'):
            try:
                destination = _network(*item.values.get('dst', ['0.0.0.0', '0.0.0.0'])[:2])
            except (ValueError, TypeError):
                ir.findings.append(Finding(severity='BLOCKED', code='ROUTE_DESTINATION', message='Invalid static route destination.', entity=item.name, line=item.line))
                continue
            ir.routes.append(Route(name=item.name, scope=scope, line=item.line, destination=destination,
                gateway=item.get('gateway') or None, interface=item.get('device') or None))
    fields = {
        'config system interface': {'type', 'ip', 'interface', 'vlanid', 'member', 'alias', 'description'},
        'config system zone': {'interface', 'description'},
        'config firewall address': {'type', 'subnet', 'start-ip', 'end-ip', 'fqdn', 'comment'},
        'config firewall addrgrp': {'member', 'comment'},
        'config firewall service custom': {'protocol', 'tcp-portrange', 'udp-portrange', 'comment'},
        'config firewall service group': {'member', 'comment'},
        'config firewall policy': {'name', 'srcintf', 'dstintf', 'srcaddr', 'dstaddr', 'service', 'action', 'schedule',
            'status', 'logtraffic', 'comments', 'nat', 'ippool', 'poolname'},
        'config firewall vip': {'extip', 'mappedip', 'extintf', 'portforward', 'extport', 'mappedport', 'protocol', 'comment'},
        'config firewall ippool': {'type', 'startip', 'endip', 'comments'},
        'config router static': {'dst', 'gateway', 'device'},
        'config firewall schedule recurring': {'start', 'end', 'day', 'color'},
        'config firewall schedule onetime': {'start', 'end'},
    }
    known = set(fields) | {'config vdom'}
    display_fields = {'alias', 'description', 'comment', 'comments', 'color'}
    def report_unknown(node: Node, path: str = '') -> None:
        for child in node.children:
            if child.name.startswith('!unsupported:'):
                ir.findings.append(Finding(severity='BLOCKED', code='UNKNOWN_COMMAND', message=f'Unknown FortiOS command {child.name[13:]}.', line=child.line))
            elif child.name.startswith('config ') and child.name not in known:
                ir.findings.append(Finding(severity='BLOCKED', code='UNSUPPORTED_SECTION', message=f'Unsupported section {child.name}.', line=child.line))
            elif child.name.startswith('config ') and child.name in fields:
                for entry in child.children:
                    for key in entry.values.keys() - fields[child.name]:
                        ir.findings.append(Finding(severity='BLOCKED', code='UNSUPPORTED_FIELD', message=f'Unsupported field {key} in {child.name}.', entity=entry.name, line=entry.line))
                    for key in entry.values.keys() & display_fields:
                        if not (child.name == 'config firewall policy' and key == 'comments'):
                            ir.findings.append(Finding(severity='INFO', code='OMITTED_METADATA', message=f'Display metadata {key} is not rendered.', entity=entry.name, line=entry.line))
                    report_unknown(entry, child.name)
            else:
                report_unknown(child, child.name)
    report_unknown(tree)
    if not any((ir.interfaces, ir.addresses, ir.policies, ir.routes)):
        raise ValueError('No supported FortiOS configuration was found.')
    return finalize_ir(ir)
