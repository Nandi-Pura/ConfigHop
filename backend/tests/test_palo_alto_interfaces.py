def test_physical_modes_and_attributes(minimal):
    interfaces = {item.name: item for item in minimal.physical_interfaces}
    assert len(interfaces) == 5
    assert interfaces["ethernet1/1"].mode == "layer3"
    assert interfaces["ethernet1/1"].ip_addresses == ["192.0.2.1/24"]
    assert interfaces["ethernet1/1"].management_profile == "example-mgmt"
    assert interfaces["ethernet1/1"].comment == "Example uplink"
    assert interfaces["ethernet1/1"].link_state == "auto"
    assert interfaces["ethernet1/1"].link_speed == "auto"
    assert interfaces["ethernet1/1"].link_duplex == "auto"
    assert interfaces["ethernet1/2"].mode == "layer2"
    assert interfaces["ethernet1/5"].mode == "virtual_wire"
    assert interfaces["ethernet1/6"].mode == "aggregate_member"
    assert interfaces["ethernet1/6"].aggregate_group == "ae1"


def test_layer3_and_layer2_units_use_xml_parent(minimal):
    units = {item.name: item for item in minimal.subinterfaces}
    assert units["ethernet1/1.10"].parent_interface == "ethernet1/1"
    assert units["ethernet1/1.10"].mode == "layer3"
    assert units["ethernet1/1.10"].tag == 10
    assert units["ethernet1/1.10"].ip_addresses == ["192.0.2.10/24"]
    assert units["ethernet1/1.10"].management_profile == "example-sub-mgmt"
    assert units["ethernet1/1.10"].adjust_tcp_mss_enabled is True
    assert units["ethernet1/2.20"].parent_interface == "ethernet1/2"
    assert units["ethernet1/2.20"].mode == "layer2"
    assert units["ethernet1/2.20"].tag == 20
    assert units["ethernet1/2.20"].ip_addresses == []


def test_aggregate_vlan_and_loopback(minimal):
    aggregate = minimal.aggregate_interfaces[0]
    assert aggregate.name == "ae1"
    assert aggregate.member_interfaces == ["ethernet1/6", "ethernet1/7"]
    assert aggregate.ip_addresses == ["198.51.100.1/24"]
    assert minimal.vlan_interfaces[0].name == "vlan.10"
    assert minimal.vlan_interfaces[0].ip_addresses == ["203.0.113.1/24"]
    assert minimal.vlan_interfaces[0].management_profile == "vlan-mgmt"
    assert minimal.loopback_interfaces[0].name == "loopback.1"
    assert minimal.loopback_interfaces[0].ip_addresses == ["192.0.2.254/32"]


def test_five_child_topology_and_aggregate_inversion(complex_inventory):
    parent = next(item for item in complex_inventory.physical_interfaces if item.name == "ethernet1/12")
    assert parent.subinterface_names == [
        "ethernet1/12.262", "ethernet1/12.264", "ethernet1/12.265", "ethernet1/12.266", "ethernet1/12.2204",
    ]
    children = [item for item in complex_inventory.subinterfaces if item.parent_interface == "ethernet1/12"]
    assert [item.tag for item in children] == [262, 264, 265, 266, 2204]
    assert children[0].management_profile == "example-mgmt"
    assert children[0].ip_addresses == ["192.0.2.1/28"]
    assert complex_inventory.aggregate_interfaces[0].member_interfaces == ["ethernet1/1", "ethernet1/2"]
    assert next(item for item in complex_inventory.subinterfaces if item.name == "ethernet1/13.30").mode == "layer2"


def test_zone_vsys_ownership(complex_inventory):
    inside = [zone for zone in complex_inventory.zones if zone.name == "inside"]
    assert [(zone.vsys, zone.zone_type) for zone in inside] == [("vsys1", "layer3"), ("vsys2", "virtual_wire")]
    assert inside[0].interface_members == ["ethernet1/12.262"]
    assert inside[1].interface_members == ["ethernet1/13"]
