from xml.etree import ElementTree

import pytest

from confighop_api.target_package import (
    TargetPackageError, analyze_target_safety, build_target_package,
)


TARGET = b"""<config version="11.1.0">
  <mgt-config><users><entry name="target-admin"/></users></mgt-config>
  <shared><certificate><entry name="target-cert"><private-key>secret</private-key></entry></certificate>
    <address><entry name="target-shared"><ip-netmask>192.0.2.1</ip-netmask></entry></address></shared>
  <devices><entry name="localhost.localdomain">
    <deviceconfig><system><hostname>target-fw</hostname><panorama-server>192.0.2.10</panorama-server></system>
      <high-availability><enabled>no</enabled></high-availability></deviceconfig>
    <network><profiles><interface-management-profile><entry name="api-safe"/></interface-management-profile></profiles>
      <interface><ethernet><entry name="ethernet1/1"><layer3/></entry></ethernet></interface></network>
    <vsys><entry name="vsys1"><address>
      <entry name="keep-target"><ip-netmask>198.51.100.1</ip-netmask></entry>
      <entry name="replace-me"><ip-netmask>198.51.100.2</ip-netmask></entry>
    </address><rulebase><security><rules><entry name="target-only"><action>deny</action></entry>
    </rules></security></rulebase></entry></vsys>
  </entry></devices>
</config>"""

SOURCE = b"""<config version="11.1.0">
  <mgt-config><users><entry name="source-admin"/></users></mgt-config>
  <shared><address><entry name="source-shared"><ip-netmask>203.0.113.1</ip-netmask></entry></address></shared>
  <devices><entry name="source-device">
    <deviceconfig><system><hostname>source-fw</hostname></system></deviceconfig>
    <network><interface><ethernet><entry name="ethernet1/2"><layer3><interface-management-profile>api-safe</interface-management-profile></layer3></entry></ethernet></interface>
      <virtual-router><entry name="vr1"><interface><member>ethernet1/2</member></interface></entry></virtual-router></network>
    <vsys><entry name="vsys1"><zone><entry name="inside"><network><layer3><member>ethernet1/2</member></layer3></network></entry></zone>
      <address><entry name="replace-me"><ip-netmask>203.0.113.2</ip-netmask></entry></address>
      <rulebase><security><rules><entry name="allow-source"><action>allow</action></entry></rules></security></rulebase>
    </entry></vsys>
  </entry></devices>
</config>"""


def test_builds_on_target_and_preserves_target_local_scopes():
    result = build_target_package(TARGET, SOURCE)
    root = ElementTree.fromstring(result.xml)

    assert root.find("./mgt-config/users/entry").get("name") == "target-admin"
    assert root.findtext("./devices/entry/deviceconfig/system/hostname") == "target-fw"
    assert root.find("./shared/certificate/entry").get("name") == "target-cert"
    assert root.find("./devices/entry/vsys/entry/address/entry[@name='keep-target']") is not None
    assert root.findtext(
        "./devices/entry/vsys/entry/address/entry[@name='replace-me']/ip-netmask") == "203.0.113.2"
    assert root.find("./devices/entry/vsys/entry/rulebase/security/rules/entry[@name='target-only']") is not None
    assert root.find("./devices/entry/vsys/entry/rulebase/security/rules/entry[@name='allow-source']") is not None
    assert root.find("./shared/address/entry[@name='source-shared']") is not None
    assert set(result.preservation.values()) == {"PRESERVED"}
    assert {item.code for item in result.findings} >= {
        "TARGET_NAMED_ENTRY_REPLACED", "TARGET_POLICY_ORDER_REVIEW_REQUIRED",
        "TARGET_LOCAL_SCOPES_PRESERVED",
    }
    assert any(item.scope == "vsys/vsys1/address" and item.object_name == "replace-me"
        and item.action == "REPLACED" for item in result.changes)


def test_missing_target_management_profile_is_blocking_finding():
    result = build_target_package(TARGET, SOURCE.replace(b"api-safe", b"source-only"))

    finding = next(item for item in result.findings
        if item.code == "TARGET_MANAGEMENT_PROFILE_MISSING")
    assert finding.severity == "ERROR"
    assert finding.requires_acceptance is False


def test_multi_vsys_or_mismatched_vsys_is_rejected():
    multi = TARGET.replace(b"</vsys>", b'<entry name="vsys2"/></vsys>')
    with pytest.raises(TargetPackageError, match="exactly one source and target vsys"):
        build_target_package(multi, SOURCE)

    mismatch = TARGET.replace(b'name="vsys1"', b'name="other"')
    with pytest.raises(TargetPackageError, match="vsys names must match"):
        build_target_package(mismatch, SOURCE)


def test_invalid_or_non_config_documents_are_rejected():
    with pytest.raises(TargetPackageError, match="Target baseline XML is invalid"):
        build_target_package(b"<config>", SOURCE)
    with pytest.raises(TargetPackageError, match="config root"):
        build_target_package(b"<response/>", SOURCE)


def test_target_safety_detects_ha_panorama_and_multi_vsys():
    unsafe = analyze_target_safety(TARGET, multi_vsys=True)
    assert unsafe.ha_clear is True
    assert unsafe.panorama_clear is False
    assert unsafe.multi_vsys_clear is False

    direct = TARGET.replace(b"<panorama-server>192.0.2.10</panorama-server>", b"")
    safe = analyze_target_safety(direct, multi_vsys=False)
    assert safe.ha_clear is True
    assert safe.panorama_clear is True
    assert safe.multi_vsys_clear is True

    enabled = direct.replace(b"<enabled>no</enabled>", b"<enabled>yes</enabled>")
    assert analyze_target_safety(enabled, multi_vsys=False).ha_clear is False
