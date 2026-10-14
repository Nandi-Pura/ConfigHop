import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from confighop_api.main import create_app
from confighop_api.services import ProjectStore
from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.compatibility import assess
from confighop_core.hardware.registry import get_profile
from confighop_core.models.hardware import CandidateSupport, RequiredCondition, TargetRenderSupport
from confighop_core.models.mapping import InterfaceMapping, PreviewStatus, TargetInterfaceSettings


GROUPS = {
    "3220": [(range(13, 17), ("1G",)), (range(17, 21), ("1G", "10G"))],
    "3250": [(range(13, 21), ("1G", "10G"))],
    "3260": [(range(13, 21), ("1G", "10G")), (range(21, 25), ("40G",))],
    "5220": [(range(5, 21), ("1G", "10G")), (range(21, 25), ("40G",))],
    "5250": [(range(5, 21), ("1G", "10G")), (range(21, 25), ("40G", "100G"))],
    "5260": [(range(5, 21), ("1G", "10G")), (range(21, 25), ("40G", "100G"))],
    "5280": [(range(5, 21), ("1G", "10G")), (range(21, 25), ("40G", "100G"))],
}


def source_xml(port: int, fields: str = "") -> bytes:
    return (f'<config version="11.1" detail-version="11.1.4"><devices>'
        f'<entry name="localhost.localdomain"><network><interface><ethernet>'
        f'<entry name="ethernet1/{port}">{fields}<layer3/></entry>'
        f'</ethernet></interface></network></entry></devices></config>').encode()


def case(tmp_path: Path, model: str, port: int, rate: str | None, *, fields: str = "", link_speed: str | None = None,
         source_port: int | None = None, allow_review: bool = True):
    source_port = source_port or port
    source = tmp_path / "source.xml"
    output = tmp_path / "candidate.xml"
    data = source_xml(source_port, fields)
    source.write_bytes(data)
    inventory = parse_palo_alto_xml(source)
    profile = get_profile(f"paloalto-pa-{model}")
    settings = TargetInterfaceSettings(optic_rate=rate, link_speed=link_speed) if rate or link_speed else None
    mapping = InterfaceMapping(source_interface=f"ethernet1/{source_port}", target_interface=f"ethernet1/{port}", target_settings=settings)
    preview = preview_interface_mappings(inventory, [mapping], profile)
    compatibility = assess(inventory, profile.id, "11.1", profile.id, "11.1", [mapping])
    result = render_panos_candidate(source, inventory, preview, profile, output, allow_review=allow_review,
        source_profile_id=profile.id, source_panos_train="11.1", target_panos_train="11.1")
    assert source.read_bytes() == data
    if result.status == PreviewStatus.BLOCKED:
        assert not output.exists()
    return preview, compatibility, result, output


@pytest.mark.parametrize("model,groups", GROUPS.items())
def test_exact_optical_groups_and_scoped_support(model, groups):
    profile = get_profile(f"paloalto-pa-{model}")
    assert profile.target_render_support == TargetRenderSupport.SCOPED
    for numbers, rates in groups:
        for number in numbers:
            port = profile.interfaces[number - 1]
            assert port.required_condition == RequiredCondition.OPTIC_CONTEXT_LINK_FIELDS_ABSENT
            assert port.candidate_support == CandidateSupport.CONDITIONAL
            assert tuple(port.speed_capabilities) == rates
    assert all(port.required_condition == RequiredCondition.AUTO_ONLY_LINK_FIELDS_ABSENT
               for port in profile.interfaces[:12 if model.startswith("3") else 4])


@pytest.mark.parametrize("model,groups", GROUPS.items())
def test_missing_context_blocks_each_model(model, groups, tmp_path):
    port = groups[0][0].start
    preview, compatibility, result, _ = case(tmp_path, model, port, None)
    assert preview.status == compatibility.status == result.status == PreviewStatus.BLOCKED
    assert "TARGET_OPTIC_RATE_REQUIRED" in {finding.code for finding in preview.findings}
    assert "TARGET_OPTIC_RATE_REQUIRED" in {finding.code for finding in compatibility.findings}


@pytest.mark.parametrize("model,port,rate", [
    (model, numbers.start, rate) for model, groups in GROUPS.items()
    for numbers, rates in groups for rate in rates
])
def test_valid_context_requires_review_and_preserves_link_xml(model, port, rate, tmp_path):
    preview, compatibility, result, output = case(tmp_path, model, port + 1, rate, source_port=port)
    assert preview.status == compatibility.status == result.status == PreviewStatus.REVIEW_REQUIRED
    assert "PHYSICAL_OPTIC_VERIFICATION_REQUIRED" in {finding.code for finding in preview.findings}
    assert "PHYSICAL_OPTIC_VERIFICATION_REQUIRED" in {finding.code for finding in compatibility.findings}
    assert result.validation.valid and result.validation.preservation_audit_ok
    assert not any(op.field in {"link-speed", "link-duplex"} for op in result.plan.operations)
    assert b"<link-speed>" not in output.read_bytes()
    assert b"<link-duplex>" not in output.read_bytes()
    denied = tmp_path / "unreviewed.xml"
    source = tmp_path / "source.xml"
    profile = get_profile(f"paloalto-pa-{model}")
    unreviewed = render_panos_candidate(source, parse_palo_alto_xml(source), preview, profile, denied,
        source_profile_id=profile.id, source_panos_train="11.1", target_panos_train="11.1")
    assert unreviewed.status == PreviewStatus.BLOCKED and not denied.exists()


@pytest.mark.parametrize("model,port,rate", [
    ("3220", 13, "10G"), ("3260", 21, "100G"), ("5220", 21, "100G"),
])
def test_unsupported_rate_blocks_even_with_review(model, port, rate, tmp_path):
    preview, _, result, _ = case(tmp_path, model, port, rate)
    assert preview.status == result.status == PreviewStatus.BLOCKED
    assert "TARGET_OPTIC_RATE_UNSUPPORTED" in {finding.code for finding in preview.findings}


@pytest.mark.parametrize("field", ["<link-speed>auto</link-speed>", "<link-speed>10000</link-speed>",
    "<link-duplex>auto</link-duplex>", "<link-duplex>full</link-duplex>"])
def test_explicit_source_link_node_blocks(field, tmp_path):
    preview, _, result, _ = case(tmp_path, "5220", 5, "10G", fields=field)
    assert preview.status == result.status == PreviewStatus.BLOCKED
    assert "TARGET_OPTICAL_LINK_SERIALIZATION_UNVERIFIED" in {finding.code for finding in preview.findings}


def test_target_link_speed_cannot_substitute_for_optic_context(tmp_path):
    preview, _, result, _ = case(tmp_path, "5250", 21, None, link_speed="40G")
    assert preview.status == result.status == PreviewStatus.BLOCKED
    assert {"TARGET_OPTIC_RATE_REQUIRED", "TARGET_OPTICAL_LINK_SETTING_NOT_APPLICABLE"} <= {finding.code for finding in preview.findings}


def test_optic_rate_type_and_media_guard(tmp_path):
    with pytest.raises(ValidationError):
        TargetInterfaceSettings(optic_rate="25G")
    _, compatibility, _, _ = case(tmp_path, "5220", 5, "10G", source_port=1)
    assert compatibility.status == PreviewStatus.BLOCKED
    assert "TARGET_MEDIA_INCOMPATIBLE" in {finding.code for finding in compatibility.findings}


@pytest.mark.parametrize("source_port,target_port,expected", [(1, 5, "BLOCKED"), (5, 6, "REVIEW_REQUIRED")])
def test_api_enforces_media_and_round_trips_optic_context(source_port, target_port, expected):
    headers = {"X-ConfigHop-Client": "web"}
    with TestClient(create_app(ProjectStore())) as client:
        project = client.post("/api/v1/projects", headers=headers).json()["project_id"]
        base = f"/api/v1/projects/{project}"
        data = source_xml(source_port)
        assert client.put(base + "/source", content=data,
            headers={**headers, "Content-Type": "application/xml", "X-ConfigHop-Filename": "synthetic.xml"}).status_code == 200
        selection = {"profile_id": "paloalto-pa-5220", "panos_train": "11.1"}
        for role in ("source", "target"):
            assert client.put(base + f"/{role}-profile", json=selection, headers=headers).status_code == 200
        body = {"mappings": [{"source_interface": f"ethernet1/{source_port}",
            "target_interface": f"ethernet1/{target_port}", "target_settings": {"optic_rate": "10G"}}]}
        preview = client.post(base + "/preview", json=body, headers=headers).json()
        assert preview["overall_status"] == expected
        assert preview["mappings"][0]["target_settings"]["optic_rate"] == "10G"
        candidate = client.post(base + "/candidate", json={**body, "allow_review": True}, headers=headers).json()
        assert candidate["candidate_available"] is (expected == "REVIEW_REQUIRED")
        if expected == "BLOCKED":
            assert "TARGET_MEDIA_INCOMPATIBLE" in {finding["code"] for finding in candidate["findings"]}
        else:
            xml = client.get(base + "/candidate/download").content
            assert b"<link-speed>" not in xml and b"<link-duplex>" not in xml


def test_frozen_optical_evidence_gaps_remain_partial():
    manifest = json.loads((Path(__file__).resolve().parents[2] / "docs/core/palo_alto_evidence_gaps.json").read_text())
    expected = {"PAN-GAP-PA3200-OPTICAL-1G", "PAN-GAP-PA3200-OPTICAL-MIXED", "PAN-GAP-PA3200-QSFP-40G",
                "PAN-GAP-PA5200-OPTICAL", "PAN-GAP-PA5200-QSFP-40G", "PAN-GAP-PA5200-QSFP-40-100G"}
    gaps = {gap["id"]: gap for gap in manifest["gaps"] if gap["id"] in expected}
    assert set(gaps) == expected
    assert all(gap["status"] == "EVIDENCE_PARTIAL" and gap["blocking"] for gap in gaps.values())
