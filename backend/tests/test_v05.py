from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from confighop_api.main import create_app
from confighop_api.services import ProjectStore
from confighop_core import parse_palo_alto_xml
from confighop_core.compatibility import assess, parse_version, version_support
from confighop_core.evidence.registry import EVIDENCE, PA3410, PA5410, EvidenceRecord
from confighop_core.models.mapping import InterfaceMapping

FIXTURE = Path(__file__).parent / "fixtures/paloalto/pa_complex_synthetic.xml"
HEADERS = {"X-ConfigHop-Client": "web"}


def test_evidence_and_exact_profiles():
    assert len(EVIDENCE) == 9
    assert all(record.source_url.startswith(("https://docs.paloaltonetworks.com/", "https://github.com/PaloAltoNetworks/pan-os-python/")) for record in EVIDENCE.values())
    assert all(evidence_id in EVIDENCE for profile in [PA3410, PA5410] for evidence_id in profile.evidence_ids)
    assert [item.name for item in PA3410.interfaces] == [f"ethernet1/{n}" for n in range(1, 27)]
    assert len([item for item in PA5410.interfaces if item.candidate_support == "SUPPORTED"]) == 24
    assert len([item for item in PA5410.interfaces if item.availability == "BREAKOUT_CHILD"]) == 16
    assert len([item for item in PA5410.interfaces if item.availability == "NATIVE_CONDITIONAL"]) == 4
    assert PA5410.interfaces[24].parent_interface == "ethernet1/41"
    assert PA5410.interfaces[39].parent_interface == "ethernet1/44"
    assert "ethernet1/50" not in {item.name for item in PA5410.interfaces}
    for url in ["http://docs.paloaltonetworks.com/page", "https://example.com/page", "https://user:pass@docs.paloaltonetworks.com/page"]:
        with pytest.raises(ValidationError):
            EvidenceRecord(id="BAD", source_title="Bad", source_url=url, source_type="HARDWARE_REFERENCE", scope="test", summary="test")


def test_version_support_and_hotfix():
    hotfix = parse_version("11.1.4-h2")
    assert (hotfix.train, hotfix.patch, hotfix.hotfix) == ("11.1", 4, 2)
    for profile in (PA3410, PA5410):
        assert profile.verified_unsupported_panos_trains == ["10.1"]
        assert "PAN-COMPAT-PANOS-BY-MODEL" in profile.evidence_ids
        for value in ("10.1", "10.1.0", "10.1.9"):
            assert version_support(profile.id, value) == "UNSUPPORTED"
        for value in ("10.2", "11.1.4", "11.1.4-h2", "12.1.2", "12.1.3"):
            assert version_support(profile.id, value) == "SUPPORTED"
        for value in ("12.1", "13.0", "13.0.0", "13.1.4", "9.9.9"):
            assert version_support(profile.id, value) == "VERSION_NOT_VERIFIED"
        for value in ("12.1.0", "12.1.1"):
            assert version_support(profile.id, value) == "VERSION_BELOW_SUPPORTED_FLOOR"
    for value in ("not-a-version", None, ""):
        assert version_support(PA3410.id, value) == "UNKNOWN_SOFTWARE"
    inventory = parse_palo_alto_xml(FIXTURE)
    inventory.platform.detail_version = "12.1.1"
    below = assess(inventory, PA3410.id, "12.1", PA5410.id, "12.1", [])
    assert below.status == "BLOCKED"
    assert below.platform.source_version_status == "VERSION_BELOW_SUPPORTED_FLOOR"


@pytest.mark.parametrize("version,status,findings", [
    ("13.0.0", "VERSION_NOT_VERIFIED", {"VERSION_NOT_VERIFIED"}),
    ("10.1.9", "UNSUPPORTED", {"SOURCE_OS_UNSUPPORTED", "TARGET_OS_UNSUPPORTED"}),
])
def test_platform_version_evidence_blocks(version, status, findings):
    inventory = parse_palo_alto_xml(FIXTURE)
    inventory.platform.detail_version = version
    train = parse_version(version).train
    result = assess(inventory, PA3410.id, train, PA5410.id, train, [])
    codes = {item.code for item in result.platform.findings}
    assert result.platform.source_version_status == status
    assert result.platform.target_version_status == status
    assert result.platform.status == result.status == "BLOCKED"
    assert findings <= codes
    if status == "VERSION_NOT_VERIFIED":
        assert "SOURCE_OS_UNSUPPORTED" not in codes
        assert "TARGET_OS_UNSUPPORTED" not in codes


def test_effective_assignments_and_blockers():
    inventory = parse_palo_alto_xml(FIXTURE)
    base = (inventory, PA3410.id, "11.1", PA5410.id, "11.1")
    ready = assess(*base, [InterfaceMapping(source_interface="ethernet1/12", target_interface="ethernet1/8")])
    assert ready.status == "READY"
    assert len(ready.hardware.effective_assignments) == len(inventory.physical_interfaces)
    assert any(item.source_interface == "ethernet1/13" and item.target_interface == "ethernet1/13" and not item.explicit_mapping for item in ready.hardware.effective_assignments)
    for target, code in [("ethernet1/25", "BREAKOUT_MODE_REQUIRED"), ("ethernet1/41", "TARGET_NATIVE_PORT_MODE_REQUIRED"), ("ethernet1/50", "TARGET_INTERFACE_NOT_FOUND")]:
        result = assess(*base, [InterfaceMapping(source_interface="ethernet1/12", target_interface=target)])
        assert result.status == "BLOCKED"
        assert code in {item.code for item in result.findings}
    changed = assess(inventory, PA3410.id, "11.2", PA5410.id, "11.1", [])
    assert "SOURCE_OS_CONTEXT_MISMATCH" in {item.code for item in changed.findings}


def test_implicit_breakout_media_review_and_speed_block():
    inventory = parse_palo_alto_xml(FIXTURE)
    extra = inventory.physical_interfaces[0].model_copy(update={"name": "ethernet1/25"})
    inventory.physical_interfaces.append(extra)
    base = (inventory, PA3410.id, "11.1", PA5410.id, "11.1")
    implicit = assess(*base, [])
    assert "BREAKOUT_MODE_REQUIRED" in {item.code for item in implicit.findings}
    inventory.physical_interfaces.pop()
    review = assess(*base, [InterfaceMapping(source_interface="ethernet1/12", target_interface="ethernet1/9")])
    assert review.status == "REVIEW_REQUIRED"
    assert "MEDIA_CHANGE_REVIEW" in {item.code for item in review.findings}
    extra.link_speed = "25000"
    inventory.physical_interfaces.append(extra)
    speed = assess(*base, [InterfaceMapping(source_interface="ethernet1/25", target_interface="ethernet1/8")])
    assert speed.status == "BLOCKED"
    assert "TARGET_SPEED_UNSUPPORTED" in {item.code for item in speed.findings}


def test_api_verified_flow_and_fail_closed(tmp_path):
    with TestClient(create_app(ProjectStore())) as client:
        assert len(client.get("/api/v1/evidence").json()) == 9
        assert len(client.get("/api/v1/hardware-profiles").json()) == 3
        project = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        client.put(f"/api/v1/projects/{project}/source-profile", json={"profile_id": PA3410.id, "panos_train": "11.1"}, headers=HEADERS)
        client.put(f"/api/v1/projects/{project}/target-profile", json={"profile_id": PA5410.id, "panos_train": "11.1"}, headers=HEADERS)
        source = client.put(f"/api/v1/projects/{project}/source", content=FIXTURE.read_bytes(), headers={**HEADERS, "Content-Type": "application/xml"})
        assert source.status_code == 200
        mapping = {"mappings": [{"source_interface": "ethernet1/12", "target_interface": "ethernet1/8"}]}
        compatibility = client.post(f"/api/v1/projects/{project}/compatibility", json=mapping, headers=HEADERS)
        assert compatibility.json()["status"] == "READY"
        preview = client.post(f"/api/v1/projects/{project}/preview", json=mapping, headers=HEADERS)
        assert preview.json()["overall_status"] == "READY"
        candidate = client.post(f"/api/v1/projects/{project}/candidate", json=mapping, headers=HEADERS)
        assert candidate.json()["candidate_available"] is True
        assert candidate.json()["validation"]["preservation_audit_ok"] is True
        downloaded = client.get(f"/api/v1/projects/{project}/candidate/download")
        assert downloaded.status_code == 200
        candidate_path = tmp_path / "public-candidate.xml"
        candidate_path.write_bytes(downloaded.content)
        reparsed = parse_palo_alto_xml(candidate_path)
        assert "ethernet1/8" in {item.name for item in reparsed.physical_interfaces}
        for target, code in [("ethernet1/25", "BREAKOUT_MODE_REQUIRED"), ("ethernet1/41", "TARGET_NATIVE_PORT_MODE_REQUIRED")]:
            mapping["mappings"][0]["target_interface"] = target
            blocked = client.post(f"/api/v1/projects/{project}/candidate", json=mapping, headers=HEADERS)
            assert blocked.status_code == 200
            assert blocked.json()["candidate_available"] is False
            assert code in {item["code"] for item in blocked.json()["findings"]}
            assert client.get(f"/api/v1/projects/{project}/candidate/download").status_code == 409


def test_api_review_requires_acknowledgment_and_context_invalidates():
    with TestClient(create_app(ProjectStore())) as client:
        project = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        client.put(f"/api/v1/projects/{project}/source", content=FIXTURE.read_bytes(), headers={**HEADERS, "Content-Type": "application/xml"})
        client.put(f"/api/v1/projects/{project}/source-profile", json={"profile_id": PA3410.id, "panos_train": "11.1"}, headers=HEADERS)
        client.put(f"/api/v1/projects/{project}/target-profile", json={"profile_id": PA5410.id, "panos_train": "11.1"}, headers=HEADERS)
        mapping = {"mappings": [{"source_interface": "ethernet1/12", "target_interface": "ethernet1/9"}]}
        denied = client.post(f"/api/v1/projects/{project}/candidate", json=mapping, headers=HEADERS).json()
        assert denied["candidate_available"] is False
        assert denied["hardware_assessment_status"] == "REVIEW_REQUIRED"
        allowed = client.post(f"/api/v1/projects/{project}/candidate", json={**mapping, "allow_review": True}, headers=HEADERS).json()
        assert allowed["candidate_available"] is True
        assert allowed["status"] == "REVIEW_REQUIRED"
        state = client.put(f"/api/v1/projects/{project}/target-profile", json={"profile_id": PA5410.id, "panos_train": "11.2"}, headers=HEADERS).json()
        assert state["source_available"] is True
        assert state["candidate_available"] is False
        assert client.get(f"/api/v1/projects/{project}/candidate/download").status_code == 409
        changed = client.post(f"/api/v1/projects/{project}/compatibility", json={"mappings": []}, headers=HEADERS).json()
        assert "TARGET_OS_CHANGE_UNSUPPORTED" in {item["code"] for item in changed["findings"]}


def test_api_unverified_future_blocks_candidate_even_with_review():
    source = FIXTURE.read_bytes().replace(b'detail-version="11.1.4"', b'detail-version="13.0.0"')
    with TestClient(create_app(ProjectStore())) as client:
        project = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        for role, profile in (("source", PA3410), ("target", PA5410)):
            response = client.put(f"/api/v1/projects/{project}/{role}-profile",
                json={"profile_id": profile.id, "panos_train": "13.0"}, headers=HEADERS)
            assert response.status_code == 200
        assert client.put(f"/api/v1/projects/{project}/source", content=source,
            headers={**HEADERS, "Content-Type": "application/xml"}).status_code == 200
        compatibility = client.post(f"/api/v1/projects/{project}/compatibility",
            json={"mappings": []}, headers=HEADERS)
        assert compatibility.status_code == 200
        result = compatibility.json()
        assert result["platform"]["source_version_status"] == "VERSION_NOT_VERIFIED"
        assert result["platform"]["target_version_status"] == "VERSION_NOT_VERIFIED"
        assert result["status"] == "BLOCKED"
        assert {item["code"] for item in result["findings"]} >= {"VERSION_NOT_VERIFIED"}
        candidate = client.post(f"/api/v1/projects/{project}/candidate",
            json={"mappings": [], "allow_review": True}, headers=HEADERS)
        assert candidate.status_code == 200
        assert candidate.json()["candidate_available"] is False
        assert client.get(f"/api/v1/projects/{project}/candidate/download").status_code == 409
