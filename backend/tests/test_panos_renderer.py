from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree as ET

import pytest

from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.hardware import load_hardware_profile
from confighop_core.models.mapping import InterfaceMapping, PreviewStatus
from confighop_core.models.transformation import OperationType
from confighop_core.transformation import build_transformation_plan
from confighop_core.validation import preservation_audit


FIXTURES = Path(__file__).parent / "fixtures"
PROFILE = FIXTURES / "hardware" / "paloalto_target_synthetic.json"
COMPLEX = FIXTURES / "paloalto" / "pa_complex_synthetic.xml"


def run(source: Path, output: Path, *pairs: tuple[str, str], allow_review=False, force=False):
    inventory = parse_palo_alto_xml(source)
    profile = load_hardware_profile(PROFILE)
    mappings = [InterfaceMapping(source_interface=old, target_interface=new) for old, new in pairs]
    preview = preview_interface_mappings(inventory, mappings, profile)
    return render_panos_candidate(source, inventory, preview, profile, output, allow_review=allow_review, force=force)


def small_xml(*names: str, members: tuple[str, ...] = ()) -> bytes:
    entries = "".join(f'<entry name="{name}"><comment>{name}-body</comment><layer3/></entry>' for name in names)
    refs = "".join(f"<member>{name}</member>" for name in members)
    return (f'<config version="11.1"><devices><entry name="localhost.localdomain">'
        f'<network><interface><ethernet>{entries}</ethernet></interface></network>'
        f'<vsys><entry name="vsys1"><zone><entry name="inside"><network><layer3>{refs}</layer3></network>'
        f'</entry></zone></entry></vsys></entry></devices><unknown-feature><value>preserve-me</value>'
        f'</unknown-feature><certificate-metadata>synthetic-only</certificate-metadata>'
        f'<log-setting>synthetic-only</log-setting><dynamic-routing>synthetic-only</dynamic-routing>'
        f'<!-- synthetic-preserve-comment --></config>').encode()


def test_complex_success_and_source_unchanged(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(COMPLEX.read_bytes())
    before = source.read_bytes()
    result = run(source, tmp_path / "candidate.xml", ("ethernet1/12", "ethernet1/50"))
    assert result.status == PreviewStatus.READY
    assert result.validation.candidate_parse_ok is True
    assert result.validation.expected_inventory_match is True
    assert result.validation.preservation_audit_ok is True
    assert result.validation.operations_applied == 16
    assert source.read_bytes() == before
    assert result.plan.source_sha256 == sha256(before).hexdigest()
    candidate = parse_palo_alto_xml(tmp_path / "candidate.xml")
    assert [child.name for child in candidate.subinterfaces if child.parent_interface == "ethernet1/50"] == [
        "ethernet1/50.262", "ethernet1/50.264", "ethernet1/50.265", "ethernet1/50.266", "ethernet1/50.2204"
    ]
    assert next(zone for zone in candidate.zones if zone.vsys == "vsys1" and zone.name == "inside").interface_members == ["ethernet1/50.262"]
    assert next(router for router in candidate.virtual_routers if router.name == "vr-external").interface_members == ["ethernet1/50.265", "ethernet1/50.266"]
    assert next(route for route in candidate.static_routes if route.name == "to-example").egress_interface == "ethernet1/50.265"
    assert b"<unrelated-feature>" in (tmp_path / "candidate.xml").read_bytes()


def test_physical_collision_blocks_without_output(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(small_xml("ethernet1/5", "ethernet1/12"))
    result = run(source, tmp_path / "candidate.xml", ("ethernet1/12", "ethernet1/5"))
    assert result.status == PreviewStatus.BLOCKED
    assert "TARGET_PHYSICAL_NAME_COLLISION" in {finding.code for finding in result.plan.findings}
    assert not (tmp_path / "candidate.xml").exists()


@pytest.mark.parametrize("names,pairs", [
    (("ethernet1/5", "ethernet1/12"), (("ethernet1/5", "ethernet1/12"), ("ethernet1/12", "ethernet1/5"))),
    (("ethernet1/1", "ethernet1/2", "ethernet1/3"), (("ethernet1/1", "ethernet1/2"), ("ethernet1/2", "ethernet1/3"), ("ethernet1/3", "ethernet1/1"))),
])
def test_atomic_swap_or_cycle(tmp_path, names, pairs):
    source = tmp_path / "source.xml"
    source.write_bytes(small_xml(*names))
    result = run(source, tmp_path / "candidate.xml", *pairs)
    assert result.validation.valid is True
    interfaces = parse_palo_alto_xml(tmp_path / "candidate.xml").physical_interfaces
    assert {item.name: item.comment for item in interfaces} == {new: f"{old}-body" for old, new in pairs}


def test_occupied_chain_blocks(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(small_xml("ethernet1/1", "ethernet1/2", "ethernet1/3"))
    result = run(source, tmp_path / "candidate.xml", ("ethernet1/1", "ethernet1/2"), ("ethernet1/2", "ethernet1/3"))
    assert "TARGET_PHYSICAL_NAME_COLLISION" in {finding.code for finding in result.plan.findings}


def test_same_name_noop_and_exact_refs(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(small_xml("ethernet1/1", "ethernet1/10", "ethernet1/11", "ethernet1/5",
        members=("ethernet1/1", "ethernet1/10", "ethernet1/11")))
    noop = run(source, tmp_path / "noop.xml", ("ethernet1/5", "ethernet1/5"))
    assert noop.validation.valid is True
    assert not noop.plan.operations
    result = run(source, tmp_path / "candidate.xml", ("ethernet1/1", "ethernet1/50"))
    assert result.validation.valid is True
    assert parse_palo_alto_xml(tmp_path / "candidate.xml").zones[0].interface_members == [
        "ethernet1/50", "ethernet1/10", "ethernet1/11"
    ]
    candidate_bytes = (tmp_path / "candidate.xml").read_bytes()
    assert b"<certificate-metadata>synthetic-only</certificate-metadata>" in candidate_bytes
    assert b"<log-setting>synthetic-only</log-setting>" in candidate_bytes
    assert b"<dynamic-routing>synthetic-only</dynamic-routing>" in candidate_bytes


def test_suffix_tag_nat_and_unknown_config(tmp_path):
    source = tmp_path / "source.xml"
    data = COMPLEX.read_text(encoding="utf-8")
    data = data.replace('</units></layer3></entry>', '<entry name="ethernet1/12.100"><tag>200</tag></entry></units></layer3></entry>', 1)
    data = data.replace('<interface>loopback.1</interface>', '<interface>ethernet1/12.262</interface>', 1)
    data = data.replace('<unrelated-feature>', '<!-- synthetic-preserve-comment --><unknown-feature><nested>preserve-me</nested></unknown-feature><unrelated-feature>', 1)
    source.write_text(data, encoding="utf-8")
    result = run(source, tmp_path / "candidate.xml", ("ethernet1/12", "ethernet1/50"))
    assert result.validation.valid is True
    candidate = parse_palo_alto_xml(tmp_path / "candidate.xml")
    assert next(item for item in candidate.subinterfaces if item.name == "ethernet1/50.100").tag == 200
    assert candidate.nat_rules[0].interface_references == ["ethernet1/50.262"]
    content = (tmp_path / "candidate.xml").read_text(encoding="utf-8")
    assert "synthetic-preserve-comment" in content
    assert "<nested>preserve-me</nested>" in content


def test_review_and_blocked_gates(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(COMPLEX.read_bytes())
    aggregate = run(source, tmp_path / "candidate.xml", ("ethernet1/1", "ethernet1/7"))
    assert "REVIEW_APPROVAL_REQUIRED" in {finding.code for finding in aggregate.plan.findings}
    approved = run(source, tmp_path / "candidate.xml", ("ethernet1/1", "ethernet1/7"), allow_review=True)
    assert approved.validation.valid is True
    assert any(op.operation_type == OperationType.ASSERT_AGGREGATE_MEMBERSHIP for op in approved.plan.operations)
    assert "ethernet1/7" in parse_palo_alto_xml(tmp_path / "candidate.xml").aggregate_interfaces[0].member_interfaces
    blocked = run(source, tmp_path / "other.xml", ("ethernet1/99", "ethernet1/50"), allow_review=True)
    assert "PREVIEW_BLOCKED" in {finding.code for finding in blocked.plan.findings}
    assert not (tmp_path / "other.xml").exists()


def test_stale_inventory_preview_and_output_policy(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(COMPLEX.read_bytes())
    inventory = parse_palo_alto_xml(source)
    profile = load_hardware_profile(PROFILE)
    preview = preview_interface_mappings(inventory, [InterfaceMapping(source_interface="ethernet1/12", target_interface="ethernet1/50")], profile)
    bad_preview = preview.model_copy(deep=True)
    bad_preview.summary.zone_reference_changes += 1
    assert "PREVIEW_MISMATCH" in {finding.code for finding in build_transformation_plan(source.read_bytes(), inventory, bad_preview, profile).findings}
    assert "OUTPUT_PATH_EQUALS_SOURCE" in {finding.code for finding in
        render_panos_candidate(source, inventory, preview, profile, source, force=True).plan.findings}
    output = tmp_path / "candidate.xml"
    output.write_text("existing")
    assert "OUTPUT_EXISTS" in {finding.code for finding in
        render_panos_candidate(source, inventory, preview, profile, output).plan.findings}
    source.write_bytes(source.read_bytes().replace(b'entry name="ethernet1/12"', b'entry name="ethernet1/14"'))
    assert "SOURCE_INVENTORY_MISMATCH" in {finding.code for finding in
        render_panos_candidate(source, inventory, preview, profile, tmp_path / "stale.xml").plan.findings}
    assert not (tmp_path / "stale.xml").exists()


def test_preservation_audit_detects_unplanned_change():
    source = ET.fromstring(b"<config><unknown>original</unknown></config>")
    candidate = ET.fromstring(b"<config><unknown>changed</unknown></config>")
    assert preservation_audit(source, candidate, []) is False


def test_failed_audit_never_writes_candidate(tmp_path, monkeypatch):
    source = tmp_path / "source.xml"
    source.write_bytes(COMPLEX.read_bytes())
    monkeypatch.setattr("confighop_core.renderers.palo_alto.renderer.preservation_audit", lambda *_: False)
    result = run(source, tmp_path / "candidate.xml", ("ethernet1/12", "ethernet1/50"))
    assert result.status == PreviewStatus.BLOCKED
    assert "PRESERVATION_AUDIT_FAILED" in {finding.code for finding in result.plan.findings}
    assert not (tmp_path / "candidate.xml").exists()


def test_layer2_review_override_and_plan_determinism(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(COMPLEX.read_bytes())
    inventory = parse_palo_alto_xml(source)
    profile = load_hardware_profile(PROFILE)
    preview = preview_interface_mappings(inventory,
        [InterfaceMapping(source_interface="ethernet1/13", target_interface="ethernet1/50")], profile)
    first = build_transformation_plan(source.read_bytes(), inventory, preview, profile, allow_review=True)
    second = build_transformation_plan(source.read_bytes(), inventory, preview, profile, allow_review=True)
    assert first.model_dump_json() == second.model_dump_json()
    assert run(source, tmp_path / "denied.xml", ("ethernet1/13", "ethernet1/50")).status == PreviewStatus.BLOCKED
    allowed = run(source, tmp_path / "allowed.xml", ("ethernet1/13", "ethernet1/50"), allow_review=True)
    assert allowed.status == PreviewStatus.REVIEW_REQUIRED
    assert allowed.validation.valid is True


def test_dtd_source_is_rejected(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(b'<!DOCTYPE config [<!ENTITY x "unsafe">]><config><devices/></config>')
    # The v0.1 parser rejects this before a render plan can be constructed.
    from confighop_core.errors import ConfigParseError
    with pytest.raises(ConfigParseError):
        parse_palo_alto_xml(source)


def test_ambiguous_route_locator_blocks(tmp_path):
    source = tmp_path / "source.xml"
    data = COMPLEX.read_text(encoding="utf-8")
    marker = '<entry name="to-example"><destination>203.0.113.0/24</destination><interface>ethernet1/12.265</interface><nexthop><ip-address>192.0.2.46</ip-address></nexthop></entry>'
    assert marker in data
    source.write_text(data.replace(marker, marker + marker), encoding="utf-8")
    result = run(source, tmp_path / "candidate.xml", ("ethernet1/12", "ethernet1/50"))
    assert result.status == PreviewStatus.BLOCKED
    assert "LOCATOR_AMBIGUOUS" in {finding.code for finding in result.plan.findings}
    assert not (tmp_path / "candidate.xml").exists()


def test_force_overwrite_and_cli_summary(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(COMPLEX.read_bytes())
    output = tmp_path / "candidate.xml"
    output.write_text("old", encoding="utf-8")
    result = run(source, output, ("ethernet1/12", "ethernet1/50"), force=True)
    assert result.validation.valid is True
    assert output.read_bytes() != b"old"
    cli = subprocess.run([sys.executable, "-m", "confighop_core.render", str(source),
        "--target-profile", str(PROFILE), "--map", "ethernet1/12=ethernet1/50",
        "--output", str(tmp_path / "cli.xml")], capture_output=True, text=True, check=True)
    assert "Candidate Parse: PASS" in cli.stdout
    assert "Preservation Audit: PASS" in cli.stdout
    assert "Physical Renames: 1" in cli.stdout
    assert "192.0.2." not in cli.stdout
    assert "203.0.113." not in cli.stdout
