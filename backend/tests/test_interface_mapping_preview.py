from pathlib import Path
import subprocess
import sys

import pytest

from confighop_core import preview_interface_mappings
from confighop_core.dependencies import build_dependency_index
from confighop_core.hardware import HardwareProfileError, load_hardware_profile
from confighop_core.models.dependency import ReferenceType
from confighop_core.models.hardware import HardwareInterface, HardwareKind
from confighop_core.models.interface import PhysicalInterface, Subinterface, Zone
from confighop_core.models.platform import DeviceEntry
from confighop_core.models.mapping import InterfaceMapping, PreviewStatus


FIXTURES = Path(__file__).parent / "fixtures"
PROFILE = FIXTURES / "hardware" / "paloalto_target_synthetic.json"


@pytest.fixture
def profile():
    return load_hardware_profile(PROFILE)


def preview(inventory, profile, *pairs):
    return preview_interface_mappings(inventory, [InterfaceMapping(source_interface=a, target_interface=b) for a, b in pairs], profile)


def test_complex_dependencies_and_immutability(complex_inventory, profile):
    before = complex_inventory.model_dump_json()
    result = preview(complex_inventory, profile, ("ethernet1/12", "ethernet1/5"))
    assert complex_inventory.model_dump_json() == before
    assert result.status == PreviewStatus.READY
    assert result.summary.derived_subinterface_mappings == 5
    assert [item.target_interface for item in result.impacts[0].derived_subinterfaces] == [
        "ethernet1/5.262", "ethernet1/5.264", "ethernet1/5.265", "ethernet1/5.266", "ethernet1/5.2204"
    ]
    assert result.summary.zone_reference_changes == 2
    assert result.summary.virtual_router_reference_changes == 2
    assert result.summary.static_route_reference_changes == 1
    assert any(change.reference_type == ReferenceType.ZONE_INTERFACE and change.object_name == "inside"
        and change.scope == "vsys1" and change.old_value == "ethernet1/12.262"
        and change.new_value == "ethernet1/5.262" for change in result.impacts[0].reference_changes)
    assert result.model_dump_json() == preview(complex_inventory, profile, ("ethernet1/12", "ethernet1/5")).model_dump_json()


def test_index_preserves_scope_and_nat(complex_inventory):
    complex_inventory = complex_inventory.model_copy(deep=True)
    complex_inventory.nat_rules[0].interface_references = ["ethernet1/12.262"]
    index = build_dependency_index(complex_inventory)
    assert any(ref.reference_type == ReferenceType.NAT_INTERFACE_REFERENCE for ref in index["ethernet1/12.262"])
    assert {ref.scope for ref in index["ethernet1/12.262"] if ref.reference_type == ReferenceType.ZONE_INTERFACE} == {"vsys1"}


def test_nat_preview_and_duplicate_zone_names(complex_inventory, profile):
    complex_inventory = complex_inventory.model_copy(deep=True)
    complex_inventory.nat_rules[0].interface_references = ["ethernet1/12.262"]
    complex_inventory.zones.append(Zone(name="inside", vsys="vsys2", zone_type="layer3", interface_members=["ethernet1/12.262"]))
    result = preview(complex_inventory, profile, ("ethernet1/12", "ethernet1/5"))
    assert result.summary.nat_reference_changes == 1
    assert result.summary.zone_reference_changes == 3
    assert {change.scope for change in result.impacts[0].reference_changes if change.reference_type == ReferenceType.ZONE_INTERFACE
        and change.object_name == "inside"} == {"vsys1", "vsys2"}


@pytest.mark.parametrize("pairs,code", [
    ([("ethernet1/12", "ethernet1/5"), ("ethernet1/12", "ethernet1/7")], "DUPLICATE_SOURCE_MAPPING"),
    ([("ethernet1/12", "ethernet1/5"), ("ethernet1/1", "ethernet1/5")], "DUPLICATE_TARGET_MAPPING"),
    ([("ethernet1/99", "ethernet1/5")], "SOURCE_INTERFACE_NOT_FOUND"),
    ([("ethernet1/12", "ethernet1/99")], "TARGET_INTERFACE_NOT_FOUND"),
    ([("ethernet1/12.262", "ethernet1/5")], "UNSUPPORTED_MAPPING_OBJECT"),
])
def test_blocking_validation(complex_inventory, profile, pairs, code):
    result = preview(complex_inventory, profile, *pairs)
    assert result.status == PreviewStatus.BLOCKED
    assert code in {finding.code for finding in result.findings}


def test_aggregate_and_partial_modes(complex_inventory, profile):
    complex_inventory = complex_inventory.model_copy(deep=True)
    aggregate = preview(complex_inventory, profile, ("ethernet1/1", "ethernet1/7"))
    assert aggregate.status == PreviewStatus.REVIEW_REQUIRED
    assert "AGGREGATE_MEMBER_REVIEW" in {finding.code for finding in aggregate.findings}
    assert aggregate.summary.aggregate_membership_changes == 1
    layer2 = preview(complex_inventory, profile, ("ethernet1/13", "ethernet1/5"))
    assert layer2.status == PreviewStatus.REVIEW_REQUIRED
    assert "PARTIAL_DEPENDENCY_COVERAGE" in {finding.code for finding in layer2.findings}
    complex_inventory.physical_interfaces.append(PhysicalInterface(name="ethernet1/5", mode="virtual_wire"))
    assert preview(complex_inventory, profile, ("ethernet1/5", "ethernet1/5")).status == PreviewStatus.REVIEW_REQUIRED


def test_target_type_and_multi_device(complex_inventory, profile):
    complex_inventory = complex_inventory.model_copy(deep=True)
    profile = profile.model_copy(deep=True)
    profile.interfaces.append(HardwareInterface(name="loopback.1", kind=HardwareKind.LOOPBACK))
    wrong_type = preview(complex_inventory, profile, ("ethernet1/12", "loopback.1"))
    assert wrong_type.status == PreviewStatus.BLOCKED
    assert "TARGET_INTERFACE_TYPE_UNSUPPORTED" in {finding.code for finding in wrong_type.findings}
    complex_inventory.device_entries.append(DeviceEntry(name="second"))
    multiple = preview(complex_inventory, profile, ("ethernet1/12", "ethernet1/5"))
    assert multiple.status == PreviewStatus.BLOCKED
    assert multiple.summary.valid_mappings == 0
    assert "MULTI_DEVICE_INVENTORY_UNSUPPORTED" in {finding.code for finding in multiple.findings}


def test_exact_identity_suffix_and_same_name(complex_inventory, profile):
    complex_inventory = complex_inventory.model_copy(deep=True)
    complex_inventory.physical_interfaces.extend([
        PhysicalInterface(name="ethernet1/10", mode="layer3"),
        PhysicalInterface(name="ethernet1/11", mode="layer3"),
        PhysicalInterface(name="ethernet1/5", mode="layer3"),
    ])
    complex_inventory.subinterfaces.append(Subinterface(name="ethernet1/12.100", parent_interface="ethernet1/12", mode="layer3", tag=200))
    result = preview(complex_inventory, profile, ("ethernet1/12", "ethernet1/5"))
    assert next(item for item in result.impacts[0].derived_subinterfaces if item.source_interface == "ethernet1/12.100").target_interface == "ethernet1/5.100"
    assert all(change.old_value not in {"ethernet1/10", "ethernet1/11"} for change in result.impacts[0].reference_changes)
    assert preview(complex_inventory, profile, ("ethernet1/5", "ethernet1/5")).status == PreviewStatus.READY


def test_similar_interface_names_never_change(complex_inventory, profile):
    inventory = complex_inventory.model_copy(deep=True)
    inventory.physical_interfaces.extend([
        PhysicalInterface(name="ethernet1/10", mode="layer3"),
        PhysicalInterface(name="ethernet1/11", mode="layer3"),
    ])
    inventory.zones.append(Zone(name="identity-check", vsys="vsys1", zone_type="layer3",
        interface_members=["ethernet1/1", "ethernet1/10", "ethernet1/11"]))
    result = preview(inventory, profile, ("ethernet1/1", "ethernet1/5"))
    changes = [change for change in result.impacts[0].reference_changes if change.object_name == "identity-check"]
    assert [(change.old_value, change.new_value) for change in changes] == [("ethernet1/1", "ethernet1/5")]
    assert inventory.zones[-1].interface_members == ["ethernet1/1", "ethernet1/10", "ethernet1/11"]


def test_profile_validation(profile, tmp_path):
    assert profile.profile_status.value == "synthetic"
    assert profile.model_dump_json() == load_hardware_profile(PROFILE).model_dump_json()
    for content in ('{', '{"vendor":"x","model":"y","profile_status":"synthetic","interfaces":[{"name":" ","kind":"physical_ethernet"}]}',
        '{"vendor":"x","model":"y","profile_status":"synthetic","interfaces":[{"name":"a","kind":"physical_ethernet"},{"name":"a","kind":"physical_ethernet"}]}',
        '{"vendor":"x","model":"y","profile_status":"synthetic","interfaces":[{"name":"a","kind":"unknown_kind"}]}'):
        path = tmp_path / "bad.json"
        path.write_text(content)
        with pytest.raises(HardwareProfileError):
            load_hardware_profile(path)


def test_cli_safe_output():
    result = subprocess.run([sys.executable, "-m", "confighop_core.preview",
        str(FIXTURES / "paloalto" / "pa_complex_synthetic.xml"),
        "--target-profile", str(PROFILE), "--map", "ethernet1/12=ethernet1/5"],
        capture_output=True, text=True, check=True)
    assert "Derived Subinterfaces: 5" in result.stdout
    assert "Preview Status: READY" in result.stdout
    assert "192.0.2." not in result.stdout
    assert "203.0.113." not in result.stdout
