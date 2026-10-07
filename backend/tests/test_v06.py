from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from confighop_api.main import create_app
from confighop_api.services import ProjectStore
from confighop_core import parse_palo_alto_xml
from confighop_core.evidence.registry import EVIDENCE, NATIVE_QSFP_SPEED_XML, PA3410, PA5410


FIXTURE = Path(__file__).parent / "fixtures/paloalto/pa_complex_synthetic.xml"
HEADERS = {"X-ConfigHop-Client": "web"}


def project(client: TestClient, source: bytes) -> str:
    project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
    for role, profile in (("source", PA3410), ("target", PA5410)):
        assert client.put(f"/api/v1/projects/{project_id}/{role}-profile",
            json={"profile_id": profile.id, "panos_train": "11.1"}, headers=HEADERS).status_code == 200
    assert client.put(f"/api/v1/projects/{project_id}/source", content=source,
        headers={**HEADERS, "Content-Type": "application/xml"}).status_code == 200
    return project_id


def mapping(target: str, speed: str | None = None) -> dict:
    value = {"source_interface": "ethernet1/12", "target_interface": target}
    if speed is not None:
        value["target_settings"] = {"link_speed": speed}
    return {"mappings": [value]}


def test_native_profile_and_documentation_evidence():
    assert len(PA3410.interfaces) == 26
    assert len(PA5410.interfaces) == 44
    assert sum(item.candidate_support == "SUPPORTED" for item in PA5410.interfaces) == 24
    assert sum(item.candidate_support == "BLOCKED" for item in PA5410.interfaces) == 16
    assert sum(item.candidate_support == "CONDITIONAL" for item in PA5410.interfaces) == 4
    assert "ethernet1/50" not in {item.name for item in PA5410.interfaces}
    assert NATIVE_QSFP_SPEED_XML == {"40G": "40000", "100G": "100000"}
    for key in ("PAN-CONFIG-ETHERNET-LINK-SPEED", "PAN-CONFIG-ETHERNET-LINK-SPEED-VALUES", "PAN-CONFIG-ETHERNET-LINK-SPEED-TEST"):
        assert EVIDENCE[key].verification_level == "DOCUMENTATION_VERIFIED"
        assert not EVIDENCE[key].device_validated


@pytest.mark.parametrize("speed,serialized", [("40G", "40000"), ("100G", "100000")])
@pytest.mark.parametrize("existing", [False, True])
def test_native_speed_api_round_trip(tmp_path, speed, serialized, existing):
    source = FIXTURE.read_bytes()
    if existing:
        source = source.replace(b'<entry name="ethernet1/12">',
            b'<entry name="ethernet1/12"><link-speed>10000</link-speed>', 1)
    source_sha = sha256(source).hexdigest()
    with TestClient(create_app(ProjectStore())) as client:
        project_id = project(client, source)
        request = mapping("ethernet1/41", speed)
        preview = client.post(f"/api/v1/projects/{project_id}/preview", json=request, headers=HEADERS)
        assert preview.status_code == 200
        assert preview.json()["overall_status"] == "REVIEW_REQUIRED"
        assert "TARGET_NATIVE_PORT_MODE_REQUIRED" not in {item["code"] for item in preview.json()["platform_assessment"]["findings"]}
        denied = client.post(f"/api/v1/projects/{project_id}/candidate", json=request, headers=HEADERS).json()
        assert denied["candidate_available"] is False
        allowed = client.post(f"/api/v1/projects/{project_id}/candidate",
            json={**request, "allow_review": True}, headers=HEADERS)
        assert allowed.status_code == 200
        result = allowed.json()
        assert result["candidate_available"] is True
        assert result["validation"]["candidate_parse_ok"] is True
        assert result["validation"]["expected_inventory_match"] is True
        assert result["validation"]["postconditions_passed"] is True
        assert result["validation"]["preservation_audit_ok"] is True
        assert any(op["operation_type"] == "SET_INTERFACE_LINK_SPEED" and op["target_value"] == serialized for op in result["plan"]["operations"])
        assert any(change["category"] == "SET_INTERFACE_LINK_SPEED" and change["new_value"] == speed for change in result["semantic_diff"]["changes"])
        downloaded = client.get(f"/api/v1/projects/{project_id}/candidate/download")
        assert downloaded.status_code == 200
        root = ET.fromstring(downloaded.content)
        target = root.find("./devices/entry/network/interface/ethernet/entry[@name='ethernet1/41']")
        assert target is not None
        assert len(target.findall("link-speed")) == 1
        assert target.findtext("link-speed") == serialized
        candidate_path = tmp_path / "public-candidate.xml"
        candidate_path.write_bytes(downloaded.content)
        parsed = parse_palo_alto_xml(candidate_path)
        assert next(item.link_speed for item in parsed.physical_interfaces if item.name == "ethernet1/41") == serialized
        assert "ethernet1/41.262" in {item.name for item in parsed.subinterfaces}
        assert sha256(client.get(f"/api/v1/projects/{project_id}/source").content).hexdigest() == source_sha
        codes = {item["code"] for item in preview.json()["hardware_assessment"]["findings"]}
        assert "PHYSICAL_LINK_CHANGE_REQUIRED" in codes
        assert ("TARGET_LINK_SPEED_CHANGED" in codes) == existing


@pytest.mark.parametrize("target,speed,code", [
    ("ethernet1/41", None, "TARGET_NATIVE_PORT_MODE_REQUIRED"),
    ("ethernet1/41", "auto", "TARGET_LINK_SPEED_UNSUPPORTED"),
    ("ethernet1/41", "10G", "TARGET_LINK_SPEED_UNSUPPORTED"),
    ("ethernet1/41", "25G", "TARGET_LINK_SPEED_UNSUPPORTED"),
    ("ethernet1/41", "invalid", "TARGET_LINK_SPEED_UNSUPPORTED"),
    ("ethernet1/10", "100G", "TARGET_INTERFACE_SETTING_NOT_APPLICABLE"),
    ("ethernet1/25", None, "BREAKOUT_MODE_REQUIRED"),
    ("ethernet1/50", None, "TARGET_INTERFACE_NOT_FOUND"),
])
def test_native_speed_negative_api(target, speed, code):
    with TestClient(create_app(ProjectStore())) as client:
        project_id = project(client, FIXTURE.read_bytes())
        request = mapping(target, speed)
        compatibility = client.post(f"/api/v1/projects/{project_id}/compatibility", json=request, headers=HEADERS)
        assert compatibility.status_code == 200
        assert compatibility.json()["status"] == "BLOCKED"
        assert code in {item["code"] for item in compatibility.json()["findings"]}
        candidate = client.post(f"/api/v1/projects/{project_id}/candidate",
            json={**request, "allow_review": True}, headers=HEADERS)
        assert candidate.status_code == 200
        assert candidate.json()["candidate_available"] is False
        assert client.get(f"/api/v1/projects/{project_id}/candidate/download").status_code == 409
