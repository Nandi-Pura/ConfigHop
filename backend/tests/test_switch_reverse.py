from fastapi.testclient import TestClient
import pytest

from confighop_api.main import create_app
from confighop_core.parsers.aruba_aoscx.migration import parse_aruba_migration
from confighop_core.switch_migration_cisco import render_cisco


def fixture(critical=False):
    lines = ['version 10.13.1110', 'hostname LAB-CX', 'vlan 1', 'vlan 99', 'vlan 101', ' name LAB_USERS',
             'spanning-tree mode rpvst', 'spanning-tree', 'spanning-tree vlan 1,99,101',
             'interface lag 1', ' no shutdown', ' vlan trunk native 1', ' vlan trunk allowed all', ' lacp mode active']
    for number in range(1, 53):
        lines += [f'interface 1/1/{number}', ' no shutdown']
        if number <= 48:
            lines.append(' vlan access 101')
        elif number <= 50:
            lines.append(' lag 1')
        else:
            lines.append(' vlan access 1')
    lines += ['interface vlan 99', ' no shutdown', ' ip address 192.0.2.30/24',
              'interface vlan 1', ' no shutdown', ' ip dhcp',
              'ip route 0.0.0.0/0 192.0.2.1', 'ntp server 192.0.2.123',
              'ip dns server-address 192.0.2.53', 'logging host 192.0.2.44']
    if critical:
        lines += ['user lab-admin password ciphertext SYNTHETIC_SECRET', 'tacacs-server host 192.0.2.5 key SYNTHETIC_KEY',
                  'aaa authentication login default group tacacs local', 'ssh server vrf default', 'https-server vrf default']
    return '\n'.join(lines) + '\n'


MAPPINGS = {f'1/1/{n}': f'GigabitEthernet1/0/{n}' for n in range(1, 53)}


def test_sanitized_standalone_acceptance_and_critical_security_gate():
    ir = parse_aruba_migration(fixture(True), '10.13')
    assert len(ir.interfaces) == 55
    assert 'SYNTHETIC_SECRET' not in ir.model_dump_json()
    assert 'SYNTHETIC_KEY' not in ir.model_dump_json()
    result = render_cisco(ir, MAPPINGS, '17.18')
    assert result == render_cisco(ir, MAPPINGS, '17.18')
    assert result.status == 'BLOCKED'
    assert result.translation_summary.interface_mapping_complete
    assert result.text.count(' switchport access vlan 101') == 48
    assert result.text.count(' channel-group 1 mode active') == 2
    assert 'switchport trunk allowed vlan all' in result.text
    assert 'interface Vlan99\n ip address 192.0.2.30 255.255.255.0' in result.text
    assert 'ip route 0.0.0.0 0.0.0.0 192.0.2.1' in result.text
    assert '\nip routing\n' in result.text
    assert 'spanning-tree mode rapid-pvst' in result.text
    assert 'SYNTHETIC_' not in result.model_dump_json()
    assert 'tacacs server' not in result.text
    assert 'ip http server' not in result.text
    assert 'dhcp snooping' not in result.text
    assert result.coverage['MANUAL_REQUIRED'] >= 6


def test_reverse_subset_is_exportable_only_with_current_review_acknowledgement():
    source = fixture().replace('interface vlan 1\n no shutdown\n ip dhcp\n', '')
    with TestClient(create_app()) as client:
        headers = {'X-ConfigHop-Client': 'web'}
        root = '/api/v1/switch-projects'
        project = client.post(root, headers=headers, json={'source_os': 'AOS_CX', 'source_version': '10.13', 'text': source}).json()
        ident = project['project_id']
        settings = {'revision': 1, 'target_os': 'IOS_XE', 'target_version': '17.18', 'mappings': MAPPINGS}
        preview = client.put(f'{root}/{ident}/preview', headers=headers, json=settings).json()
        assert preview['candidate']['status'] == 'REVIEW_REQUIRED', preview['candidate']['findings']
        digest = preview['candidate']['sha256']
        body = {'revision': 1, 'sha256': digest}
        assert client.post(f'{root}/{ident}/export', headers=headers, json=body).status_code == 409
        body['acknowledge_review'] = True
        assert client.post(f'{root}/{ident}/export', headers=headers, json=body).status_code == 200
        settings['revision'], settings['target_version'] = 2, '17.15'
        blocked = client.put(f'{root}/{ident}/preview', headers=headers, json=settings).json()['candidate']
        assert blocked['status'] == 'BLOCKED'
        assert client.post(f'{root}/{ident}/export', headers=headers, json=body).status_code == 409
        assert client.post(f'{root}/{ident}/export', headers=headers, json={'revision': 2, 'sha256': blocked['sha256'], 'acknowledge_review': True}).status_code == 409


def test_reverse_rejects_unsafe_mapping_and_unknown_source():
    ir = parse_aruba_migration('vlan 101\ninterface 1/1/1\n no shutdown\n vlan access 101\ninterface 1/1/2\n no shutdown\n vlan access 101\n', '10.13')
    assert render_cisco(ir, {'1/1/1': 'GigabitEthernet1/0/1', '1/1/2': 'Gi1/0/1'}, '17.18').status == 'BLOCKED'
    assert render_cisco(ir, {'1/1/1': 'GigabitEthernet1/0/1;shutdown'}, '17.18').status == 'BLOCKED'
    assert render_cisco(ir, {'1/1/1': 'GigabitEthernet1/0/01'}, '17.18').status == 'BLOCKED'
    assert render_cisco(ir, {'1/1/1': 'GigabitEthernet1/0/1'}, '17.18', 'hpe-aruba-jl663a').status == 'BLOCKED'
    assert render_cisco(ir, {'1/1/1': 'GigabitEthernet1/0/1'}, '17.18').status == 'BLOCKED'
    unknown = parse_aruba_migration('vlan 101\nunknown feature\n', '10.13')
    assert render_cisco(unknown, {}, '17.18').status == 'BLOCKED'


def test_stacking_and_operational_transcript_never_become_configuration():
    ir = parse_aruba_migration('vsf member 1\ninterface 1/1/1\n no shutdown\n vlan access 1\n', '10.13')
    result = render_cisco(ir, {'1/1/1': 'GigabitEthernet1/0/1'}, '17.18')
    assert result.status == 'BLOCKED'
    assert 'MANUAL_STACKING' in {f.code for f in result.findings}
    assert 'switch provision' not in result.text
    try:
        parse_aruba_migration('show interface 1/1/1\n', '10.13')
    except ValueError:
        pass
    else:
        raise AssertionError('Operational transcript accepted')
    with TestClient(create_app()) as client:
        response = client.post('/api/v1/switch-projects', headers={'X-ConfigHop-Client': 'web'}, json={
            'source_os': 'AOS_CX', 'source_version': '10.13', 'text': 'show interface 1/1/1\n'})
        assert response.status_code == 400
        assert response.json()['error']['code'] == 'OPERATIONAL_TRANSCRIPT'


@pytest.mark.parametrize('source,code', [
    ('vlan 4095\n', 'SOURCE_BLOCKED'),
    ('hostname ' + 'X' * 33 + '\n', 'SOURCE_UNSUPPORTED'),
    ('interface malformed\n no shutdown\n', 'SOURCE_BLOCKED'),
    ('interface lag 257\n', 'SOURCE_BLOCKED'),
    ('interface vlan 4095\n', 'SOURCE_BLOCKED'),
    ('vlan 101\ninterface 1/1/1\n no shutdown\n vlan access 102\n', 'DEPENDENCY_UNRESOLVED'),
    ('vlan 101\ninterface 1/1/1\n no shutdown\n vlan access 101\n vlan trunk native 101\n', 'SWITCHPORT_MODE_CONFLICT'),
    ('vlan 101\ninterface 1/1/1\n no shutdown\n lag 9\n', 'LAG_MEMBER_UNRESOLVED'),
    ('vlan 101\ninterface 1/1/1\n no shutdown\n vlan access 101\ninterface 1/1/1\n', 'SOURCE_BLOCKED'),
    ('vlan 101\ninterface 1/1/1\n no shutdown\n vlan access 101\nspanning-tree mode rpvst\nspanning-tree vlan 99\n', 'STP_VLAN_SCOPE_UNRESOLVED'),
    ('banner motd ^\nunfinished\n', 'SOURCE_BLOCKED'),
    ('ip route malformed 192.0.2.1\n', 'SOURCE_BLOCKED'),
    ('dhcpv4-snooping event-log\n', 'SOURCE_UNSUPPORTED'),
    ('aaa authentication login default group radius local\n', 'SOURCE_MANUAL_REQUIRED'),
])
def test_reverse_unsafe_constructs_are_explicitly_blocked(source, code):
    result = render_cisco(parse_aruba_migration(source, '10.13'), {}, '17.18')
    assert result.status == 'BLOCKED'
    assert code in {finding.code for finding in result.findings}


def test_header_version_mismatch_and_crlf_provenance():
    ir = parse_aruba_migration('! Version : FL.10.16.1000\r\nvlan 1\r\n', '10.13')
    assert ir.statements[0].line == 1
    result = render_cisco(ir, {}, '17.18')
    assert 'SOURCE_VERSION_MISMATCH' in {finding.code for finding in result.findings}
    assert result.status == 'BLOCKED'


def test_sensitive_tokens_in_supported_fields_never_enter_ir_or_draft():
    text = 'vlan 101\n name secret SYNTHETIC_MARKER\ninterface 1/1/1\n description password SYNTHETIC_SECRET\n no shutdown\n vlan access 101\n'
    ir = parse_aruba_migration(text, '10.13')
    result = render_cisco(ir, {'1/1/1': 'GigabitEthernet1/0/1'}, '17.18')
    assert result.status == 'BLOCKED'
    assert 'SYNTHETIC_SECRET' not in ir.model_dump_json() + result.model_dump_json()
    assert 'SYNTHETIC_MARKER' not in ir.model_dump_json() + result.model_dump_json()


def test_explicit_routing_without_address_emits_no_switchport():
    ir = parse_aruba_migration('interface 1/1/1\n no shutdown\n routing\n', '10.13')
    assert [(s.line, s.feature) for s in ir.statements] == [(1, 'interface'), (2, 'admin'), (3, 'mode')]
    result = render_cisco(ir, {'1/1/1': 'GigabitEthernet1/0/1'}, '17.18')
    assert result.status == 'REVIEW_REQUIRED'
    assert 'interface GigabitEthernet1/0/1\n no switchport\n no shutdown\n' in result.text
    assert all(s.status == 'TRANSLATED' for s in result.report)
    conflict = parse_aruba_migration('vlan 101\ninterface 1/1/1\n no shutdown\n routing\n vlan access 101\n', '10.13')
    blocked = render_cisco(conflict, {'1/1/1': 'GigabitEthernet1/0/1'}, '17.18')
    assert blocked.status == 'BLOCKED'
    assert 'L2_L3_CONFLICT' in {f.code for f in blocked.findings}


@pytest.mark.parametrize('source,code', [
    ('spanning-tree\n', 'STP_MODE_REQUIRED'),
    ('spanning-tree mode rpvst\n', 'STP_ENABLEMENT_REQUIRED'),
])
def test_incomplete_stp_is_blocked_and_not_misreported_as_translated(source, code):
    ir = parse_aruba_migration(source, '10.13')
    assert ir.statements[0].line == 1
    result = render_cisco(ir, {}, '17.18')
    assert result.status == 'BLOCKED'
    assert code in {f.code for f in result.findings}
    assert result.report[0].status == 'BLOCKED'
    assert 'spanning-tree mode rapid-pvst' not in result.text


def test_missing_lacp_mode_is_a_blocked_candidate_and_api_never_crashes():
    source = 'vlan 1\ninterface lag 1\n no shutdown\n vlan access 1\ninterface 1/1/1\n no shutdown\n lag 1\n'
    ir = parse_aruba_migration(source, '10.13')
    assert [(i.name, i.kind) for i in ir.interfaces] == [('Port-channel1', 'LAG'), ('1/1/1', 'Physical')]
    result = render_cisco(ir, {'1/1/1': 'GigabitEthernet1/0/1'}, '17.18')
    assert result.status == 'BLOCKED'
    assert {f.scope for f in result.findings if f.code == 'LACP_MODE_REQUIRED'} == {'Port-channel1', '1/1/1'}
    assert 'channel-group' not in result.text
    with TestClient(create_app()) as client:
        headers = {'X-ConfigHop-Client': 'web'}
        root = '/api/v1/switch-projects'
        project = client.post(root, headers=headers, json={'source_os': 'AOS_CX', 'source_version': '10.13', 'text': source}).json()
        response = client.put(f"{root}/{project['project_id']}/preview", headers=headers, json={
            'revision': 1, 'target_os': 'IOS_XE', 'target_version': '17.18',
            'mappings': {'1/1/1': 'GigabitEthernet1/0/1'},
        })
        assert response.status_code == 200, response.text
        candidate = response.json()['candidate']
        assert candidate['status'] == 'BLOCKED'
        assert client.post(f"{root}/{project['project_id']}/export", headers=headers, json={
            'revision': 1, 'sha256': candidate['sha256'], 'acknowledge_review': True,
        }).status_code == 409


@pytest.mark.parametrize('source,code', [
    ('vlan 101\ninterface 1/1/1\n vlan access 101\n', 'ADMIN_STATE_UNRESOLVED'),
    ('vlan 101\ninterface vlan 101\n ip address 192.0.2.2/24\n', 'ADMIN_STATE_UNRESOLVED'),
    ('spanning-tree\n', 'STP_MODE_REQUIRED'),
])
def test_unsafe_reverse_sources_cannot_export_even_with_acknowledgement(source, code):
    with TestClient(create_app()) as client:
        headers = {'X-ConfigHop-Client': 'web'}
        root = '/api/v1/switch-projects'
        project = client.post(root, headers=headers, json={'source_os': 'AOS_CX', 'source_version': '10.13', 'text': source}).json()
        mappings = {'1/1/1': 'GigabitEthernet1/0/1'} if 'interface 1/1/1' in source else {}
        preview = client.put(f"{root}/{project['project_id']}/preview", headers=headers, json={
            'revision': 1, 'target_os': 'IOS_XE', 'target_version': '17.18', 'mappings': mappings,
        })
        assert preview.status_code == 200, preview.text
        candidate = preview.json()['candidate']
        assert candidate['status'] == 'BLOCKED'
        assert code in {f['code'] for f in candidate['findings']}
        assert client.post(f"{root}/{project['project_id']}/export", headers=headers, json={
            'revision': 1, 'sha256': candidate['sha256'], 'acknowledge_review': True,
        }).status_code == 409
