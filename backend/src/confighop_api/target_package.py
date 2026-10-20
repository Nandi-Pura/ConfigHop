import copy
from dataclasses import dataclass
from xml.etree import ElementTree as StdElementTree

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from .project_state import TargetPackageChange, TargetPackageFinding


class TargetPackageError(ValueError):
    pass


@dataclass(frozen=True)
class TargetPackageBuild:
    xml: bytes
    changes: list[TargetPackageChange]
    preservation: dict[str, str]
    findings: list[TargetPackageFinding]


@dataclass(frozen=True)
class TargetSafety:
    ha_clear: bool
    panorama_clear: bool
    multi_vsys_clear: bool


_DEVICE_ENTRY_SCOPES = (
    "network/interface/ethernet",
    "network/interface/aggregate-ethernet",
    "network/interface/vlan/units",
    "network/interface/loopback/units",
    "network/interface/tunnel/units",
    "network/virtual-router",
)
_VSYS_ENTRY_SCOPES = (
    "zone", "address", "address-group", "service", "service-group", "application-group",
    "schedule", "rulebase/security/rules", "rulebase/nat/rules",
)
_SHARED_ENTRY_SCOPES = (
    "address", "address-group", "service", "service-group", "application-group", "schedule",
)


def _parse(document: bytes, label: str):
    try:
        root = ElementTree.fromstring(document)
    except (ElementTree.ParseError, DefusedXmlException, ValueError) as exc:
        raise TargetPackageError(f"{label} XML is invalid.") from exc
    if root.tag != "config":
        raise TargetPackageError(f"{label} XML must have a config root.")
    entries = root.findall("./devices/entry")
    if len(entries) != 1:
        raise TargetPackageError(f"{label} XML must contain exactly one device entry.")
    return root, entries[0]


def _serialized(element) -> bytes | None:
    return StdElementTree.tostring(element, encoding="utf-8") if element is not None else None


def _ensure_path(parent, path: str):
    current = parent
    for tag in path.split("/"):
        child = current.find(tag)
        if child is None:
            child = StdElementTree.SubElement(current, tag)
        current = child
    return current


def _merge_entries(source_parent, target_parent, path: str, prefix: str,
    changes: list[TargetPackageChange], findings: list[TargetPackageFinding]) -> None:
    source_container = source_parent.find(path)
    if source_container is None:
        return
    target_container = _ensure_path(target_parent, path)
    for source_entry in source_container.findall("entry"):
        name = (source_entry.get("name") or "").strip()
        if not name:
            raise TargetPackageError(f"Migration scope {prefix}/{path} contains an unnamed entry.")
        existing = next((item for item in target_container.findall("entry")
            if item.get("name") == name), None)
        if existing is not None and _serialized(existing) == _serialized(source_entry):
            continue
        action = "REPLACED" if existing is not None else "ADDED"
        if existing is not None:
            index = list(target_container).index(existing)
            target_container.remove(existing)
            target_container.insert(index, copy.deepcopy(source_entry))
            findings.append(TargetPackageFinding(code="TARGET_NAMED_ENTRY_REPLACED",
                severity="WARNING", scope=f"{prefix}/{path}",
                message=f"Target entry {name} will be replaced by the reviewed migration entry.",
                requires_acceptance=True))
        else:
            target_container.append(copy.deepcopy(source_entry))
        changes.append(TargetPackageChange(scope=f"{prefix}/{path}", object_name=name,
            action=action))


def _protected_snapshot(root, device) -> dict[str, bytes | tuple[str, ...] | None]:
    shared = root.find("shared")
    vsys_names = tuple(sorted((entry.get("name") or "") for entry in device.findall("./vsys/entry")))
    return {
        "management_plane": _serialized(root.find("mgt-config")),
        "device_identity_and_services": _serialized(device.find("deviceconfig")),
        "network_management_profiles": _serialized(device.find("./network/profiles")),
        "certificates_and_private_keys": _serialized(
            shared.find("certificate") if shared is not None else None),
        "vsys_topology": vsys_names,
    }


def build_target_package(target_baseline: bytes, source_candidate: bytes) -> TargetPackageBuild:
    target_root, target_device = _parse(target_baseline, "Target baseline")
    source_root, source_device = _parse(source_candidate, "Source candidate")
    source_vsys = source_device.findall("./vsys/entry")
    target_vsys = target_device.findall("./vsys/entry")
    if len(source_vsys) != 1 or len(target_vsys) != 1:
        raise TargetPackageError("Direct-firewall package building requires exactly one source and target vsys.")
    if source_vsys[0].get("name") != target_vsys[0].get("name"):
        raise TargetPackageError("Source and target vsys names must match for direct-firewall migration.")

    before = _protected_snapshot(target_root, target_device)
    changes: list[TargetPackageChange] = []
    findings: list[TargetPackageFinding] = []
    for path in _DEVICE_ENTRY_SCOPES:
        _merge_entries(source_device, target_device, path, "device", changes, findings)
    for path in _VSYS_ENTRY_SCOPES:
        _merge_entries(source_vsys[0], target_vsys[0], path,
            f"vsys/{source_vsys[0].get('name')}", changes, findings)
    source_shared = source_root.find("shared")
    if source_shared is not None:
        target_shared = target_root.find("shared")
        if target_shared is None:
            target_shared = StdElementTree.SubElement(target_root, "shared")
        for path in _SHARED_ENTRY_SCOPES:
            _merge_entries(source_shared, target_shared, path, "shared", changes, findings)

    referenced_profiles = {(element.text or "").strip() for element in source_device.iterfind(
        ".//interface-management-profile") if (element.text or "").strip()}
    target_profiles = {entry.get("name") for entry in target_device.findall(
        "./network/profiles/interface-management-profile/entry")}
    for name in sorted(referenced_profiles - target_profiles):
        findings.append(TargetPackageFinding(code="TARGET_MANAGEMENT_PROFILE_MISSING",
            severity="ERROR", scope="device/network/profiles/interface-management-profile",
            message=f"Target-local interface management profile {name} is referenced but unavailable."))

    if source_vsys[0].find("./rulebase/security/rules/entry") is not None or (
        source_vsys[0].find("./rulebase/nat/rules/entry") is not None):
        findings.append(TargetPackageFinding(code="TARGET_POLICY_ORDER_REVIEW_REQUIRED",
            severity="WARNING", scope=f"vsys/{source_vsys[0].get('name')}/rulebase",
            message="Review final security and NAT rule order against the target baseline.",
            requires_acceptance=True))

    after = _protected_snapshot(target_root, target_device)
    preservation: dict[str, str] = {}
    for name, value in before.items():
        if after[name] != value:
            raise TargetPackageError(f"Protected target-local scope changed: {name}.")
        preservation[name] = "PRESERVED"
    findings.append(TargetPackageFinding(code="TARGET_LOCAL_SCOPES_PRESERVED",
        severity="INFO", scope="target-local",
        message="Protected management, identity, HA/Panorama, certificate, and vsys topology scopes are unchanged."))
    return TargetPackageBuild(xml=StdElementTree.tostring(target_root, encoding="utf-8"),
        changes=changes, preservation=preservation, findings=findings)


def analyze_target_safety(document: bytes, *, multi_vsys: bool | None) -> TargetSafety:
    root, device = _parse(document, "Target running configuration")
    ha = device.find("./deviceconfig/high-availability")
    ha_enabled = (ha.findtext("enabled") or "").strip().lower() if ha is not None else ""
    ha_clear = ha is None or ha_enabled in {"no", "false", "off"}
    system = device.find("./deviceconfig/system")
    panorama_values = [] if system is None else [
        (system.findtext(name) or "").strip()
        for name in ("panorama-server", "panorama-server-2")
    ]
    panorama_clear = not any(panorama_values) and root.find("./panorama") is None
    multi_vsys_clear = multi_vsys is False and len(device.findall("./vsys/entry")) == 1
    return TargetSafety(ha_clear=ha_clear, panorama_clear=panorama_clear,
        multi_vsys_clear=multi_vsys_clear)
