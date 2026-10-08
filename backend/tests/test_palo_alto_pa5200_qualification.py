from pathlib import Path

import pytest

from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.compatibility import assess, version_support
from confighop_core.evidence.registry import EVIDENCE
from confighop_core.hardware.registry import get_profile
from confighop_core.models.hardware import CandidateSupport, ProfileStatus, TargetRenderSupport
from confighop_core.models.mapping import InterfaceMapping, PreviewStatus


FIXTURE = Path(__file__).parent / "fixtures/paloalto/pa5220_reference_migration.xml"
NEGATIVE = Path(__file__).parent / "fixtures/paloalto/pa5220_unmodeled_reference.xml"
MODELS = {"5220": ("40G",), "5250": ("40G", "100G"),
          "5260": ("40G", "100G"), "5280": ("40G", "100G")}


@pytest.mark.parametrize("model,speeds", MODELS.items())
def test_each_pa5200_hardware_software_and_mode_boundary(model, speeds):
    profile = get_profile(f"paloalto-pa-{model}")
    assert profile.profile_status == ProfileStatus.VERIFIED
    assert profile.target_render_support == TargetRenderSupport.ANALYSIS_ONLY
    assert [port.name for port in profile.interfaces] == [f"ethernet1/{i}" for i in range(1, 25)]
    assert {port.media for port in profile.interfaces[:4]} == {"RJ45"}
    assert {port.media for port in profile.interfaces[4:20]} == {"SFP"}
    assert tuple(profile.interfaces[20].speed_capabilities) == speeds
    assert all(port.candidate_support == CandidateSupport.SUPPORTED for port in profile.interfaces)
    assert all(port.required_condition == "NONE" for port in profile.interfaces)
    assert all(port.parent_interface is None for port in profile.interfaces)
    assert version_support(profile.id, "11.1.4") == "SUPPORTED"
    assert version_support(profile.id, "12.1.2") == "UNSUPPORTED"
    assert version_support(profile.id, "13.0.1") == "VERSION_NOT_VERIFIED"
    assert all(EVIDENCE[key].source_url.startswith("https://docs.paloaltonetworks.com/")
               for key in profile.evidence_ids)
    assert not any(EVIDENCE[key].device_validated for key in profile.evidence_ids)


@pytest.mark.parametrize("model", MODELS)
def test_each_pa5200_generic_renderer_mechanics_without_promotion(model, tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(FIXTURE.read_bytes())
    before = source.read_bytes()
    inventory = parse_palo_alto_xml(source)
    profile = get_profile(f"paloalto-pa-{model}")
    qualification_profile = profile.model_copy(update={"target_render_support": TargetRenderSupport.SUPPORTED})
    mappings = [InterfaceMapping(source_interface="ethernet1/5", target_interface="ethernet1/9"),
                InterfaceMapping(source_interface="ethernet1/6", target_interface="ethernet1/10")]
    preview = preview_interface_mappings(inventory, mappings, qualification_profile)
    output = tmp_path / "candidate.xml"
    result = render_panos_candidate(source, inventory, preview, qualification_profile, output, allow_review=True)
    assert result.validation.valid
    assert result.validation.candidate_parse_ok and result.validation.expected_inventory_match
    assert result.validation.postconditions_passed and result.validation.preservation_audit_ok
    assert source.read_bytes() == before
    after = parse_palo_alto_xml(output)
    # Qualification-only profile exposes the missing PA-5200 RJ45 normalization: the
    # generic renderer preserves a manual value although official hardware docs say auto-only.
    assert next(port for port in after.physical_interfaces if port.name == "ethernet1/1").link_speed == "1000"
    assert {child.name for child in after.subinterfaces} == {"ethernet1/9.100", "ethernet1/9.200"}
    assert after.zones[0].interface_members == ["ethernet1/9.100"]
    assert after.virtual_routers[0].interface_members[:2] == ["ethernet1/9.100", "ethernet1/9.200"]
    assert after.static_routes[0].egress_interface == "ethernet1/9.100"
    assert after.nat_rules[0].interface_references == ["ethernet1/9.100"]
    assert after.aggregate_interfaces[0].member_interfaces == ["ethernet1/10"]
    assert after.security_rules == inventory.security_rules
    assert after.address_objects == inventory.address_objects
    assert after.service_objects == inventory.service_objects
    assert all(not change.category.startswith("ASSERT_") for change in result.semantic_diff.changes)

    unsafe = parse_palo_alto_xml(NEGATIVE)
    unsafe_preview = preview_interface_mappings(unsafe, [mappings[0]], qualification_profile)
    blocked = render_panos_candidate(NEGATIVE, unsafe, unsafe_preview, qualification_profile,
        tmp_path / "unsafe.xml", allow_review=True)
    assert blocked.status == PreviewStatus.BLOCKED
    assert "UNMODELED_INTERFACE_REFERENCE" in {finding.code for finding in blocked.plan.findings}
    assert not (tmp_path / "unsafe.xml").exists()


@pytest.mark.parametrize("model", MODELS)
def test_each_pa5200_negative_hardware_and_version_gates(model, tmp_path):
    profile_id = f"paloalto-pa-{model}"
    source = tmp_path / "source.xml"
    source.write_bytes(FIXTURE.read_bytes())
    inventory = parse_palo_alto_xml(source)
    bad_target = assess(inventory, "paloalto-pa-5220", "11.1", profile_id, "11.1",
        [InterfaceMapping(source_interface="ethernet1/5", target_interface="ethernet1/41")])
    assert "TARGET_INTERFACE_NOT_FOUND" in {finding.code for finding in bad_target.findings}
    collision = assess(inventory, "paloalto-pa-5220", "11.1", profile_id, "11.1",
        [InterfaceMapping(source_interface="ethernet1/5", target_interface="ethernet1/9"),
         InterfaceMapping(source_interface="ethernet1/6", target_interface="ethernet1/9")])
    assert "TARGET_HARDWARE_PROFILE_MISMATCH" in {finding.code for finding in collision.findings}
    speed = assess(inventory, "paloalto-pa-5220", "11.1", profile_id, "11.1",
        [InterfaceMapping(source_interface="ethernet1/21", target_interface="ethernet1/5")])
    assert "TARGET_SPEED_UNSUPPORTED" in {finding.code for finding in speed.findings}
    media = assess(inventory, "paloalto-pa-5220", "11.1", profile_id, "11.1",
        [InterfaceMapping(source_interface="ethernet1/1", target_interface="ethernet1/5")])
    assert "MEDIA_CHANGE_REVIEW" in {finding.code for finding in media.findings}
    mismatch = source.read_bytes().replace(b'entry name="ethernet1/21"', b'entry name="ethernet1/25"')
    source.write_bytes(mismatch)
    assert "SOURCE_HARDWARE_PROFILE_MISMATCH" in {finding.code for finding in assess(
        parse_palo_alto_xml(source), "paloalto-pa-5220", "11.1", profile_id, "11.1", []).findings}
    assert version_support(profile_id, "12.1.2") == "UNSUPPORTED"
