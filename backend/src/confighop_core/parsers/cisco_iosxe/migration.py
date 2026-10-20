"""Strict, line-oriented IOS XE migration parser; unknown syntax is never emitted."""
import ipaddress
import re

from ...models.switch_migration import SwitchInterface, SwitchMigrationIR, SwitchStatement
from ..switch_common import vlan_list

MAX_SWITCH_BYTES = 2 * 1024 * 1024
IDENTIFIER = r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}'
PHYSICAL = re.compile(r'(GigabitEthernet|Gi|TenGigabitEthernet|Te|TwentyFiveGigE|Twe|FortyGigabitEthernet|Fo|HundredGigE|Hu)(\d+(?:/\d+){1,2})', re.I)
PREFIXES = {'gi': 'GigabitEthernet', 'te': 'TenGigabitEthernet', 'twe': 'TwentyFiveGigE', 'fo': 'FortyGigabitEthernet', 'hu': 'HundredGigE'}
SECRET = re.compile(r'\b(password|secret|community|key|key-string|private-key|certificate|credential|authentication-key|auth-key|encrypted|ciphertext)\b', re.I)


def interface_name(value: str) -> str:
    match = PHYSICAL.fullmatch(value)
    if match:
        prefix = match[1]
        return PREFIXES.get(prefix.lower(), next((v for v in PREFIXES.values() if v.lower() == prefix.lower()), prefix)) + match[2]
    for prefix in ('Port-channel', 'Vlan', 'Loopback'):
        if re.fullmatch(prefix + r'\d+', value, re.I):
            return prefix + str(int(value[len(prefix):]))
    return value


def parse_migration(text: str, version: str) -> SwitchMigrationIR:
    if len(text.encode('utf-8')) > MAX_SWITCH_BYTES or len(text.splitlines()) > 20000:
        raise ValueError('Source exceeds the 2 MB limit.')
    if not text.strip() or any(ord(c) < 32 and c not in '\r\n\t' for c in text) or text.lstrip().startswith(('<', '{')):
        raise ValueError('Expected a nonempty plain-text IOS XE configuration.')
    ir = SwitchMigrationIR(source_version=version)
    scope, context = 'global', 'global'
    interfaces: set[str] = set()
    unsupported_interfaces: set[str] = set()
    seen: dict[tuple[str, str], list[str]] = {}
    opaque = False
    banner_delimiter: str | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        command = raw.strip()
        if not command:
            continue
        if banner_delimiter:
            ir.statements.append(SwitchStatement(line=number, source='[REDACTED banner content]', scope='global', feature='banner', status='UNSUPPORTED', render_supported=False))
            if banner_delimiter in command:
                banner_delimiter = None
            continue
        if command.startswith('!') or command in {'end', 'exit'}:
            scope, context, opaque = 'global', 'global', False
            continue
        if opaque:
            ir.statements.append(SwitchStatement(line=number, source='[REDACTED sensitive block]', scope=scope,
                feature='secret_reentry', status='BLOCKED', render_supported=False))
            if command == 'quit':
                scope, context, opaque = 'global', 'global', False
            continue
        if not raw[0].isspace():
            scope, context, opaque = 'global', 'global', False
        safe = '[REDACTED sensitive statement]' if SECRET.search(command) or opaque or command.startswith(('username ', 'snmp-server ', 'crypto ', 'radius ', 'tacacs ')) else command
        item = SwitchStatement(line=number, source=safe, scope=scope, feature='unknown', status='UNSUPPORTED', render_supported=False)
        ir.statements.append(item)

        def parsed(feature: str, values: list[str] = [], dependencies: list[str] = []) -> None:
            item.feature, item.values, item.dependencies = feature, values, dependencies
            item.status, item.render_supported = 'TRANSLATED', True

        try:
            if command.startswith('banner '):
                item.source, item.feature = '[REDACTED banner]', 'banner'
                parts = command.split(maxsplit=2)
                if len(parts) == 3:
                    delimiter = parts[2][0]
                    if parts[2].count(delimiter) < 2:
                        banner_delimiter = delimiter
            elif safe != command:
                item.feature = 'secret_reentry'
                item.status = 'BLOCKED'
                if match := re.match(r'username (' + IDENTIFIER + r')(?: |$)', command):
                    item.feature, item.values = 'local_user_reentry', [match[1]]
                elif command.startswith('snmp-server '):
                    item.feature = 'snmp_reentry'
                if command.startswith(('crypto ', 'radius ', 'tacacs ')):
                    context, opaque = 'opaque', True
            elif command.startswith('interface '):
                name = interface_name(command[10:].strip())
                if not re.fullmatch(r'[A-Za-z][A-Za-z0-9/.-]{0,90}', name):
                    raise ValueError('interface identifier')
                kind = 'Physical' if PHYSICAL.fullmatch(name) else 'LAG' if re.fullmatch(r'Port-channel\d+', name) else 'SVI' if re.fullmatch(r'Vlan\d+', name) else 'Loopback' if re.fullmatch(r'Loopback\d+', name) else 'Other'
                scope, context = name, 'interface'
                item.scope = name
                parsed('interface', [kind, name])
                if name in interfaces:
                    item.status, item.render_supported = 'BLOCKED', False
                else:
                    ir.interfaces.append(SwitchInterface(name=name, kind=kind, line=number))
                    interfaces.add(name)
                if kind in {'Other', 'Loopback'}:
                    item.status, item.render_supported = 'UNSUPPORTED', False
                    unsupported_interfaces.add(name)
                if kind == 'SVI':
                    item.dependencies = ['vlan:' + str(int(name[4:]))]
            elif context == 'global' and (match := re.fullmatch(r'vlan (\d+)', command)):
                value = str(vlan_list(match[1])[0])
                scope, context = 'vlan:' + value, 'vlan'
                item.scope = scope
                parsed('vlan', [value])
            elif context == 'global' and (match := re.fullmatch(r'ip access-list extended (' + IDENTIFIER + ')', command)):
                scope, context = 'acl:' + match[1], 'acl'
                item.scope = scope
                parsed('acl', [match[1]])
            elif context == 'vlan' and (match := re.fullmatch(r'name (' + IDENTIFIER + ')', command)):
                if len(match[1]) > 32:
                    raise ValueError('VLAN name length')
                parsed('name', [match[1]])
            elif context == 'acl' and (match := re.fullmatch(r'(?:(\d+) )?(permit|deny) ip any any', command)):
                previous = [s for s in ir.statements[:-1] if s.scope == scope and s.feature == 'acl_rule']
                seq = int(match[1]) if match[1] else (int(previous[-1].values[0]) + 10 if previous else 10)
                if not 1 <= seq <= 4294967295:
                    raise ValueError('ACL sequence')
                parsed('acl_rule', [str(seq), match[2]])
            elif context == 'global':
                if match := re.fullmatch(r'hostname (' + IDENTIFIER + ')', command):
                    if len(match[1]) > 32:
                        raise ValueError('hostname length')
                    parsed('hostname', [match[1]])
                elif match := re.fullmatch(r'version (\d+\.\d+(?:\.\d+)?)', command):
                    parsed('source_version', [match[1]])
                    item.status = 'PRESERVED'
                elif command == 'aaa authentication login default local':
                    parsed('aaa_local')
                elif command == 'aaa new-model':
                    parsed('aaa_enabled')
                    item.status = 'PRESERVED'
                elif command == 'lldp run':
                    parsed('lldp')
                elif match := re.fullmatch(r'ip route (\S+) (\S+) (\S+)', command):
                    destination = str(ipaddress.IPv4Network(f'{match[1]}/{match[2]}', strict=True))
                    hop = str(ipaddress.IPv4Address(match[3]))
                    parsed('route', [destination, hop], ['next-hop:' + hop])
                elif command == 'spanning-tree mode rapid-pvst':
                    parsed('stp_mode', ['rapid-pvst'])
                elif match := re.fullmatch(r'spanning-tree vlan ([\d,-]+) priority (\d+)', command):
                    priority = int(match[2])
                    if priority % 4096 or not 0 <= priority <= 61440:
                        raise ValueError('STP priority')
                    ids = [str(v) for v in vlan_list(match[1])]
                    if len(ids) > 256:
                        raise ValueError('VLAN expansion limit')
                    parsed('stp_priority', [str(priority // 4096), *ids], ['vlan:' + v for v in ids])
                elif match := re.fullmatch(r'ntp server (\d+\.\d+\.\d+\.\d+)', command):
                    parsed('ntp', [str(ipaddress.IPv4Address(match[1]))])
                elif command == 'ip routing':
                    parsed('routing_enabled')
                    item.status = 'PRESERVED'
                elif match := re.fullmatch(r'ip domain[- ]name (' + IDENTIFIER + ')', command):
                    item.feature, item.values = 'domain', [match[1]]
                elif command.startswith('ip name-server '):
                    item.feature = 'dns'
                    item.values = [str(ipaddress.ip_address(v)) for v in command[15:].split()]
                elif match := re.fullmatch(r'logging (?:host )?(\d+\.\d+\.\d+\.\d+)', command):
                    item.feature, item.values = 'logging', [str(ipaddress.IPv4Address(match[1]))]
                elif match := re.fullmatch(r'ip default-gateway (\S+)', command):
                    item.feature, item.values = 'management_gateway', [str(ipaddress.IPv4Address(match[1]))]
                else:
                    item.feature = next((name for prefix, name in [('ip domain', 'domain'), ('ip name-server', 'dns'), ('logging', 'logging'), ('ntp', 'ntp'), ('snmp', 'snmp'), ('aaa', 'aaa'), ('router ', 'dynamic_routing'), ('line ', 'management'), ('ip dhcp snooping', 'dhcp_snooping'), ('spanning-tree', 'stp')] if command.startswith(prefix)), 'unknown')
                    if command.startswith(('router ', 'line ', 'ip access-list ', 'vlan ', 'spanning-tree mst configuration')):
                        scope, context = f'unsupported:{number}', 'unsupported'
                        item.values = command.split()[1:]
            elif context == 'unsupported':
                if match := re.fullmatch(r'access-class (' + IDENTIFIER + r') (in|out)', command):
                    item.feature, item.values, item.dependencies = 'management_acl', [match[1], match[2]], ['acl:' + match[1]]
            elif context == 'interface':
                if command.startswith('description ') and len(command) <= 255 and not any(c in command for c in ';"\\'):
                    parsed('description', [command[12:]])
                elif command in {'shutdown', 'no shutdown'}:
                    parsed('admin', ['down' if command == 'shutdown' else 'up'])
                elif command in {'switchport mode access', 'switchport mode trunk', 'no switchport'}:
                    parsed('mode', ['routed' if command == 'no switchport' else command.split()[-1]])
                elif match := re.fullmatch(r'switchport (access vlan|trunk native vlan|trunk allowed vlan) ([\d,-]+)', command):
                    ids = [str(v) for v in vlan_list(match[2])]
                    if len(ids) > 256:
                        raise ValueError('VLAN expansion limit')
                    feature = {'access vlan': 'access_vlan', 'trunk native vlan': 'native_vlan', 'trunk allowed vlan': 'allowed_vlans'}[match[1]]
                    if feature != 'allowed_vlans' and len(ids) != 1:
                        raise ValueError('VLAN cardinality')
                    parsed(feature, ids, ['vlan:' + v for v in ids])
                elif match := re.fullmatch(r'channel-group (\d+) mode (active|passive|on)', command):
                    if not 1 <= int(match[1]) <= 256:
                        raise ValueError('LAG range')
                    parsed('lag_member', [str(int(match[1])), match[2]], ['Port-channel' + str(int(match[1]))])
                elif match := re.fullmatch(r'ip address (\S+) (\S+)', command):
                    parsed('address', [str(ipaddress.IPv4Interface(f'{match[1]}/{match[2]}'))])
                elif command == 'spanning-tree portfast':
                    parsed('edge', dependencies=['stp:global'])
                elif command == 'spanning-tree bpduguard enable':
                    parsed('bpdu_guard', dependencies=['stp:global'])
                elif match := re.fullmatch(r'ip access-group (' + IDENTIFIER + r') (in|out)', command):
                    parsed('acl_attachment', [match[1], match[2]], ['acl:' + match[1]])
                else:
                    item.feature = next((name for prefix, name in [('ip dhcp snooping', 'dhcp_snooping'), ('spanning-tree', 'stp'), ('switchport', 'switchport'), ('ip ', 'layer3')] if command.startswith(prefix)), 'unknown')
            if item.render_supported:
                key = (item.scope, item.feature)
                if item.feature in {'route', 'ntp', 'acl_rule', 'stp_priority'}:
                    key = (item.scope, item.feature + ':' + (item.values[0] if item.values else ''))
                if key in seen:
                    item.status, item.render_supported = 'BLOCKED', False
                seen[key] = item.values
            if item.scope in unsupported_interfaces and item.feature != 'interface':
                item.status, item.render_supported = 'UNSUPPORTED', False
        except (ValueError, IndexError):
            item.feature, item.values, item.dependencies = 'malformed', [], []
            item.status, item.render_supported = 'BLOCKED', False
    return ir
