from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from confighop_api.main import create_app
from confighop_api.services import ProjectStore
from confighop_core.compatibility import version_support
from confighop_core.hardware.registry import get_profile, list_profiles
from confighop_core.models.hardware import HardwareProfile, PlatformDomain, ProfileStatus, TargetRenderSupport
from pydantic import ValidationError


FIXTURE = Path(__file__).parent / "fixtures/paloalto/pa_complex_synthetic.xml"
HEADERS = {"X-ConfigHop-Client": "web"}


def test_registry_identity_order_and_filters():
    profiles = list_profiles()
    assert len(profiles) == 12
    assert [p.model for p in profiles if p.profile_status == ProfileStatus.VERIFIED] == [
        "PA-1410", "PA-1420", "PA-3220", "PA-3250", "PA-3260", "PA-3410",
        "PA-5220", "PA-5250", "PA-5260", "PA-5280", "PA-5410"]
    assert len(list_profiles(profile_status=ProfileStatus.SYNTHETIC)) == 1
    assert len(list_profiles(target_render_support=TargetRenderSupport.ANALYSIS_ONLY)) == 2
    assert len(list_profiles(target_render_support=TargetRenderSupport.SCOPED)) == 7
    assert len(list_profiles(domain=PlatformDomain.FIREWALL)) == 12
    assert not list_profiles(domain=PlatformDomain.SWITCH)
    assert len(list_profiles(vendor="palo_alto", series="PA-5200")) == 4
    assert get_profile("paloalto-pa-1420").model == "PA-1420"
    assert get_profile("paloalto-pa-1400") is None
    assert get_profile("paloalto-pa-9999") is None
    assert version_support("paloalto-pa-9999", "11.1") == "UNKNOWN_HARDWARE"
    assert [p.id for p in list_profiles()] == [p.id for p in list_profiles()]


def test_profile_validation_rejects_duplicate_rules_and_missing_parent():
    template = get_profile("paloalto-pa-5410").model_dump()
    template["software_support_rules"].append(template["software_support_rules"][0])
    with pytest.raises(ValidationError, match="duplicate software support train"):
        HardwareProfile.model_validate(template)
    template["software_support_rules"].pop()
    template["interfaces"][24]["parent_interface"] = "ethernet1/999"
    with pytest.raises(ValidationError, match="unknown parent"):
        HardwareProfile.model_validate(template)


@pytest.mark.parametrize("model,count,groups", [
    ("PA-1410", 22, [(1, ["10M", "100M", "1G"]), (9, ["10M", "100M", "1G", "2.5G", "5G"]), (13, ["1G"]), (19, ["1G", "10G"])]),
    ("PA-1420", 22, [(1, ["10M", "100M", "1G"]), (5, ["10M", "100M", "1G", "2.5G", "5G"]), (13, ["1G"]), (15, ["1G", "10G"])]),
    ("PA-3220", 20, [(13, ["1G"]), (17, ["1G", "10G"])]),
    ("PA-3250", 20, [(13, ["1G", "10G"])]),
    ("PA-3260", 24, [(21, ["40G"])]),
    ("PA-5220", 24, [(21, ["40G"])]),
    ("PA-5250", 24, [(21, ["40G", "100G"])]),
    ("PA-5260", 24, [(21, ["40G", "100G"])]),
    ("PA-5280", 24, [(21, ["40G", "100G"])]),
])
def test_exact_model_ports(model, count, groups):
    p = get_profile(f"paloalto-{model.lower()}")
    assert len(p.interfaces) == count
    assert p.target_render_support == (TargetRenderSupport.ANALYSIS_ONLY if p.series == "PA-1400" else TargetRenderSupport.SCOPED)
    ports = {i.name: i for i in p.interfaces}
    for number, speeds in groups:
        assert ports[f"ethernet1/{number}"].speed_capabilities == speeds
    assert all(not i.ztp_capable for i in p.interfaces) if p.series != "PA-1400" else ports["ethernet1/1"].ztp_capable
    assert all(i.parent_interface is None for i in p.interfaces)
    if p.series == "PA-1400":
        assert "PoE" in ports["ethernet1/9"].notes
    if p.series == "PA-5200":
        assert ports["ethernet1/1"].speed_capabilities == ["100M", "1G", "10G"]
        assert ports["ethernet1/5"].media_capabilities == ["SFP", "SFP_PLUS"]


@pytest.mark.parametrize("series,expected", [
    ("PA-1400", ["UNSUPPORTED", "UNSUPPORTED", "SUPPORTED", "SUPPORTED", "SUPPORTED", "SUPPORTED", "SUPPORTED"]),
    ("PA-3200", ["SUPPORTED", "SUPPORTED", "SUPPORTED", "SUPPORTED", "UNSUPPORTED", "UNSUPPORTED", "UNSUPPORTED"]),
    ("PA-5200", ["SUPPORTED", "SUPPORTED", "SUPPORTED", "SUPPORTED", "SUPPORTED", "UNSUPPORTED", "UNSUPPORTED"]),
])
def test_profile_software_rules(series, expected):
    p = list_profiles(series=series)[0]
    trains = ["10.1", "10.2", "11.0", "11.1", "11.2", "12.1", "12.2"]
    for train, status in zip(trains, expected):
        value = "12.1.2" if train == "12.1" else train
        assert version_support(p.id, value) == status
    assert p.supported_panos_trains == [r.train for r in p.software_support_rules if r.status == "SUPPORTED"]
    assert p.verified_unsupported_panos_trains == [r.train for r in p.software_support_rules if r.status == "UNSUPPORTED"]
    assert all(r.evidence_ids == ["PAN-COMPAT-PANOS-BY-MODEL"] for r in p.software_support_rules)
    assert version_support(p.id, "9.1") == "VERSION_NOT_VERIFIED"
    assert version_support(p.id, "13.0") == "VERSION_NOT_VERIFIED"
    assert version_support(p.id, "nonsense") == "UNKNOWN_SOFTWARE"
    if series == "PA-1400":
        assert version_support(p.id, "12.1") == "VERSION_NOT_VERIFIED"
        assert version_support(p.id, "12.1.1") == "VERSION_BELOW_SUPPORTED_FLOOR"
        assert version_support(p.id, "12.1.3") == "SUPPORTED"


def test_api_catalog_and_analysis_only_gate():
    with TestClient(create_app(ProjectStore())) as client:
        catalog = client.get("/api/v1/hardware-profiles").json()
        assert len(catalog) == 12
        detail = client.get("/api/v1/hardware-profiles/paloalto-pa-5250").json()
        assert detail["domain"] == "firewall" and detail["software_family"] == "pan_os"
        assert detail["target_render_support"] == "SCOPED"
        assert len(detail["software_support_rules"]) == 7
        caps = client.get("/api/v1/capabilities").json()
        assert len(caps["verified_hardware_profiles"]) == 11
        assert len(caps["candidate_render_profiles"]) == 2
        assert len(caps["analysis_only_target_profiles"]) == 2
        assert caps["domains"]["switch"]["backend_enabled"] is False
        project = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        for role, profile in (("source", "paloalto-pa-5410"), ("target", "paloalto-pa-5250")):
            response = client.put(f"/api/v1/projects/{project}/{role}-profile",
                json={"profile_id": profile, "panos_train": "11.1"}, headers=HEADERS)
            assert response.status_code == 200
        client.put(f"/api/v1/projects/{project}/source", content=FIXTURE.read_bytes(),
            headers={**HEADERS, "Content-Type": "application/xml"})
        mapping = {"mappings": [{"source_interface": "ethernet1/12", "target_interface": "ethernet1/8"}]}
        result = client.post(f"/api/v1/projects/{project}/compatibility", json=mapping, headers=HEADERS).json()
        assert result["status"] == "BLOCKED"
        assert result["platform"]["target_version_status"] == "SUPPORTED"
        assert "SCOPED_TARGET_ACTIVE_INTERFACE_MAPPING_REQUIRED" in {f["code"] for f in result["findings"]}
        candidate = client.post(f"/api/v1/projects/{project}/candidate", json={**mapping, "allow_review": True}, headers=HEADERS).json()
        assert not candidate["candidate_available"]
        assert candidate["target_render_support"] == "SCOPED"
        assert client.get(f"/api/v1/projects/{project}/candidate/download").status_code == 409


@pytest.mark.parametrize("source", ["paloalto-pa-1410", "paloalto-pa-3260", "paloalto-pa-5220"])
def test_new_source_candidate_to_verified_target(source):
    with TestClient(create_app(ProjectStore())) as client:
        project = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        for role, profile in (("source", source), ("target", "paloalto-pa-5410")):
            assert client.put(f"/api/v1/projects/{project}/{role}-profile",
                json={"profile_id": profile, "panos_train": "11.1"}, headers=HEADERS).status_code == 200
        assert client.put(f"/api/v1/projects/{project}/source", content=FIXTURE.read_bytes(),
            headers={**HEADERS, "Content-Type": "application/xml"}).status_code == 200
        mapping = {"mappings": [{"source_interface": "ethernet1/12", "target_interface": "ethernet1/8"}]}
        compatibility = client.post(f"/api/v1/projects/{project}/compatibility", json=mapping, headers=HEADERS).json()
        assert compatibility["platform"]["source_version_status"] == "SUPPORTED"
        assert compatibility["platform"]["target_version_status"] == "SUPPORTED"
        candidate = client.post(f"/api/v1/projects/{project}/candidate", json={**mapping, "allow_review": True}, headers=HEADERS).json()
        assert candidate["candidate_available"]
        assert candidate["validation"]["preservation_audit_ok"]
        assert candidate["semantic_diff"]["changes"]


@pytest.mark.parametrize("source,version,expected", [
    ("paloalto-pa-1410", "10.2.4", "UNSUPPORTED"),
    ("paloalto-pa-3260", "11.2.4", "UNSUPPORTED"),
    ("paloalto-pa-5220", "12.1.2", "UNSUPPORTED"),
    ("paloalto-pa-1410", "13.0.1", "VERSION_NOT_VERIFIED"),
])
def test_unsupported_source_version_blocks_candidate(source, version, expected):
    xml = FIXTURE.read_bytes().replace(b'config version="11.1.0" detail-version="11.1.4"',
        f'config version="{version}" detail-version="{version}"'.encode(), 1)
    with TestClient(create_app(ProjectStore())) as client:
        project = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        train = ".".join(version.split(".")[:2])
        for role, profile in (("source", source), ("target", "paloalto-pa-5410")):
            client.put(f"/api/v1/projects/{project}/{role}-profile",
                json={"profile_id": profile, "panos_train": train}, headers=HEADERS)
        assert client.put(f"/api/v1/projects/{project}/source", content=xml,
            headers={**HEADERS, "Content-Type": "application/xml"}).status_code == 200
        mapping = {"mappings": [{"source_interface": "ethernet1/12", "target_interface": "ethernet1/8"}], "allow_review": True}
        compatibility = client.post(f"/api/v1/projects/{project}/compatibility", json=mapping, headers=HEADERS).json()
        assert compatibility["platform"]["source_version_status"] == expected
        assert compatibility["status"] == "BLOCKED"
        candidate = client.post(f"/api/v1/projects/{project}/candidate", json=mapping, headers=HEADERS).json()
        assert not candidate["candidate_available"]
