import json
import subprocess
import sys
from pathlib import Path

import pytest

from confighop_core import parse_palo_alto_xml
from confighop_core.errors import ConfigTooLargeError, MalformedXmlError, UnsupportedConfigFormatError
from confighop_core.parsers.palo_alto.parser import MAX_XML_BYTES


def test_metadata_and_json_contract(minimal):
    assert minimal.platform.vendor == "palo_alto"
    assert minimal.platform.config_version == "11.1.0"
    assert minimal.platform.detail_version == "11.1.4"
    assert minimal.platform.source_format == "panos_xml"
    assert [entry.name for entry in minimal.device_entries] == ["synthetic-device"]
    assert minimal.vsys_names == ["vsys1"]
    output = json.loads(minimal.model_dump_json())
    assert output["platform"]["detail_version"] == "11.1.4"
    assert output["physical_interfaces"][0]["name"] == "ethernet1/1"


def test_unknown_unrelated_sections_are_ignored(complex_inventory):
    assert complex_inventory.platform.config_version == "11.1.0"
    assert complex_inventory.vsys_names == ["vsys1", "vsys2"]
    assert complex_inventory.warnings == []


def test_malformed_and_unsafe_xml_are_controlled(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("<config><devices>", encoding="utf-8")
    with pytest.raises(MalformedXmlError, match="malformed"):
        parse_palo_alto_xml(bad)
    bad.write_text('<!DOCTYPE config [<!ENTITY x SYSTEM "file:///private">]><config>&x;</config>', encoding="utf-8")
    with pytest.raises(MalformedXmlError, match="prohibited"):
        parse_palo_alto_xml(bad)
    bad.write_text("<another-root />", encoding="utf-8")
    with pytest.raises(UnsupportedConfigFormatError):
        parse_palo_alto_xml(bad)


def test_oversized_input_is_rejected_before_read(tmp_path):
    huge = tmp_path / "too-large.xml"
    with huge.open("wb") as file:
        file.truncate(MAX_XML_BYTES + 1)
    with pytest.raises(ConfigTooLargeError, match="100 MiB"):
        parse_palo_alto_xml(huge)


def test_invalid_ip_is_preserved_with_redacted_warning(tmp_path):
    source = tmp_path / "invalid-ip.xml"
    source.write_text('<config><devices><entry name="device"><network><interface><ethernet><entry name="ethernet1/1"><layer3><ip><entry name="not-an-ip" /></ip></layer3></entry></ethernet></interface></network></entry></devices></config>', encoding="utf-8")
    inventory = parse_palo_alto_xml(source)
    assert inventory.physical_interfaces[0].ip_addresses == ["not-an-ip"]
    assert inventory.warnings[0].code == "INVALID_IP_VALUE"
    assert "not-an-ip" not in inventory.warnings[0].message


def test_unknown_interface_and_route_nexthop_are_safe(tmp_path):
    source = tmp_path / "unknown.xml"
    source.write_text('<config><devices><entry name="device"><network><interface><ethernet><entry name="ethernet1/9" /></ethernet></interface><virtual-router><entry name="vr"><routing-table><ip><static-route><entry name="route"><nexthop><custom-hop>opaque</custom-hop></nexthop></entry></static-route></ip></routing-table></entry></virtual-router></network></entry></devices></config>', encoding="utf-8")
    inventory = parse_palo_alto_xml(source)
    assert inventory.physical_interfaces[0].mode == "unknown"
    assert inventory.static_routes[0].next_hop_type == "custom-hop"
    assert inventory.warnings[0].code == "UNSUPPORTED_ROUTE_NEXTHOP"
    assert "opaque" not in inventory.warnings[0].message


def test_inspection_command_prints_counts_only():
    fixture = Path(__file__).parent / "fixtures" / "paloalto" / "pa_minimal.xml"
    result = subprocess.run([sys.executable, "-m", "confighop_core.inspect", str(fixture)], capture_output=True, text=True, check=True)
    assert "Physical Ethernet: 5" in result.stdout
    assert "Security Rules: 2" in result.stdout
    assert "192.0.2.1/24" not in result.stdout
    assert "shared-net" not in result.stdout
    assert "outbound-nat" not in result.stdout
