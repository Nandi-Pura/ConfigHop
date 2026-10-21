from pathlib import Path
import json

from fastapi.testclient import TestClient
import pytest

from confighop_api.main import create_app
from confighop_core.parsers.cisco_iosxe.migration import parse_migration
from confighop_core.switch_migration import render_switch

FIXTURES = Path(__file__).parent / 'fixtures' / 'switch'
SOURCE = (FIXTURES / 'phase9a-iosxe.cfg').read_text()
MAPPINGS = {f'GigabitEthernet1/0/{i}': slot for i, slot in enumerate([24, 10, 48, 7, 8], 1)}
HEADERS = {'X-ConfigHop-Client': 'web'}


def candidate(text=SOURCE, mappings=None, version='10.15', capability='hpe-aruba-jl663a'):
    return render_switch(parse_migration(text, '17.12'), MAPPINGS if mappings is None else mappings, version, capability)


def test_golden_and_determinism():
    result = candidate()
    assert result.status == 'REVIEW_REQUIRED', result.findings
    assert result.text == (FIXTURES / 'phase9a-aos-cx.cfg').read_text()
    assert result == candidate()
    assert len(result.resolved_interfaces) == 5
    assert all(d.resolved for d in result.dependencies)
    assert not result.deployment_verified
    assert 'interface 1/1/24' in result.text
    assert 'vlan trunk native 99\n    vlan trunk allowed 10,20,99' in result.text


@pytest.mark.parametrize('source_train', ['17.12', '17.15', '17.18'])
@pytest.mark.parametrize('target_train', ['10.10', '10.13', '10.16'])
def test_os_based_translation_without_hardware(source_train, target_train):
    source = SOURCE.replace('version 17.12', f'version {source_train}')
    names = {name: f'1/1/{slot}' for name, slot in MAPPINGS.items()}
    ir = parse_migration(source, source_train)
    result = render_switch(ir, names, target_train)
    assert result.status == 'REVIEW_REQUIRED', result.findings
    assert result == render_switch(ir, names, target_train)
    assert result.resolved_interfaces == names
    assert result.translation_summary.source_version == source_train
    assert result.translation_summary.target_version == target_train
    assert result.translation_summary.interface_mapping_complete
    assert result.translation_summary.hardware_compatibility_status == 'NOT_VERIFIED'
    assert result.translation_summary.output_validation_status == 'CHECKED_SUBSET'
    assert 'PORT_EXISTENCE_NOT_VERIFIED' in {finding.code for finding in result.findings}


@pytest.mark.parametrize('mapping,code', [
    ({'GigabitEthernet1/0/1': '1/1/0'}, 'INVALID_MAPPING'),
    ({'GigabitEthernet1/0/1': '1/1/2; no shutdown'}, 'INVALID_MAPPING'),
    ({'GigabitEthernet1/0/1': '1/1/24', 'GigabitEthernet1/0/2': '1/1/24'}, 'DUPLICATE_TARGET'),
])
def test_manual_mapping_rejects_unsafe_names_and_duplicates(mapping, code):
    result = candidate(mappings=mapping, capability=None)
    assert result.status == 'BLOCKED'
    assert code in {finding.code for finding in result.findings}


def test_optional_hardware_profile_checks_manual_target():
    result = candidate(mappings={'GigabitEthernet1/0/1': '9/9/9'}, capability='hpe-aruba-jl663a')
    assert result.status == 'BLOCKED'
    assert 'TARGET_PORT_NOT_IN_PROFILE' in {finding.code for finding in result.findings}
    newer = candidate(version='10.16')
    assert newer.translation_summary.hardware_compatibility_status == 'NOT_VERIFIED'
    assert 'TARGET_HARDWARE_OS_NOT_VERIFIED' in {finding.code for finding in newer.findings}


def test_native_vlan_excluded_from_target_allowed_list_blocks():
    source = SOURCE.replace('switchport trunk allowed vlan 10,20,99', 'switchport trunk allowed vlan 10,20')
    result = candidate(source)
    assert result.status == 'BLOCKED'
    assert 'TRUNK_NATIVE_NOT_ALLOWED' in {finding.code for finding in result.findings}


def test_legacy_ssr_pair_does_not_expand_to_untested_source_train():
    source = SOURCE.replace('version 17.12', 'version 17.18')
    result = render_switch(parse_migration(source, '17.18'), MAPPINGS, '10.15', 'hpe-aruba-jl663a')
    assert result.status == 'BLOCKED'
    assert 'OS_VERSION_UNVERIFIED' in {finding.code for finding in result.findings}


@pytest.mark.parametrize('ending', ['\n', '\r\n'])
def test_parser_inventory_provenance(ending):
    ir = parse_migration(SOURCE.replace('\n', ending), '17.12')
    assert len([i for i in ir.interfaces if i.kind == 'Physical']) == 5
    assert {i.kind for i in ir.interfaces} == {'Physical', 'LAG', 'SVI'}
    assert ir.statements[0].line == 1
    assert ir.statements[1].source == 'hostname LAB-SWITCH'
    assert all(s.explicit for s in ir.statements)


@pytest.mark.parametrize('count', [5, 38, 48])
def test_dynamic_inventory_and_mapping(count):
    text = 'vlan 10\n!\n' + ''.join(f'interface Gi1/0/{i}\n no shutdown\n switchport mode access\n switchport access vlan 10\n!\n' for i in range(1, count + 1))
    mapping = {f'GigabitEthernet1/0/{i}': 49-i for i in range(1, count + 1)}
    ir = parse_migration(text, '17.12')
    assert len(ir.interfaces) == count
    result = candidate(text, mapping)
    assert result.status == 'REVIEW_REQUIRED'
    assert len(result.resolved_interfaces) == count
    assert result.text.count('\ninterface ') == count


@pytest.mark.parametrize('mapping,code', [({'GigabitEthernet1/0/1': 0}, 'INVALID_MAPPING'), ({'GigabitEthernet1/0/1': 49}, 'INVALID_MAPPING'), ({'Vlan99': 1}, 'INVALID_MAPPING'), ({'unknown': 1}, 'INVALID_MAPPING'), ({'GigabitEthernet1/0/1': 2, 'GigabitEthernet1/0/2': 2}, 'DUPLICATE_TARGET')])
def test_invalid_mapping(mapping, code):
    result = candidate(mappings=mapping)
    assert result.status == 'BLOCKED'
    assert code in {f.code for f in result.findings}


def test_removal_replacement_unknown_hardware():
    mapping = {**MAPPINGS}; del mapping['GigabitEthernet1/0/1']
    result = candidate(mappings=mapping)
    assert 'interface 1/1/24\n' not in result.text
    assert 'hostname LAB-SWITCH' in result.text
    mapping['GigabitEthernet1/0/2'] = 3
    assert 'interface 1/1/3\n' in candidate(mappings=mapping).text
    result = candidate(capability=None)
    assert result.status == 'BLOCKED'
    assert not result.resolved_interfaces
    assert '\ninterface 1/1/' not in result.text


@pytest.mark.parametrize('text,code', [
    (SOURCE.replace('vlan 20\n name SERVERS\n!\n', ''), 'DEPENDENCY_UNRESOLVED'),
    (SOURCE.replace('channel-group 10 mode active', 'channel-group 11 mode active', 1), 'LAG_MEMBER_UNRESOLVED'),
    (SOURCE.replace('ip access-group LAB-ACL in', 'ip access-group MISSING in'), 'DEPENDENCY_UNRESOLVED'),
    (SOURCE.replace('192.0.2.1\n', '198.51.100.1\n'), 'DEPENDENCY_UNRESOLVED'),
    (SOURCE + '\ninterface Gi1/0/1\n', 'SOURCE_BLOCKED'),
    (SOURCE + '\nunknown command\n', 'SOURCE_UNSUPPORTED'),
    (SOURCE.replace('vlan 20\n', 'vlan 4095\n', 1), 'SOURCE_BLOCKED'),
    (SOURCE.replace('ip access-group LAB-ACL in', 'ip access-group LAB-ACL out'), 'ACL_ATTACHMENT_UNSUPPORTED'),
])
def test_dependencies_and_unknowns(text, code):
    result = candidate(text)
    assert result.status == 'BLOCKED'
    assert code in {f.code for f in result.findings}


def test_versions_and_secrets():
    assert candidate(version='').status == 'BLOCKED'
    assert candidate(version='10.13').status == 'REVIEW_REQUIRED'
    assert candidate(SOURCE.replace('version 17.12', 'version 17.9')).status == 'BLOCKED'
    text = SOURCE + '\nusername admin secret 9 SYNTHETIC_SECRET\nsnmp-server community SYNTHETIC_COMMUNITY ro\n'
    ir = parse_migration(text, '17.12')
    assert 'SYNTHETIC_SECRET' not in ir.model_dump_json()
    assert 'SYNTHETIC_COMMUNITY' not in candidate(text).model_dump_json()


def test_routed_physical_acl_and_shutdown():
    source = 'ip routing\nip access-list extended DENY\n 10 deny ip any any\n!\ninterface Gi1/0/1\n shutdown\n no switchport\n ip address 198.51.100.2 255.255.255.0\n ip access-group DENY in\n'
    result = candidate(source, {'GigabitEthernet1/0/1': 11})
    assert result.status == 'REVIEW_REQUIRED'
    assert '    apply access-list ip DENY in\n' in result.text
    assert '    shutdown\n    routing\n    ip address 198.51.100.2/24' in result.text
    assert '10 deny any any any' in result.text


def test_management_metadata_and_sensitive_blocks():
    text = 'ip domain name example.test\nip name-server 192.0.2.53\nlogging host 192.0.2.4\nip default-gateway 192.0.2.1\nusername admin secret 9 SYNTHETIC\ncrypto pki certificate chain TEST\nCERTIFICATE_SYNTHETIC_PAYLOAD\n quit\n!\nline vty 0 4\n access-class MANAGEMENT in\n!\nrouter ospf 1\n network 192.0.2.0 0.0.0.255 area 0\n'
    ir = parse_migration(text, '17.12')
    features = {s.feature: s.values for s in ir.statements}
    assert features['domain'] == ['example.test']
    assert features['dns'] == ['192.0.2.53']
    assert features['logging'] == ['192.0.2.4']
    assert features['local_user_reentry'] == ['admin']
    assert features['management_acl'] == ['MANAGEMENT', 'in']
    assert features['dynamic_routing'] == ['ospf', '1']
    assert 'SYNTHETIC' not in ir.model_dump_json()
    assert candidate(text, {}).status == 'BLOCKED'


def test_mode_conflict_and_lag_member_mapping_dependency():
    result = candidate(SOURCE.replace('switchport mode access', 'switchport mode trunk', 1))
    assert 'SWITCHPORT_MODE_CONFLICT' in {f.code for f in result.findings}
    mapping = {**MAPPINGS}; del mapping['GigabitEthernet1/0/4']
    assert 'LAG_MEMBER_UNRESOLVED' in {f.code for f in candidate(mappings=mapping).findings}


def test_opaque_banner_unknown_loopback_and_duplicate_acl_are_reported():
    ir = parse_migration('banner motd ^C\nSYNTHETIC_BANNER\n^C\n!\ninterface Loopback0\n ip address 192.0.2.1 255.255.255.255\n!\nip access-list extended TEST\n 10 permit ip any any\n 10 deny ip any any\n', '17.12')
    assert 'SYNTHETIC_BANNER' not in ir.model_dump_json()
    assert ir.interfaces[0].kind == 'Loopback'
    assert any(s.scope == 'Loopback0' and s.feature == 'address' and s.status == 'UNSUPPORTED' for s in ir.statements)
    assert any(s.status == 'BLOCKED' and s.feature == 'acl_rule' for s in ir.statements)


def test_partial_acl_and_aaa_do_not_render_dangling_settings():
    text = SOURCE.replace(' 10 permit ip any any', ' 10 permit tcp any any eq 443')
    result = candidate(text)
    assert result.status == 'BLOCKED'
    assert 'access-list ip LAB-ACL\n' not in result.text
    assert 'apply access-list ip LAB-ACL' not in result.text
    assert 'DEPENDENCY_UNRESOLVED' in {f.code for f in result.findings}
    result = candidate('aaa new-model\n')
    assert 'AAA_METHOD_UNSUPPORTED' in {f.code for f in result.findings}


@pytest.mark.parametrize('text', ['', '<config/>', 'host\x00name', 'x\n' * 20001, 'x' * (2 * 1024 * 1024 + 1)], ids=['empty', 'xml', 'control', 'lines', 'bytes'])
def test_invalid_input(text):
    with pytest.raises(ValueError):
        parse_migration(text, '17.12')


def test_api_sessions_revisions_export_and_safe_errors():
    with TestClient(create_app()) as client:
        root = '/api/v1/switch-projects'
        assert client.post(root, json={}).status_code == 400
        assert client.post(root, headers=HEADERS, json={'text': 'SYNTHETIC_SECRET', 'source_os': 'NX_OS', 'source_version': '17.12'}).json() == {'error': {'code': 'INVALID_REQUEST', 'message': 'Request shape is invalid.'}}
        def create():
            response = client.post(root, headers=HEADERS, json={'text': SOURCE, 'source_os': 'IOS_XE', 'source_version': '17.12'})
            assert response.status_code == 200, response.text
            return response.json()['project_id']
        one, two = create(), create()
        settings = {'revision': 1, 'target_os': 'AOS_CX', 'target_version': '10.15', 'capability_id': 'hpe-aruba-jl663a', 'mappings': MAPPINGS}
        result = client.put(f'{root}/{one}/preview', headers=HEADERS, json=settings)
        assert result.status_code == 200, result.text
        body = {'revision': 1, 'sha256': result.json()['candidate']['sha256']}
        assert client.post(f'{root}/{one}/export', headers=HEADERS, json=body).status_code == 409
        body['acknowledge_review'] = True
        assert client.post(f'{root}/{one}/export', headers=HEADERS, json=body).status_code == 200
        assert client.post(f'{root}/{two}/export', headers=HEADERS, json=body).status_code == 409
        assert client.put(f'{root}/{one}/preview', headers=HEADERS, json=settings).status_code == 409
        settings.update(revision=2, capability_id=None)
        assert client.put(f'{root}/{one}/preview', headers=HEADERS, json=settings).status_code == 200
        assert client.post(f'{root}/{one}/export', headers=HEADERS, json=body).status_code == 409
        settings.update(revision=3, target_version='10.16', mappings={name: f'1/1/{slot}' for name, slot in MAPPINGS.items()})
        os_preview = client.put(f'{root}/{one}/preview', headers=HEADERS, json=settings)
        assert os_preview.status_code == 200, os_preview.text
        assert os_preview.json()['candidate']['status'] == 'REVIEW_REQUIRED'
        assert os_preview.json()['candidate']['translation_summary']['hardware_compatibility_status'] == 'NOT_VERIFIED'
        assert client.post(f'{root}/{one}/export', headers=HEADERS, json=body).status_code == 409
        os_body = {'revision': 3, 'sha256': os_preview.json()['candidate']['sha256'], 'acknowledge_review': True}
        assert client.post(f'{root}/{one}/export', headers=HEADERS, json=os_body).status_code == 200
        settings.update(revision=4, target_version='10.17')
        assert client.put(f'{root}/{one}/preview', headers=HEADERS, json=settings).json()['candidate']['status'] == 'BLOCKED'
        assert client.post(f'{root}/{one}/export', headers=HEADERS, json=os_body).status_code == 409
        settings['mappings'] = {'GigabitEthernet1/0/1': True}
        settings['revision'] = 5
        assert client.put(f'{root}/{one}/preview', headers=HEADERS, json=settings).status_code == 400
        assert client.delete(f'{root}/{one}', headers=HEADERS).status_code == 204
        assert client.get(f'{root}/{one}').status_code == 404
        assert client.get(f'{root}/{two}').status_code == 200
