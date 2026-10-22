"""Bounded AOS-CX running-config parser for Switch migration."""
import ipaddress
import re

from ...models.switch_migration import SwitchInterface, SwitchMigrationIR, SwitchStatement
from ..switch_common import vlan_list
from ..cisco_iosxe.migration import MAX_SWITCH_BYTES

PORT = re.compile(r'[1-9]\d*/[1-9]\d*/[1-9]\d*')
IDENT = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}')
SECRET = re.compile(r'\b(password|secret|key|ciphertext|encrypted|hash|community|certificate)\b', re.I)


def parse_aruba_migration(text: str, version: str) -> SwitchMigrationIR:
    if len(text.encode('utf-8')) > MAX_SWITCH_BYTES or len(text.splitlines()) > 20000:
        raise ValueError('Source exceeds limits.')
    if not text.strip() or any(ord(c) < 32 and c not in '\r\n\t' for c in text) or text.lstrip().startswith(('<', '{')):
        raise ValueError('Expected plain-text AOS-CX running configuration.')
    ir = SwitchMigrationIR(source_os='AOS_CX', source_version=version)
    scope = 'global'
    seen: set[tuple[str, str]] = set()
    interfaces: set[str] = set()
    banner_end: str | None = None
    for line, raw in enumerate(text.splitlines(), 1):
        cmd = raw.strip()
        if not cmd or cmd == '!':
            if cmd == '!':
                scope = 'global'
            continue
        if cmd.startswith('!'):
            if match := re.fullmatch(r'!\s*Version\s*:\s*(?:[A-Z]{1,3}\.)?(10\.\d+(?:\.\d+)?)', cmd, re.I):
                ir.statements.append(SwitchStatement(line=line, source=cmd, feature='source_version', values=[match[1]], status='PRESERVED'))
            continue
        if banner_end:
            ir.statements.append(SwitchStatement(line=line, source='[REDACTED banner]', scope='global', feature='banner', status='MANUAL_REQUIRED', render_supported=False))
            if cmd == banner_end:
                banner_end = None
            continue
        if cmd.lower().startswith(('show ', 'switch#', 'switch>', 'interface statistics', 'port statistics')):
            raise ValueError('Operational transcript is not a running configuration.')
        if not raw[0].isspace():
            scope = 'global'
        safe = '[REDACTED sensitive statement]' if SECRET.search(cmd) or cmd.startswith(('user ', 'tacacs-server ', 'radius-server ', 'snmp-server ')) else cmd
        item = SwitchStatement(line=line, source=safe, scope=scope, feature='unknown', status='UNSUPPORTED', render_supported=False)
        ir.statements.append(item)

        def parsed(feature: str, values: list[str] | None = None, deps: list[str] | None = None):
            item.feature, item.values, item.dependencies = feature, values or [], deps or []
            item.status, item.render_supported = 'TRANSLATED', True

        def manual(feature: str, values: list[str] | None = None):
            item.feature, item.values = feature, values or []
            item.status = 'MANUAL_REQUIRED'

        try:
            if cmd.startswith('banner motd '):
                manual('banner')
                banner_end = cmd[12:]
                if not banner_end or len(banner_end) > 8:
                    raise ValueError('banner delimiter')
            elif safe != cmd:
                manual('secret_reentry')
            elif cmd.startswith(('vsf ', 'vsx ', 'stack ', 'member ', 'link ')):
                manual('stacking')
            elif cmd.startswith('interface '):
                name = cmd[10:]
                kind = 'Physical' if PORT.fullmatch(name) else 'LAG' if re.fullmatch(r'lag ([1-9]\d*)', name) else 'SVI' if re.fullmatch(r'vlan ([1-9]\d*)', name) else 'Other'
                if kind == 'LAG' and not 1 <= int(name[4:]) <= 256:
                    raise ValueError('LAG range')
                if kind == 'SVI':
                    vlan_list(name[5:])
                canonical = 'Port-channel' + name[4:] if kind == 'LAG' else 'Vlan' + name[5:] if kind == 'SVI' else name
                scope = canonical
                item.scope = scope
                parsed('interface', [kind, canonical])
                if canonical in interfaces or kind == 'Other':
                    item.status, item.render_supported = 'BLOCKED', False
                else:
                    interfaces.add(canonical)
                    ir.interfaces.append(SwitchInterface(name=canonical, kind=kind, line=line))
                if kind == 'SVI':
                    item.dependencies = ['vlan:' + name[5:]]
            elif match := re.fullmatch(r'vlan (\d+)', cmd):
                vlan = str(vlan_list(match[1])[0])
                scope = 'vlan:' + vlan
                item.scope = scope
                parsed('vlan', [vlan])
            elif scope.startswith('vlan:') and cmd.startswith('name '):
                name = cmd[5:]
                if len(name) > 32 or any(c in name for c in '\r\n;"\\'):
                    raise ValueError('VLAN name')
                parsed('name', [name])
            elif scope == 'global':
                if match := re.fullmatch(r'!?(?:AOS-CX|ArubaOS-CX|version)\s+(10\.\d+(?:\.\d+)?)', cmd, re.I):
                    parsed('source_version', [match[1]])
                    item.status = 'PRESERVED'
                elif cmd.startswith('hostname ') and IDENT.fullmatch(cmd[9:]) and len(cmd[9:]) <= 32:
                    parsed('hostname', [cmd[9:]])
                elif cmd == 'spanning-tree mode rpvst':
                    parsed('stp_mode', ['rapid-pvst'])
                elif cmd == 'spanning-tree':
                    parsed('stp_enabled')
                elif match := re.fullmatch(r'spanning-tree vlan ([\d,-]+)', cmd):
                    ids = [str(v) for v in vlan_list(match[1])]
                    if len(ids) > 256:
                        raise ValueError('VLAN expansion')
                    parsed('stp_vlans', ids, ['vlan:' + v for v in ids])
                elif match := re.fullmatch(r'ip route (\S+) (\S+)', cmd):
                    net = str(ipaddress.IPv4Network(match[1], strict=True))
                    hop = str(ipaddress.IPv4Address(match[2]))
                    parsed('route', [net, hop], ['next-hop:' + hop])
                elif match := re.fullmatch(r'ntp server (\d+\.\d+\.\d+\.\d+)', cmd):
                    parsed('ntp', [str(ipaddress.IPv4Address(match[1]))])
                elif cmd.startswith(('ip dns server-address ', 'ip name-server ')):
                    address = cmd.split()[-1]
                    parsed('dns', [str(ipaddress.IPv4Address(address))])
                elif match := re.fullmatch(r'logging (?:host )?(\d+\.\d+\.\d+\.\d+)', cmd):
                    parsed('syslog', [str(ipaddress.IPv4Address(match[1]))])
                elif cmd.startswith('clock timezone '):
                    manual('timezone', [cmd[15:]])
                elif cmd.startswith(('user ', 'tacacs-server ', 'radius-server ', 'aaa ', 'ssh ', 'https-server ', 'https ')):
                    manual('management_security')
                elif cmd.startswith('dhcpv4-snooping'):
                    item.feature = 'dhcp_snooping'
                elif cmd.startswith(('vsf', 'vsx')):
                    manual('stacking')
            elif scope in interfaces:
                if cmd.startswith('description ') and len(cmd) <= 255 and not any(c in cmd for c in ';"\\<>'):
                    parsed('description', [cmd[12:]])
                elif cmd in {'shutdown', 'no shutdown'}:
                    parsed('admin', ['down' if cmd == 'shutdown' else 'up'])
                elif cmd == 'no routing':
                    parsed('switching')
                elif cmd == 'routing':
                    parsed('mode', ['routed'])
                elif match := re.fullmatch(r'vlan access (\d+)', cmd):
                    vlan = str(vlan_list(match[1])[0])
                    parsed('access_vlan', [vlan], ['vlan:' + vlan])
                elif match := re.fullmatch(r'vlan trunk native (\d+)', cmd):
                    vlan = str(vlan_list(match[1])[0])
                    parsed('native_vlan', [vlan], ['vlan:' + vlan])
                elif match := re.fullmatch(r'vlan trunk allowed (all|[\d,-]+)', cmd):
                    ids = ['all'] if match[1] == 'all' else [str(v) for v in vlan_list(match[1])]
                    if len(ids) > 256:
                        raise ValueError('VLAN expansion')
                    parsed('allowed_vlans', ids, [] if ids == ['all'] else ['vlan:' + v for v in ids])
                elif match := re.fullmatch(r'lag ([1-9]\d*)', cmd):
                    if not 1 <= int(match[1]) <= 256:
                        raise ValueError('LAG range')
                    parsed('lag_member', [match[1]], ['Port-channel' + match[1]])
                elif cmd in {'lacp mode active', 'lacp mode passive'}:
                    parsed('lacp_mode', [cmd.split()[-1]])
                elif match := re.fullmatch(r'ip address (\S+)', cmd):
                    parsed('address', [str(ipaddress.IPv4Interface(match[1]))])
                elif cmd == 'ip dhcp':
                    manual('dhcp_client')
                elif cmd.startswith(('vsf ', 'vsx ')):
                    manual('stacking')
            if item.render_supported:
                key = (item.scope, item.feature)
                if item.feature in {'ntp', 'dns', 'syslog', 'route'}:
                    key += (item.values[0],)
                if key in seen:
                    item.status, item.render_supported = 'BLOCKED', False
                seen.add(key)
        except (ValueError, IndexError, ipaddress.AddressValueError):
            item.feature, item.values, item.dependencies = 'malformed', [], []
            item.status, item.render_supported = 'BLOCKED', False
    if banner_end:
        ir.statements.append(SwitchStatement(line=len(text.splitlines()), source='[REDACTED incomplete banner]', feature='banner', status='BLOCKED', render_supported=False))
    return ir
