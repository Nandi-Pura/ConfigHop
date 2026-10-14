from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from confighop_api.main import create_app
from confighop_api.services import ProjectStore
from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.compatibility import version_support
from confighop_core.hardware.registry import get_profile
from confighop_core.models.hardware import TargetRenderSupport
from confighop_core.models.mapping import PreviewStatus


GROUPS = {
    "1410": (("RJ45 1-8", 1, 8, ("RJ45",), ("10M", "100M", "1G"), False),
             ("Multi-Gig PoE 9-12", 9, 12, ("RJ45",), ("10M", "100M", "1G", "2.5G", "5G"), True),
             ("SFP 13-18", 13, 18, ("SFP",), ("1G",), False),
             ("SFP+ 19-22", 19, 22, ("SFP", "SFP_PLUS"), ("1G", "10G"), False)),
    "1420": (("RJ45 1-4", 1, 4, ("RJ45",), ("10M", "100M", "1G"), False),
             ("Multi-Gig 5-8", 5, 8, ("RJ45",), ("10M", "100M", "1G", "2.5G", "5G"), False),
             ("Multi-Gig PoE 9-12", 9, 12, ("RJ45",), ("10M", "100M", "1G", "2.5G", "5G"), True),
             ("SFP 13-14", 13, 14, ("SFP",), ("1G",), False),
             ("SFP+ 15-22", 15, 22, ("SFP", "SFP_PLUS"), ("1G", "10G"), False)),
}
PORTS = (
    ("1410", "ethernet1/1"), ("1410", "ethernet1/9"),
    ("1410", "ethernet1/13"), ("1410", "ethernet1/19"),
    ("1420", "ethernet1/1"), ("1420", "ethernet1/5"),
    ("1420", "ethernet1/9"), ("1420", "ethernet1/13"),
    ("1420", "ethernet1/15"),
)
SETTINGS = (
    (None, None, None), ("auto", "auto", "auto"),
    ("10", "full", None), ("100", "half", None),
    ("1000", "full", "up"), ("2500", "full", None),
    ("5000", "full", "down"), ("10000", "full", None),
    ("unverified", "unverified", None),
)
HEADERS = {"X-ConfigHop-Client": "web"}


def synthetic_source(name, speed=None, duplex=None, state=None):
    settings = "".join(f"<{tag}>{value}</{tag}>" for tag, value in
        (("link-speed", speed), ("link-duplex", duplex), ("link-state", state)) if value is not None)
    return (f'<config version="11.1" detail-version="11.1.4"><devices>'
        f'<entry name="localhost.localdomain"><network><interface><ethernet>'
        f'<entry name="{name}">{settings}<layer3/></entry></ethernet></interface></network>'
        f'</entry></devices></config>').encode()


@pytest.mark.parametrize("model", ("1410", "1420"))
def test_exact_pa1400_groups_and_informational_metadata(model):
    profile = get_profile(f"paloalto-pa-{model}")
    assert profile.model == f"PA-{model}"
    assert profile.profile_status == "verified"
    assert profile.first_supported_release == "11.0"
    assert profile.target_render_support == TargetRenderSupport.ANALYSIS_ONLY
    assert {group.label for group in profile.interface_groups} == {row[0] for row in GROUPS[model]}
    assert [port.name for port in profile.interfaces if port.ztp_capable] == ["ethernet1/1"]
    for label, first, last, media, speeds, poe in GROUPS[model]:
        group = next(item for item in profile.interface_groups if item.label == label)
        assert group.interface_names == [f"ethernet1/{number}" for number in range(first, last + 1)]
        assert group.media_capabilities == list(media)
        assert group.speed_capabilities == list(speeds)
        assert group.evidence_ids == ["PAN-HW-PA1400-FRONT"]
        assert ("PoE is informational" in (group.notes or "")) == poe


@pytest.mark.parametrize("model,name", PORTS)
@pytest.mark.parametrize("speed,duplex,link_state", SETTINGS)
def test_pa1400_qualification_probe_does_not_enable_real_target(
    tmp_path, model, name, speed, duplex, link_state,
):
    source = tmp_path / "source.xml"
    source.write_bytes(synthetic_source(name, speed, duplex, link_state))
    before = source.read_bytes()
    before_sha = sha256(before).hexdigest()
    inventory = parse_palo_alto_xml(source)
    profile = get_profile(f"paloalto-pa-{model}")
    output = tmp_path / "candidate.xml"
    blocked = render_panos_candidate(source, inventory,
        preview_interface_mappings(inventory, [], profile), profile, output, allow_review=True)
    assert blocked.status == PreviewStatus.BLOCKED
    assert "TARGET_PROFILE_RENDERING_NOT_VERIFIED" in {item.code for item in blocked.plan.findings}
    assert not output.exists()
    assert source.read_bytes() == before
    assert sha256(source.read_bytes()).hexdigest() == before_sha

    # Isolated mechanical probe; it supplies no target XML qualification evidence.
    probe = profile.model_copy(update={"id": f"test-only-pa-{model}",
        "target_render_support": TargetRenderSupport.SUPPORTED})
    rendered = render_panos_candidate(source, inventory,
        preview_interface_mappings(inventory, [], probe), probe, output, allow_review=True)
    assert rendered.validation.valid
    candidate = parse_palo_alto_xml(output).physical_interfaces[0]
    assert (candidate.link_speed, candidate.link_duplex, candidate.link_state) == (speed, duplex, link_state)
    assert source.read_bytes() == before
    assert get_profile(f"paloalto-pa-{model}").target_render_support == TargetRenderSupport.ANALYSIS_ONLY


@pytest.mark.parametrize("model", ("1410", "1420"))
def test_real_pa1400_api_target_blocks_candidate_and_download(model):
    source = synthetic_source("ethernet1/9", "5000", "full", "up")
    with TestClient(create_app(ProjectStore())) as client:
        project = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        for role, profile_id in (("source", "paloalto-pa-3410"), ("target", f"paloalto-pa-{model}")):
            assert client.put(f"/api/v1/projects/{project}/{role}-profile",
                json={"profile_id": profile_id, "panos_train": "11.1"}, headers=HEADERS).status_code == 200
        assert client.put(f"/api/v1/projects/{project}/source", content=source,
            headers={**HEADERS, "Content-Type": "application/xml"}).status_code == 200
        result = client.post(f"/api/v1/projects/{project}/candidate",
            json={"mappings": [], "allow_review": True}, headers=HEADERS).json()
        assert result["status"] == "BLOCKED"
        assert not result["candidate_available"]
        assert "TARGET_PROFILE_RENDERING_NOT_VERIFIED" in {item["code"] for item in result["findings"]}
        assert client.get(f"/api/v1/projects/{project}/candidate/download").status_code == 409
        assert client.get(f"/api/v1/projects/{project}/source").content == source


@pytest.mark.parametrize("model", ("1410", "1420"))
def test_pa1400_software_boundary(model):
    profile_id = f"paloalto-pa-{model}"
    for train in ("11.0", "11.1", "11.2", "12.2"):
        assert version_support(profile_id, train) == "SUPPORTED"
    assert version_support(profile_id, "12.1.2") == "SUPPORTED"
    assert version_support(profile_id, "12.1.1") == "VERSION_BELOW_SUPPORTED_FLOOR"
    for train in ("10.1", "10.2"):
        assert version_support(profile_id, train) == "UNSUPPORTED"
    assert version_support(profile_id, "13.0") == "VERSION_NOT_VERIFIED"
    assert version_support(profile_id, "malformed") == "UNKNOWN_SOFTWARE"
