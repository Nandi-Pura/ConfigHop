import re
from collections import Counter
from enum import StrEnum

from pydantic import BaseModel, Field

from .hardware.registry import get_profile
from .palo_alto_constants import NATIVE_QSFP_EVIDENCE, NATIVE_QSFP_SPEED_XML
from .models.hardware import CandidateSupport, PortAvailability, TargetRenderSupport, SoftwareSupportStatus
from .models.inventory import PaloAltoInventory
from .models.mapping import InterfaceMapping, Severity


class AssessmentStatus(StrEnum):
    READY = "READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class Finding(BaseModel):
    code: str
    severity: Severity
    message: str
    source_interface: str | None = None
    target_interface: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class Version(BaseModel):
    raw: str
    major: int
    minor: int
    patch: int | None = None
    hotfix: int | None = None

    @property
    def train(self) -> str:
        return f"{self.major}.{self.minor}"


def parse_version(value: str | None) -> Version | None:
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+)(?:-h(\d+))?)?", value or "")
    if not match:
        return None
    return Version(raw=value, major=int(match[1]), minor=int(match[2]),
        patch=int(match[3]) if match[3] else None, hotfix=int(match[4]) if match[4] else None)


def version_support(profile_id: str, value: str | None) -> str:
    profile = get_profile(profile_id)
    version = parse_version(value)
    if profile is None:
        return "UNKNOWN_HARDWARE"
    if profile.profile_status != "verified":
        return "VERSION_NOT_VERIFIED"
    if version is None:
        return "UNKNOWN_SOFTWARE"
    rule = next((item for item in profile.software_support_rules if item.train == version.train), None)
    if rule is None:
        return "VERSION_NOT_VERIFIED"
    if rule.status == SoftwareSupportStatus.UNSUPPORTED:
        return "UNSUPPORTED"
    if rule.minimum_version:
        minimum = parse_version(rule.minimum_version)
        if minimum is None:
            return "VERSION_NOT_VERIFIED"
        if version.patch is None:
            return "VERSION_NOT_VERIFIED"
        if (version.major, version.minor, version.patch, version.hotfix or 0) < (minimum.major, minimum.minor, minimum.patch or 0, minimum.hotfix or 0):
            return "VERSION_BELOW_SUPPORTED_FLOOR"
    return "SUPPORTED"


class PlatformAssessment(BaseModel):
    source_profile_id: str | None
    target_profile_id: str | None
    selected_source_train: str | None
    selected_target_train: str | None
    effective_source_version: str | None
    source_version_status: str
    target_version_status: str
    status: AssessmentStatus
    findings: list[Finding]
    evidence_ids: list[str]


class InterfaceAssessment(BaseModel):
    source_interface: str
    target_interface: str
    explicit_mapping: bool
    configured_source_speed: str | None
    source_speed_capabilities: list[str]
    target_speed_capabilities: list[str]
    source_media_capabilities: list[str]
    target_media_capabilities: list[str]
    target_availability: PortAvailability | None
    candidate_support: CandidateSupport | None
    status: AssessmentStatus
    findings: list[Finding]
    evidence_ids: list[str]


class HardwareAssessment(BaseModel):
    source_profile_id: str | None
    target_profile_id: str | None
    effective_assignments: list[InterfaceAssessment]
    status: AssessmentStatus
    findings: list[Finding]
    evidence_ids: list[str]


class CompatibilityAssessment(BaseModel):
    platform: PlatformAssessment
    hardware: HardwareAssessment
    status: AssessmentStatus
    findings: list[Finding]
    evidence_ids: list[str]


def _status(findings: list[Finding]) -> AssessmentStatus:
    if any(item.severity == Severity.ERROR for item in findings):
        return AssessmentStatus.BLOCKED
    if any(item.severity == Severity.WARNING for item in findings):
        return AssessmentStatus.REVIEW_REQUIRED
    return AssessmentStatus.READY


def _finding(code: str, message: str, *, severity: Severity = Severity.ERROR,
             source: str | None = None, target: str | None = None,
             evidence: list[str] | None = None) -> Finding:
    return Finding(code=code, severity=severity, message=message, source_interface=source,
        target_interface=target, evidence_ids=evidence or [])


def _configured_speed(value: str | None) -> str | None:
    if not value or value.lower() == "auto":
        return None
    aliases = {"10": "10M", "100": "100M", "1000": "1G", "2500": "2.5G", "5000": "5G",
        "10000": "10G", "25000": "25G", "40000": "40G", "100000": "100G"}
    normalized = value.upper().replace("BPS", "").replace("GB", "G").replace("MB", "M")
    return aliases.get(normalized, normalized if normalized in aliases.values() else "UNKNOWN")


def assess(inventory: PaloAltoInventory, source_profile_id: str | None, source_train: str | None,
           target_profile_id: str | None, target_train: str | None,
           mappings: list[InterfaceMapping]) -> CompatibilityAssessment:
    source = get_profile(source_profile_id or "")
    target = get_profile(target_profile_id or "")
    effective = parse_version(inventory.platform.detail_version) or parse_version(inventory.platform.config_version)
    version = effective.raw if effective else None
    source_support = version_support(source_profile_id or "", version)
    target_support = version_support(target_profile_id or "", version)
    platform_findings: list[Finding] = []
    matrix = ["PAN-COMPAT-PANOS-BY-MODEL"]
    if not source:
        platform_findings.append(_finding("SOURCE_PROFILE_REQUIRED", "Select a source hardware profile."))
    if not target:
        platform_findings.append(_finding("TARGET_PROFILE_REQUIRED", "Select a target hardware profile."))
    elif target.target_render_support == TargetRenderSupport.ANALYSIS_ONLY:
        platform_findings.append(_finding("TARGET_PROFILE_RENDERING_NOT_VERIFIED", "Target hardware is verified for analysis, but candidate rendering is not verified.", evidence=target.evidence_ids))
    if not source_train or not target_train:
        platform_findings.append(_finding("VERSION_NOT_VERIFIED", "Select source and target PAN-OS trains.", evidence=matrix))
    if effective is None:
        platform_findings.append(_finding("VERSION_NOT_VERIFIED", "The exact source PAN-OS version could not be verified.", evidence=matrix))
    elif source_train and source_train != effective.train:
        platform_findings.append(_finding("SOURCE_OS_CONTEXT_MISMATCH", "Selected source train differs from the parsed source version.", evidence=matrix))
    if effective and target_train and target_train != effective.train:
        platform_findings.append(_finding("TARGET_OS_CHANGE_UNSUPPORTED", "Changing PAN-OS train is outside this migration flow.", evidence=matrix))
    for role, result in [("SOURCE", source_support), ("TARGET", target_support)]:
        if result != "SUPPORTED" and (source if role == "SOURCE" else target):
            code = result if result in {"VERSION_NOT_VERIFIED", "VERSION_BELOW_SUPPORTED_FLOOR"} else f"{role}_OS_UNSUPPORTED"
            platform_findings.append(_finding(code, f"{role.lower().capitalize()} PAN-OS support is {result.lower().replace('_', ' ')}.", evidence=matrix))
    platform = PlatformAssessment(source_profile_id=source_profile_id, target_profile_id=target_profile_id,
        selected_source_train=source_train, selected_target_train=target_train,
        effective_source_version=version, source_version_status=source_support,
        target_version_status=target_support, status=_status(platform_findings),
        findings=platform_findings, evidence_ids=matrix)

    explicit = {item.source_interface: item.target_interface for item in mappings}
    decisions = {item.source_interface: item.target_settings for item in mappings}
    source_ports = {item.name: item for item in source.interfaces} if source else {}
    target_ports = {item.name: item for item in target.interfaces} if target else {}
    hardware_findings: list[Finding] = []
    source_names = {item.name for item in inventory.physical_interfaces}
    source_counts = Counter(item.source_interface for item in mappings)
    for mapping in mappings:
        if mapping.source_interface not in source_names:
            hardware_findings.append(_finding("SOURCE_INTERFACE_NOT_FOUND", "Mapped source physical interface is absent from the inventory.", source=mapping.source_interface, target=mapping.target_interface))
        if source_counts[mapping.source_interface] > 1:
            hardware_findings.append(_finding("DUPLICATE_SOURCE_MAPPING", "Source interface has multiple submitted mappings.", source=mapping.source_interface, target=mapping.target_interface))
    target_counts = Counter(explicit.get(item.name, item.name) for item in inventory.physical_interfaces)
    assignments: list[InterfaceAssessment] = []
    for item in inventory.physical_interfaces:
        target_name = explicit.get(item.name, item.name)
        source_port = source_ports.get(item.name)
        target_port = target_ports.get(target_name)
        findings: list[Finding] = []
        if source and source.profile_status == "verified" and source_port is None:
            findings.append(_finding("SOURCE_HARDWARE_PROFILE_MISMATCH", "Source interface is absent from the selected hardware profile.", source=item.name, evidence=source.evidence_ids))
        if target and target_port is None:
            findings.append(_finding("TARGET_INTERFACE_NOT_FOUND", "Effective target interface is absent from the selected hardware profile.", source=item.name, target=target_name, evidence=target.evidence_ids))
        if target_counts[target_name] > 1:
            findings.append(_finding("TARGET_HARDWARE_PROFILE_MISMATCH", "Multiple source interfaces resolve to this target identity.", source=item.name, target=target_name))
        if target_port and target_port.candidate_support == CandidateSupport.BLOCKED:
            if target_port.availability == PortAvailability.BREAKOUT_CHILD:
                findings.append(_finding("BREAKOUT_MODE_REQUIRED", "This breakout child requires target QSFP breakout configuration that ConfigHop does not render.", source=item.name, target=target_name, evidence=target_port.evidence_ids))
            else:
                findings.append(_finding("TARGET_NATIVE_PORT_MODE_REQUIRED", "This native QSFP target requires explicit speed configuration that ConfigHop does not render.", source=item.name, target=target_name, evidence=target_port.evidence_ids))
        settings = decisions.get(item.name)
        chosen = settings.link_speed if settings else None
        native = bool(target_port and target_port.candidate_support == CandidateSupport.CONDITIONAL)
        if native and chosen is None:
            findings.append(_finding("TARGET_NATIVE_PORT_MODE_REQUIRED", "Select 40G or 100G for the native QSFP target.", source=item.name, target=target_name, evidence=NATIVE_QSFP_EVIDENCE))
        elif native and chosen not in NATIVE_QSFP_SPEED_XML:
            findings.append(_finding("TARGET_LINK_SPEED_UNSUPPORTED", "The selected speed cannot configure this native QSFP target.", source=item.name, target=target_name, evidence=NATIVE_QSFP_EVIDENCE))
        elif settings is not None and not native:
            findings.append(_finding("TARGET_INTERFACE_SETTING_NOT_APPLICABLE", "Native QSFP target speed does not apply to this interface.", source=item.name, target=target_name))
        speed = _configured_speed(item.link_speed)
        if native and chosen in NATIVE_QSFP_SPEED_XML:
            findings.append(_finding("PHYSICAL_LINK_CHANGE_REQUIRED", "Target speed was selected explicitly; verify optics, cabling and peer compatibility before deployment.", severity=Severity.WARNING, source=item.name, target=target_name, evidence=NATIVE_QSFP_EVIDENCE))
            if speed and speed != chosen:
                findings.append(_finding("TARGET_LINK_SPEED_CHANGED", "Configured source link speed differs from the selected target speed.", severity=Severity.WARNING, source=item.name, target=target_name, evidence=NATIVE_QSFP_EVIDENCE))
        if source_port and target_port and target_port.candidate_support == CandidateSupport.SUPPORTED and source_port.speed_capabilities and target_port.speed_capabilities:
            if speed == "UNKNOWN":
                findings.append(_finding("CONFIGURED_SPEED_NOT_VERIFIED", "Configured source speed could not be normalized.", severity=Severity.WARNING, source=item.name, target=target_name))
            elif speed and speed not in target_port.speed_capabilities:
                findings.append(_finding("TARGET_SPEED_UNSUPPORTED", "Configured source speed is unsupported by the target port.", source=item.name, target=target_name, evidence=target_port.evidence_ids))
            elif not set(source_port.speed_capabilities) & set(target_port.speed_capabilities):
                findings.append(_finding("NO_COMMON_SPEED", "Source and target port groups have no common documented speed.", source=item.name, target=target_name))
            elif not speed and not set(source_port.speed_capabilities) <= set(target_port.speed_capabilities):
                findings.append(_finding("SPEED_CAPABILITY_NARROWED", "Target port supports fewer speeds; verify the actual link speed.", severity=Severity.WARNING, source=item.name, target=target_name))
            if not set(source_port.media_capabilities) & set(target_port.media_capabilities):
                findings.append(_finding("MEDIA_CHANGE_REVIEW", "Physical media changes; verify cabling and transceiver plan.", severity=Severity.WARNING, source=item.name, target=target_name))
        hardware_findings.extend(findings)
        assignments.append(InterfaceAssessment(source_interface=item.name, target_interface=target_name,
            explicit_mapping=item.name in explicit, configured_source_speed=item.link_speed,
            source_speed_capabilities=source_port.speed_capabilities if source_port else [],
            target_speed_capabilities=target_port.speed_capabilities if target_port else [],
            source_media_capabilities=source_port.media_capabilities if source_port else [],
            target_media_capabilities=target_port.media_capabilities if target_port else [],
            target_availability=target_port.availability if target_port else None,
            candidate_support=target_port.candidate_support if target_port else None,
            status=_status(findings), findings=findings,
            evidence_ids=list(dict.fromkeys((source_port.evidence_ids if source_port else []) + (target_port.evidence_ids if target_port else [])))))
    hardware = HardwareAssessment(source_profile_id=source_profile_id, target_profile_id=target_profile_id,
        effective_assignments=assignments, status=_status(hardware_findings), findings=hardware_findings,
        evidence_ids=list(dict.fromkeys((source.evidence_ids if source else []) + (target.evidence_ids if target else []))))
    findings = platform_findings + hardware_findings
    return CompatibilityAssessment(platform=platform, hardware=hardware, status=_status(findings),
        findings=findings, evidence_ids=list(dict.fromkeys(platform.evidence_ids + hardware.evidence_ids)))
