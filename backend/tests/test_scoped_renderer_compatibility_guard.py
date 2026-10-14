import pytest

from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.compatibility import assess
from confighop_core.hardware.registry import get_profile
from confighop_core.models.hardware import TargetRenderSupport
from confighop_core.models.mapping import InterfaceMapping, PreviewStatus, TargetInterfaceSettings


def source_xml(*ports, version="11.1.4"):
    entries = "".join(f'<entry name="ethernet1/{port}"><layer3/></entry>' for port in ports)
    return (f'<config version="{version[:4]}" detail-version="{version}"><devices>'
        f'<entry name="localhost.localdomain"><network><interface><ethernet>{entries}'
        f'</ethernet></interface></network></entry></devices></config>').encode()


def render_case(tmp_path, ports, mappings, *, source_id="paloalto-pa-5220", target_id="paloalto-pa-5220",
                source_train="11.1", target_train="11.1", version="11.1.4", allow_review=True,
                target_profile=None):
    source = tmp_path / "source.xml"
    output = tmp_path / "candidate.xml"
    data = source_xml(*ports, version=version)
    source.write_bytes(data)
    inventory = parse_palo_alto_xml(source)
    profile = target_profile or get_profile(target_id)
    preview = preview_interface_mappings(inventory, mappings, profile)
    result = render_panos_candidate(source, inventory, preview, profile, output,
        allow_review=allow_review, source_profile_id=source_id,
        source_panos_train=source_train, target_panos_train=target_train)
    assert source.read_bytes() == data
    if result.status == PreviewStatus.BLOCKED:
        assert not output.exists()
    return preview, result, output


def test_direct_scoped_renderer_rejects_media_incompatibility(tmp_path):
    source = tmp_path / "source.xml"
    output = tmp_path / "candidate.xml"
    data = (b'<config version="11.1" detail-version="11.1.4"><devices><entry name="localhost.localdomain">'
            b'<network><interface><ethernet><entry name="ethernet1/1"><layer3/></entry></ethernet>'
            b'</interface></network></entry></devices></config>')
    source.write_bytes(data)
    inventory = parse_palo_alto_xml(source)
    profile = get_profile("paloalto-pa-5220")
    mappings = [InterfaceMapping(source_interface="ethernet1/1", target_interface="ethernet1/5",
        target_settings=TargetInterfaceSettings(optic_rate="10G"))]
    preview = preview_interface_mappings(inventory, mappings, profile)
    compatibility = assess(inventory, profile.id, "11.1", profile.id, "11.1", mappings)
    assert preview.status == PreviewStatus.REVIEW_REQUIRED
    assert compatibility.status == PreviewStatus.BLOCKED
    assert "TARGET_MEDIA_INCOMPATIBLE" not in {finding.code for finding in preview.findings}
    assert "TARGET_MEDIA_INCOMPATIBLE" in {finding.code for finding in compatibility.findings}

    result = render_panos_candidate(source, inventory, preview, profile, output, allow_review=True,
        source_profile_id=profile.id, source_panos_train="11.1", target_panos_train="11.1")
    assert result.status == PreviewStatus.BLOCKED
    assert not result.validation.valid
    assert "TARGET_MEDIA_INCOMPATIBLE" in {finding.code for finding in result.validation.findings}
    assert not output.exists()
    assert source.read_bytes() == data


@pytest.mark.parametrize("missing", ["source_profile_id", "source_panos_train", "target_panos_train"])
def test_scoped_context_is_required(tmp_path, missing):
    kwargs = {"source_profile_id": "paloalto-pa-5220", "source_panos_train": "11.1",
        "target_panos_train": "11.1"}
    kwargs[missing] = None
    source = tmp_path / "source.xml"
    output = tmp_path / "candidate.xml"
    data = source_xml(5)
    source.write_bytes(data)
    inventory = parse_palo_alto_xml(source)
    profile = get_profile("paloalto-pa-5220")
    mappings = [InterfaceMapping(source_interface="ethernet1/5", target_interface="ethernet1/6",
        target_settings=TargetInterfaceSettings(optic_rate="10G"))]
    preview = preview_interface_mappings(inventory, mappings, profile)
    result = render_panos_candidate(source, inventory, preview, profile, output, allow_review=True, **kwargs)
    assert result.status == PreviewStatus.BLOCKED
    assert "SCOPED_RENDER_CONTEXT_REQUIRED" in {finding.code for finding in result.plan.findings}
    assert not output.exists() and source.read_bytes() == data


@pytest.mark.parametrize("source_id,source_train,target_train,version,ports,mappings,code", [
    ("does-not-exist", "11.1", "11.1", "11.1.4", (5,), [(5, 6, "10G")], "SOURCE_PROFILE_REQUIRED"),
    ("paloalto-pa-3220", "11.1", "11.1", "11.1.4", (21,), [(21, 22, "40G")], "SOURCE_HARDWARE_PROFILE_MISMATCH"),
    ("paloalto-pa-5220", "11.1", "11.1", "11.1.4", (21,), [(21, 5, "10G")], "NO_COMMON_SPEED"),
    ("paloalto-pa-5220", "11.1", "10.2", "11.1.4", (5,), [(5, 6, "10G")], "TARGET_OS_CHANGE_UNSUPPORTED"),
    ("paloalto-pa-5220", "10.2", "11.1", "11.1.4", (5,), [(5, 6, "10G")], "SOURCE_OS_CONTEXT_MISMATCH"),
    ("paloalto-pa-3220", "11.2", "11.2", "11.2.1", (5,), [(5, 6, "10G")], "SOURCE_OS_UNSUPPORTED"),
])
def test_direct_renderer_keeps_compatibility_errors(tmp_path, source_id, source_train, target_train,
                                                    version, ports, mappings, code):
    decisions = [InterfaceMapping(source_interface=f"ethernet1/{old}", target_interface=f"ethernet1/{new}",
        target_settings=TargetInterfaceSettings(optic_rate=rate)) for old, new, rate in mappings]
    _, result, _ = render_case(tmp_path, ports, decisions, source_id=source_id,
        source_train=source_train, target_train=target_train, version=version)
    assert result.status == PreviewStatus.BLOCKED
    assert not result.validation.valid
    assert code in {finding.code for finding in result.plan.findings}
    assert code in {finding.code for finding in result.validation.findings}


def test_review_only_allows_compatible_optical_path(tmp_path):
    mappings = [InterfaceMapping(source_interface="ethernet1/5", target_interface="ethernet1/6",
        target_settings=TargetInterfaceSettings(optic_rate="10G"))]
    preview, denied, _ = render_case(tmp_path, (5,), mappings, allow_review=False)
    assert preview.status == PreviewStatus.REVIEW_REQUIRED
    assert denied.status == PreviewStatus.BLOCKED
    assert "REVIEW_APPROVAL_REQUIRED" in {finding.code for finding in denied.plan.findings}
    _, allowed, output = render_case(tmp_path, (5,), mappings)
    assert allowed.status == PreviewStatus.REVIEW_REQUIRED
    assert allowed.validation.valid and allowed.validation.preservation_audit_ok
    assert b"<link-speed>" not in output.read_bytes()
    assert b"<link-duplex>" not in output.read_bytes()


def test_registered_target_must_match_rendered_profile(tmp_path):
    profile = get_profile("paloalto-pa-5220")
    altered = profile.model_copy(update={"interfaces": profile.interfaces[:-1]})
    _, result, _ = render_case(tmp_path, (5,), [InterfaceMapping(source_interface="ethernet1/5",
        target_interface="ethernet1/6", target_settings=TargetInterfaceSettings(optic_rate="10G"))],
        target_profile=altered)
    assert result.status == PreviewStatus.BLOCKED
    assert "TARGET_PROFILE_CONTEXT_MISMATCH" in {finding.code for finding in result.plan.findings}


def test_registered_scoped_target_cannot_be_relabeled_supported(tmp_path):
    source = tmp_path / "source.xml"
    output = tmp_path / "candidate.xml"
    data = source_xml(1)
    source.write_bytes(data)
    inventory = parse_palo_alto_xml(source)
    profile = get_profile("paloalto-pa-5220").model_copy(update={"target_render_support": TargetRenderSupport.SUPPORTED})
    preview = preview_interface_mappings(inventory, [], profile)
    result = render_panos_candidate(source, inventory, preview, profile, output, allow_review=True)
    assert result.status == PreviewStatus.BLOCKED
    assert "TARGET_PROFILE_CONTEXT_MISMATCH" in {finding.code for finding in result.plan.findings}
    assert not output.exists() and source.read_bytes() == data


def test_target_collision_keeps_compatibility_finding(tmp_path):
    mappings = [InterfaceMapping(source_interface="ethernet1/5", target_interface="ethernet1/6",
        target_settings=TargetInterfaceSettings(optic_rate="10G")),
        InterfaceMapping(source_interface="ethernet1/6", target_interface="ethernet1/6",
        target_settings=TargetInterfaceSettings(optic_rate="10G"))]
    _, result, _ = render_case(tmp_path, (5, 6), mappings)
    assert result.status == PreviewStatus.BLOCKED
    assert "TARGET_HARDWARE_PROFILE_MISMATCH" in {finding.code for finding in result.validation.findings}


def test_forged_preview_still_blocks(tmp_path):
    source = tmp_path / "source.xml"
    output = tmp_path / "candidate.xml"
    data = source_xml(5)
    source.write_bytes(data)
    inventory = parse_palo_alto_xml(source)
    profile = get_profile("paloalto-pa-5220")
    mappings = [InterfaceMapping(source_interface="ethernet1/5", target_interface="ethernet1/6",
        target_settings=TargetInterfaceSettings(optic_rate="10G"))]
    preview = preview_interface_mappings(inventory, mappings, profile)
    forged = preview.model_copy(update={"status": PreviewStatus.READY})
    result = render_panos_candidate(source, inventory, forged, profile, output, allow_review=True,
        source_profile_id=profile.id, source_panos_train="11.1", target_panos_train="11.1")
    assert result.status == PreviewStatus.BLOCKED
    assert "PREVIEW_MISMATCH" in {finding.code for finding in result.plan.findings}
    assert not output.exists() and source.read_bytes() == data
