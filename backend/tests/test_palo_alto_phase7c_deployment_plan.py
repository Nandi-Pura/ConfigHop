from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from confighop_api.main import create_app
from confighop_api.services import ProjectStore
from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.compatibility import assess
from confighop_core.deployment import RequirementCategory, VerificationStatus, build_deployment_plan
from confighop_core.evidence.registry import EVIDENCE
from confighop_core.hardware.registry import get_profile
from confighop_core.models.mapping import InterfaceMapping, PreviewStatus, TargetInterfaceSettings


def synthetic_xml(port: int, *, mode: str = "layer3", fields: str = "", extra: str = "") -> bytes:
    return (f'<config version="11.1" detail-version="11.1.4"><devices><entry name="localhost.localdomain">'
        f'<network><interface><ethernet><entry name="ethernet1/{port}">{fields}<{mode}/></entry>'
        f'</ethernet></interface></network>{extra}</entry></devices></config>').encode()


def case(tmp_path: Path, model: str, source_port: int, target_port: int, rate: str | None = None,
         *, mode: str = "layer3", fields: str = "", extra: str = "", render: bool = False):
    source = tmp_path / "source.xml"
    data = synthetic_xml(source_port, mode=mode, fields=fields, extra=extra)
    source.write_bytes(data)
    inventory = parse_palo_alto_xml(source)
    profile = get_profile(f"paloalto-pa-{model}")
    mappings = [InterfaceMapping(source_interface=f"ethernet1/{source_port}",
        target_interface=f"ethernet1/{target_port}",
        target_settings=TargetInterfaceSettings(optic_rate=rate) if rate else None)]
    preview = preview_interface_mappings(inventory, mappings, profile)
    compatibility = assess(inventory, profile.id, "11.1", profile.id, "11.1", mappings)
    output = tmp_path / "candidate.xml"
    candidate = render_panos_candidate(source, inventory, preview, profile, output, allow_review=True,
        source_profile_id=profile.id, source_panos_train="11.1", target_panos_train="11.1") if render else None
    before = [item.model_dump() for item in (inventory, profile, preview, compatibility, *mappings)]
    if candidate:
        before.append(candidate.model_dump())
    plan = build_deployment_plan(inventory, profile.id, "11.1", profile, "11.1", mappings,
        preview, compatibility, candidate)
    assert source.read_bytes() == data
    assert before == [item.model_dump() for item in (inventory, profile, preview, compatibility, *mappings,
        *([candidate] if candidate else []))]
    assert plan.model_dump() == build_deployment_plan(inventory, profile.id, "11.1", profile, "11.1",
        mappings, preview, compatibility, candidate).model_dump()
    assert len({item.id for item in plan.deployment_requirements}) == len(plan.deployment_requirements)
    assert set(plan.evidence_ids) <= set(EVIDENCE)
    assert not plan.unavailable_evidence_ids
    return plan, candidate, output


def test_optical_plan_separates_valid_candidate_and_physical_work(tmp_path):
    plan, candidate, output = case(tmp_path, "5220", 5, 6, "10G", render=True)
    assert candidate.validation.valid and plan.candidate_validation.valid
    assert "PHYSICAL_OPTIC_VERIFICATION_REQUIRED" in {item.code for item in plan.review_findings}
    assert plan.physical_verification_status == VerificationStatus.NOT_VERIFIED
    assert plan.configuration_operations == candidate.plan.operations
    assert {"Verify Target Transceiver", "Verify Selected Optic Rate", "Verify Cabling Compatibility",
        "Verify Remote Peer", "Verify Interface State", "Rollback Plan Prepared"} <= {
            item.title for item in plan.deployment_requirements}
    optic = next(item for item in plan.deployment_requirements if item.title == "Verify Selected Optic Rate")
    assert (optic.source_interface, optic.target_interface, optic.selected_optic_rate) == (
        "ethernet1/5", "ethernet1/6", "10G")
    assert optic.evidence_ids and set(optic.evidence_ids) <= set(EVIDENCE)
    assert all(item.status != "VERIFIED" for item in plan.deployment_requirements)
    assert all(not hasattr(item, "category") for item in candidate.plan.operations)
    assert not any(op.field in {"link-speed", "link-duplex"} for op in candidate.plan.operations)
    assert b"<link-speed>" not in output.read_bytes() and b"<link-duplex>" not in output.read_bytes()
    assert output.exists()


@pytest.mark.parametrize("model,port,rate,capabilities", [
    ("3220", 13, "1G", ["1G"]), ("3260", 21, "40G", ["40G"]),
    ("5220", 21, "40G", ["40G"]),
    *( (model, 21, rate, ["40G", "100G"]) for model in ("5250", "5260", "5280")
       for rate in ("40G", "100G") ),
])
def test_fixed_and_mixed_rates_are_operator_context(tmp_path, model, port, rate, capabilities):
    plan, candidate, _ = case(tmp_path, model, port, port + 1, rate, render=True)
    optic = next(item for item in plan.deployment_requirements if item.title == "Verify Selected Optic Rate")
    assert optic.selected_optic_rate == rate
    assert optic.target_rate_capabilities == capabilities
    assert optic.evidence_ids
    assert candidate.validation.valid
    assert not any(op.field in {"link-speed", "link-duplex"} for op in candidate.plan.operations)


def test_missing_rate_and_rj45_paths(tmp_path):
    plan, _, _ = case(tmp_path, "5220", 5, 6)
    assert plan.assessment_status == PreviewStatus.BLOCKED
    assert "TARGET_OPTIC_RATE_REQUIRED" in {item.code for item in plan.blockers}
    assert next(item for item in plan.deployment_requirements if item.title == "Verify Selected Optic Rate").selected_optic_rate is None
    plan, _, _ = case(tmp_path, "5220", 1, 2)
    assert not any(item.category == RequirementCategory.PHYSICAL_OPTIC for item in plan.deployment_requirements)
    assert any(item.title == "Verify RJ45 Link Negotiation" for item in plan.deployment_requirements)


def test_blocked_media_and_dependencies_stay_blocked(tmp_path):
    plan, candidate, output = case(tmp_path, "5220", 1, 5, "10G", render=True)
    assert plan.assessment_status == PreviewStatus.BLOCKED
    assert "TARGET_MEDIA_INCOMPATIBLE" in {item.code for item in plan.blockers}
    assert not candidate.validation.valid and not output.exists()
    for mode, fields in (("layer2", ""), ("virtual-wire", ""), ("layer3", "<aggregate-group>ae1</aggregate-group>")):
        plan, candidate, output = case(tmp_path, "5220", 1, 2, mode=mode, fields=fields, render=True)
        assert plan.assessment_status == PreviewStatus.BLOCKED
        assert "SCOPED_TARGET_DEPENDENCY_COVERAGE_INSUFFICIENT" in {item.code for item in plan.blockers}
        assert any(item.category == RequirementCategory.DEPENDENCY_BOUNDARY and item.status == VerificationStatus.BLOCKED
            for item in plan.deployment_requirements)
        assert not candidate.validation.valid and not output.exists()


def test_renderer_only_unmodeled_reference_is_in_deployment_blockers(tmp_path):
    extra = '<dynamic-routing><ospf><interface>ethernet1/5</interface></ospf></dynamic-routing>'
    plan, candidate, output = case(tmp_path, "5220", 5, 6, "10G", extra=extra, render=True)
    assert candidate.status == PreviewStatus.BLOCKED and not output.exists()
    assert plan.assessment_status == PreviewStatus.BLOCKED
    assert "UNMODELED_INTERFACE_REFERENCE" in {item.code for item in plan.blockers}
    assert any(item.category == RequirementCategory.DEPENDENCY_BOUNDARY and item.status == VerificationStatus.BLOCKED
        for item in plan.deployment_requirements)


def test_api_preview_and_candidate_plan_and_invalidation():
    headers = {"X-ConfigHop-Client": "web"}
    with TestClient(create_app(ProjectStore())) as client:
        project = client.post("/api/v1/projects", headers=headers).json()["project_id"]
        base = f"/api/v1/projects/{project}"
        assert client.put(base + "/source", content=synthetic_xml(5),
            headers={**headers, "Content-Type": "application/xml", "X-ConfigHop-Filename": "synthetic.xml"}).status_code == 200
        selection = {"profile_id": "paloalto-pa-5220", "panos_train": "11.1"}
        for role in ("source", "target"):
            assert client.put(base + f"/{role}-profile", json=selection, headers=headers).status_code == 200
        body = {"mappings": [{"source_interface": "ethernet1/5", "target_interface": "ethernet1/6",
            "target_settings": {"optic_rate": "10G"}}]}
        preview = client.post(base + "/preview", json=body, headers=headers).json()
        assert preview["deployment_plan"]["candidate_validation"] is None
        assert preview["deployment_plan"]["physical_verification_status"] == "NOT_VERIFIED"
        candidate = client.post(base + "/candidate", json={**body, "allow_review": True}, headers=headers).json()
        assert candidate["candidate_available"]
        assert candidate["deployment_plan"]["candidate_validation"]["valid"]
        assert candidate["deployment_plan"]["physical_verification_status"] == "NOT_VERIFIED"
        blocked = client.post(base + "/preview", json={"mappings": [{"source_interface": "ethernet1/5",
            "target_interface": "ethernet1/6"}]}, headers=headers).json()
        assert blocked["deployment_plan"]["assessment_status"] == "BLOCKED"
        assert "TARGET_OPTIC_RATE_REQUIRED" in {item["code"] for item in blocked["deployment_plan"]["blockers"]}
        assert blocked["deployment_plan"]["candidate_validation"] is None
        remapped = client.post(base + "/preview", json={"mappings": [{"source_interface": "ethernet1/5",
            "target_interface": "ethernet1/7", "target_settings": {"optic_rate": "1G"}}]}, headers=headers).json()
        optical = next(item for item in remapped["deployment_plan"]["deployment_requirements"]
            if item["title"] == "Verify Selected Optic Rate")
        assert (optical["target_interface"], optical["selected_optic_rate"]) == ("ethernet1/7", "1G")
        media_blocked = client.post(base + "/preview", json={"mappings": [{"source_interface": "ethernet1/5",
            "target_interface": "ethernet1/1", "target_settings": {"optic_rate": "10G"}}]}, headers=headers).json()
        assert media_blocked["deployment_plan"]["assessment_status"] == "BLOCKED"
        assert "TARGET_MEDIA_INCOMPATIBLE" in {item["code"] for item in media_blocked["deployment_plan"]["blockers"]}
        assert client.put(base + "/target-profile", json={"profile_id": "paloalto-pa-5250", "panos_train": "11.1"}, headers=headers).status_code == 200
        assert client.get(base + "/preview", headers=headers).status_code == 409
