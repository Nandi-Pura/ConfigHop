"""Limited IOS XE 17.12 -> AOS-CX 10.15 semantic migration."""
from collections import Counter, defaultdict
from hashlib import sha256
from ipaddress import IPv4Address, IPv4Interface
import re

from .hardware.switch import JL663A
from .models.switch_migration import SwitchCandidate, SwitchDependency, SwitchFinding, SwitchMigrationIR


def render_switch(ir: SwitchMigrationIR, mappings: dict[str, int], target_version: str,
                  capability_id: str | None = None) -> SwitchCandidate:
    report = [s.model_copy(deep=True) for s in ir.statements]
    findings: list[SwitchFinding] = []
    dependencies: list[SwitchDependency] = []

    def finding(code, message, scope='global', line=None, severity='BLOCKED'):
        findings.append(SwitchFinding(code=code, message=message, scope=scope, line=line, severity=severity))

    compatible = bool(re.fullmatch(r'17\.12(?:\.\d+)?', ir.source_version) and re.fullmatch(r'10\.15(?:\.\d+)?', target_version))
    if not compatible:
        finding('OS_VERSION_UNVERIFIED', 'Only IOS XE 17.12 to AOS-CX 10.15 is covered by this limited adapter.')
    for s in report:
        if s.feature == 'source_version' and '.'.join(s.values[0].split('.')[:2]) != '.'.join(ir.source_version.split('.')[:2]):
            finding('SOURCE_VERSION_MISMATCH', 'The source version declaration differs from the selected train.', line=s.line)
        if not s.render_supported:
            finding('SOURCE_' + s.status, f'Line {s.line}: {s.feature} is not safely translated; inspect the redacted translation report.', s.scope, s.line)
    physical = {i.name for i in ir.interfaces if i.kind == 'Physical'}
    counts = Counter(mappings.values())
    resolved = {}
    if capability_id != JL663A.id:
        finding('TARGET_CAPABILITY_REQUIRED', 'Select the exact JL663A standalone capability context to resolve physical ports and capacity.')
    for name, slot in sorted(mappings.items()):
        if name not in physical or type(slot) is not int or not 1 <= slot <= 48:
            finding('INVALID_MAPPING', 'Only parsed physical interfaces and integer slots 1–48 are eligible.', name)
        elif counts[slot] > 1:
            finding('DUPLICATE_TARGET', 'Each target slot must have one source owner.', name)
        elif capability_id == JL663A.id:
            # Logical slots resolve against the existing exact-SKU inventory, never an OS naming guess.
            port = JL663A.interfaces[slot - 1]
            resolved[name] = port.name
    groups = defaultdict(list)
    for s in report:
        groups[s.scope].append(s)
    valid = lambda scope: {s.feature: s.values for s in groups[scope] if s.render_supported}
    scopes = {s.scope for s in report if s.feature in {'vlan', 'acl', 'interface'} and s.render_supported}
    if 'stp_mode' in valid('global'):
        scopes.add('stp:global')
        for scope in sorted(s for s in scopes if s.startswith('vlan:')):
            dependencies.append(SwitchDependency(source='stp:global', target=scope, relation='stp_vlan', line=next(s.line for s in report if s.feature == 'stp_mode'), resolved=True))
    kinds = {i.name: i.kind for i in ir.interfaces}
    active = set(resolved) | {i.name for i in ir.interfaces if i.kind in {'LAG', 'SVI'}}
    members = defaultdict(list)
    for name in kinds:
        f = valid(name)
        if 'lag_member' in f:
            members['Port-channel' + f['lag_member'][0]].append(name)
    for lag, names in members.items():
        for name in names:
            ok = name in resolved and lag in scopes
            dependencies.append(SwitchDependency(source=lag, target=name, relation='lag_member', line=next(i.line for i in ir.interfaces if i.name == name), resolved=ok))
            if not ok:
                finding('LAG_MEMBER_UNRESOLVED', 'Every LAG member must be mapped and its Port-channel declared.', lag)
        modes = {valid(name)['lag_member'][1] for name in names}
        if len(modes) > 1:
            finding('LAG_MODE_CONFLICT', 'LAG members have different aggregation modes.', lag)
    for name in sorted(physical - set(mappings)):
        finding('UNMAPPED_INTERFACE', 'Unmapped source interface omitted; review its intended disposition.', name, severity='REVIEW_REQUIRED')
    addresses = [(name, IPv4Interface(values['address'][0])) for name in active if 'address' in (values := valid(name))]
    for s in report:
        for target in s.dependencies:
            if target.startswith('next-hop:'):
                hop = IPv4Address(target.split(':', 1)[1])
                contexts = [name for name, address in addresses if hop in address.network and hop != address.ip and valid(name).get('admin') == ['up']]
                ok = bool(contexts) and all(hop != address.ip for _, address in addresses)
                for name in contexts:
                    dependencies.append(SwitchDependency(source=f'route:{s.line}', target=name, relation='route_egress', line=s.line, resolved=True))
            else:
                ok = target in scopes and (target not in physical or target in resolved)
                if target.startswith('acl:') and any(not item.render_supported for item in groups[target]):
                    ok = False
            dependencies.append(SwitchDependency(source=s.scope if s.feature != 'route' else f'route:{s.line}', target=target, relation=s.feature, line=s.line, resolved=ok))
            if not ok:
                finding('DEPENDENCY_UNRESOLVED', f'Line {s.line}: required {target} is missing or unresolved.', s.scope, s.line)
    global_features = valid('global')
    if 'aaa_local' in global_features:
        finding('AAA_ACCOUNT_REENTRY', 'Local authentication requires an independently provisioned target account and tested console access.', severity='REVIEW_REQUIRED')
    for name in sorted(active):
        f = valid(name)
        kind = kinds[name]
        if 'admin' not in f:
            finding('ADMIN_STATE_UNRESOLVED', 'Explicit shutdown/no shutdown is required; source and target defaults are not assumed.', name)
        if kind == 'LAG' and not members[name]:
            finding('EMPTY_LAG', 'Declared Port-channel has no configured physical members.', name)
        if kind == 'SVI':
            if not 1 <= int(name[4:]) <= 4094:
                finding('INVALID_SVI', 'SVI identifier is outside VLAN range.', name)
        elif 'lag_member' not in f:
            mode = f.get('mode', ['unknown'])[0]
            required = {'access': ['access_vlan'], 'trunk': ['native_vlan', 'allowed_vlans'], 'routed': []}.get(mode)
            if required is None or any(key not in f for key in required):
                finding('INTERFACE_MODE_INCOMPLETE', 'Explicit access VLAN, trunk native/allowed VLANs, or routed mode is required.', name)
        mode = f.get('mode', [''])[0]
        if (mode == 'access' and any(k in f for k in ('native_vlan', 'allowed_vlans'))) or (mode == 'trunk' and 'access_vlan' in f):
            finding('SWITCHPORT_MODE_CONFLICT', 'VLAN attributes do not agree with the explicit switchport mode.', name)
        if ('address' in f and mode in {'access', 'trunk'}) or (mode == 'routed' and any(k in f for k in ('access_vlan', 'native_vlan', 'allowed_vlans'))):
            finding('L2_L3_CONFLICT', 'Interface has conflicting Layer 2 and Layer 3 declarations.', name)
        if kind == 'SVI' and any(k in f for k in ('mode', 'lag_member', 'access_vlan', 'native_vlan', 'allowed_vlans', 'edge', 'bpdu_guard')):
            finding('INVALID_SVI_FEATURE', 'Physical switching features cannot be applied to an SVI.', name)
        if 'lag_member' in f:
            if kind != 'Physical':
                finding('INVALID_LAG_MEMBER', 'Only physical interfaces may join a LAG.', name)
            lag = 'Port-channel' + f['lag_member'][0]
            lf = valid(lag)
            for key in ('mode', 'access_vlan', 'native_vlan', 'allowed_vlans'):
                if key in f and f[key] != lf.get(key):
                    finding('LAG_FEATURE_CONFLICT', 'Member switching settings must agree with the Port-channel.', name)
            if any(key in f for key in ('address', 'acl_attachment', 'edge', 'bpdu_guard')):
                finding('LAG_MEMBER_FEATURE', 'Member Layer 3/security/STP settings require manual reconciliation.', name)
        if 'acl_attachment' in f and (mode != 'routed' and kind != 'SVI' or f['acl_attachment'][1] != 'in'):
            finding('ACL_ATTACHMENT_UNSUPPORTED', 'Only inbound routed IPv4 ACL attachment is supported.', name)
        if any(key in f for key in ('edge', 'bpdu_guard')) and (mode != 'access' or 'stp_mode' not in global_features):
            finding('STP_SCOPE_UNRESOLVED', 'Edge/BPDU protection requires an explicit access port and supported global STP mode.', name)
    for scope in scopes:
        if scope.startswith('acl:') and not any(s.feature == 'acl_rule' for s in groups[scope]):
            finding('EMPTY_ACL', 'An ACL definition must contain supported rules.', scope)
    if 'stp_priority' in global_features and 'stp_mode' not in global_features:
        finding('STP_MODE_REQUIRED', 'Per-VLAN priorities require explicit rapid-pvst mode.')
        for statement in report:
            if statement.feature == 'stp_priority':
                statement.status, statement.render_supported = 'BLOCKED', False
    if 'aaa_enabled' in global_features and 'aaa_local' not in global_features:
        finding('AAA_METHOD_UNSUPPORTED', 'AAA is enabled without the supported local default login method.')
        for statement in report:
            if statement.feature == 'aaa_enabled':
                statement.status = 'BLOCKED'
    if any('address' in valid(name) for name in active) and 'routing_enabled' not in global_features:
        finding('ROUTING_DEFAULT_REVIEW', 'Target routing defaults differ; verify intended forwarding and management reachability.', severity='REVIEW_REQUIRED')
    finding('DEPLOYMENT_REVIEW', 'Limited syntax translation only. Verify target baseline, firmware patch, cabling, resource limits and management access in a lab before deployment.', severity='REVIEW_REQUIRED')

    lines = ['! ConfigHop limited IOS XE 17.12 -> AOS-CX 10.15 candidate', '! Review findings before deployment; no device validation performed.']
    if compatible:
        if 'hostname' in global_features:
            lines.append('hostname ' + global_features['hostname'][0])
        for scope in sorted((s for s in scopes if s.startswith('vlan:')), key=lambda s: int(s[5:])):
            lines.append('vlan ' + scope[5:])
            if 'name' in valid(scope):
                lines.append('    name ' + valid(scope)['name'][0])
            lines.append('exit')
        if 'stp_mode' in global_features:
            lines += ['spanning-tree mode rpvst', 'spanning-tree']
            vlans = sorted(int(s[5:]) for s in scopes if s.startswith('vlan:'))
            if vlans:
                lines.append('spanning-tree vlan ' + ','.join(map(str, vlans)))
            for s in sorted((s for s in report if s.feature == 'stp_priority' and s.render_supported), key=lambda s: s.values):
                lines.append('spanning-tree vlan ' + ','.join(s.values[1:]) + ' priority ' + s.values[0])
        if 'lldp' in global_features:
            lines.append('lldp')
        if 'aaa_local' in global_features:
            lines.append('aaa authentication login default local')
        ntp = sorted(s.values[0] for s in report if s.feature == 'ntp' and s.render_supported)
        if ntp:
            lines.extend('ntp server ' + host for host in ntp)
            lines.append('ntp enable')
        for scope in sorted(s for s in scopes if s.startswith('acl:')):
            if any(not s.render_supported for s in groups[scope]):
                continue
            lines.append('access-list ip ' + scope[4:])
            for s in sorted((s for s in groups[scope] if s.feature == 'acl_rule'), key=lambda s: int(s.values[0])):
                lines.append(f'    {s.values[0]} {s.values[1]} any any any')
            lines.append('exit')
        for name in sorted(active, key=lambda n: (0 if kinds[n] == 'LAG' else 1 if kinds[n] == 'SVI' else 2, resolved.get(n, n))):
            f = valid(name)
            if any(x.severity == 'BLOCKED' and x.scope == name for x in findings):
                continue
            target = resolved.get(name) or ('lag ' + name[12:] if kinds[name] == 'LAG' else 'vlan ' + name[4:])
            lines.append('interface ' + target)
            if 'description' in f:
                lines.append('    description ' + f['description'][0])
            if 'admin' in f:
                lines.append('    shutdown' if f['admin'] == ['down'] else '    no shutdown')
            if 'lag_member' in f:
                lines.append('    lag ' + f['lag_member'][0])
            else:
                mode = f.get('mode', [''])[0]
                if mode in {'access', 'trunk'}:
                    lines.append('    no routing')
                elif mode == 'routed':
                    lines.append('    routing')
                if mode == 'access' and 'access_vlan' in f:
                    lines.append('    vlan access ' + f['access_vlan'][0])
                if mode == 'trunk':
                    if 'native_vlan' in f:
                        lines.append('    vlan trunk native ' + f['native_vlan'][0])
                    if 'allowed_vlans' in f:
                        lines.append('    vlan trunk allowed ' + ','.join(f['allowed_vlans']))
                if kinds[name] == 'LAG' and members[name]:
                    mode = valid(members[name][0])['lag_member'][1]
                    if mode != 'on':
                        lines.append('    lacp mode ' + mode)
                if 'address' in f:
                    lines.append('    ip address ' + f['address'][0])
                if 'edge' in f:
                    lines.append('    spanning-tree port-type admin-edge')
                if 'bpdu_guard' in f:
                    lines.append('    spanning-tree bpdu-guard')
                if 'acl_attachment' in f:
                    direction = 'routed-in' if kinds[name] == 'SVI' else 'in'
                    lines.append('    apply access-list ip ' + f['acl_attachment'][0] + ' ' + direction)
            lines.append('exit')
        for s in sorted((s for s in report if s.feature == 'route' and s.render_supported), key=lambda s: s.values):
            if not any(f.line == s.line and f.severity == 'BLOCKED' for f in findings):
                lines.append('ip route ' + ' '.join(s.values))
    blocked_scopes = {f.scope for f in findings if f.severity == 'BLOCKED' and f.scope != 'global'}
    blocked_lines = {f.line for f in findings if f.severity == 'BLOCKED' and f.line is not None}
    for s in report:
        if s.render_supported and (not compatible or s.scope in blocked_scopes or s.line in blocked_lines):
            s.status = 'BLOCKED'
        elif s.scope in physical and s.scope not in resolved and s.render_supported:
            s.status = 'REVIEW_REQUIRED'
    text = '\n'.join(lines) + '\n'
    declarations = [line for line in lines if re.fullmatch(r'(?:interface .+|vlan \d+|access-list ip .+)', line)]
    if len(declarations) != len(set(declarations)):
        finding('CANDIDATE_DUPLICATE_DECLARATION', 'Generated candidate contains duplicate object declarations.')
    return SwitchCandidate(text=text, sha256=sha256(text.encode()).hexdigest(),
        status='BLOCKED' if any(f.severity == 'BLOCKED' for f in findings) else 'REVIEW_REQUIRED',
        findings=findings, dependencies=dependencies, report=report, coverage=dict(Counter(s.status for s in report)),
        resolved_interfaces=resolved, syntax_compatible=compatible, hardware_context=capability_id)
