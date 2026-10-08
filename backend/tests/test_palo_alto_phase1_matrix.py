from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from confighop_api.main import create_app
from confighop_api.services import ProjectStore
from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.compatibility import assess
from confighop_core.hardware.registry import get_profile
from confighop_core.models.mapping import InterfaceMapping, PreviewStatus, TargetInterfaceSettings


REFERENCE = Path(__file__).parent / "fixtures/paloalto/pa5220_reference_migration.xml"
TARGET = get_profile("paloalto-pa-5410")
HEADERS = {"X-ConfigHop-Client": "web"}


def pair(old, new, speed=None):
    return InterfaceMapping(source_interface=old, target_interface=new,
        target_settings=TargetInterfaceSettings(link_speed=speed) if speed else None)


def source_xml(*names, children=(), extra="", speed=None):
    entries = ""
    for name in names:
        units = "".join(f'<entry name="{child}"><tag>100</tag></entry>'
            for child in children if child.startswith(name + "."))
        link = f"<link-speed>{speed}</link-speed>" if speed else ""
        entries += f'<entry name="{name}">{link}<layer3><units>{units}</units></layer3></entry>'
    return (f'<config version="11.1" detail-version="11.1.4"><devices><entry name="localhost.localdomain">'
        f'<network><interface><ethernet>{entries}</ethernet></interface></network>{extra}'
        f'</entry></devices></config>').encode()


def run(tmp_path, data, mappings, *, allow_review=True):
    source = tmp_path / "source.xml"
    source.write_bytes(data)
    inventory = parse_palo_alto_xml(source)
    compatibility = assess(inventory, "paloalto-pa-5220", "11.1", "paloalto-pa-5410", "11.1", mappings)
    preview = preview_interface_mappings(inventory, mappings, TARGET)
    output = tmp_path / "candidate.xml"
    result = (render_panos_candidate(source, inventory, preview, TARGET, output, allow_review=allow_review)
              if compatibility.status.value != "BLOCKED" else None)
    return compatibility, preview, result, output


def test_a_copper_identity_ready(tmp_path):
    assessment, preview, result, output = run(tmp_path, source_xml("ethernet1/1", speed="1000"), [])
    assert assessment.status.value == preview.status == PreviewStatus.READY
    assert result.validation.valid and output.exists()
    assert not result.plan.operations


def test_b_sfp_rename_and_children(tmp_path):
    data = REFERENCE.read_bytes().replace(b'<entry name="ethernet1/21"><link-speed>40000</link-speed><layer3/></entry>', b'')
    assessment, preview, result, output = run(tmp_path, data,
        [pair("ethernet1/5", "ethernet1/9"), pair("ethernet1/6", "ethernet1/10")])
    assert assessment.status.value == "READY"
    assert preview.status == PreviewStatus.REVIEW_REQUIRED
    assert result.validation.valid
    before = parse_palo_alto_xml(tmp_path / "source.xml")
    after = parse_palo_alto_xml(output)
    for old, new in zip(before.subinterfaces, after.subinterfaces):
        assert new.name == old.name.replace("ethernet1/5.", "ethernet1/9.")
        assert new.parent_interface == "ethernet1/9"
        assert new.model_dump(exclude={"name", "parent_interface"}) == old.model_dump(exclude={"name", "parent_interface"})
    assert after.zones[:2][0].interface_members == ["ethernet1/9.100"]
    assert after.virtual_routers[0].interface_members[:2] == ["ethernet1/9.100", "ethernet1/9.200"]
    assert [route.egress_interface for route in after.static_routes] == ["ethernet1/9.100", "ethernet1/9.200"]
    assert after.nat_rules[0].interface_references == ["ethernet1/9.100"]
    assert result.validation.candidate_parse_ok and result.validation.expected_inventory_match
    assert result.validation.postconditions_passed and result.validation.preservation_audit_ok


@pytest.mark.parametrize("speed,xml_speed,changed", [("40G", "40000", False), ("100G", "100000", True)])
def test_c_d_native_qsfp_review(tmp_path, speed, xml_speed, changed):
    mappings = [pair("ethernet1/21", "ethernet1/41", speed)]
    data = source_xml("ethernet1/21", speed="40000")
    assessment, preview, denied, output = run(tmp_path, data, mappings, allow_review=False)
    assert assessment.status.value == preview.status == PreviewStatus.REVIEW_REQUIRED
    codes = {finding.code for finding in assessment.findings}
    assert "PHYSICAL_LINK_CHANGE_REQUIRED" in codes
    assert ("TARGET_LINK_SPEED_CHANGED" in codes) == changed
    assert denied.status == PreviewStatus.BLOCKED and not output.exists()
    _, _, allowed, output = run(tmp_path, data, mappings)
    assert allowed.validation.valid and f"<link-speed>{xml_speed}</link-speed>".encode() in output.read_bytes()
    assert any(change.category == "SET_INTERFACE_LINK_SPEED" and change.new_value == speed
        for change in allowed.semantic_diff.changes)


@pytest.mark.parametrize("name,target,code", [
    ("ethernet1/21", "ethernet1/25", "BREAKOUT_MODE_REQUIRED"),
    ("ethernet1/45", None, "TARGET_INTERFACE_NOT_FOUND"),
    ("ethernet1/25", None, "SOURCE_HARDWARE_PROFILE_MISMATCH"),
])
def test_e_g_i_blocked_hardware_even_with_review(tmp_path, name, target, code):
    mappings = [pair(name, target)] if target else []
    assessment, preview, result, output = run(tmp_path, source_xml(name), mappings)
    assert assessment.status.value == "BLOCKED"
    assert code in {finding.code for finding in assessment.findings}
    assert result is None and not output.exists()


@pytest.mark.parametrize("mappings", [
    [pair("ethernet1/5", "ethernet1/9"), pair("ethernet1/6", "ethernet1/9")],
    [pair("ethernet1/5", "ethernet1/6")],
])
def test_h_explicit_and_implicit_target_collision(tmp_path, mappings):
    assessment, preview, result, output = run(tmp_path, source_xml("ethernet1/5", "ethernet1/6"), mappings)
    assert assessment.status.value == "BLOCKED"
    if result is None:
        result = render_panos_candidate(tmp_path / "source.xml", parse_palo_alto_xml(tmp_path / "source.xml"),
            preview, TARGET, output, allow_review=True)
    assert result.status == PreviewStatus.BLOCKED
    assert "TARGET_HARDWARE_PROFILE_MISMATCH" in {finding.code for finding in assessment.findings}
    assert not output.exists()


def test_j_derived_child_collision(tmp_path):
    data = source_xml("ethernet1/5", children=("ethernet1/5.100", "ethernet1/5.100"))
    _, preview, result, output = run(tmp_path, data, [pair("ethernet1/5", "ethernet1/9")])
    if result is None:
        result = render_panos_candidate(tmp_path / "source.xml", parse_palo_alto_xml(tmp_path / "source.xml"),
            preview, TARGET, output, allow_review=True)
    assert result.status == PreviewStatus.BLOCKED
    assert "TARGET_SUBINTERFACE_NAME_COLLISION" in {finding.code for finding in result.plan.findings}
    assert not output.exists()


def test_f_unknown_reference_and_k_l_safe_text(tmp_path):
    unsafe = source_xml("ethernet1/5", extra="<unknown><ospf><interface>ethernet1/5</interface></ospf></unknown>")
    _, _, blocked, output = run(tmp_path, unsafe, [pair("ethernet1/5", "ethernet1/9")])
    assert blocked.status == PreviewStatus.BLOCKED
    assert any(f.code == "UNMODELED_INTERFACE_REFERENCE" and "ethernet1/5" in f.message and "/ospf/" in f.message for f in blocked.plan.findings)
    assert not output.exists()
    safe = source_xml("ethernet1/5", extra="<unknown><value>preserve</value><comment>ethernet1/5</comment><description>ethernet1/5</description></unknown>")
    _, _, result, output = run(tmp_path, safe, [pair("ethernet1/5", "ethernet1/9")])
    assert result.validation.valid
    assert b"<unknown><value>preserve</value><comment>ethernet1/5</comment><description>ethernet1/5</description></unknown>" in output.read_bytes()


def test_multiple_unmodeled_reference_findings_follow_xml_order(tmp_path):
    data = source_xml("ethernet1/5", extra=(
        "<unknown><first>ethernet1/5</first><second>ethernet1/5</second></unknown>"))
    findings = []
    for _ in range(2):
        _, _, result, _ = run(tmp_path, data, [pair("ethernet1/5", "ethernet1/9")])
        findings.append([f.message for f in result.plan.findings if f.code == "UNMODELED_INTERFACE_REFERENCE"])
    assert findings[0] == findings[1]
    assert len(findings[0]) == 2
    assert "/first/" in findings[0][0] and "/second/" in findings[0][1]


def test_partial_aggregate_member_mapping_preserves_logical_interface(tmp_path):
    data = (b'<config version="11.1" detail-version="11.1.4"><devices><entry name="localhost.localdomain">'
        b'<network><interface><ethernet><entry name="ethernet1/5"><aggregate-group>ae1</aggregate-group></entry>'
        b'<entry name="ethernet1/6"><aggregate-group>ae1</aggregate-group></entry></ethernet>'
        b'<aggregate-ethernet><entry name="ae1"><comment>synthetic bundle</comment><layer3>'
        b'<ip><entry name="192.0.2.1/24"/></ip><interface-management-profile>ping</interface-management-profile>'
        b'</layer3></entry></aggregate-ethernet></interface></network></entry></devices></config>')
    assessment, preview, result, output = run(tmp_path, data, [pair("ethernet1/5", "ethernet1/9")])
    assert assessment.status.value == "REVIEW_REQUIRED"
    assert preview.status == PreviewStatus.REVIEW_REQUIRED
    assert "AGGREGATE_MEMBER_REVIEW" in {finding.code for finding in preview.findings}
    assert result.validation.valid
    before = parse_palo_alto_xml(tmp_path / "source.xml").aggregate_interfaces[0]
    after = parse_palo_alto_xml(output).aggregate_interfaces[0]
    assert before.member_interfaces == ["ethernet1/5", "ethernet1/6"]
    assert after.member_interfaces == ["ethernet1/9", "ethernet1/6"]
    assert after.model_dump(exclude={"member_interfaces"}) == before.model_dump(exclude={"member_interfaces"})


def test_api_reference_flow_and_download(tmp_path):
    source = REFERENCE.read_bytes()
    mappings = {"mappings": [pair("ethernet1/5", "ethernet1/9").model_dump(exclude_none=True),
        pair("ethernet1/6", "ethernet1/10").model_dump(exclude_none=True),
        pair("ethernet1/21", "ethernet1/41", "40G").model_dump(exclude_none=True)]}
    with TestClient(create_app(ProjectStore())) as client:
        project = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        for role, model in (("source", "5220"), ("target", "5410")):
            response = client.put(f"/api/v1/projects/{project}/{role}-profile",
                json={"profile_id": f"paloalto-pa-{model}", "panos_train": "11.1"}, headers=HEADERS)
            assert response.status_code == 200
        assert client.put(f"/api/v1/projects/{project}/source", content=source,
            headers={**HEADERS, "Content-Type": "application/xml"}).status_code == 200
        assert client.get(f"/api/v1/projects/{project}/inventory").status_code == 200
        assert client.post(f"/api/v1/projects/{project}/compatibility", json=mappings, headers=HEADERS).json()["status"] == "REVIEW_REQUIRED"
        assert client.post(f"/api/v1/projects/{project}/preview", json=mappings, headers=HEADERS).status_code == 200
        result = client.post(f"/api/v1/projects/{project}/candidate", json={**mappings, "allow_review": True}, headers=HEADERS).json()
        assert result["candidate_available"] and result["validation"]["valid"]
        assert result["semantic_diff"]["changes"]
        downloaded = client.get(f"/api/v1/projects/{project}/candidate/download")
        assert downloaded.status_code == 200
        candidate = tmp_path / "download.xml"
        candidate.write_bytes(downloaded.content)
        assert "ethernet1/9.100" in {item.name for item in parse_palo_alto_xml(candidate).subinterfaces}
        assert client.get(f"/api/v1/projects/{project}/source").content == source


@pytest.mark.parametrize("case,data,mappings,code", [
    ("breakout", source_xml("ethernet1/21"), [pair("ethernet1/21", "ethernet1/25")], "BREAKOUT_MODE_REQUIRED"),
    ("unknown", source_xml("ethernet1/5", extra="<ospf><interface>ethernet1/5</interface></ospf>"),
     [pair("ethernet1/5", "ethernet1/9")], "UNMODELED_INTERFACE_REFERENCE"),
    ("source", source_xml("ethernet1/25"), [], "SOURCE_HARDWARE_PROFILE_MISMATCH"),
    ("absent", source_xml("ethernet1/45"), [], "TARGET_INTERFACE_NOT_FOUND"),
    ("collision", source_xml("ethernet1/5", "ethernet1/6"), [pair("ethernet1/5", "ethernet1/6")],
     "TARGET_HARDWARE_PROFILE_MISMATCH"),
])
def test_allow_review_never_bypasses_blocked_api_case(case, data, mappings, code):
    with TestClient(create_app(ProjectStore())) as client:
        project = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        for role, model in (("source", "5220"), ("target", "5410")):
            assert client.put(f"/api/v1/projects/{project}/{role}-profile",
                json={"profile_id": f"paloalto-pa-{model}", "panos_train": "11.1"}, headers=HEADERS).status_code == 200
        assert client.put(f"/api/v1/projects/{project}/source", content=data,
            headers={**HEADERS, "Content-Type": "application/xml"}).status_code == 200
        request = {"mappings": [item.model_dump(exclude_none=True) for item in mappings], "allow_review": True}
        result = client.post(f"/api/v1/projects/{project}/candidate", json=request, headers=HEADERS).json()
        assert result["status"] == "BLOCKED", case
        assert not result["candidate_available"], case
        assert code in {finding["code"] for finding in result["findings"]}, case
        assert client.get(f"/api/v1/projects/{project}/candidate/download").status_code == 409
