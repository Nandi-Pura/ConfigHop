from hashlib import sha256
from pathlib import Path

import pytest

from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.compatibility import assess
from confighop_core.hardware.registry import get_profile
from confighop_core.models.hardware import TargetRenderSupport
from confighop_core.models.mapping import InterfaceMapping, PreviewStatus, TargetInterfaceSettings
from confighop_core.models.transformation import OperationType


FIXTURES = Path(__file__).parent / "fixtures/paloalto"
REFERENCE = FIXTURES / "pa5220_reference_migration.xml"
TARGET = get_profile("paloalto-pa-5410")


def mapping(old, new, speed=None):
    return InterfaceMapping(source_interface=old, target_interface=new,
        target_settings=TargetInterfaceSettings(link_speed=speed) if speed else None)


def test_pa5220_to_pa5410_reference_migration(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(REFERENCE.read_bytes())
    before = source.read_bytes()
    mappings = [mapping("ethernet1/5", "ethernet1/9"), mapping("ethernet1/6", "ethernet1/10"),
                mapping("ethernet1/21", "ethernet1/41", "40G")]
    inventory = parse_palo_alto_xml(source)
    assessment = assess(inventory, "paloalto-pa-5220", "11.1", "paloalto-pa-5410", "11.1", mappings)
    assert assessment.status.value == "REVIEW_REQUIRED"
    preview = preview_interface_mappings(inventory, mappings, TARGET)
    assert preview.status == PreviewStatus.REVIEW_REQUIRED
    output = tmp_path / "candidate.xml"
    result = render_panos_candidate(source, inventory, preview, TARGET, output, allow_review=True)
    assert result.validation.valid is True, [f.code for f in result.plan.findings]
    assert source.read_bytes() == before
    assert result.plan.source_sha256 == sha256(before).hexdigest()
    candidate = parse_palo_alto_xml(output)
    assert {item.name for item in candidate.subinterfaces} == {"ethernet1/9.100", "ethernet1/9.200"}
    assert next(item for item in candidate.subinterfaces if item.name == "ethernet1/9.100").tag == 100
    assert candidate.aggregate_interfaces[0].member_interfaces == ["ethernet1/10"]
    assert candidate.aggregate_interfaces[0].name == "ae1"
    assert candidate.zones[0].interface_members == ["ethernet1/9.100"]
    assert candidate.virtual_routers[0].interface_members[:2] == ["ethernet1/9.100", "ethernet1/9.200"]
    assert candidate.static_routes[0].egress_interface == "ethernet1/9.100"
    assert candidate.nat_rules[0].interface_references == ["ethernet1/9.100"]
    assert candidate.security_rules == inventory.security_rules
    assert candidate.address_objects == inventory.address_objects
    assert candidate.service_objects == inventory.service_objects
    assert b"<unmodeled-safe><setting>synthetic-preserved</setting></unmodeled-safe>" in output.read_bytes()
    assert b"<link-speed>40000</link-speed>" in output.read_bytes()
    assert all(not change.category.startswith("ASSERT_") for change in result.semantic_diff.changes)
    assert any(op.operation_type == OperationType.ASSERT_AGGREGATE_MEMBERSHIP for op in result.plan.operations)


def test_reference_fixture_unknown_ospf_identity_blocks(tmp_path):
    source = FIXTURES / "pa5220_unmodeled_reference.xml"
    inventory = parse_palo_alto_xml(source)
    preview = preview_interface_mappings(inventory, [mapping("ethernet1/5", "ethernet1/9")], TARGET)
    output = tmp_path / "candidate.xml"
    result = render_panos_candidate(source, inventory, preview, TARGET, output)
    assert result.status == PreviewStatus.BLOCKED
    assert any(f.code == "UNMODELED_INTERFACE_REFERENCE" and "/ospf/" in f.message for f in result.plan.findings)
    assert not output.exists()


def test_source_profile_mismatch_and_implicit_target_validation(tmp_path):
    source = tmp_path / "source.xml"
    source.write_text('<config version="11.1" detail-version="11.1.4"><devices><entry name="localhost.localdomain"><network><interface><ethernet><entry name="ethernet1/25"><layer3/></entry></ethernet></interface></network></entry></devices></config>')
    inventory = parse_palo_alto_xml(source)
    assessment = assess(inventory, "paloalto-pa-5220", "11.1", "paloalto-pa-5410", "11.1", [])
    assert assessment.status.value == "BLOCKED"
    codes = {finding.code for finding in assessment.findings}
    assert "SOURCE_HARDWARE_PROFILE_MISMATCH" in codes
    assert "BREAKOUT_MODE_REQUIRED" in codes
    source.write_text(source.read_text().replace("ethernet1/25", "ethernet1/45"))
    inventory = parse_palo_alto_xml(source)
    codes = {finding.code for finding in assess(inventory, "paloalto-pa-5220", "11.1",
        "paloalto-pa-5410", "11.1", []).findings}
    assert "TARGET_INTERFACE_NOT_FOUND" in codes


def test_malformed_subinterface_identity_blocks_parent_rename(tmp_path):
    source = tmp_path / "source.xml"
    source.write_text('<config version="11.1"><devices><entry name="localhost.localdomain"><network><interface><ethernet><entry name="ethernet1/5"><layer3><units><entry name="ethernet1/6.100"><tag>100</tag></entry></units></layer3></entry></ethernet></interface></network></entry></devices></config>')
    inventory = parse_palo_alto_xml(source)
    preview = preview_interface_mappings(inventory, [mapping("ethernet1/5", "ethernet1/9")], TARGET)
    assert preview.status == PreviewStatus.BLOCKED
    assert "SUBINTERFACE_IDENTITY_INVALID" in {finding.code for finding in preview.findings}


@pytest.mark.parametrize("model", ["5220", "5250", "5260", "5280"])
def test_pa5200_target_promotion_remains_model_specific(model):
    profile = get_profile(f"paloalto-pa-{model}")
    assert profile.target_render_support == TargetRenderSupport.SCOPED
    assert all(port.name not in {"ethernet1/41", "ethernet1/25"} for port in profile.interfaces)
