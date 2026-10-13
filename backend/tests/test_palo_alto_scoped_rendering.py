from pathlib import Path

import pytest

from confighop_core import parse_palo_alto_xml, preview_interface_mappings, render_panos_candidate
from confighop_core.hardware.registry import get_profile
from confighop_core.models.hardware import TargetRenderSupport
from confighop_core.models.mapping import InterfaceMapping, PreviewStatus, TargetInterfaceSettings


SCOPED = ("3220", "3250", "3260", "5220", "5250", "5260", "5280")


def xml(*, name="ethernet1/1", fields="", mode="layer3", extra=""):
    return (f'<config version="11.1" detail-version="11.1.4"><devices>'
        f'<entry name="localhost.localdomain"><network><interface><ethernet>'
        f'<entry name="{name}">{fields}<{mode}/></entry>{extra}</ethernet></interface>'
        f'</network><vsys><entry name="vsys1"><zone><entry name="inside"><network>'
        f'<layer3><member>{name}</member></layer3></network></entry></zone></entry></vsys>'
        f'</entry></devices></config>').encode()


def run(tmp_path: Path, model: str, data: bytes, destination="ethernet1/2", settings=None, mapped=True):
    source = tmp_path / "source.xml"
    output = tmp_path / "candidate.xml"
    source.write_bytes(data)
    inventory = parse_palo_alto_xml(source)
    profile = get_profile(f"paloalto-pa-{model}")
    mappings = [InterfaceMapping(source_interface=inventory.physical_interfaces[0].name,
        target_interface=destination, target_settings=settings)] if mapped else []
    preview = preview_interface_mappings(inventory, mappings, profile)
    result = render_panos_candidate(source, inventory, preview, profile, output, allow_review=True)
    assert source.read_bytes() == data
    if result.status == PreviewStatus.BLOCKED:
        assert not output.exists()
    return inventory, preview, result, output


@pytest.mark.parametrize("model", SCOPED)
def test_layer3_rj45_non_interference_renders(model, tmp_path):
    inventory, preview, result, output = run(tmp_path, model, xml())
    assert not inventory.physical_interfaces[0].link_speed_explicit
    assert not inventory.physical_interfaces[0].link_duplex_explicit
    assert result.validation.valid
    assert result.status != PreviewStatus.BLOCKED
    assert b'ethernet1/2' in output.read_bytes()
    assert b'<link-speed>' not in output.read_bytes()
    assert b'<link-duplex>' not in output.read_bytes()


@pytest.mark.parametrize("model", SCOPED)
@pytest.mark.parametrize("field", ("<link-speed>auto</link-speed>", "<link-speed>1000</link-speed>",
    "<link-duplex>auto</link-duplex>", "<link-duplex>full</link-duplex>"))
def test_explicit_link_field_blocks(model, field, tmp_path):
    inventory, preview, result, _ = run(tmp_path, model, xml(fields=field))
    assert inventory.physical_interfaces[0].link_speed_explicit == ("speed" in field)
    assert inventory.physical_interfaces[0].link_duplex_explicit == ("duplex" in field)
    assert result.status == PreviewStatus.BLOCKED
    assert "TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED" in {f.code for f in preview.findings}


@pytest.mark.parametrize("model", SCOPED)
def test_target_link_setting_blocks(model, tmp_path):
    _, preview, result, _ = run(tmp_path, model, xml(),
        settings=TargetInterfaceSettings(link_speed="auto"))
    assert result.status == PreviewStatus.BLOCKED
    assert "TARGET_AUTO_ONLY_LINK_SETTING_NOT_APPLICABLE" in {f.code for f in preview.findings}


@pytest.mark.parametrize("model", SCOPED)
@pytest.mark.parametrize("port", (5, 21))
def test_optical_or_qsfp_without_context_blocks(model, port, tmp_path):
    if model in {"3220", "3250"} and port == 21:
        return
    optical_port = 13 if model in {"3220", "3250", "3260"} and port == 5 else port
    _, preview, result, _ = run(tmp_path, model, xml(), destination=f"ethernet1/{optical_port}")
    assert result.status == PreviewStatus.BLOCKED
    assert "TARGET_OPTIC_RATE_REQUIRED" in {f.code for f in preview.findings}


@pytest.mark.parametrize("model", SCOPED)
def test_active_interface_requires_explicit_mapping(model, tmp_path):
    _, preview, result, _ = run(tmp_path, model, xml(), mapped=False)
    assert result.status == PreviewStatus.BLOCKED
    assert "SCOPED_TARGET_ACTIVE_INTERFACE_MAPPING_REQUIRED" in {f.code for f in preview.findings}


@pytest.mark.parametrize("mode", ("layer2", "virtual-wire"))
def test_partial_dependency_mode_blocks_even_with_review(mode, tmp_path):
    _, preview, result, _ = run(tmp_path, "5220", xml(mode=mode))
    assert result.status == PreviewStatus.BLOCKED
    assert "SCOPED_TARGET_DEPENDENCY_COVERAGE_INSUFFICIENT" in {f.code for f in preview.findings}


def test_aggregate_member_blocks(tmp_path):
    _, preview, result, _ = run(tmp_path, "5220", xml(fields="<aggregate-group>ae1</aggregate-group>"))
    assert result.status == PreviewStatus.BLOCKED
    assert "SCOPED_TARGET_DEPENDENCY_COVERAGE_INSUFFICIENT" in {f.code for f in preview.findings}


def test_layer3_subinterface_and_references_rewrite(tmp_path):
    data = xml().replace(b'<layer3/>',
        b'<layer3><units><entry name="ethernet1/1.100"><tag>100</tag></entry></units></layer3>')
    data = data.replace(b'<member>ethernet1/1</member>', b'<member>ethernet1/1.100</member>')
    _, _, result, output = run(tmp_path, "5220", data)
    assert result.validation.valid
    assert b'ethernet1/2.100' in output.read_bytes()
    assert b'<link-speed>' not in output.read_bytes()


def test_inactive_unmapped_identity_is_preserved(tmp_path):
    data = xml(extra='<entry name="ethernet1/3"><comment>empty</comment></entry>')
    _, _, result, output = run(tmp_path, "5220", data)
    assert result.validation.valid
    assert b'<entry name="ethernet1/3">' in output.read_bytes()


def test_inactive_unmapped_unknown_target_identity_blocks(tmp_path):
    data = xml(extra='<entry name="ethernet1/99"><comment>empty</comment></entry>')
    _, preview, result, _ = run(tmp_path, "5220", data)
    assert result.status == PreviewStatus.BLOCKED
    assert "TARGET_INTERFACE_NOT_FOUND" in {f.code for f in preview.findings}


def test_profile_status_remains_distinct():
    assert all(get_profile(f"paloalto-pa-{model}").target_render_support == TargetRenderSupport.SCOPED
        for model in SCOPED)
    assert all(get_profile(f"paloalto-pa-{model}").target_render_support == TargetRenderSupport.SUPPORTED
        for model in ("3410", "5410"))
    assert all(get_profile(f"paloalto-pa-{model}").target_render_support == TargetRenderSupport.ANALYSIS_ONLY
        for model in ("1410", "1420"))
