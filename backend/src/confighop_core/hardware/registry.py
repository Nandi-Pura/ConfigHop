from ..evidence.registry import EVIDENCE
from ..models.hardware import HardwareProfile, PlatformDomain, ProfileStatus, SoftwareFamily, TargetRenderSupport
from .palo_alto import PA1410, PA1420, PA3220, PA3250, PA3260, PA3410, PA5220, PA5250, PA5260, PA5280, PA5410, SYNTHETIC


_CATALOG = (SYNTHETIC, PA1410, PA1420, PA3220, PA3250, PA3260, PA3410, PA5220, PA5250, PA5260, PA5280, PA5410)
PROFILES = {profile.id: profile for profile in _CATALOG}
if len(PROFILES) != len(_CATALOG):
    raise ValueError("duplicate hardware profile ID")
if len({(profile.domain, profile.vendor, profile.model) for profile in _CATALOG}) != len(_CATALOG):
    raise ValueError("duplicate hardware model identity")
for profile in _CATALOG:
    references = profile.evidence_ids + [item for group in profile.interface_groups for item in group.evidence_ids]
    references += [item for interface in profile.interfaces for item in interface.evidence_ids]
    references += [item for rule in profile.software_support_rules for item in rule.evidence_ids]
    if any(item not in EVIDENCE for item in references):
        raise ValueError(f"unknown evidence ID in {profile.id}")


def get_profile(profile_id: str) -> HardwareProfile | None:
    return PROFILES.get(profile_id)


def list_profiles(*, domain: PlatformDomain | None = None, vendor: str | None = None,
                  series: str | None = None, profile_status: ProfileStatus | None = None,
                  software_family: SoftwareFamily | None = None,
                  target_render_support: TargetRenderSupport | None = None) -> list[HardwareProfile]:
    return [profile for profile in _CATALOG if
        (domain is None or profile.domain == domain) and
        (vendor is None or profile.vendor == vendor) and
        (series is None or profile.series == series) and
        (profile_status is None or profile.profile_status == profile_status) and
        (software_family is None or profile.software_family == software_family) and
        (target_render_support is None or profile.target_render_support == target_render_support)]
