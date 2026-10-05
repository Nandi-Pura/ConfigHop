from datetime import date
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator

from confighop_core.models.hardware import (
    CandidateSupport, HardwareInterface, HardwareInterfaceGroup, HardwareKind, HardwareProfile,
    MappingSupport, PortAvailability, ProfileStatus, RequiredCondition,
)

CHECKED_AT = date(2026, 10, 5)
TRAINS = ["10.2", "11.0", "11.1", "11.2", "12.1", "12.2"]


class EvidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    RETIRED = "RETIRED"


class EvidenceRecord(BaseModel):
    id: str
    vendor: str = "palo_alto"
    source_title: str
    source_url: str
    source_type: str
    checked_at: date = CHECKED_AT
    scope: str
    summary: str
    status: EvidenceStatus = EvidenceStatus.VERIFIED

    @field_validator("source_url")
    @classmethod
    def official_https(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in {"docs.paloaltonetworks.com", "paloaltonetworks.com", "www.paloaltonetworks.com"} or parsed.username or parsed.password:
            raise ValueError("verified evidence requires an official HTTPS URL")
        return value


EVIDENCE = {
    item.id: item for item in [
        EvidenceRecord(id="PAN-HW-PA3400-OVERVIEW", source_title="PA-3400 Series Firewall Overview", source_url="https://docs.paloaltonetworks.com/hardware/pa-3400-hardware-reference/pa-3400-series-overview", source_type="HARDWARE_OVERVIEW", scope="PA-3400 models and first supported PAN-OS release", summary="PA-3410 belongs to PA-3400; first supported PAN-OS release is 10.2."),
        EvidenceRecord(id="PAN-HW-PA3400-FRONT", source_title="PA-3400 Series Front Panel", source_url="https://docs.paloaltonetworks.com/hardware/pa-3400-hardware-reference/pa-3400-series-overview/front-panel-3400-series", source_type="HARDWARE_REFERENCE", scope="PA-3410 dataplane port groups", summary="PA-3410 has Ethernet 1–26 in RJ45, SFP/SFP+, and SFP28 groups."),
        EvidenceRecord(id="PAN-HW-PA5400-OVERVIEW", source_title="PA-5400 Series Firewall Overview", source_url="https://docs.paloaltonetworks.com/hardware/pa-5400-hardware-reference/pa-5400-series-firewall-overview", source_type="HARDWARE_OVERVIEW", scope="PA-5410 model and first supported release", summary="PA-5410 first supports PAN-OS 10.2.0."),
        EvidenceRecord(id="PAN-HW-PA5400-FRONT", source_title="PA-5400 Series Front Panel", source_url="https://docs.paloaltonetworks.com/hardware/pa-5400-hardware-reference/pa-5400-series-firewall-overview/pa-5400-series-front-and-back-panel-descriptions/pa-5400-series-front-panel", source_type="HARDWARE_REFERENCE", scope="PA-5410 dataplane ports, breakout topology, native QSFP speed condition", summary="PA-5410 has 1–24 direct ports, 25–40 breakout identities and 41–44 native QSFP identities; auto speed defaults QSFP to breakout."),
        EvidenceRecord(id="PAN-COMPAT-PANOS-BY-MODEL", source_title="Palo Alto Networks Next-Generation Firewalls", source_url="https://docs.paloaltonetworks.com/compatibility-matrix/reference/supported-os-releases-by-model/palo-alto-networks-next-gen-firewalls", source_type="COMPATIBILITY_MATRIX", scope="PA-3400 and PA-5410 PAN-OS trains", summary="Both model groups support 10.2, 11.0, 11.1, 11.2, 12.1 and 12.2; 12.x starts at 12.1.2."),
        EvidenceRecord(id="PAN-COMPAT-BREAKOUT", source_title="Breakout Port Support", source_url="https://docs.paloaltonetworks.com/compatibility-matrix/reference/supported-os-releases-by-model/breakout-port-support", source_type="COMPATIBILITY_MATRIX", scope="PA-5410 QSFP breakout parent and child identities", summary="Ports 41–44 each break out to four children at 10G or 25G."),
    ]
}


def _group(profile: str, key: str, numbers: range, media: list[str], speeds: list[str], evidence: str,
           availability: PortAvailability = PortAvailability.NATIVE,
           condition: RequiredCondition = RequiredCondition.NONE, notes: str | None = None) -> tuple[HardwareInterfaceGroup, list[HardwareInterface]]:
    names = [f"ethernet1/{number}" for number in numbers]
    blocked = condition != RequiredCondition.NONE
    group = HardwareInterfaceGroup(id=f"{profile}-{key}", label=key, interface_names=names,
        media_capabilities=media, speed_capabilities=speeds, availability=availability,
        mapping_support=MappingSupport.CONDITIONAL if availability == PortAvailability.NATIVE_CONDITIONAL else MappingSupport.UNSUPPORTED if blocked else MappingSupport.SUPPORTED,
        candidate_support=CandidateSupport.BLOCKED if blocked else CandidateSupport.SUPPORTED,
        required_condition=condition, evidence_ids=[evidence], notes=notes)
    interfaces = [HardwareInterface(name=name, kind=HardwareKind.PHYSICAL_ETHERNET,
        speed_capabilities=speeds, media_capabilities=media, media=media[0], availability=availability,
        mapping_support=group.mapping_support, candidate_support=group.candidate_support,
        required_condition=condition, parent_interface=f"ethernet1/{41 + (number - 25) // 4}" if availability == PortAvailability.BREAKOUT_CHILD else None,
        evidence_ids=[evidence], ztp_capable=number == 1, notes=notes) for number, name in zip(numbers, names)]
    return group, interfaces


def _profile(profile_id: str, model: str, series: str, groups: list[tuple[HardwareInterfaceGroup, list[HardwareInterface]]], evidence_ids: list[str], first: str) -> HardwareProfile:
    return HardwareProfile(id=profile_id, vendor="palo_alto", model=model, series=series,
        profile_status=ProfileStatus.VERIFIED, interfaces=sorted([item for _, members in groups for item in members], key=lambda item: int(item.name.split("/")[1])),
        interface_groups=[group for group, _ in groups], evidence_ids=evidence_ids,
        supported_panos_trains=TRAINS, first_supported_release=first, verified_at=CHECKED_AT.isoformat())


PA3410 = _profile("paloalto-pa-3410", "PA-3410", "PA-3400", [
    _group("pa3410", "RJ45 1-12", range(1, 13), ["RJ45"], ["10M", "100M", "1G", "2.5G", "5G", "10G"], "PAN-HW-PA3400-FRONT"),
    _group("pa3410", "SFP 13-22", range(13, 23), ["SFP", "SFP_PLUS"], ["1G", "10G"], "PAN-HW-PA3400-FRONT"),
    _group("pa3410", "SFP28 23-26", range(23, 27), ["SFP", "SFP_PLUS", "SFP28"], ["1G", "10G", "25G"], "PAN-HW-PA3400-FRONT", notes="RS-FEC is documented; ConfigHop does not configure FEC."),
], ["PAN-HW-PA3400-OVERVIEW", "PAN-HW-PA3400-FRONT", "PAN-COMPAT-PANOS-BY-MODEL"], "10.2")

PA5410 = _profile("paloalto-pa-5410", "PA-5410", "PA-5400", [
    _group("pa5410", "RJ45 1-8", range(1, 9), ["RJ45"], ["10M", "100M", "1G", "2.5G", "5G", "10G"], "PAN-HW-PA5400-FRONT"),
    _group("pa5410", "SFP 9-20", range(9, 21), ["SFP", "SFP_PLUS"], ["1G", "10G"], "PAN-HW-PA5400-FRONT"),
    _group("pa5410", "SFP28 21-24", range(21, 25), ["SFP", "SFP_PLUS", "SFP28"], ["1G", "10G", "25G"], "PAN-HW-PA5400-FRONT", notes="Remote endpoint RS-FEC is documented; ConfigHop does not configure FEC."),
    _group("pa5410", "Breakout 25-40", range(25, 41), ["QSFP_PLUS", "QSFP28"], ["10G", "25G"], "PAN-COMPAT-BREAKOUT", PortAvailability.BREAKOUT_CHILD, RequiredCondition.BREAKOUT_MODE),
    _group("pa5410", "Conditional QSFP 41-44", range(41, 45), ["QSFP_PLUS", "QSFP28"], ["40G", "100G"], "PAN-HW-PA5400-FRONT", PortAvailability.NATIVE_CONDITIONAL, RequiredCondition.MANUAL_NATIVE_PORT_SPEED, notes="Auto speed defaults to breakout; native mode needs explicit speed that ConfigHop does not render."),
], ["PAN-HW-PA5400-OVERVIEW", "PAN-HW-PA5400-FRONT", "PAN-COMPAT-PANOS-BY-MODEL", "PAN-COMPAT-BREAKOUT"], "10.2.0")

SYNTHETIC = HardwareProfile(id="paloalto-synthetic-64", vendor="palo_alto", model="synthetic-panos-target-64",
    profile_status=ProfileStatus.SYNTHETIC,
    interfaces=[HardwareInterface(name=f"ethernet1/{number}", kind=HardwareKind.PHYSICAL_ETHERNET) for number in range(1, 65)],
    notes="Development profile only; no real hardware compatibility claim.")

PROFILES = {profile.id: profile for profile in [SYNTHETIC, PA3410, PA5410]}


def get_profile(profile_id: str) -> HardwareProfile | None:
    return PROFILES.get(profile_id)
