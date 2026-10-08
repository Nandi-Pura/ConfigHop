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


PORTS = (
    ("3220", "ethernet1/1", "1000"),
    ("3220", "ethernet1/13", "1000"),
    ("3220", "ethernet1/17", "10000"),
    ("3250", "ethernet1/1", "1000"),
    ("3250", "ethernet1/13", "10000"),
    ("3260", "ethernet1/1", "1000"),
    ("3260", "ethernet1/13", "10000"),
    ("3260", "ethernet1/21", "40000"),
)
GROUPS = {
    "3220": (("RJ45 1-12", 1, 12, ("RJ45",), ("10M", "100M", "1G")),
             ("SFP 13-16", 13, 16, ("SFP",), ("1G",)),
             ("SFP+ 17-20", 17, 20, ("SFP", "SFP_PLUS"), ("1G", "10G"))),
    "3250": (("RJ45 1-12", 1, 12, ("RJ45",), ("10M", "100M", "1G")),
             ("SFP+ 13-20", 13, 20, ("SFP", "SFP_PLUS"), ("1G", "10G"))),
    "3260": (("RJ45 1-12", 1, 12, ("RJ45",), ("10M", "100M", "1G")),
             ("SFP+ 13-20", 13, 20, ("SFP", "SFP_PLUS"), ("1G", "10G")),
             ("QSFP+ 21-24", 21, 24, ("QSFP_PLUS",), ("40G",))),
}
STATES = {
    "absent": (None, None, None),
    "auto": ("auto", "auto", None),
    "manual": ("manual", "full", None),
    "speed_only": ("manual", None, None),
    "duplex_only": (None, "full", None),
    "up": (None, None, "up"),
    "down": (None, None, "down"),
    "unknown_speed": ("unverified", None, None),
    "unknown_duplex": (None, "unverified", None),
}
HEADERS = {"X-ConfigHop-Client": "web"}


def synthetic_source(name, speed=None, duplex=None, state=None):
    settings = "".join(f"<{tag}>{value}</{tag}>" for tag, value in
        (("link-speed", speed), ("link-duplex", duplex), ("link-state", state)) if value is not None)
    return (f'<config version="11.1" detail-version="11.1.4"><devices>'
        f'<entry name="localhost.localdomain"><network><interface><ethernet>'
        f'<entry name="{name}">{settings}<layer3/></entry></ethernet></interface></network>'
        f'</entry></devices></config>').encode()


@pytest.mark.parametrize("model", ("3220", "3250", "3260"))
def test_each_model_has_exact_official_port_groups(model):
    profile = get_profile(f"paloalto-pa-{model}")
    assert profile.profile_status == "verified"
    assert profile.first_supported_release == "8.1"
    assert {group.label for group in profile.interface_groups} == {group[0] for group in GROUPS[model]}
    for label, first, last, media, speeds in GROUPS[model]:
        group = next(item for item in profile.interface_groups if item.label == label)
        assert group.interface_names == [f"ethernet1/{number}" for number in range(first, last + 1)]
        assert group.media_capabilities == list(media)
        assert group.speed_capabilities == list(speeds)
        assert group.evidence_ids == ["PAN-HW-PA3200-FRONT"]


@pytest.mark.parametrize("model,name,manual_speed", PORTS)
@pytest.mark.parametrize("state", STATES)
def test_each_pa3200_target_group_remains_unqualified(
    tmp_path, model, name, manual_speed, state,
):
    speed, duplex, link_state = STATES[state]
    speed = manual_speed if speed == "manual" else speed
    values = (speed, duplex, link_state)
    source = tmp_path / "source.xml"
    source.write_bytes(synthetic_source(name, *values))
    before = source.read_bytes()
    before_sha = sha256(before).hexdigest()
    inventory = parse_palo_alto_xml(source)
    profile = get_profile(f"paloalto-pa-{model}")
    assert profile.model == f"PA-{model}"
    assert name in {port.name for port in profile.interfaces}
    assert profile.target_render_support == TargetRenderSupport.ANALYSIS_ONLY
    output = tmp_path / "candidate.xml"
    preview = preview_interface_mappings(inventory, [], profile)
    blocked = render_panos_candidate(source, inventory, preview, profile, output, allow_review=True)
    assert blocked.status == PreviewStatus.BLOCKED
    assert "TARGET_PROFILE_RENDERING_NOT_VERIFIED" in {item.code for item in blocked.plan.findings}
    assert not output.exists()
    assert source.read_bytes() == before
    assert sha256(source.read_bytes()).hexdigest() == before_sha

    # This isolated copy exposes generic mechanics without changing the registry.
    probe = profile.model_copy(update={"target_render_support": TargetRenderSupport.SUPPORTED})
    probe_preview = preview_interface_mappings(inventory, [], probe)
    rendered = render_panos_candidate(source, inventory, probe_preview, probe, output, allow_review=True)
    assert rendered.validation.valid
    assert output.exists()
    candidate = parse_palo_alto_xml(output).physical_interfaces[0]
    assert (candidate.link_speed, candidate.link_duplex, candidate.link_state) == values
    assert source.read_bytes() == before
    assert get_profile(f"paloalto-pa-{model}").target_render_support == TargetRenderSupport.ANALYSIS_ONLY


@pytest.mark.parametrize("model", ("3220", "3250", "3260"))
def test_each_real_pa3200_api_target_blocks_candidate(model):
    source = synthetic_source("ethernet1/1", "1000", "full", "up")
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


@pytest.mark.parametrize("model", ("3220", "3250", "3260"))
def test_pa3200_software_matrix_stays_bounded(model):
    profile_id = f"paloalto-pa-{model}"
    for train in ("10.1", "10.2", "11.0", "11.1"):
        assert version_support(profile_id, train) == "SUPPORTED"
    for train in ("11.2", "12.1", "12.2"):
        assert version_support(profile_id, train) == "UNSUPPORTED"
    assert version_support(profile_id, "13.0") == "VERSION_NOT_VERIFIED"
    assert version_support(profile_id, "malformed") == "UNKNOWN_SOFTWARE"
