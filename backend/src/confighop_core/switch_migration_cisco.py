"""Bounded AOS-CX 10.13 to IOS XE 17.18 semantic renderer."""
from collections import Counter, defaultdict
from hashlib import sha256
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
import re

from .models.switch_migration import SwitchCandidate, SwitchCoverage, SwitchDependency, SwitchFinding, SwitchMigrationIR
from .parsers.cisco_iosxe.migration import PHYSICAL, interface_name


def render_cisco(ir: SwitchMigrationIR, mappings: dict[str, str | int], target_version: str,
                 capability_id: str | None = None) -> SwitchCandidate:
    report = [s.model_copy(deep=True) for s in ir.statements]
    findings: list[SwitchFinding] = []
    dependencies: list[SwitchDependency] = []

    def finding(code: str, message: str, scope='global', line=None, severity='BLOCKED'):
        findings.append(SwitchFinding(code=code, message=message, scope=scope, line=line, severity=severity))

    compatible = ir.source_os == 'AOS_CX' and re.fullmatch(r'10\.13(?:\.\d+)?', ir.source_version) and re.fullmatch(r'17\.18(?:\.\d+)?', target_version)
    if not compatible:
        finding('OS_PAIR_UNSUPPORTED', 'Only the bounded AOS-CX 10.13 to IOS XE 17.18 reverse path is implemented.')
    if capability_id:
        finding('TARGET_HARDWARE_UNSUPPORTED', 'The Aruba capability profile cannot validate a Cisco target.')
    grouped: dict[str, list] = defaultdict(list)
    for s in report:
        grouped[s.scope].append(s)
        if s.feature == 'source_version' and '.'.join(s.values[0].split('.')[:2]) != '.'.join(ir.source_version.split('.')[:2]):
            finding('SOURCE_VERSION_MISMATCH', 'Configuration release differs from selected source train.', s.scope, s.line)
        if not s.render_supported:
            code = 'MANUAL_STACKING' if s.feature == 'stacking' else 'SOURCE_' + s.status
            finding(code, f'Line {s.line}: {s.feature} requires separate engineering review; see the redacted report.', s.scope, s.line)
    physical = {i.name for i in ir.interfaces if i.kind == 'Physical'}
    kinds = {i.name: i.kind for i in ir.interfaces}
    resolved: dict[str, str] = {}
    for source, target in sorted(mappings.items()):
        match = PHYSICAL.fullmatch(target) if isinstance(target, str) else None
        numbers = match[2].split('/') if match else []
        if source not in physical or len(numbers) != 3 or any(n != str(int(n)) for n in numbers) or int(numbers[0]) < 1 or int(numbers[2]) < 1:
            finding('INVALID_MAPPING', 'Map a parsed physical source to an explicit IOS XE physical interface.', source)
        else:
            resolved[source] = interface_name(target)
    target_counts = Counter(resolved.values())
    for source, target in resolved.items():
        if target_counts[target] > 1:
            finding('DUPLICATE_TARGET', 'Target interface has multiple source owners.', source)
    if resolved:
        finding('PORT_EXISTENCE_NOT_VERIFIED', 'IOS XE naming grammar does not verify physical port existence.', severity='REVIEW_REQUIRED')
    for source in sorted(physical - resolved.keys()):
        finding('UNMAPPED_INTERFACE', 'Map this physical source before validated export.', source)

    def values(scope):
        return {s.feature: s.values for s in grouped[scope] if s.render_supported}

    vlans = {s.scope for s in report if s.feature == 'vlan' and s.render_supported}
    lags = {i.name for i in ir.interfaces if i.kind == 'LAG'}
    members: dict[str, list[str]] = defaultdict(list)
    for source in sorted(physical):
        f = values(source)
        if 'lag_member' in f:
            lag = 'Port-channel' + f['lag_member'][0]
            members[lag].append(source)
            ok = lag in lags and source in resolved
            dependencies.append(SwitchDependency(source=source, target=lag, relation='lag_member', line=next(i.line for i in ir.interfaces if i.name == source), resolved=ok))
            if not ok:
                finding('LAG_MEMBER_UNRESOLVED', 'LAG and every physical member require explicit declarations and mappings.', source)
    for lag in sorted(lags):
        if not members[lag]:
            finding('EMPTY_LAG', 'LAG has no declared physical members.', lag)
        if 'lacp_mode' not in values(lag):
            finding('LACP_MODE_REQUIRED', 'An explicit LACP mode is required for a translated LAG.', lag)
            for member in members[lag]:
                finding('LACP_MODE_REQUIRED', 'The member cannot be rendered without its LAG LACP mode.', member)
    for s in report:
        for target in s.dependencies:
            if target.startswith('next-hop:'):
                hop = IPv4Address(target[9:])
                connected = [IPv4Interface(t.values[0]) for t in report if t.feature == 'address' and t.render_supported]
                ok = any(hop in addr.network and hop != addr.ip for addr in connected)
            else:
                ok = target in vlans or target in lags
            dependencies.append(SwitchDependency(source=s.scope, target=target, relation=s.feature, line=s.line, resolved=ok))
            if not ok:
                finding('DEPENDENCY_UNRESOLVED', f'Line {s.line}: required {target} is unresolved.', s.scope, s.line)
    for scope in sorted(physical | lags | {i.name for i in ir.interfaces if i.kind == 'SVI'}):
        f = values(scope)
        if scope in physical and 'lag_member' not in f and not any(key in f for key in ('access_vlan', 'native_vlan', 'allowed_vlans', 'address', 'mode')):
            finding('INTERFACE_MODE_INCOMPLETE', 'Explicit access, trunk, or routed intent is required.', scope)
        if 'access_vlan' in f and ('native_vlan' in f or 'allowed_vlans' in f):
            finding('SWITCHPORT_MODE_CONFLICT', 'Access and trunk settings conflict.', scope)
        if 'native_vlan' in f and 'allowed_vlans' in f and f['allowed_vlans'] != ['all'] and f['native_vlan'][0] not in f['allowed_vlans']:
            finding('TRUNK_NATIVE_NOT_ALLOWED', 'Native VLAN is excluded from the allowed set.', scope)
        if 'lag_member' in f and any(key in f for key in ('access_vlan', 'native_vlan', 'allowed_vlans', 'address')):
            finding('LAG_MEMBER_FEATURE', 'LAG members must inherit switching intent from the logical LAG.', scope)
        if 'lag_member' in f and any(key in f for key in ('mode', 'switching')):
            finding('LAG_MEMBER_MODE_CONFLICT', f'{scope}: physical routing mode conflicts with LAG membership; configure mode on the logical LAG.', scope)
        if 'address' in f and any(key in f for key in ('access_vlan', 'native_vlan', 'allowed_vlans', 'switching')):
            finding('L2_L3_CONFLICT', 'Interface combines routed and switched settings.', scope)
        if f.get('mode') == ['routed'] and any(key in f for key in ('access_vlan', 'native_vlan', 'allowed_vlans', 'switching')):
            finding('L2_L3_CONFLICT', 'Explicit routed mode conflicts with switching settings.', scope)
        if 'admin' not in f:
            finding('ADMIN_STATE_UNRESOLVED', 'Explicit shutdown/no shutdown is required; source and target defaults are not assumed.', scope)
    has_stp_enable = 'stp_enabled' in values('global')
    has_stp_mode = 'stp_mode' in values('global')
    if has_stp_enable and not has_stp_mode:
        finding('STP_MODE_REQUIRED', 'Standalone STP enablement has no verified equivalent without an explicit RPVST mode.')
    if has_stp_mode and not has_stp_enable:
        finding('STP_ENABLEMENT_REQUIRED', 'RPVST mode alone does not establish source STP enablement.')
    if any(s.feature == 'stp_vlans' for s in report) and not has_stp_mode:
        finding('STP_MODE_REQUIRED', 'Explicit RPVST mode is required for VLAN-scoped STP.')
    if has_stp_enable != has_stp_mode or any(s.feature == 'stp_vlans' for s in report) and not has_stp_mode:
        for s in report:
            if s.feature == 'stp_vlans' and set(s.values) != {v[5:] for v in vlans}:
                finding('STP_VLAN_SCOPE_UNRESOLVED', 'Explicit source STP VLAN scope differs from defined VLANs; target default could widen STP.', s.scope, s.line)
            if s.feature in {'stp_enabled', 'stp_mode', 'stp_vlans'} and s.render_supported:
                s.status, s.render_supported = 'BLOCKED', False
    finding('DEPLOYMENT_REVIEW', 'Synthetic subset only; verify configuration on the actual target in a lab.', severity='REVIEW_REQUIRED')
    lines = ['! ConfigHop limited AOS-CX 10.13 -> IOS XE 17.18 candidate', '! Review findings; no device validation performed.'] if compatible else ['! ConfigHop unsupported Switch version pair']
    blocked_scopes = {f.scope for f in findings if f.severity == 'BLOCKED' and f.scope != 'global'}
    if compatible:
        global_values = values('global')
        if 'hostname' in global_values:
            lines.append('hostname ' + global_values['hostname'][0])
        for scope in sorted(vlans, key=lambda v: int(v[5:])):
            lines.append('vlan ' + scope[5:])
            name = values(scope).get('name')
            if name and scope != 'vlan:1':
                normalized = re.sub(r'[^A-Za-z0-9_.-]', '_', name[0]).strip('_')
                if not normalized or len(normalized) > 32:
                    finding('VLAN_NAME_UNSAFE', 'VLAN name cannot be safely normalized.', scope)
                else:
                    lines.append(' name ' + normalized)
                    if normalized != name[0]:
                        finding('VLAN_NAME_NORMALIZED', 'Original VLAN name is retained in the source report; review the target spelling.', scope, severity='REVIEW_REQUIRED')
            elif name:
                finding('DEFAULT_VLAN_NAME_REVIEW', 'Default VLAN 1 name was not copied; review source intent.', scope, severity='REVIEW_REQUIRED')
            lines.append('exit')
        if 'stp_mode' in global_values:
            lines.append('spanning-tree mode rapid-pvst')
        if any(s.feature == 'route' and s.render_supported for s in report):
            lines.append('ip routing')
            finding('ROUTING_MODE_REVIEW', 'IOS XE IP routing is enabled for translated static-route intent; verify target license and forwarding role.', severity='REVIEW_REQUIRED')
        for s in report:
            if s.feature == 'stp_vlans' and s.render_supported and s.scope not in blocked_scopes:
                if set(s.values) != {v[5:] for v in vlans}:
                    finding('STP_VLAN_SCOPE_UNRESOLVED', 'Explicit source STP VLAN scope differs from defined VLANs; target default could widen STP.', s.scope, s.line)
                else:
                    finding('STP_VLAN_SCOPE_REVIEW', 'Verify enabled RPVST VLAN scope on the target; IOS XE global mode has different defaults.', s.scope, s.line, 'REVIEW_REQUIRED')
        for scope in sorted(lags | {i.name for i in ir.interfaces if i.kind == 'SVI'} | set(resolved)):
            if scope in blocked_scopes:
                continue
            kind = kinds[scope]
            f = values(scope)
            target = resolved.get(scope, scope)
            lines.append('interface ' + target)
            if 'description' in f:
                lines.append(' description ' + f['description'][0])
            if 'lag_member' in f:
                lag = 'Port-channel' + f['lag_member'][0]
                lines.append(' channel-group ' + f['lag_member'][0] + ' mode ' + values(lag)['lacp_mode'][0])
            elif kind in {'Physical', 'LAG'}:
                if 'access_vlan' in f:
                    lines += [' switchport mode access', ' switchport access vlan ' + f['access_vlan'][0]]
                elif 'native_vlan' in f or 'allowed_vlans' in f:
                    lines.append(' switchport mode trunk')
                    if 'native_vlan' in f:
                        lines.append(' switchport trunk native vlan ' + f['native_vlan'][0])
                    if 'allowed_vlans' in f:
                        lines.append(' switchport trunk allowed vlan ' + (f['allowed_vlans'][0] if f['allowed_vlans'] == ['all'] else ','.join(f['allowed_vlans'])))
                elif f.get('mode') == ['routed'] or 'address' in f:
                    lines.append(' no switchport')
            if 'address' in f:
                address = IPv4Interface(f['address'][0])
                lines.append(f' ip address {address.ip} {address.netmask}')
            if 'admin' in f:
                lines.append(' shutdown' if f['admin'] == ['down'] else ' no shutdown')
            lines.append('exit')
        for s in sorted((s for s in report if s.feature == 'route' and s.render_supported), key=lambda s: s.values):
            if s.scope not in blocked_scopes and s.line not in {f.line for f in findings if f.severity == 'BLOCKED'}:
                net = IPv4Network(s.values[0])
                lines.append(f'ip route {net.network_address} {net.netmask} {s.values[1]}')
        for s in report:
            if s.feature in {'ntp', 'dns', 'syslog'} and s.render_supported:
                lines.append({'ntp': 'ntp server ', 'dns': 'ip name-server ', 'syslog': 'logging host '}[s.feature] + s.values[0])
    for s in report:
        if s.render_supported and (not compatible or s.scope in blocked_scopes):
            s.status = 'BLOCKED'
        elif s.scope in physical and s.scope not in resolved and s.render_supported:
            s.status = 'BLOCKED'
    text = '\n'.join(lines) + '\n'
    declarations = [line for line in lines if re.fullmatch(r'(?:interface [A-Za-z0-9/.-]+|vlan \d+)', line)]
    if len(declarations) != len(set(declarations)):
        finding('CANDIDATE_DUPLICATE_DECLARATION', 'Generated CLI contains duplicate declarations.')
    blocked = any(f.severity == 'BLOCKED' for f in findings)
    counts = Counter(s.status for s in report)
    summary = SwitchCoverage(source_vendor='HPE Aruba Networking', source_os=ir.source_os, source_version=ir.source_version,
        target_vendor='Cisco', target_os='IOS_XE', target_version=target_version, meaningful_constructs=len(report),
        translated_constructs=counts['TRANSLATED'], preserved_for_review_constructs=counts['PRESERVED'],
        review_required_constructs=counts['REVIEW_REQUIRED'] + counts['MANUAL_REQUIRED'],
        manual_required_constructs=counts['MANUAL_REQUIRED'], unsupported_constructs=counts['UNSUPPORTED'],
        blocked_constructs=counts['BLOCKED'] + counts['UNSUPPORTED'],
        unsupported_feature_families=sorted({s.feature for s in report if not s.render_supported}),
        unresolved_dependencies=sum(not d.resolved for d in dependencies), interface_mapping_complete=physical <= resolved.keys(),
        version_limitations=[] if compatible else ['OS_PAIR_UNSUPPORTED'], hardware_compatibility_status='NOT_VERIFIED',
        output_validation_status='BLOCKED' if blocked else 'CHECKED_SUBSET')
    return SwitchCandidate(text=text, sha256=sha256(text.encode()).hexdigest(), status='BLOCKED' if blocked else 'REVIEW_REQUIRED',
        findings=findings, dependencies=dependencies, report=report, coverage=dict(counts), translation_summary=summary,
        resolved_interfaces=resolved, syntax_compatible=bool(compatible), hardware_context=capability_id)
