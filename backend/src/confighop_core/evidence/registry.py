from datetime import date
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, ValidationInfo, field_validator

CHECKED_AT = date(2026, 10, 7)


class EvidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    RETIRED = "RETIRED"


class VerificationLevel(StrEnum):
    DOCUMENTATION_VERIFIED = "DOCUMENTATION_VERIFIED"
    DEVICE_VALIDATED = "DEVICE_VALIDATED"


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
    verification_level: VerificationLevel | None = None
    device_validated: bool = False

    @field_validator("source_url")
    @classmethod
    def official_https(cls, value: str, info: ValidationInfo) -> str:
        parsed = urlparse(value)
        vendor = info.data.get("vendor")
        hosts = {
            "palo_alto": {"docs.paloaltonetworks.com", "paloaltonetworks.com", "www.paloaltonetworks.com"},
            "cisco": {"www.cisco.com"},
            "hpe_aruba": {"arubanetworking.hpe.com", "www.hpe.com"},
        }
        official = parsed.hostname in hosts.get(vendor, set()) or (
            vendor == "palo_alto" and parsed.hostname == "github.com"
            and parsed.path.startswith("/PaloAltoNetworks/pan-os-python/"))
        if parsed.scheme != "https" or not official or parsed.username or parsed.password:
            raise ValueError("verified evidence requires an official HTTPS URL")
        return value


EVIDENCE = {
    item.id: item for item in [
        EvidenceRecord(id="PAN-HW-PA3400-OVERVIEW", source_title="PA-3400 Series Firewall Overview", source_url="https://docs.paloaltonetworks.com/hardware/pa-3400-hardware-reference/pa-3400-series-overview", source_type="HARDWARE_OVERVIEW", scope="PA-3400 models and first supported PAN-OS release", summary="PA-3410 belongs to PA-3400; first supported PAN-OS release is 10.2."),
        EvidenceRecord(id="PAN-HW-PA3400-FRONT", source_title="PA-3400 Series Front Panel", source_url="https://docs.paloaltonetworks.com/hardware/pa-3400-hardware-reference/pa-3400-series-overview/front-panel-3400-series", source_type="HARDWARE_REFERENCE", scope="PA-3410 dataplane port groups", summary="PA-3410 has Ethernet 1–26 in RJ45, SFP/SFP+, and SFP28 groups."),
        EvidenceRecord(id="PAN-HW-PA5400-OVERVIEW", source_title="PA-5400 Series Firewall Overview", source_url="https://docs.paloaltonetworks.com/hardware/pa-5400-hardware-reference/pa-5400-series-firewall-overview", source_type="HARDWARE_OVERVIEW", scope="PA-5410 model and first supported release", summary="PA-5410 first supports PAN-OS 10.2.0."),
        EvidenceRecord(id="PAN-HW-PA5400-FRONT", source_title="PA-5400 Series Front Panel", source_url="https://docs.paloaltonetworks.com/hardware/pa-5400-hardware-reference/pa-5400-series-firewall-overview/pa-5400-series-front-and-back-panel-descriptions/pa-5400-series-front-panel", source_type="HARDWARE_REFERENCE", scope="PA-5410 dataplane ports, breakout topology, native QSFP speed condition", summary="PA-5410 has 1–24 direct ports, 25–40 breakout identities and 41–44 native QSFP identities; auto speed defaults QSFP to breakout."),
        EvidenceRecord(id="PAN-COMPAT-PANOS-BY-MODEL", source_title="Palo Alto Networks Next-Generation Firewalls", source_url="https://docs.paloaltonetworks.com/compatibility-matrix/reference/supported-os-releases-by-model/palo-alto-networks-next-gen-firewalls", source_type="COMPATIBILITY_MATRIX", scope="PA-1400, PA-3200, PA-3400, PA-5200, and PA-5410 PAN-OS trains", summary="The current matrix lists explicit supported and unsupported trains for each series; 12.x support begins at 12.1.2 where listed."),
        EvidenceRecord(id="PAN-COMPAT-BREAKOUT", source_title="Breakout Port Support", source_url="https://docs.paloaltonetworks.com/compatibility-matrix/reference/supported-os-releases-by-model/breakout-port-support", source_type="COMPATIBILITY_MATRIX", scope="PA-5410 QSFP breakout parent and child identities", summary="Ports 41–44 each break out to four children at 10G or 25G."),
        EvidenceRecord(id="PAN-CONFIG-ETHERNET-LINK-SPEED", source_title="PAN-OS Python SDK EthernetInterface", source_url="https://github.com/PaloAltoNetworks/pan-os-python/blob/92ed648d89b7541052a15e234eb34e99edba6d2d/panos/network.py", source_type="VENDOR_SDK", scope="Ethernet link-speed XML node", summary="EthernetInterface serializes link_speed under the direct link-speed node; the official SDK Ethernet serialization test confirms direct value output.", verification_level="DOCUMENTATION_VERIFIED"),
        EvidenceRecord(id="PAN-CONFIG-ETHERNET-LINK-SPEED-VALUES", source_title="Configure an Aggregate Ethernet Interface Variable", source_url="https://docs.paloaltonetworks.com/ngfw/networking/configure-interfaces/configure-an-aggregate-interface-group/configure-an-aggregate-ethernet-interface", source_type="CONFIGURATION_REFERENCE", scope="PAN-OS interface link speed values in Mbps", summary="Interface link speed values include 40000 and 100000 Mbps.", verification_level="DOCUMENTATION_VERIFIED"),
        EvidenceRecord(id="PAN-CONFIG-ETHERNET-LINK-SPEED-TEST", source_title="PAN-OS Python SDK Ethernet serialization test", source_url="https://github.com/PaloAltoNetworks/pan-os-python/blob/92ed648d89b7541052a15e234eb34e99edba6d2d/tests/test_integration.py", source_type="VENDOR_SDK_TEST", scope="EthernetInterface XML serialization", summary="Official SDK test serializes link_speed=1000 as a direct Ethernet entry child <link-speed>1000</link-speed>.", verification_level="DOCUMENTATION_VERIFIED"),
        EvidenceRecord(id="PAN-HW-PA1400-OVERVIEW", source_title="PA-1400 Series Firewall Overview", source_url="https://docs.paloaltonetworks.com/hardware/pa-1400-hardware-reference/pa-1400-series-overview", source_type="HARDWARE_OVERVIEW", scope="PA-1410 and PA-1420 identity and first release", summary="PA-1400 comprises PA-1410 and PA-1420; first supported PAN-OS release is 11.0."),
        EvidenceRecord(id="PAN-HW-PA1400-FRONT", source_title="PA-1400 Series Front Panel", source_url="https://docs.paloaltonetworks.com/hardware/pa-1400-hardware-reference/pa-1400-series-overview/front-panel-1400-series", source_type="HARDWARE_REFERENCE", scope="PA-1410 and PA-1420 dataplane ports", summary="Documents model-specific RJ45 and SFP speeds, port 1 ZTP, and PoE on ports 9-12."),
        EvidenceRecord(id="PAN-HW-PA3200-OVERVIEW", source_title="PA-3200 Series Firewall Overview", source_url="https://docs.paloaltonetworks.com/hardware/pa-3200-hardware-reference/pa-3220-series-overview", source_type="HARDWARE_OVERVIEW", scope="PA-3220, PA-3250 and PA-3260 identity and first release", summary="PA-3200 first supports PAN-OS 8.1."),
        EvidenceRecord(id="PAN-HW-PA3200-FRONT", source_title="PA-3200 Series Front Panel", source_url="https://docs.paloaltonetworks.com/hardware/pa-3200-hardware-reference/pa-3220-series-overview/front-panel-3200-series", source_type="HARDWARE_REFERENCE", scope="PA-3200 model-specific dataplane ports", summary="Documents model-specific SFP groups and PA-3260 40G QSFP+ ports."),
        EvidenceRecord(id="PAN-HW-PA5200-OVERVIEW", source_title="PA-5200 Series Firewall Overview", source_url="https://docs.paloaltonetworks.com/hardware/pa-5200-hardware-reference/pa-5200-series-firewall-overview", source_type="HARDWARE_OVERVIEW", scope="PA-5200 identity and first releases", summary="PA-5220, PA-5250 and PA-5260 first support PAN-OS 8.0; PA-5280 first supports 8.1."),
        EvidenceRecord(id="PAN-HW-PA5200-FRONT", source_title="PA-5200 Front Panel", source_url="https://docs.paloaltonetworks.com/hardware/pa-5200-hardware-reference/pa-5200-series-firewall-overview/pa-5200-front-panel", source_type="HARDWARE_REFERENCE", scope="PA-5200 model-specific dataplane ports", summary="Documents 1-24 and model-specific 40G or 40G/100G QSFP capabilities."),
    ]
}
