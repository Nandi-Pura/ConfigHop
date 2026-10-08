from pathlib import Path

import pytest
from pydantic import ValidationError

from confighop_core import inspect_switch_config
from confighop_core.evidence.switch import SWITCH_EVIDENCE
from confighop_core.evidence.registry import EvidenceRecord
from confighop_core.hardware.switch import get_switch_profile, switch_version_support, SWITCH_PROFILES
from confighop_core.models.hardware import PlatformDomain, SoftwareFamily, TargetRenderSupport
from confighop_core.models.switch import SwitchConfig, SwitchPlatform, SwitchportMode, Vlan, vlan_id
from confighop_core.parsers.switch_common import vlan_list

FIXTURES = Path(__file__).parent / "fixtures/switch"
CISCO = ("cisco", SoftwareFamily.IOS_XE, "17.12.1", "cisco-c9300-48p")
ARUBA = ("hpe_aruba", SoftwareFamily.AOS_CX, "10.15", "hpe-aruba-jl663a")


def load(name: str, context: tuple) -> SwitchConfig:
    return inspect_switch_config((FIXTURES / name).read_text(), *context)


def test_canonical_vlan_enum_and_deterministic_order():
    assert Vlan(id=1).id == 1 and Vlan(id=4094).id == 4094
    for invalid in (0, 4095):
        with pytest.raises(ValidationError):
            Vlan(id=invalid)
    assert SwitchportMode.ACCESS.value == "ACCESS"
    assert vlan_list("10,20-25,30,10") == [10, 20, 21, 22, 23, 24, 25, 30]
    for invalid in ("10-9", "0", "4095", "10,broken"):
        with pytest.raises(ValueError):
            vlan_list(invalid)
    config = SwitchConfig(platform=SwitchPlatform(vendor="cisco", software_family=SoftwareFamily.IOS_XE,
        software_version="17.12", hardware_profile_id="cisco-c9300-48p"), vlans=[Vlan(id=30), Vlan(id=10)])
    assert [vlan.id for vlan in config.vlans] == [10, 30]


def test_cisco_basic_parser_and_lag_closure():
    config = load("cisco_iosxe_17_12_basic.txt", CISCO)
    assert config.hostname == "C9300-LAB"
    assert [(v.id, v.name) for v in config.vlans] == [(10, "USERS"), (20, "VOICE"), (30, "SERVERS"), (99, "MANAGEMENT"), (999, "NATIVE")]
    access, trunk = config.physical_interfaces
    assert access.description == "User desk" and access.admin_enabled
    assert access.switchport_mode == SwitchportMode.ACCESS and access.access_vlan == 10 and access.voice_vlan == 20
    assert access.stp_edge and config.stp.edge_interfaces == [access.name]
    assert trunk.switchport_mode == SwitchportMode.TRUNK and trunk.native_vlan == 999
    assert trunk.allowed_vlans == [10, 20, 30, 99, 999]
    assert len(config.lags) == 1 and config.lags[0].id == 10
    assert config.lags[0].members == [trunk.name] and config.lags[0].protocol == "LACP"
    assert config.lags[0].mode == "ACTIVE" and config.lags[0].description == "Lab LAG"
    assert config.svis[0].vlan_id == 99 and config.svis[0].ip_addresses == ["192.0.2.10/24"]
    assert config.static_routes[0].destination == "0.0.0.0/0"
    assert config.stp.global_mode == "RAPID_PVST"
    assert {warning.code for warning in config.parser_warnings} == {"UNSUPPORTED_FEATURE"}
    assert config.vendor_extensions[0].feature == "router"
    assert config.model_dump() == load("cisco_iosxe_17_12_basic.txt", CISCO).model_dump()


def test_cisco_conflicts_ranges_routed_port_and_references():
    config = load("cisco_iosxe_17_12_edge_cases.txt", CISCO)
    port = config.physical_interfaces[0]
    assert port.switchport_mode == SwitchportMode.ACCESS and port.lag_id == 10
    routed = config.physical_interfaces[1]
    assert routed.switchport_mode == SwitchportMode.ROUTED and routed.ip_addresses == ["198.51.100.2/24"]
    assert config.physical_interfaces[2].allowed_vlans == [10, 20, 21, 22, 23, 24, 25, 30]
    assert len(config.lags) == 1 and config.lags[0].members == [port.name]
    codes = {warning.code for warning in config.parser_warnings}
    assert {"CONFLICTING_DECLARATION", "INVALID_VLAN", "INVALID_VLAN_LIST", "UNDEFINED_VLAN", "MISSING_LAG_BLOCK", "UNSUPPORTED_FEATURE"} <= codes
    assert config.svis[0].vlan_id == 100 and all(v.id != 4095 for v in config.vlans)


def test_aruba_basic_parser_and_lag_closure():
    config = load("aruba_aoscx_10_15_basic.txt", ARUBA)
    assert config.hostname == "CX6300-LAB"
    assert config.physical_interfaces[0].name == "1/1/1"
    assert config.physical_interfaces[0].switchport_mode == SwitchportMode.ACCESS
    assert config.physical_interfaces[0].access_vlan == 10 and config.physical_interfaces[0].stp_edge
    assert config.lags[0].id == 10 and config.lags[0].members == ["1/1/2"]
    assert config.lags[0].protocol == "LACP" and config.lags[0].mode == "ACTIVE"
    assert config.lags[0].switchport_mode == SwitchportMode.TRUNK
    assert config.lags[0].native_vlan == 999 and config.lags[0].allowed_vlans == [10, 20, 30, 99, 999]
    assert config.svis[0].vlan_id == 99 and config.svis[0].ip_addresses == ["192.0.2.10/24"]
    assert config.static_routes[0].destination == "0.0.0.0/0"
    assert config.stp.global_mode == "MSTP"
    assert {warning.code for warning in config.parser_warnings} == {"UNSUPPORTED_FEATURE"}
    assert config.vendor_extensions[0].feature == "vsx"
    assert config.model_dump() == load("aruba_aoscx_10_15_basic.txt", ARUBA).model_dump()


def test_aruba_conflicts_ranges_and_references():
    config = load("aruba_aoscx_10_15_edge_cases.txt", ARUBA)
    assert config.physical_interfaces[0].lag_id == 10
    assert config.physical_interfaces[0].switchport_mode == SwitchportMode.ACCESS
    assert config.physical_interfaces[1].allowed_vlans == [10, 20, 21, 22, 23, 24, 25, 30]
    assert len(config.lags) == 1 and config.lags[0].members == ["1/1/1"]
    codes = {warning.code for warning in config.parser_warnings}
    assert {"CONFLICTING_DECLARATION", "INVALID_VLAN", "INVALID_VLAN_LIST", "UNDEFINED_VLAN", "MISSING_LAG_BLOCK", "UNSUPPORTED_FEATURE"} <= codes


def test_bounded_normalization_equivalence_without_conversion():
    cisco = load("cisco_iosxe_17_12_basic.txt", CISCO)
    aruba = load("aruba_aoscx_10_15_basic.txt", ARUBA)
    assert [(v.id, v.name) for v in cisco.vlans] == [(v.id, v.name) for v in aruba.vlans]
    assert cisco.physical_interfaces[0].access_vlan == aruba.physical_interfaces[0].access_vlan == 10
    assert cisco.lags[0].id == aruba.lags[0].id == 10
    assert cisco.svis[0].vlan_id == aruba.svis[0].vlan_id == 99
    assert cisco.stp.global_mode != aruba.stp.global_mode


def test_exact_hardware_and_official_evidence():
    assert len(SWITCH_PROFILES) == 2
    cisco = get_switch_profile("cisco-c9300-48p")
    aruba = get_switch_profile("hpe-aruba-jl663a")
    assert cisco.domain == aruba.domain == PlatformDomain.SWITCH
    assert cisco.software_family == SoftwareFamily.IOS_XE
    assert aruba.software_family == SoftwareFamily.AOS_CX
    assert cisco.model == "C9300-48P" and len(cisco.interfaces) == 48
    assert all(port.name.startswith("GigabitEthernet1/0/") for port in cisco.interfaces)
    assert aruba.model == "JL663A" and aruba.series == "CX 6300M 48G"
    assert len(aruba.interfaces) == 52 and aruba.interfaces[-1].name == "1/1/52"
    assert aruba.interfaces[48].media == "SFP56"
    assert aruba.interfaces[48].speed_capabilities == ["1G", "10G", "25G", "50G"]
    assert all(profile.target_render_support == TargetRenderSupport.ANALYSIS_ONLY for profile in SWITCH_PROFILES.values())
    assert all(profile.supported_panos_trains == [] for profile in SWITCH_PROFILES.values())
    for profile in SWITCH_PROFILES.values():
        ids = profile.evidence_ids + [id for port in profile.interfaces for id in port.evidence_ids]
        ids += [id for rule in profile.software_support_rules for id in rule.evidence_ids]
        assert all(id in SWITCH_EVIDENCE and SWITCH_EVIDENCE[id].source_url.startswith("https://") for id in ids)
    assert len(SWITCH_EVIDENCE) == 5
    with pytest.raises(ValidationError):
        EvidenceRecord(id="wrong-vendor", vendor="cisco", source_title="Wrong", source_url=SWITCH_EVIDENCE["ARUBA-JL663A-PORTS"].source_url,
            source_type="TEST", scope="test", summary="test")


def test_version_and_explicit_context_fail_closed(monkeypatch):
    assert switch_version_support(CISCO[3], "17.12") == "SUPPORTED"
    assert switch_version_support(CISCO[3], "17.12.4") == "SUPPORTED"
    assert switch_version_support(CISCO[3], "17.13") == "VERSION_NOT_VERIFIED"
    assert switch_version_support(ARUBA[3], "10.15") == "SUPPORTED"
    assert switch_version_support(ARUBA[3], "10.16") == "VERSION_NOT_VERIFIED"
    assert switch_version_support("missing", "17.12") == "UNKNOWN_HARDWARE"
    with pytest.raises(ValueError, match="VERSION_NOT_VERIFIED"):
        inspect_switch_config("hostname X", *CISCO[:2], "17.13", CISCO[3])
    with pytest.raises(ValueError, match="do not match"):
        inspect_switch_config("hostname X", "hpe_aruba", SoftwareFamily.IOS_XE, "17.12", CISCO[3])
    monkeypatch.setattr("confighop_core.switch_inspection.MAX_SWITCH_TEXT_BYTES", 5)
    with pytest.raises(Exception, match="100 MiB"):
        inspect_switch_config("hostname X", *CISCO)


def test_unknown_modular_uplink_is_not_verified():
    config = inspect_switch_config("interface TenGigabitEthernet1/1/1\n description unknown module", *CISCO)
    assert "HARDWARE_PORT_NOT_VERIFIED" in {warning.code for warning in config.parser_warnings}
    assert not any(port.name == "TenGigabitEthernet1/1/1" for port in get_switch_profile(CISCO[3]).interfaces)


@pytest.mark.parametrize("name", ["GigabitEthernet1/0/1", "TenGigabitEthernet1/1/1", "TwentyFiveGigE1/1/1", "FortyGigabitEthernet1/1/1"])
def test_cisco_physical_interface_types_and_admin_state(name):
    config = inspect_switch_config(f"interface {name}\n shutdown\n description Lab port", *CISCO)
    assert config.physical_interfaces[0].name == name
    assert config.physical_interfaces[0].admin_enabled is False
    assert config.physical_interfaces[0].description == "Lab port"


def test_cisco_lag_modes_and_invalid_references():
    passive = inspect_switch_config("interface GigabitEthernet1/0/1\n channel-group 4 mode passive", *CISCO)
    static = inspect_switch_config("interface GigabitEthernet1/0/1\n channel-group 4 mode on", *CISCO)
    assert passive.lags[0].protocol == "LACP" and passive.lags[0].mode == "PASSIVE"
    assert static.lags[0].protocol == "STATIC" and static.lags[0].mode == "ON"
    bad = inspect_switch_config("vlan 4095\ninterface GigabitEthernet1/0/1\n switchport access vlan nope", *CISCO)
    assert not bad.vlans and bad.physical_interfaces[0].access_vlan is None
    assert {w.code for w in bad.parser_warnings} == {"INVALID_VLAN"}


def test_aruba_shutdown_passive_lacp_and_invalid_references():
    config = inspect_switch_config("interface 1/1/1\n shutdown\n lag 4\ninterface lag 4\n lacp mode passive", *ARUBA)
    assert config.physical_interfaces[0].admin_enabled is False
    assert config.lags[0].members == ["1/1/1"]
    assert config.lags[0].protocol == "LACP" and config.lags[0].mode == "PASSIVE"
    bad = inspect_switch_config("vlan 0\ninterface 1/1/1\n vlan access nope", *ARUBA)
    assert not bad.vlans and bad.physical_interfaces[0].access_vlan is None
    assert {w.code for w in bad.parser_warnings} == {"INVALID_VLAN"}


def test_incompatible_layer_two_and_ip_state_is_visible():
    cisco = inspect_switch_config("interface GigabitEthernet1/0/1\n switchport mode access\n ip address 192.0.2.10 255.255.255.0", *CISCO)
    aruba = inspect_switch_config("interface 1/1/1\n vlan access 10\n ip address 192.0.2.10/24", *ARUBA)
    for config in (cisco, aruba):
        assert "SWITCHPORT_IP_CONFLICT" in {warning.code for warning in config.parser_warnings}


def test_cisco_route_with_egress_interface():
    config = inspect_switch_config("ip route 203.0.113.0 255.255.255.0 GigabitEthernet1/0/1 192.0.2.1 10", *CISCO)
    route = config.static_routes[0]
    assert (route.destination, route.egress_interface, route.next_hop, route.metric) == (
        "203.0.113.0/24", "GigabitEthernet1/0/1", "192.0.2.1", 10)
