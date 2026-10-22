from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from confighop_core.firewall_migration import FirewallMappings, generate_firewall
from confighop_core.parsers.fortios import parse_fortios, parse_fortios_tree
from confighop_core.parsers.panos_firewall import parse_panos_firewall


FIXTURE = Path(__file__).parent / 'fixtures' / 'phase9b' / 'fortios.conf'
PANOS = FIXTURE.parent / 'panos.xml'
PANOS_MAPPINGS = FirewallMappings(interfaces={'ethernet1/1': 'port1', 'ethernet1/2': 'port2'})
FORTIOS_MAPPINGS = FirewallMappings(interfaces={'port1': 'ethernet1/1', 'port2': 'ethernet1/2'})


def _panos_with(change):
    root = ET.fromstring(PANOS.read_text())
    change(root)
    return ET.tostring(root, encoding='unicode')


def _extra_address(root, path='./devices/entry/network/interface/ethernet/entry/layer3/ip', count=1):
    ip = root.find(path)
    assert ip is not None
    for index in range(count):
        ET.SubElement(ip, 'entry', {'name': f'203.0.113.{6 + index * 4}/30'})


def _translated_port(root, port='9443'):
    dnat = root.find('.//destination-translation')
    assert dnat is not None
    ET.SubElement(dnat, 'translated-port').text = port


def _extra_router(root, with_route=True):
    routers = root.find('./devices/entry/network/virtual-router')
    assert routers is not None
    second = ET.SubElement(routers, 'entry', {'name': 'VR2'})
    ET.SubElement(ET.SubElement(second, 'interface'), 'member').text = 'ethernet1/1'
    if with_route:
        original = routers.find('./entry/routing-table')
        assert original is not None
        copied = ET.fromstring(ET.tostring(original))
        copied.find('./ip/static-route/entry').set('name', 'VR2-route')
        second.append(copied)


def _assert_blocked(candidate, code, entity):
    assert candidate.status == 'BLOCKED' and candidate.text == ''
    assert any(f.code == code and f.entity == entity and f.severity == 'BLOCKED' for f in candidate.findings)
    assert all(c.translated == 0 and c.rendered == 0 for c in candidate.coverage)


@pytest.mark.parametrize(('category', 'source', 'target'), [
    ('zones', 'LAN', 'any'), ('zones', 'LAN', 'AnY'),
    ('zones', 'LAN', 'AnY '),
    ('addresses', 'CLIENTS', 'any'), ('addresses', 'CLIENT_GROUP', 'any'),
    ('services', 'TCP_8443', 'any'), ('services', 'WEB_GROUP', 'any'),
    ('services', 'TCP_8443', 'application-default'),
])
def test_concrete_fortios_identity_cannot_become_panos_wildcard(category, source, target):
    ir = parse_fortios(FIXTURE.read_text(), '7.4')
    mappings = FORTIOS_MAPPINGS.model_copy(deep=True)
    getattr(mappings, category)[source] = target
    candidate = generate_firewall(ir, 'panos', mappings, 1)
    _assert_blocked(candidate, 'RESERVED_TARGET_IDENTITY', source)
    if source in {'LAN', 'CLIENT_GROUP', 'WEB_GROUP'}:
        assert any('References:' in f.message for f in candidate.findings if f.code == 'RESERVED_TARGET_IDENTITY' and f.entity == source)


def test_reserved_source_identity_and_casefold_collision_block_but_safe_rename_remains():
    ir = parse_fortios(FIXTURE.read_text(), '7.4')
    collision = FORTIOS_MAPPINGS.model_copy(deep=True)
    collision.zones = {'LAN': 'Inside', 'WAN': 'inside'}
    _assert_blocked(generate_firewall(ir, 'panos', collision, 1), 'NAME_COLLISION', 'LAN')
    safe = FORTIOS_MAPPINGS.model_copy(deep=True)
    safe.zones = {'LAN': 'Inside'}
    assert generate_firewall(ir, 'panos', safe, 1).status == 'REVIEW_REQUIRED'
    ir.zones[0].name = 'any'
    _assert_blocked(generate_firewall(ir, 'panos', FORTIOS_MAPPINGS, 1), 'RESERVED_TARGET_IDENTITY', 'any')


def test_fortios_reserved_target_and_explicit_source_wildcard():
    ir = parse_panos_firewall(PANOS.read_text(), '11.1')
    mappings = PANOS_MAPPINGS.model_copy(deep=True)
    mappings.addresses['CLIENTS'] = 'ALL'
    _assert_blocked(generate_firewall(ir, 'fortios', mappings, 1), 'RESERVED_TARGET_IDENTITY', 'CLIENTS')
    vip = next(item for item in ir.nat if item.kind == 'dnat')
    mappings = PANOS_MAPPINGS.model_copy(deep=True)
    mappings.nat[vip.name] = 'all'
    _assert_blocked(generate_firewall(ir, 'fortios', mappings, 1), 'RESERVED_TARGET_IDENTITY', vip.name)
    assert generate_firewall(parse_fortios(FIXTURE.read_text(), '7.4'), 'panos', FORTIOS_MAPPINGS, 1).status == 'REVIEW_REQUIRED'


@pytest.mark.parametrize('port', ['9443', '8080'])
def test_translated_port_dnat_is_blocked_with_source_disposition(port):
    source = _panos_with(lambda root: _translated_port(root, port))
    ir = parse_panos_firewall(source, '11.1')
    nat = next(item for item in ir.nat if item.translated_port == port)
    assert nat.translation_status == 'BLOCKED' and nat.source_location
    _assert_blocked(generate_firewall(ir, 'fortios', PANOS_MAPPINGS, 1), 'UNSUPPORTED_DNAT_TRANSLATED_PORT', nat.name)
    assert generate_firewall(parse_panos_firewall(PANOS.read_text(), '11.1'), 'fortios', PANOS_MAPPINGS, 1).status == 'REVIEW_REQUIRED'


@pytest.mark.parametrize('count', [1, 2])
def test_secondary_physical_addresses_block_before_adapter_loss(count):
    ir = parse_panos_firewall(_panos_with(lambda root: _extra_address(root, count=count)), '11.1')
    interface = next(item for item in ir.interfaces if item.name == 'ethernet1/1')
    assert interface.translation_status == 'BLOCKED' and interface.source_location
    _assert_blocked(generate_firewall(ir, 'fortios', PANOS_MAPPINGS, 1), 'MULTIPLE_INTERFACE_ADDRESSES', 'ethernet1/1')


@pytest.mark.parametrize(('kind', 'path', 'name'), [
    ('aggregate', './devices/entry/network/interface/aggregate-ethernet/entry/layer3/ip', 'ae1'),
    ('subinterface', './devices/entry/network/interface/ethernet/entry/layer3/units/entry/ip', 'ethernet1/1.101'),
])
def test_secondary_aggregate_and_subinterface_addresses_block(kind, path, name):
    def add(root):
        interfaces = root.find('./devices/entry/network/interface')
        assert interfaces is not None
        if kind == 'aggregate':
            ip = ET.SubElement(ET.SubElement(ET.SubElement(interfaces, 'aggregate-ethernet'), 'entry', {'name': name}), 'layer3')
            ET.SubElement(ET.SubElement(ip, 'ip'), 'entry', {'name': '192.0.2.1/30'})
        else:
            parent = root.find('./devices/entry/network/interface/ethernet/entry/layer3')
            assert parent is not None
            unit = ET.SubElement(ET.SubElement(parent, 'units'), 'entry', {'name': name})
            ET.SubElement(unit, 'tag').text = '101'
            ET.SubElement(ET.SubElement(unit, 'ip'), 'entry', {'name': '192.0.2.1/30'})
        _extra_address(root, path)
    ir = parse_panos_firewall(_panos_with(add), '11.1')
    assert next(item for item in ir.interfaces if item.name == name).translation_status == 'BLOCKED'
    _assert_blocked(generate_firewall(ir, 'fortios', PANOS_MAPPINGS, 1), 'MULTIPLE_INTERFACE_ADDRESSES', name)


@pytest.mark.parametrize('tag', ['dhcp-client', 'ipv6'])
def test_unmodeled_interface_addressing_blocks(tag):
    def add(root):
        layer3 = root.find('./devices/entry/network/interface/ethernet/entry/layer3')
        assert layer3 is not None
        ET.SubElement(layer3, tag)
    ir = parse_panos_firewall(_panos_with(add), '11.1')
    assert ir.interfaces[0].translation_status == 'BLOCKED'
    _assert_blocked(generate_firewall(ir, 'fortios', PANOS_MAPPINGS, 1), 'UNSUPPORTED_INTERFACE_ADDRESSING', 'ethernet1/1')


def test_duplicate_address_has_no_distinct_secondary_semantic():
    def duplicate(root):
        ip = root.find('./devices/entry/network/interface/ethernet/entry/layer3/ip')
        assert ip is not None
        ET.SubElement(ip, 'entry', {'name': '203.0.113.2/30'})
    ir = parse_panos_firewall(_panos_with(duplicate), '11.1')
    assert generate_firewall(ir, 'fortios', PANOS_MAPPINGS, 1).status == 'REVIEW_REQUIRED'


def test_aggregate_subinterface_is_blocked_before_adapter_omits_it():
    def add(root):
        interfaces = root.find('./devices/entry/network/interface')
        assert interfaces is not None
        aggregate = ET.SubElement(ET.SubElement(interfaces, 'aggregate-ethernet'), 'entry', {'name': 'ae1'})
        unit = ET.SubElement(ET.SubElement(ET.SubElement(aggregate, 'layer3'), 'units'), 'entry', {'name': 'ae1.101'})
        ET.SubElement(unit, 'tag').text = '101'
    ir = parse_panos_firewall(_panos_with(add), '11.1')
    assert next(item for item in ir.interfaces if item.name == 'ae1').translation_status == 'BLOCKED'
    _assert_blocked(generate_firewall(ir, 'fortios', PANOS_MAPPINGS, 1), 'UNSUPPORTED_INTERFACE_KIND', 'ae1')


@pytest.mark.parametrize('kind', ['vlan', 'loopback'])
def test_unmodeled_logical_interfaces_block(kind):
    def add(root):
        interfaces = root.find('./devices/entry/network/interface')
        assert interfaces is not None
        ET.SubElement(ET.SubElement(ET.SubElement(interfaces, kind), 'units'), 'entry', {'name': f'{kind}.1'})
    ir = parse_panos_firewall(_panos_with(add), '11.1')
    _assert_blocked(generate_firewall(ir, 'fortios', PANOS_MAPPINGS, 1), 'UNSUPPORTED_INTERFACE_KIND', f'{kind}.1')


def test_validator_blocks_direct_ir_translated_port_and_nondefault_route():
    ir = parse_panos_firewall(PANOS.read_text(), '11.1')
    dnat = next(item for item in ir.nat if item.kind == 'dnat')
    dnat.translated_port = '9443'
    _assert_blocked(generate_firewall(ir, 'fortios', PANOS_MAPPINGS, 1), 'UNSUPPORTED_DNAT_TRANSLATED_PORT', dnat.name)
    dnat.translated_port = None
    ir.routes[0].router = 'VR2'
    _assert_blocked(generate_firewall(ir, 'fortios', PANOS_MAPPINGS, 1), 'UNSUPPORTED_ROUTING_CONTEXT', ir.routes[0].name)


@pytest.mark.parametrize('with_route', [True, False])
def test_second_router_blocks_even_if_it_has_no_routes(with_route):
    ir = parse_panos_firewall(_panos_with(lambda root: _extra_router(root, with_route)), '11.1')
    candidate = generate_firewall(ir, 'fortios', PANOS_MAPPINGS, 1)
    _assert_blocked(candidate, 'UNSUPPORTED_ROUTING_CONTEXT', 'VR2')
    if with_route:
        assert any(route.translation_status == 'BLOCKED' for route in ir.routes)


def test_single_nondefault_router_blocks_and_default_route_is_preserved():
    def rename(root):
        root.find('./devices/entry/network/virtual-router/entry').set('name', 'VR2')
    ir = parse_panos_firewall(_panos_with(rename), '11.1')
    _assert_blocked(generate_firewall(ir, 'fortios', PANOS_MAPPINGS, 1), 'UNSUPPORTED_ROUTING_CONTEXT', 'VR2')
    assert generate_firewall(parse_panos_firewall(PANOS.read_text(), '11.1'), 'fortios', PANOS_MAPPINGS, 1).status == 'REVIEW_REQUIRED'


@pytest.mark.parametrize(('source_os', 'text', 'target_os', 'mapping', 'code'), [
    ('fortios', None, 'panos', {'zones': {'LAN': 'any'}}, 'RESERVED_TARGET_IDENTITY'),
    ('fortios', None, 'panos', {'addresses': {'CLIENTS': 'AnY'}}, 'RESERVED_TARGET_IDENTITY'),
    ('fortios', None, 'panos', {'addresses': {'CLIENT_GROUP': 'any'}}, 'RESERVED_TARGET_IDENTITY'),
    ('fortios', None, 'panos', {'services': {'TCP_8443': 'any'}}, 'RESERVED_TARGET_IDENTITY'),
    ('fortios', None, 'panos', {'services': {'WEB_GROUP': 'any'}}, 'RESERVED_TARGET_IDENTITY'),
    ('panos', None, 'fortios', {'addresses': {'CLIENTS': 'ALL'}}, 'RESERVED_TARGET_IDENTITY'),
    ('panos', 'port', 'fortios', {}, 'UNSUPPORTED_DNAT_TRANSLATED_PORT'),
    ('panos', 'address', 'fortios', {}, 'MULTIPLE_INTERFACE_ADDRESSES'),
    ('panos', 'router', 'fortios', {}, 'UNSUPPORTED_ROUTING_CONTEXT'),
    ('panos', 'empty_router', 'fortios', {}, 'UNSUPPORTED_ROUTING_CONTEXT'),
    ('panos', 'nondefault_router', 'fortios', {}, 'UNSUPPORTED_ROUTING_CONTEXT'),
])
def test_semantic_blockers_reject_acknowledged_api_export(source_os, text, target_os, mapping, code):
    from fastapi.testclient import TestClient
    from confighop_api.main import create_app

    def nondefault_router(root):
        root.find('./devices/entry/network/virtual-router/entry').set('name', 'VR2')
    changes = {'port': _translated_port, 'address': _extra_address, 'router': _extra_router,
        'empty_router': lambda root: _extra_router(root, False), 'nondefault_router': nondefault_router}
    source = FIXTURE.read_text() if source_os == 'fortios' else _panos_with(changes[text]) if text else PANOS.read_text()
    interfaces = FORTIOS_MAPPINGS.interfaces if source_os == 'fortios' else PANOS_MAPPINGS.interfaces
    headers = {'X-ConfigHop-Client': 'web'}
    with TestClient(create_app()) as client:
        response = client.post('/api/v1/firewall-projects', headers=headers,
            json={'text': source, 'source_os': source_os, 'source_version': '7.4' if source_os == 'fortios' else '11.1'})
        assert response.status_code == 200, response.text
        path = f"/api/v1/firewall-projects/{response.json()['project_id']}"
        preview = client.put(path + '/preview', headers=headers, json={
            'revision': 1, 'target_os': target_os, 'target_version': '11.1' if target_os == 'panos' else '7.4',
            'mappings': {'interfaces': interfaces, **mapping}})
        assert preview.status_code == 200, preview.text
        candidate = preview.json()['candidate']
        assert candidate['status'] == 'BLOCKED' and not candidate['text']
        assert any(item['code'] == code and item['severity'] == 'BLOCKED' for item in candidate['findings'])
        export = {'revision': 1, 'sha256': candidate['sha256'], 'acknowledge_review': True}
        assert client.post(path + '/export', headers=headers, json=export).status_code == 409


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
