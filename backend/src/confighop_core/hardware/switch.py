import re

from ..evidence.switch import SWITCH_EVIDENCE
from ..models.hardware import (CandidateSupport, HardwareInterface, HardwareKind, HardwareProfile,
    PlatformDomain, ProfileStatus, SoftwareFamily, SoftwareSupportRule, SoftwareSupportStatus,
    TargetRenderSupport)
from ..evidence.registry import CHECKED_AT


def _ports(prefix: str, numbers: range, media: str, speeds: list[str], evidence: str) -> list[HardwareInterface]:
    return [HardwareInterface(name=f"{prefix}{number}", kind=HardwareKind.PHYSICAL_ETHERNET,
        speed_capabilities=speeds, media=media, media_capabilities=[media],
        candidate_support=CandidateSupport.BLOCKED, evidence_ids=[evidence]) for number in numbers]


C9300_48P = HardwareProfile(id="cisco-c9300-48p", vendor="cisco", model="C9300-48P",
    series="Catalyst 9300", domain=PlatformDomain.SWITCH, software_family=SoftwareFamily.IOS_XE,
    profile_status=ProfileStatus.VERIFIED, target_render_support=TargetRenderSupport.ANALYSIS_ONLY,
    interfaces=_ports("GigabitEthernet1/0/", range(1, 49), "RJ45", ["10M", "100M", "1G"], "CISCO-C9300-HARDWARE"),
    evidence_ids=["CISCO-C9300-HARDWARE", "CISCO-C9300-IOSXE-17-12"],
    software_support_rules=[SoftwareSupportRule(train="17.12", status=SoftwareSupportStatus.SUPPORTED,
        evidence_ids=["CISCO-C9300-IOSXE-17-12"])], verified_at=CHECKED_AT.isoformat(),
    notes="Base data ports only. Installed modular uplink module is unknown; uplink ports are not verified.")

JL663A = HardwareProfile(id="hpe-aruba-jl663a", vendor="hpe_aruba", model="JL663A",
    series="CX 6300M 48G", domain=PlatformDomain.SWITCH, software_family=SoftwareFamily.AOS_CX,
    profile_status=ProfileStatus.VERIFIED, target_render_support=TargetRenderSupport.ANALYSIS_ONLY,
    interfaces=_ports("1/1/", range(1, 49), "RJ45", ["1G"], "ARUBA-JL663A-PORTS")
        + _ports("1/1/", range(49, 53), "SFP56", ["1G", "10G", "25G", "50G"], "ARUBA-JL663A-QUICKSPECS"),
    evidence_ids=["ARUBA-JL663A-PORTS", "ARUBA-JL663A-QUICKSPECS", "ARUBA-JL663A-AOSCX-10-15"],
    software_support_rules=[SoftwareSupportRule(train="10.15", status=SoftwareSupportStatus.SUPPORTED,
        evidence_ids=["ARUBA-JL663A-AOSCX-10-15"])], verified_at=CHECKED_AT.isoformat(),
    notes="Exact JL663A SKU; 48 fixed copper ports and four fixed SFP56 uplinks. No renderer.")

SWITCH_PROFILES = {profile.id: profile for profile in (C9300_48P, JL663A)}
if len(SWITCH_PROFILES) != 2:
    raise ValueError("duplicate Switch hardware profile ID")
for profile in SWITCH_PROFILES.values():
    ids = profile.evidence_ids + [id for item in profile.interfaces for id in item.evidence_ids]
    ids += [id for rule in profile.software_support_rules for id in rule.evidence_ids]
    if any(id not in SWITCH_EVIDENCE for id in ids):
        raise ValueError(f"unknown Switch evidence ID in {profile.id}")


def get_switch_profile(profile_id: str) -> HardwareProfile | None:
    return SWITCH_PROFILES.get(profile_id)


def switch_version_support(profile_id: str, version: str) -> str:
    profile = get_switch_profile(profile_id)
    if profile is None:
        return "UNKNOWN_HARDWARE"
    if profile.profile_status != ProfileStatus.VERIFIED:
        return "VERSION_NOT_VERIFIED"
    match = re.fullmatch(r"(\d+\.\d+)(?:\.\d+)?", version)
    if match is None:
        return "VERSION_NOT_VERIFIED"
    return "SUPPORTED" if any(rule.train == match[1] and rule.status == SoftwareSupportStatus.SUPPORTED
        for rule in profile.software_support_rules) else "VERSION_NOT_VERIFIED"
