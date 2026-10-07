from ..models.hardware import CandidateSupport, HardwareInterface, HardwareInterfaceGroup, HardwareKind, HardwareProfile, MappingSupport, PlatformDomain, PortAvailability, ProfileStatus, RequiredCondition, SoftwareFamily, SoftwareSupportRule, SoftwareSupportStatus, TargetRenderSupport
from ..evidence.registry import CHECKED_AT

MATRIX = "PAN-COMPAT-PANOS-BY-MODEL"


def _rules(supported: str, unsupported: str, minimums: dict[str, str] | None = None) -> list[SoftwareSupportRule]:
    states = {train: SoftwareSupportStatus.UNSUPPORTED for train in unsupported.split()}
    states.update({train: SoftwareSupportStatus.SUPPORTED for train in supported.split()})
    order = ("10.1", "10.2", "11.0", "11.1", "11.2", "12.1", "12.2")
    return [SoftwareSupportRule(train=train, status=states[train],
        minimum_version=(minimums or {}).get(train),
        evidence_ids=[MATRIX]) for train in order]


RULES_1400 = _rules("11.0 11.1 11.2 12.1 12.2", "10.1 10.2", {"12.1": "12.1.2"})
RULES_3200 = _rules("10.1 10.2 11.0 11.1", "11.2 12.1 12.2")
RULES_5200 = _rules("10.1 10.2 11.0 11.1 11.2", "12.1 12.2")
RULES_3400_5400 = _rules("10.2 11.0 11.1 11.2 12.1 12.2", "10.1", {"12.1": "12.1.2"})


def _group(profile: str, key: str, numbers: range, media: list[str], speeds: list[str], evidence: str,
           availability: PortAvailability = PortAvailability.NATIVE,
           condition: RequiredCondition = RequiredCondition.NONE, notes: str | None = None,
           ztp_ports: tuple[int, ...] = (), parents: dict[int, int] | None = None) -> tuple[HardwareInterfaceGroup, list[HardwareInterface]]:
    if availability == PortAvailability.BREAKOUT_CHILD and set(numbers) != set(parents or {}):
        raise ValueError("breakout topology must assign every child explicitly")
    names = [f"ethernet1/{number}" for number in numbers]
    blocked = condition != RequiredCondition.NONE
    group = HardwareInterfaceGroup(id=f"{profile}-{key}", label=key, interface_names=names,
        media_capabilities=media, speed_capabilities=speeds, availability=availability,
        mapping_support=MappingSupport.CONDITIONAL if availability == PortAvailability.NATIVE_CONDITIONAL else MappingSupport.UNSUPPORTED if blocked else MappingSupport.SUPPORTED,
        candidate_support=CandidateSupport.CONDITIONAL if condition == RequiredCondition.MANUAL_NATIVE_PORT_SPEED else CandidateSupport.BLOCKED if blocked else CandidateSupport.SUPPORTED,
        required_condition=condition, evidence_ids=[evidence], notes=notes)
    interfaces = [HardwareInterface(name=name, kind=HardwareKind.PHYSICAL_ETHERNET,
        speed_capabilities=speeds, media_capabilities=media, media=media[0], availability=availability,
        mapping_support=group.mapping_support, candidate_support=group.candidate_support,
        required_condition=condition, parent_interface=f"ethernet1/{parents[number]}" if parents and number in parents else None,
        evidence_ids=[evidence], ztp_capable=number in ztp_ports, notes=notes) for number, name in zip(numbers, names)]
    return group, interfaces


def _profile(profile_id: str, model: str, series: str, groups: list[tuple[HardwareInterfaceGroup, list[HardwareInterface]]], evidence_ids: list[str], first: str, rules: list[SoftwareSupportRule] = RULES_3400_5400, render: TargetRenderSupport = TargetRenderSupport.SUPPORTED) -> HardwareProfile:
    return HardwareProfile(id=profile_id, vendor="palo_alto", model=model, series=series,
        domain=PlatformDomain.FIREWALL, software_family=SoftwareFamily.PAN_OS,
        profile_status=ProfileStatus.VERIFIED, target_render_support=render,
        interfaces=[item for _, members in groups for item in members],
        interface_groups=[group for group, _ in groups], evidence_ids=evidence_ids,
        software_support_rules=rules,
        first_supported_release=first, verified_at=CHECKED_AT.isoformat())


PA3410 = _profile("paloalto-pa-3410", "PA-3410", "PA-3400", [
    _group("pa3410", "RJ45 1-12", range(1, 13), ["RJ45"], ["10M", "100M", "1G", "2.5G", "5G", "10G"], "PAN-HW-PA3400-FRONT", ztp_ports=(1,)),
    _group("pa3410", "SFP 13-22", range(13, 23), ["SFP", "SFP_PLUS"], ["1G", "10G"], "PAN-HW-PA3400-FRONT"),
    _group("pa3410", "SFP28 23-26", range(23, 27), ["SFP", "SFP_PLUS", "SFP28"], ["1G", "10G", "25G"], "PAN-HW-PA3400-FRONT", notes="RS-FEC is documented; ConfigHop does not configure FEC."),
], ["PAN-HW-PA3400-OVERVIEW", "PAN-HW-PA3400-FRONT", "PAN-COMPAT-PANOS-BY-MODEL"], "10.2")

PA5410 = _profile("paloalto-pa-5410", "PA-5410", "PA-5400", [
    _group("pa5410", "RJ45 1-8", range(1, 9), ["RJ45"], ["10M", "100M", "1G", "2.5G", "5G", "10G"], "PAN-HW-PA5400-FRONT", ztp_ports=(1,)),
    _group("pa5410", "SFP 9-20", range(9, 21), ["SFP", "SFP_PLUS"], ["1G", "10G"], "PAN-HW-PA5400-FRONT"),
    _group("pa5410", "SFP28 21-24", range(21, 25), ["SFP", "SFP_PLUS", "SFP28"], ["1G", "10G", "25G"], "PAN-HW-PA5400-FRONT", notes="Remote endpoint RS-FEC is documented; ConfigHop does not configure FEC."),
    _group("pa5410", "Breakout 25-40", range(25, 41), ["QSFP_PLUS", "QSFP28"], ["10G", "25G"], "PAN-COMPAT-BREAKOUT", PortAvailability.BREAKOUT_CHILD, RequiredCondition.BREAKOUT_MODE,
        parents={25: 41, 26: 41, 27: 41, 28: 41, 29: 42, 30: 42, 31: 42, 32: 42, 33: 43, 34: 43, 35: 43, 36: 43, 37: 44, 38: 44, 39: 44, 40: 44}),
    _group("pa5410", "Conditional QSFP 41-44", range(41, 45), ["QSFP_PLUS", "QSFP28"], ["40G", "100G"], "PAN-HW-PA5400-FRONT", PortAvailability.NATIVE_CONDITIONAL, RequiredCondition.MANUAL_NATIVE_PORT_SPEED, notes="Auto speed defaults to breakout; native mode requires an explicit 40G or 100G target speed."),
], ["PAN-HW-PA5400-OVERVIEW", "PAN-HW-PA5400-FRONT", "PAN-COMPAT-PANOS-BY-MODEL", "PAN-COMPAT-BREAKOUT", "PAN-CONFIG-ETHERNET-LINK-SPEED", "PAN-CONFIG-ETHERNET-LINK-SPEED-VALUES", "PAN-CONFIG-ETHERNET-LINK-SPEED-TEST"], "10.2.0")


def _new(model: str, series: str, first: str, groups: list[tuple[HardwareInterfaceGroup, list[HardwareInterface]]], rules: list[SoftwareSupportRule]) -> HardwareProfile:
    prefix = f"PAN-HW-{series.replace('-', '')}"
    return _profile(f"paloalto-{model.lower()}", model, series, groups,
        [f"{prefix}-OVERVIEW", f"{prefix}-FRONT", MATRIX], first, rules, TargetRenderSupport.ANALYSIS_ONLY)


PA1410 = _new("PA-1410", "PA-1400", "11.0", [
    _group("pa1410", "RJ45 1-8", range(1, 9), ["RJ45"], ["10M", "100M", "1G"], "PAN-HW-PA1400-FRONT", ztp_ports=(1,)),
    _group("pa1410", "Multi-Gig PoE 9-12", range(9, 13), ["RJ45"], ["10M", "100M", "1G", "2.5G", "5G"], "PAN-HW-PA1400-FRONT", notes="PoE is informational; ConfigHop does not render PoE."),
    _group("pa1410", "SFP 13-18", range(13, 19), ["SFP"], ["1G"], "PAN-HW-PA1400-FRONT"),
    _group("pa1410", "SFP+ 19-22", range(19, 23), ["SFP", "SFP_PLUS"], ["1G", "10G"], "PAN-HW-PA1400-FRONT"),
], RULES_1400)

PA1420 = _new("PA-1420", "PA-1400", "11.0", [
    _group("pa1420", "RJ45 1-4", range(1, 5), ["RJ45"], ["10M", "100M", "1G"], "PAN-HW-PA1400-FRONT", ztp_ports=(1,)),
    _group("pa1420", "Multi-Gig 5-8", range(5, 9), ["RJ45"], ["10M", "100M", "1G", "2.5G", "5G"], "PAN-HW-PA1400-FRONT"),
    _group("pa1420", "Multi-Gig PoE 9-12", range(9, 13), ["RJ45"], ["10M", "100M", "1G", "2.5G", "5G"], "PAN-HW-PA1400-FRONT", notes="PoE is informational; ConfigHop does not render PoE."),
    _group("pa1420", "SFP 13-14", range(13, 15), ["SFP"], ["1G"], "PAN-HW-PA1400-FRONT"),
    _group("pa1420", "SFP+ 15-22", range(15, 23), ["SFP", "SFP_PLUS"], ["1G", "10G"], "PAN-HW-PA1400-FRONT"),
], RULES_1400)

PA3220 = _new("PA-3220", "PA-3200", "8.1", [
    _group("pa3220", "RJ45 1-12", range(1, 13), ["RJ45"], ["10M", "100M", "1G"], "PAN-HW-PA3200-FRONT"),
    _group("pa3220", "SFP 13-16", range(13, 17), ["SFP"], ["1G"], "PAN-HW-PA3200-FRONT"),
    _group("pa3220", "SFP+ 17-20", range(17, 21), ["SFP", "SFP_PLUS"], ["1G", "10G"], "PAN-HW-PA3200-FRONT"),
], RULES_3200)

PA3250 = _new("PA-3250", "PA-3200", "8.1", [
    _group("pa3250", "RJ45 1-12", range(1, 13), ["RJ45"], ["10M", "100M", "1G"], "PAN-HW-PA3200-FRONT"),
    _group("pa3250", "SFP+ 13-20", range(13, 21), ["SFP", "SFP_PLUS"], ["1G", "10G"], "PAN-HW-PA3200-FRONT"),
], RULES_3200)

PA3260 = _new("PA-3260", "PA-3200", "8.1", [
    _group("pa3260", "RJ45 1-12", range(1, 13), ["RJ45"], ["10M", "100M", "1G"], "PAN-HW-PA3200-FRONT"),
    _group("pa3260", "SFP+ 13-20", range(13, 21), ["SFP", "SFP_PLUS"], ["1G", "10G"], "PAN-HW-PA3200-FRONT"),
    _group("pa3260", "QSFP+ 21-24", range(21, 25), ["QSFP_PLUS"], ["40G"], "PAN-HW-PA3200-FRONT"),
], RULES_3200)


def _pa5200(model: str, first: str, speeds: list[str], media: list[str]) -> HardwareProfile:
    key = model.lower().replace("-", "")
    return _new(model, "PA-5200", first, [
        _group(key, "RJ45 1-4", range(1, 5), ["RJ45"], ["100M", "1G", "10G"], "PAN-HW-PA5200-FRONT"),
        _group(key, "SFP+ 5-20", range(5, 21), ["SFP", "SFP_PLUS"], ["1G", "10G"], "PAN-HW-PA5200-FRONT"),
        _group(key, "QSFP 21-24", range(21, 25), media, speeds, "PAN-HW-PA5200-FRONT"),
    ], RULES_5200)


PA5220 = _pa5200("PA-5220", "8.0", ["40G"], ["QSFP_PLUS"])
PA5250 = _pa5200("PA-5250", "8.0", ["40G", "100G"], ["QSFP_PLUS", "QSFP28"])
PA5260 = _pa5200("PA-5260", "8.0", ["40G", "100G"], ["QSFP_PLUS", "QSFP28"])
PA5280 = _pa5200("PA-5280", "8.1", ["40G", "100G"], ["QSFP_PLUS", "QSFP28"])

SYNTHETIC = HardwareProfile(id="paloalto-synthetic-64", vendor="palo_alto", model="synthetic-panos-target-64",
    domain=PlatformDomain.FIREWALL, software_family=SoftwareFamily.PAN_OS,
    profile_status=ProfileStatus.SYNTHETIC,
    interfaces=[HardwareInterface(name=f"ethernet1/{number}", kind=HardwareKind.PHYSICAL_ETHERNET) for number in range(1, 65)],
    notes="Development profile only; no real hardware compatibility claim.")
