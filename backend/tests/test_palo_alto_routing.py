def test_virtual_router_membership_and_next_hops(complex_inventory):
    routers = {item.name: item for item in complex_inventory.virtual_routers}
    assert routers["vr-external"].interface_members == ["ethernet1/12.265", "ethernet1/12.266"]
    assert routers["vr-external"].static_route_names == ["to-example", "to-internal"]
    routes = {item.name: item for item in complex_inventory.static_routes}
    assert routes["to-example"].virtual_router == "vr-external"
    assert routes["to-example"].destination == "203.0.113.0/24"
    assert routes["to-example"].egress_interface == "ethernet1/12.265"
    assert routes["to-example"].next_hop_type == "ip-address"
    assert routes["to-example"].next_hop_value == "192.0.2.46"
    assert routes["to-internal"].next_hop_type == "next-vr"
    assert routes["to-internal"].next_hop_value == "vr-internal"


def test_metric_and_route_order(minimal):
    assert [route.name for route in minimal.static_routes] == ["default-route", "internal-route"]
    assert minimal.static_routes[0].metric == 10
    assert minimal.static_routes[1].next_hop_type == "next-vr"
