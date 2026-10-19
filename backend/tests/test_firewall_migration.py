from pathlib import Path

from confighop_core.firewall_migration import FirewallMappings, generate_firewall
from confighop_core.parsers.fortios import parse_fortios, parse_fortios_tree
from confighop_core.parsers.panos_firewall import parse_panos_firewall


FIXTURE = Path(__file__).parent / 'fixtures' / 'phase9b' / 'fortios.conf'


def test_fortios_to_panos_candidate_preserves_order_and_policy_state():
    ir = parse_fortios(FIXTURE.read_text(), '7.4')
    assert len(ir.policies) == 3
    assert len(ir.nat) == 2
    assert ir.interfaces[0].address == '203.0.113.2/30'
    candidate = generate_firewall(ir, 'panos', FirewallMappings(interfaces={'port1': 'ethernet1/1', 'port2': 'ethernet1/2'}), 1)
    assert candidate.status == 'REVIEW_REQUIRED', [finding.model_dump() for finding in candidate.findings]
    assert candidate.text.index('Outbound Web') < candidate.text.index('Inbound Web') < candidate.text.index('Disabled Deny')
    assert '<disabled>yes</disabled>' in candidate.text
    assert '<dynamic-ip-and-port>' in candidate.text
    assert '<destination-translation>' in candidate.text
    assert '<service>TCP_8443</service>' in candidate.text
    assert candidate.text == (FIXTURE.parent / 'panos.xml').read_text()
    parsed = parse_panos_firewall(candidate.text, '11.1')
    assert len(parsed.policies) == 3


def test_panos_to_fortios_candidate_links_nat_to_policies():
    source = parse_fortios(FIXTURE.read_text(), '7.4')
    panos = generate_firewall(source, 'panos', FirewallMappings(interfaces={'port1': 'ethernet1/1', 'port2': 'ethernet1/2'}), 1)
    ir = parse_panos_firewall(panos.text, '11.1')
    candidate = generate_firewall(ir, 'fortios', FirewallMappings(interfaces={'ethernet1/1': 'port1', 'ethernet1/2': 'port2'}), 2)
    assert candidate.status == 'REVIEW_REQUIRED', [finding.model_dump() for finding in candidate.findings]
    assert 'set poolname' in candidate.text
    assert 'set dstaddr "dnat-WEB_VIP"' in candidate.text
    assert candidate.text.index('Outbound Web') < candidate.text.index('Inbound Web') < candidate.text.index('Disabled Deny')
    assert 'set status "disable"' in candidate.text
    assert candidate.text == (FIXTURE.parent / 'fortios-candidate.cfg').read_text()
    parsed = parse_fortios(candidate.text, '7.4')
    assert len(parsed.policies) == 3
    assert len(parsed.routes) == 1
    assert not [finding for finding in parsed.findings if finding.severity == 'BLOCKED']


def test_panos_adapter_rejects_unsafe_policy_semantics_and_xml_entities():
    import pytest
    xml = (FIXTURE.parent / 'panos.xml').read_text()
    changed = xml.replace('<member>any</member>\n                  </application>', '<member>ssl</member>\n                  </application>', 1)
    ir = parse_panos_firewall(changed, '11.1')
    candidate = generate_firewall(ir, 'fortios', FirewallMappings(interfaces={'ethernet1/1': 'port1', 'ethernet1/2': 'port2'}), 1)
    assert candidate.status == 'BLOCKED'
    assert any(f.code == 'APP_ID' for f in candidate.findings)
    with pytest.raises(Exception):
        parse_panos_firewall('<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><config>&x;</config>', '11.1')


def test_dependency_cycle_missing_reference_schedule_and_vip_ingress_block():
    source = FIXTURE.read_text().replace('set member "CLIENTS"', 'set member "CLIENT_GROUP"')
    source = source.replace('set schedule "always"', 'set schedule "OfficeHours"', 1)
    source = source.replace('set extintf "port1"', 'set extintf "any"')
    source = source.replace('set service "WEB_GROUP"', 'set service "MISSING_SERVICE"', 1)
    ir = parse_fortios(source, '7.4')
    result = generate_firewall(ir, 'panos', FirewallMappings(interfaces={'port1': 'ethernet1/1', 'port2': 'ethernet1/2'}), 1)
    assert result.status == 'BLOCKED' and not result.text
    assert {'CYCLIC_GROUP', 'MISSING_REFERENCE', 'SCHEDULE', 'VIP_INGRESS'} <= {finding.code for finding in result.findings}


def test_policy_nat_with_multiple_services_blocks_instead_of_broadening():
    source = FIXTURE.read_text().replace('set member "TCP_8443"', 'set member "TCP_8443" "TCP_9000"')
    ir = parse_fortios(source, '7.4')
    result = generate_firewall(ir, 'panos', FirewallMappings(interfaces={'port1': 'ethernet1/1', 'port2': 'ethernet1/2'}), 1)
    assert result.status == 'BLOCKED' and not result.text
    assert any(f.code == 'NAT_SERVICE' for f in result.findings)


def test_vip_protocol_restriction_cannot_be_dropped():
    source = FIXTURE.read_text().replace('set extip 203.0.113.100', 'set protocol udp\n        set extip 203.0.113.100')
    candidate = generate_firewall(parse_fortios(source, '7.4'), 'panos',
        FirewallMappings(interfaces={'port1': 'ethernet1/1', 'port2': 'ethernet1/2'}), 1)
    assert candidate.status == 'BLOCKED' and not candidate.text
    assert any(f.code == 'VIP_PROTOCOL' for f in candidate.findings)


def test_combined_or_disabled_policy_nat_cannot_become_active_target_nat():
    source = FIXTURE.read_text().replace('set dstaddr "WEB_VIP"', 'set dstaddr "WEB_VIP"\n        set nat enable', 1)
    ir = parse_fortios(source, '7.4')
    result = generate_firewall(ir, 'panos', FirewallMappings(interfaces={'port1': 'ethernet1/1', 'port2': 'ethernet1/2'}), 1)
    assert result.status == 'BLOCKED'
    assert any(f.code == 'COMBINED_NAT' for f in result.findings)
    source = FIXTURE.read_text().replace('set nat enable', 'set nat enable\n        set status disable', 1)
    ir = parse_fortios(source, '7.4')
    result = generate_firewall(ir, 'panos', FirewallMappings(interfaces={'port1': 'ethernet1/1', 'port2': 'ethernet1/2'}), 1)
    assert result.status == 'BLOCKED'
    assert any(f.code == 'NAT_DISABLED_POLICY' for f in result.findings)


def test_ir_provenance_serialization_and_mapping_rename_are_deterministic():
    ir = parse_fortios(FIXTURE.read_text(), '7.4')
    assert ir.policies[0].identity == 'root:1'
    assert ir.policies[0].source_location.startswith('line ')
    assert 'CLIENT_GROUP' in ir.policies[0].dependencies
    assert ir.model_dump_json() == parse_fortios(FIXTURE.read_text(), '7.4').model_dump_json()
    mappings = FirewallMappings(interfaces={'port1': 'ethernet1/1', 'port2': 'ethernet1/2'},
        addresses={'CLIENTS': 'CUSTOMERS', 'CLIENT_GROUP': 'CUSTOMER_GROUP'})
    result = generate_firewall(ir, 'panos', mappings, 1)
    assert result.status == 'REVIEW_REQUIRED'
    assert '<member>CUSTOMERS</member>' in result.text
    assert '<member>CUSTOMER_GROUP</member>' in result.text
    assert 'CLIENT_GROUP</member>' not in result.text


def test_fortios_parser_rejects_malformed_and_reports_unknown():
    import pytest
    with pytest.raises(ValueError):
        parse_fortios_tree('config firewall address\n edit "broken\n next\nend')
    with pytest.raises(ValueError):
        parse_fortios_tree('config firewall address\n edit test\nend')
    ir = parse_fortios(FIXTURE.read_text() + '\nconfig vpn ipsec phase1-interface\nend\n', '7.4')
    candidate = generate_firewall(ir, 'panos', FirewallMappings(interfaces={'port1': 'ethernet1/1', 'port2': 'ethernet1/2'}), 1)
    assert candidate.status == 'BLOCKED'
    assert not candidate.text
    assert any(f.code == 'UNSUPPORTED_SECTION' for f in candidate.findings)


def test_multiple_firewall_scopes_block_cross_vendor_output():
    source = FIXTURE.read_text() + '\nconfig vdom\n    edit "one"\n    next\n    edit "two"\n    next\nend\n'
    fortios = generate_firewall(parse_fortios(source, '7.4'), 'panos',
        FirewallMappings(interfaces={'port1': 'ethernet1/1', 'port2': 'ethernet1/2'}), 1)
    assert fortios.status == 'BLOCKED' and any(f.code == 'MULTI_VDOM' for f in fortios.findings)
    xml = (FIXTURE.parent / 'panos.xml').read_text().replace('</vsys>', '<entry name="vsys2" /></vsys>')
    panos = generate_firewall(parse_panos_firewall(xml, '11.1'), 'fortios',
        FirewallMappings(interfaces={'ethernet1/1': 'port1', 'ethernet1/2': 'port2'}), 1)
    assert panos.status == 'BLOCKED' and any(f.code == 'PANOS_SCOPE' for f in panos.findings)


def test_firewall_api_revision_export_and_session_isolation():
    from fastapi.testclient import TestClient
    from confighop_api.main import create_app

    headers = {'X-ConfigHop-Client': 'web'}
    with TestClient(create_app()) as client:
        source = client.post('/api/v1/firewall-projects', headers=headers,
            json={'text': FIXTURE.read_text(), 'source_os': 'fortios', 'source_version': '7.4'})
        assert source.status_code == 200, source.text
        assert client.post('/api/v1/firewall-projects', headers=headers,
            json={'text': 'x' * (2 * 1024 * 1024 + 1), 'source_os': 'fortios', 'source_version': '7.4'}).status_code == 400
        project_id = source.json()['project_id']
        assert source.json()['inventory']['source_vendor'] == 'fortios'
        path = f'/api/v1/firewall-projects/{project_id}'
        body = {'revision': 1, 'target_os': 'panos', 'target_version': '11.1',
            'mappings': {'interfaces': {'port1': 'ethernet1/1', 'port2': 'ethernet1/2'}}}
        result = client.put(path + '/preview', headers=headers, json=body)
        assert result.status_code == 200, result.text
        assert client.put(path + '/preview', headers=headers, json={**body, 'revision': 2, 'target_os': 'fortios'}).status_code == 400
        candidate = result.json()['candidate']
        assert candidate['status'] == 'REVIEW_REQUIRED'
        assert client.put(path + '/preview', headers=headers, json=body).status_code == 409
        export = {'revision': 1, 'sha256': candidate['sha256']}
        assert client.post(path + '/export', headers=headers, json=export).status_code == 409
        assert client.post(path + '/export', headers=headers, json={**export, 'sha256': '0' * 64, 'acknowledge_review': True}).status_code == 409
        approved = client.post(path + '/export', headers=headers, json={**export, 'acknowledge_review': True})
        assert approved.status_code == 200
        assert approved.json()['text'] == candidate['text']
        assert client.post(path + '/export', headers=headers, json={**export, 'acknowledge_review': True}).json() == approved.json()
        body['revision'] = 2
        body['mappings']['interfaces']['port2'] = 'ethernet1/1'
        blocked = client.put(path + '/preview', headers=headers, json=body)
        assert blocked.json()['candidate']['status'] == 'BLOCKED'
        assert client.post(path + '/export', headers=headers, json={**export, 'acknowledge_review': True}).status_code == 409
        assert client.get('/api/v1/firewall-projects/not-a-session').status_code == 404
        assert client.delete(path, headers=headers).status_code == 204
        assert client.get(path).status_code == 404


def test_concurrent_firewall_previews_accept_one_revision():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from confighop_api.main import create_app

    headers = {'X-ConfigHop-Client': 'web'}
    with TestClient(create_app()) as client:
        source = client.post('/api/v1/firewall-projects', headers=headers,
            json={'text': FIXTURE.read_text(), 'source_os': 'fortios', 'source_version': '7.4'})
        project_id = source.json()['project_id']
        body = {'revision': 1, 'target_os': 'panos', 'target_version': '11.1',
            'mappings': {'interfaces': {'port1': 'ethernet1/1', 'port2': 'ethernet1/2'}}}
        barrier = Barrier(3)
        def preview():
            barrier.wait()
            return client.put(f'/api/v1/firewall-projects/{project_id}/preview', headers=headers, json=body)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(preview), pool.submit(preview)
            barrier.wait()
            responses = [first.result(), second.result()]
        assert sorted(response.status_code for response in responses) == [200, 409]
        assert client.get(f'/api/v1/firewall-projects/{project_id}').json()['revision'] == 1
