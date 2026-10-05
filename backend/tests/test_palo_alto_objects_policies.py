def test_shared_and_vsys_objects_keep_scopes(complex_inventory):
    repeated = [obj for obj in complex_inventory.address_objects if obj.name == "repeat-name"]
    assert [(obj.scope.type, obj.scope.name, obj.kind) for obj in repeated] == [
        ("shared", None, "fqdn"), ("vsys", "vsys1", "ip-range"),
    ]
    assert repeated[0].value == "example.invalid"
    assert repeated[1].value == "192.0.2.10-192.0.2.20"
    assert [(service.name, service.protocol, service.destination_port) for service in complex_inventory.service_objects] == [
        ("shared-http", "tcp", "80"), ("dns-service", "udp", "53"),
    ]


def test_security_order_and_fields(minimal):
    assert [rule.name for rule in minimal.security_rules] == ["allow-web", "deny-other"]
    assert minimal.security_rules[0].uuid == "synthetic-rule-1"
    assert minimal.security_rules[0].vsys == "vsys1"
    assert minimal.security_rules[0].from_zones == ["trust"]
    assert minimal.security_rules[0].to_zones == ["inside"]
    assert minimal.security_rules[0].sources == ["shared-net"]
    assert minimal.security_rules[0].destinations == ["vsys-host"]
    assert minimal.security_rules[0].applications == ["web-browsing"]
    assert minimal.security_rules[0].services == ["shared-web"]
    assert minimal.security_rules[0].action == "allow"
    assert minimal.security_rules[1].disabled is True


def test_nat_interface_reference_and_translation_form(complex_inventory):
    nat = complex_inventory.nat_rules[0]
    assert nat.name == "loopback-nat"
    assert nat.vsys == "vsys1"
    assert nat.source_translation_type == "dynamic-ip-and-port"
    assert nat.interface_references == ["loopback.1"]
    assert nat.from_zones == ["inside"]
    assert nat.to_zones == ["outside"]


def test_minimal_fixture_has_exact_contract_counts(minimal):
    assert [len(getattr(minimal, field)) for field in (
        "physical_interfaces", "subinterfaces", "aggregate_interfaces", "vlan_interfaces", "loopback_interfaces",
        "zones", "virtual_routers", "static_routes", "address_objects", "service_objects", "security_rules", "nat_rules",
    )] == [5, 2, 1, 1, 1, 2, 1, 2, 2, 2, 2, 1]
    assert minimal.warnings == []
