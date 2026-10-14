from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from confighop_api.main import create_app
from confighop_api.services import ProjectStore
from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.hardware.registry import get_profile
from confighop_core.models.hardware import TargetRenderSupport
from confighop_core.models.mapping import PreviewStatus


MODELS = ("5220", "5250", "5260", "5280")
GROUPS = (("RJ45", "ethernet1/1", "1000"),
          ("SFP", "ethernet1/5", "10000"),
          ("QSFP", "ethernet1/21", "40000"))
HEADERS = {"X-ConfigHop-Client": "web"}


def synthetic_source(name, speed=None, duplex=None, state=None):
    settings = "".join(f"<{tag}>{value}</{tag}>" for tag, value in
        (("link-speed", speed), ("link-duplex", duplex), ("link-state", state)) if value is not None)
    return (f'<config version="11.1" detail-version="11.1.4"><devices>'
        f'<entry name="localhost.localdomain"><network><interface><ethernet>'
        f'<entry name="{name}">{settings}<layer3/></entry></ethernet></interface></network>'
        f'</entry></devices></config>').encode()


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("group,name,manual_speed", GROUPS)
@pytest.mark.parametrize("state", ("absent", "auto", "manual", "unknown"))
def test_each_target_group_remains_fail_closed_without_serialization_proof(
    tmp_path, model, group, name, manual_speed, state,
):
    values = {
        "absent": (None, None, "down"),
        "auto": ("auto", "auto", "up"),
        "manual": (manual_speed, "full", "down"),
        "unknown": ("unverified", "unverified", "down"),
    }
    speed, duplex, link_state = values[state]
    source = tmp_path / "source.xml"
    source.write_bytes(synthetic_source(name, speed, duplex, link_state))
    before = source.read_bytes()
    inventory = parse_palo_alto_xml(source)
    profile = get_profile(f"paloalto-pa-{model}")
    assert profile.target_render_support == TargetRenderSupport.SCOPED
    preview = preview_interface_mappings(inventory, [], profile)
    output = tmp_path / "candidate.xml"
    blocked = render_panos_candidate(source, inventory, preview, profile, output, allow_review=True,
        source_profile_id=profile.id, source_panos_train="11.1", target_panos_train="11.1")
    assert blocked.status == PreviewStatus.BLOCKED
    assert "SCOPED_TARGET_ACTIVE_INTERFACE_MAPPING_REQUIRED" in {finding.code for finding in preview.findings}
    assert not output.exists()
    assert source.read_bytes() == before

    # A test-only override exposes what the unchanged generic renderer would preserve.
    probe = profile.model_copy(update={"id": f"test-only-pa-{model}",
        "target_render_support": TargetRenderSupport.SUPPORTED})
    probe_preview = preview_interface_mappings(inventory, [], probe)
    rendered = render_panos_candidate(source, inventory, probe_preview, probe, output, allow_review=True)
    assert rendered.validation.valid
    candidate = parse_palo_alto_xml(output).physical_interfaces[0]
    assert (candidate.link_speed, candidate.link_duplex, candidate.link_state) == values[state]
    assert source.read_bytes() == before


@pytest.mark.parametrize("model", MODELS)
def test_each_pa5200_api_target_blocks_manual_rj45_settings(model):
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
        assert "SCOPED_TARGET_ACTIVE_INTERFACE_MAPPING_REQUIRED" in {finding["code"] for finding in result["findings"]}
        assert client.get(f"/api/v1/projects/{project}/candidate/download").status_code == 409
        assert client.get(f"/api/v1/projects/{project}/source").content == source
