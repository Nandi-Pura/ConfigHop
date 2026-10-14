"""Read-only operational guidance derived from a current migration preview."""

from enum import StrEnum

from pydantic import BaseModel, Field

from .compatibility import CompatibilityAssessment
from .evidence.registry import EVIDENCE
from .models.hardware import HardwareProfile, RequiredCondition
from .models.inventory import PaloAltoInventory
from .models.mapping import InterfaceMapping, MigrationPreview, PreviewStatus, Severity
from .models.transformation import CandidateRenderResult, CandidateValidationReport, TransformationOperation


class RequirementCategory(StrEnum):
    PHYSICAL_OPTIC = "PHYSICAL_OPTIC"
    CABLING = "CABLING"
    REMOTE_PEER = "REMOTE_PEER"
    INTERFACE_VALIDATION = "INTERFACE_VALIDATION"
    DEPENDENCY_BOUNDARY = "DEPENDENCY_BOUNDARY"
    CONFIGURATION_VALIDATION = "CONFIGURATION_VALIDATION"
    ROLLBACK_PREPARATION = "ROLLBACK_PREPARATION"
    POST_CHANGE_VERIFICATION = "POST_CHANGE_VERIFICATION"


class RequirementPhase(StrEnum):
    PRE_CHANGE = "PRE_CHANGE"
    CUTOVER = "CUTOVER"
    POST_CHANGE = "POST_CHANGE"


class VerificationStatus(StrEnum):
    NOT_VERIFIED = "NOT_VERIFIED"
    ENGINEER_ACTION_REQUIRED = "ENGINEER_ACTION_REQUIRED"
    BLOCKED = "BLOCKED"
    INFORMATIONAL = "INFORMATIONAL"


class DeploymentRequirement(BaseModel):
    id: str
    category: RequirementCategory
    phase: RequirementPhase
    source_interface: str | None = None
    target_interface: str | None = None
    title: str
    description: str
    status: VerificationStatus
    target_port_type: str | None = None
    target_rate_capabilities: list[str] = Field(default_factory=list)
    selected_optic_rate: str | None = None
    source_configured_speed: str | None = None
    finding_codes: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    operator_action_required: bool = True


class DeploymentBlocker(BaseModel):
    code: str
    message: str
    source_interface: str | None = None
    target_interface: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class DeploymentPlan(BaseModel):
    source_profile_id: str
    target_profile_id: str
    target_render_support: str
    source_panos_train: str
    target_panos_train: str
    assessment_status: PreviewStatus
    candidate_validation: CandidateValidationReport | None = None
    physical_verification_status: VerificationStatus = VerificationStatus.NOT_VERIFIED
    configuration_operations: list[TransformationOperation] = Field(default_factory=list)
    deployment_requirements: list[DeploymentRequirement] = Field(default_factory=list)
    blockers: list[DeploymentBlocker] = Field(default_factory=list)
    review_findings: list[DeploymentBlocker] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    unavailable_evidence_ids: list[str] = Field(default_factory=list)


def build_deployment_plan(
    inventory: PaloAltoInventory, source_profile_id: str, source_panos_train: str,
    target_profile: HardwareProfile, target_panos_train: str, mappings: list[InterfaceMapping],
    preview: MigrationPreview, compatibility: CompatibilityAssessment,
    candidate: CandidateRenderResult | None = None,
) -> DeploymentPlan:
    """Project existing facts into operator tasks; never authorize or alter rendering."""
    ports = {item.name: item for item in target_profile.interfaces}
    source_ports = {item.name: item for item in inventory.physical_interfaces}
    requirements: list[DeploymentRequirement] = []
    blockers: list[DeploymentBlocker] = []
    review_findings: list[DeploymentBlocker] = []
    evidence: set[str] = set()

    def add(key: str, category: RequirementCategory, phase: RequirementPhase, title: str,
            description: str, *, source: str | None = None, target: str | None = None,
            status: VerificationStatus = VerificationStatus.ENGINEER_ACTION_REQUIRED,
            finding_codes: list[str] | None = None, evidence_ids: list[str] | None = None,
            optic_rate: str | None = None) -> None:
        port = ports.get(target or "")
        ids = list(dict.fromkeys(evidence_ids or []))
        evidence.update(ids)
        requirements.append(DeploymentRequirement(id=f"{key}:{source or 'project'}:{target or 'project'}",
            category=category, phase=phase, source_interface=source, target_interface=target,
            title=title, description=description, status=status,
            target_port_type="/".join(port.media_capabilities) if port else None,
            target_rate_capabilities=list(port.speed_capabilities) if port else [],
            selected_optic_rate=optic_rate,
            source_configured_speed=source_ports[source].link_speed if source in source_ports else None,
            finding_codes=finding_codes or [], evidence_ids=ids,
            operator_action_required=status != VerificationStatus.INFORMATIONAL))

    add("confirm-platform", RequirementCategory.CONFIGURATION_VALIDATION, RequirementPhase.PRE_CHANGE,
        "Confirm Migration Context", f"Confirm target {target_profile.model}, source PAN-OS {source_panos_train}, and target PAN-OS {target_panos_train}.",
        evidence_ids=target_profile.evidence_ids)
    add("review-mappings", RequirementCategory.CONFIGURATION_VALIDATION, RequirementPhase.PRE_CHANGE,
        "Review Interface Mappings", "Review every intended source-to-target interface mapping and outstanding backend finding.")
    add("prepare-rollback", RequirementCategory.ROLLBACK_PREPARATION, RequirementPhase.PRE_CHANGE,
        "Rollback Plan Prepared", "Confirm an approved rollback procedure and retained source configuration backup before deployment.")

    for mapping in sorted(mappings, key=lambda item: (item.source_interface, item.target_interface)):
        source, target = mapping.source_interface, mapping.target_interface
        port = ports.get(target)
        if not port:
            continue
        ids = port.evidence_ids
        rate = str(mapping.target_settings.optic_rate) if mapping.target_settings and mapping.target_settings.optic_rate else None
        if port.required_condition == RequiredCondition.OPTIC_CONTEXT_LINK_FIELDS_ABSENT:
            rate_label = rate or "unselected"
            add("verify-transceiver", RequirementCategory.PHYSICAL_OPTIC, RequirementPhase.PRE_CHANGE,
                "Verify Target Transceiver", f"Verify the installed or intended transceiver on {target} supports {rate_label} operation.",
                source=source, target=target, evidence_ids=ids, optic_rate=rate,
                finding_codes=["PHYSICAL_OPTIC_VERIFICATION_REQUIRED"] if rate else ["TARGET_OPTIC_RATE_REQUIRED"])
            add("verify-optic-rate", RequirementCategory.PHYSICAL_OPTIC, RequirementPhase.PRE_CHANGE,
                "Verify Selected Optic Rate", f"Confirm the selected {rate_label} optic rate against the installed target transceiver; actual runtime speed is unknown.",
                source=source, target=target, evidence_ids=ids, optic_rate=rate)
            add("verify-cabling", RequirementCategory.CABLING, RequirementPhase.PRE_CHANGE,
                "Verify Cabling Compatibility", f"Confirm cable, connector, and optical medium for {target} and its intended {rate_label} transceiver.",
                source=source, target=target, evidence_ids=ids, optic_rate=rate)
            add("verify-peer", RequirementCategory.REMOTE_PEER, RequirementPhase.PRE_CHANGE,
                "Verify Remote Peer", f"Confirm the connected peer supports the planned medium and {rate_label} optic rate for {target}; peer details are unknown.",
                source=source, target=target, optic_rate=rate)
            add("baseline-interface", RequirementCategory.INTERFACE_VALIDATION, RequirementPhase.PRE_CHANGE,
                "Record Source Interface Baseline", f"Record the observed state of {source} before cutover; ConfigHop has no live telemetry.",
                source=source, target=target, optic_rate=rate)
        elif port.required_condition == RequiredCondition.AUTO_ONLY_LINK_FIELDS_ABSENT:
            add("verify-rj45-peer", RequirementCategory.REMOTE_PEER, RequirementPhase.CUTOVER,
                "Verify RJ45 Link Negotiation", f"Confirm target {target} and the connected peer negotiate an operational link during cutover.",
                source=source, target=target, evidence_ids=ids)
        else:
            continue
        add("verify-interface", RequirementCategory.POST_CHANGE_VERIFICATION, RequirementPhase.POST_CHANGE,
            "Verify Interface State", f"Check the observed link state and interface errors on {target} after cutover; no runtime value is assumed.",
            source=source, target=target, evidence_ids=ids, optic_rate=rate)
        if source in source_ports and source_ports[source].mode == "layer3":
            add("verify-layer3", RequirementCategory.POST_CHANGE_VERIFICATION, RequirementPhase.POST_CHANGE,
                "Verify Layer3 Connectivity", f"Validate the intended Layer3 connectivity through {target} after cutover.",
                source=source, target=target)

    seen: set[tuple[str, str | None, str | None, str]] = set()
    for finding in [*compatibility.findings, *preview.findings,
                    *(candidate.plan.findings if candidate else [])]:
        if finding.severity not in {Severity.ERROR, Severity.WARNING}:
            continue
        source = getattr(finding, "source_interface", None)
        target = getattr(finding, "target_interface", None)
        key = (finding.code, source, target, finding.message)
        if key in seen:
            continue
        seen.add(key)
        ids = list(getattr(finding, "evidence_ids", []))
        evidence.update(ids)
        item = DeploymentBlocker(code=finding.code, message=finding.message,
            source_interface=source, target_interface=target,
            evidence_ids=ids)
        (blockers if finding.severity == Severity.ERROR else review_findings).append(item)
        if finding.severity == Severity.ERROR and (finding.code.startswith("SCOPED_TARGET_") or finding.code == "UNMODELED_INTERFACE_REFERENCE"):
            add(f"blocked-{finding.code.lower()}", RequirementCategory.DEPENDENCY_BOUNDARY,
                RequirementPhase.PRE_CHANGE, finding.code.replace("_", " ").title(),
                f"Resolve the unsupported migration scope: {finding.message}",
                source=source, target=target,
                status=VerificationStatus.BLOCKED, finding_codes=[finding.code], evidence_ids=ids)

    status = PreviewStatus.BLOCKED if ((candidate is not None and candidate.status == PreviewStatus.BLOCKED)
        or compatibility.status == PreviewStatus.BLOCKED or preview.status == PreviewStatus.BLOCKED) else (
        PreviewStatus.REVIEW_REQUIRED if compatibility.status == PreviewStatus.REVIEW_REQUIRED or preview.status == PreviewStatus.REVIEW_REQUIRED
        else PreviewStatus.READY)
    valid_candidate = candidate if candidate and candidate.validation.valid else None
    return DeploymentPlan(source_profile_id=source_profile_id, target_profile_id=target_profile.id,
        target_render_support=target_profile.target_render_support.value, source_panos_train=source_panos_train,
        target_panos_train=target_panos_train, assessment_status=status,
        candidate_validation=candidate.validation if candidate else None,
        configuration_operations=list(valid_candidate.plan.operations) if valid_candidate else [],
        deployment_requirements=requirements, blockers=blockers, review_findings=review_findings,
        evidence_ids=sorted(item for item in evidence if item in EVIDENCE),
        unavailable_evidence_ids=sorted(item for item in evidence if item not in EVIDENCE))
