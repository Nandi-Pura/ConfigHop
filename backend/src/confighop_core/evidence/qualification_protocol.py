"""Offline protocol planning and structural evidence review; no renderer authorization."""

from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..compatibility import parse_version, version_support
from ..hardware.registry import get_profile
from .registry import EVIDENCE


DOCS = Path(__file__).resolve().parents[4] / "docs" / "core"


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class XMLField(StrEnum):
    SPEED = "link-speed"
    DUPLEX = "link-duplex"


class CaseType(StrEnum):
    DEFAULT_ABSENT = "DEFAULT_ABSENT"
    EXPLICIT_AUTO = "EXPLICIT_AUTO"
    EXPLICIT_MANUAL = "EXPLICIT_MANUAL"
    ACCEPTANCE_REJECTION = "ACCEPTANCE_REJECTION"
    EXPORT_NORMALIZATION = "EXPORT_NORMALIZATION"
    REIMPORT_STABILITY = "REIMPORT_STABILITY"


class EvidenceClass(StrEnum):
    SYNTHETIC = "SYNTHETIC"
    CONTROLLED_DEVICE = "CONTROLLED_DEVICE"
    OFFICIAL_DOCUMENTATION = "OFFICIAL_DOCUMENTATION"
    VENDOR_ENGINEERING = "VENDOR_ENGINEERING"
    COMMUNITY = "COMMUNITY"


class ExecutionStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    OBSERVATION_RECORDED = "OBSERVATION_RECORDED"
    REFERENCE_RECORDED = "REFERENCE_RECORDED"


class Readiness(StrEnum):
    INCOMPLETE = "INCOMPLETE"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    REJECTED = "REJECTED"


class Outcome(StrEnum):
    LOAD_ACCEPTED = "LOAD_ACCEPTED"
    LOAD_REJECTED = "LOAD_REJECTED"
    COMMIT_ACCEPTED = "COMMIT_ACCEPTED"
    COMMIT_REJECTED = "COMMIT_REJECTED"
    EXPORTED_UNCHANGED = "EXPORTED_UNCHANGED"
    EXPORTED_NORMALIZED = "EXPORTED_NORMALIZED"
    NODE_OMITTED = "NODE_OMITTED"
    REIMPORT_ACCEPTED = "REIMPORT_ACCEPTED"
    REIMPORT_REJECTED = "REIMPORT_REJECTED"
    NOT_OBSERVED = "NOT_OBSERVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class GapInventory(ProtocolModel):
    gap_id: str
    priority: str
    series: str
    models: list[str]
    port_groups: list[str]
    required_facts: str
    required_evidence: str
    resolution_requirements: list[str]
    gap_status: str
    blocking: bool
    evidence_ids: list[str]
    unresolved_dimensions: list[str]
    runtime_support: dict[str, str]
    protocol_scope: Literal["TARGETED", "PARKED"]


class ProtocolScope(ProtocolModel):
    gap_id: str
    hardware_model: str
    port_group_id: str
    interface_names: list[str]
    media_types: list[str]
    panos_trains: list[str]
    optic_rates: list[str | None]


class CaseDefinition(ProtocolModel):
    case_type: CaseType
    xml_field: XMLField
    controlled_action: str
    expected_device_outcome: Literal["UNDETERMINED"] = "UNDETERMINED"
    execution_status: Literal["NOT_RUN"] = "NOT_RUN"


class ProtocolManifest(ProtocolModel):
    schema_version: Literal[1] = 1
    protocol_scope: Literal["PA3200_PA5200_OFFLINE_PLANNING"] = "PA3200_PA5200_OFFLINE_PLANNING"
    canonical_gap_catalog: str = "docs/core/palo_alto_evidence_gaps.json"
    required_dimensions: list[str]
    required_evidence_fields: list[str]
    scopes: list[ProtocolScope]
    case_definitions: list[CaseDefinition]
    execution_status: Literal["NOT_RUN"] = "NOT_RUN"
    observed_device_records: Literal[0] = 0


class ProtocolCase(CaseDefinition):
    id: str
    gap_id: str
    hardware_model: str
    panos_train: str
    port_group_id: str
    optic_rate: str | None


class QualificationScope(ProtocolModel):
    gap_id: str
    hardware_model: str
    exact_panos_version: str
    panos_train: str
    port_group_id: str
    interface_name: str
    optic_rate: str | None = None


class ArtifactReference(ProtocolModel):
    reference: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    redaction_status: Literal["SANITIZED", "NOT_REVIEWED"] = "NOT_REVIEWED"

    @field_validator("reference")
    @classmethod
    def safe_reference(cls, value: str) -> str:
        if not re.fullmatch(r"artifact://[A-Za-z0-9][A-Za-z0-9._/-]*", value) or ".." in value:
            raise ValueError("use a safe artifact identifier, without credentials or filesystem paths")
        return value


class ObservationRecord(ProtocolModel):
    evidence_record_id: str
    protocol_case_id: str
    gap_id: str | None = None
    hardware_model: str | None = None
    exact_panos_version: str | None = None
    panos_train: str | None = None
    port_group_id: str | None = None
    interface_name: str | None = None
    optic_rate: str | None = None
    media_type: str | None = None
    transceiver_context: str | None = None
    xml_field: XMLField | None = None
    initial_node_presence: bool | None = None
    initial_node_value: str | None = None
    attempted_node_presence: bool | None = None
    attempted_node_value: str | None = None
    load_result: Outcome = Outcome.NOT_OBSERVED
    commit_result: Outcome = Outcome.NOT_OBSERVED
    export_result: Outcome = Outcome.NOT_OBSERVED
    exported_node_presence: bool | None = None
    exported_node_value: str | None = None
    normalization_observed: bool | None = None
    reimport_result: Outcome = Outcome.NOT_OBSERVED
    reimported_node_presence: bool | None = None
    reimported_node_value: str | None = None
    reimport_stable: bool | None = None
    not_applicable_reason: str | None = None
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    observation_timestamp: datetime | None = None
    tester_identifier: str | None = None
    reviewer_identifier: str | None = None
    provenance: str | None = None
    evidence_class: EvidenceClass = EvidenceClass.SYNTHETIC
    execution_status: ExecutionStatus = ExecutionStatus.NOT_RUN


class QualificationReport(ProtocolModel):
    scope: QualificationScope
    status: Readiness
    required_case_count: int
    covered_case_ids: list[str]
    missing_case_ids: list[str]
    missing_evidence: list[str]
    scope_errors: list[str]
    conflicts: list[str]
    synthetic: bool
    device_validated: Literal[False] = False
    production_state_changed: Literal[False] = False


def load_gap_catalog(path: Path | None = None) -> dict:
    return json.loads((path or DOCS / "palo_alto_evidence_gaps.json").read_text(encoding="utf-8"))


def evidence_inventory(catalog: dict) -> list[GapInventory]:
    inventory = []
    for gap in sorted(catalog["gaps"], key=lambda item: item["id"]):
        profiles = [get_profile(f"paloalto-{model.lower()}") for model in gap["affected_models"]]
        if any(profile is None for profile in profiles) or any(ref not in EVIDENCE for ref in gap["existing_evidence_ids"]):
            raise ValueError(f"Unknown canonical hardware or evidence for {gap['id']}")
        inventory.append(GapInventory(gap_id=gap["id"], priority=gap["priority"], series=gap["series"],
            models=gap["affected_models"], port_groups=gap["affected_port_groups"], required_facts=gap["missing_fact"],
            required_evidence=gap["required_evidence"], resolution_requirements=gap["resolution_requirements"],
            gap_status=gap["status"], blocking=gap["blocking"], evidence_ids=gap["existing_evidence_ids"],
            unresolved_dimensions=gap["gap_types"], runtime_support={p.model: p.target_render_support.value for p in profiles},
            protocol_scope="TARGETED" if gap["series"] in {"PA-3200", "PA-5200"} else "PARKED"))
    if len({item.gap_id for item in inventory}) != len(inventory):
        raise ValueError("Duplicate gap identities")
    return inventory


def build_protocol_manifest(catalog: dict) -> ProtocolManifest:
    scopes = []
    for gap in evidence_inventory(catalog):
        if gap.protocol_scope != "TARGETED":
            continue
        for model in gap.models:
            profile = get_profile(f"paloalto-{model.lower()}")
            for group in profile.interface_groups:
                if group.id in gap.port_groups:
                    scopes.append(ProtocolScope(gap_id=gap.gap_id, hardware_model=model, port_group_id=group.id,
                        interface_names=group.interface_names, media_types=group.media_capabilities,
                        panos_trains=[rule.train for rule in profile.software_support_rules if rule.status == "SUPPORTED"],
                        optic_rates=[None] if group.media_capabilities == ["RJ45"] else group.speed_capabilities))
    actions = {
        CaseType.DEFAULT_ABSENT: "Capture an untouched default, then omit this node in a controlled synthetic candidate.",
        CaseType.EXPLICIT_AUTO: "Supply only this field as explicit auto; record acceptance and resulting export.",
        CaseType.EXPLICIT_MANUAL: "Supply one recorded manual candidate value (numeric for speed); acceptance is undetermined.",
        CaseType.ACCEPTANCE_REJECTION: "Test one lab-approved unsupported-value hypothesis; record rejection, ignoring, retention, or normalization.",
        CaseType.EXPORT_NORMALIZATION: "Compare attempted and exported node presence/value after the controlled action.",
        CaseType.REIMPORT_STABILITY: "Re-import the sanitized exported representation and record load/commit and re-export stability.",
    }
    return ProtocolManifest(required_dimensions=list(QualificationScope.model_fields) + ["media_type", "transceiver_context", "xml_field", "case_type"],
        required_evidence_fields=list(ObservationRecord.model_fields), scopes=scopes,
        case_definitions=[CaseDefinition(case_type=kind, xml_field=field, controlled_action=actions[kind])
            for field in XMLField for kind in CaseType])


def validate_protocol_manifest(manifest: ProtocolManifest, catalog: dict) -> None:
    if manifest.model_dump() != build_protocol_manifest(catalog).model_dump():
        raise ValueError("Protocol snapshot diverges from canonical gaps, hardware, software, or case definitions")


def protocol_cases(manifest: ProtocolManifest, catalog: dict) -> list[ProtocolCase]:
    validate_protocol_manifest(manifest, catalog)
    cases = []
    for scope in manifest.scopes:
        for train in scope.panos_trains:
            for rate in scope.optic_rates:
                for definition in manifest.case_definitions:
                    identity = [scope.gap_id, scope.hardware_model, train, scope.port_group_id,
                        definition.case_type, definition.xml_field, rate]
                    digest = sha256(json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
                    cases.append(ProtocolCase(**definition.model_dump(), id=f"PAN-7D-{digest}", gap_id=scope.gap_id,
                        hardware_model=scope.hardware_model, panos_train=train, port_group_id=scope.port_group_id, optic_rate=rate))
    return sorted(cases, key=lambda item: item.id)


def protocol_review_report(manifest: ProtocolManifest, catalog: dict) -> dict:
    cases = protocol_cases(manifest, catalog)
    inventory = evidence_inventory(catalog)
    return {"gap_count": len(inventory), "priorities": {p: sum(g.priority == p for g in inventory) for p in ("P0", "P1")},
        "inventory": [item.model_dump(mode="json") for item in inventory],
        "cases_defined": len(cases), "cases_not_run": len(cases), "evidence_supplied": 0,
        "status": Readiness.INCOMPLETE.value, "gap_coverage": [{"gap_id": gap.gap_id,
            "cases_defined": sum(c.gap_id == gap.gap_id for c in cases), "status": Readiness.INCOMPLETE.value,
            "missing_evidence": "No exact-model device observations or equivalent authoritative statements supplied"}
            for gap in inventory if gap.protocol_scope == "TARGETED"]}


def assess_serialization_evidence(scope: QualificationScope, records: list[ObservationRecord],
                                  manifest: ProtocolManifest, catalog: dict) -> QualificationReport:
    cases = protocol_cases(manifest, catalog)
    planned = next((item for item in manifest.scopes if (item.gap_id, item.hardware_model, item.port_group_id)
        == (scope.gap_id, scope.hardware_model, scope.port_group_id)), None)
    errors, missing, conflicts = [], [], []
    version = parse_version(scope.exact_panos_version)
    if planned is None:
        errors.append("Unknown, parked, or mismatched gap/model/port group")
    else:
        if scope.interface_name not in planned.interface_names:
            errors.append("Interface does not belong to the exact model port group")
        if scope.panos_train not in planned.panos_trains:
            errors.append("Unsupported model/PAN-OS train")
        if scope.optic_rate not in planned.optic_rates:
            errors.append("Unsupported or missing optic rate context")
    if version is None or version.patch is None:
        errors.append("Qualification scope requires an exact PAN-OS patch/build version")
    elif version.train != scope.panos_train or version_support(f"paloalto-{scope.hardware_model.lower()}", scope.exact_panos_version) != "SUPPORTED":
        errors.append("Exact version does not match the supported train")
    expected = {c.id: c for c in cases if (c.gap_id, c.hardware_model, c.port_group_id, c.panos_train, c.optic_rate)
        == (scope.gap_id, scope.hardware_model, scope.port_group_id, scope.panos_train, scope.optic_rate)}
    covered: set[str] = set()
    signatures: dict[str, set[str]] = {}
    for record in records:
        prefix = record.evidence_record_id
        required = expected.get(record.protocol_case_id)
        if required is None:
            errors.append(f"{prefix}: case outside the requested exact scope")
            continue
        record_missing, record_errors = [], []
        for field, value in scope.model_dump().items():
            observed = getattr(record, field)
            if observed is None and value is not None:
                record_missing.append(field)
            elif observed != value:
                record_errors.append(f"scope mismatch: {field}")
        if record.xml_field is None:
            record_missing.append("xml_field")
        elif record.xml_field != required.xml_field:
            record_errors.append("XML field does not match protocol case")
        if record.evidence_class == EvidenceClass.COMMUNITY:
            record_errors.append("Community material cannot independently establish review readiness")
        if record.execution_status == ExecutionStatus.NOT_RUN:
            record_missing.append("execution_status")
        if record.evidence_class == EvidenceClass.CONTROLLED_DEVICE and record.execution_status != ExecutionStatus.OBSERVATION_RECORDED:
            record_missing.append("controlled device observation")
        for field in ("media_type", "provenance", "tester_identifier", "reviewer_identifier", "observation_timestamp"):
            if not getattr(record, field):
                record_missing.append(field)
        if planned and record.media_type and record.media_type not in planned.media_types:
            record_errors.append("Media does not match port group")
        if scope.optic_rate and not record.transceiver_context:
            record_missing.append("transceiver_context")
        if record.observation_timestamp and record.observation_timestamp.tzinfo is None:
            record_missing.append("observation_timestamp timezone")
        if record.tester_identifier and record.tester_identifier == record.reviewer_identifier:
            record_errors.append("Independent reviewer must differ from observation author")
        if not record.artifacts:
            record_missing.append("artifact provenance")
        if any(item.redaction_status != "SANITIZED" for item in record.artifacts):
            record_missing.append("artifact sanitization")
        for field, values in {
            "load_result": {Outcome.LOAD_ACCEPTED, Outcome.LOAD_REJECTED},
            "commit_result": {Outcome.COMMIT_ACCEPTED, Outcome.COMMIT_REJECTED},
            "export_result": {Outcome.EXPORTED_UNCHANGED, Outcome.EXPORTED_NORMALIZED, Outcome.NODE_OMITTED},
            "reimport_result": {Outcome.REIMPORT_ACCEPTED, Outcome.REIMPORT_REJECTED},
        }.items():
            value = getattr(record, field)
            if value == Outcome.NOT_OBSERVED:
                record_missing.append(field)
            elif value == Outcome.NOT_APPLICABLE:
                if field == "load_result" or not record.not_applicable_reason or not (
                    record.load_result == Outcome.LOAD_REJECTED or record.commit_result == Outcome.COMMIT_REJECTED):
                    record_errors.append(f"Unjustified NOT_APPLICABLE: {field}")
            elif value not in values:
                record_errors.append(f"Invalid outcome stage: {field}")
        if required.case_type in {CaseType.EXPORT_NORMALIZATION, CaseType.REIMPORT_STABILITY} and record.export_result in {
            Outcome.NOT_APPLICABLE, Outcome.NOT_OBSERVED
        }:
            record_missing.append(f"{required.case_type.value} export observation")
        if required.case_type == CaseType.REIMPORT_STABILITY and record.reimport_result in {
            Outcome.NOT_APPLICABLE, Outcome.NOT_OBSERVED
        }:
            record_missing.append("REIMPORT_STABILITY re-import observation")
        for presence, value in (("initial_node_presence", "initial_node_value"),
                                ("attempted_node_presence", "attempted_node_value")):
            if getattr(record, presence) is None:
                record_missing.append(presence)
            elif getattr(record, presence) and getattr(record, value) is None:
                record_missing.append(value)
            elif not getattr(record, presence) and getattr(record, value) is not None:
                record_errors.append(f"Absent node has value: {value}")
        if record.export_result != Outcome.NOT_APPLICABLE:
            if record.exported_node_presence is None:
                record_missing.append("exported_node_presence")
            elif record.exported_node_presence and record.exported_node_value is None:
                record_missing.append("exported_node_value")
            elif not record.exported_node_presence and record.exported_node_value is not None:
                record_errors.append("Absent exported node has value")
            if record.normalization_observed is None:
                record_missing.append("normalization_observed")
        if record.export_result == Outcome.NODE_OMITTED and record.exported_node_presence is True:
            record_errors.append("NODE_OMITTED contradicts exported node presence")
        if record.export_result == Outcome.EXPORTED_NORMALIZED and record.normalization_observed is False:
            record_errors.append("Normalized export requires explicit normalization observation")
        if record.load_result == Outcome.LOAD_REJECTED and record.commit_result not in {Outcome.NOT_APPLICABLE, Outcome.NOT_OBSERVED}:
            record_errors.append("A rejected load cannot have a commit outcome")
        if record.export_result == Outcome.EXPORTED_UNCHANGED and (
            record.normalization_observed is True or (record.exported_node_presence is not None
                and (record.exported_node_presence, record.exported_node_value) !=
                    (record.attempted_node_presence, record.attempted_node_value))):
            record_errors.append("Unchanged export contradicts attempted representation or normalization")
        if record.reimport_result == Outcome.REIMPORT_ACCEPTED:
            if record.reimported_node_presence is None:
                record_missing.append("reimported_node_presence")
            elif record.reimported_node_presence and record.reimported_node_value is None:
                record_missing.append("reimported_node_value")
            elif not record.reimported_node_presence and record.reimported_node_value is not None:
                record_errors.append("Absent re-imported node has value")
            if record.reimport_stable is None:
                record_missing.append("reimport_stable")
            elif record.reimported_node_presence is not None and record.exported_node_presence is not None:
                unchanged = (record.reimported_node_presence, record.reimported_node_value) == (
                    record.exported_node_presence, record.exported_node_value)
                if record.reimport_stable != unchanged:
                    record_errors.append("Re-import stability contradicts observed representations")
        if required.case_type == CaseType.DEFAULT_ABSENT and record.attempted_node_presence is True:
            record_errors.append("Default/absent case must omit the attempted node")
        if required.case_type == CaseType.EXPLICIT_AUTO and (record.attempted_node_presence is False or (
            record.attempted_node_value is not None and record.attempted_node_value != "auto")):
            record_errors.append("Explicit-auto case must supply auto")
        if required.case_type in {CaseType.EXPLICIT_MANUAL, CaseType.ACCEPTANCE_REJECTION} and (
            record.attempted_node_presence is False or record.attempted_node_value in {"", "auto"}):
            record_errors.append("Manual/boundary case requires an explicit candidate value")
        if required.case_type == CaseType.EXPLICIT_MANUAL and required.xml_field == XMLField.SPEED and record.attempted_node_value is not None and not record.attempted_node_value.isdigit():
            record_errors.append("Manual-speed hypothesis requires a numeric candidate token")
        missing.extend(f"{prefix}: missing {field}" for field in record_missing)
        errors.extend(f"{prefix}: {message}" for message in record_errors)
        signature = json.dumps(record.model_dump(mode="json", include={"initial_node_presence", "initial_node_value",
            "attempted_node_presence", "attempted_node_value", "load_result", "commit_result", "export_result",
            "exported_node_presence", "exported_node_value", "normalization_observed", "reimport_result",
            "reimported_node_presence", "reimported_node_value", "reimport_stable"}), sort_keys=True)
        signatures.setdefault(record.protocol_case_id, set()).add(signature)
        if not record_missing and not record_errors:
            covered.add(record.protocol_case_id)
    conflicts = sorted(f"Conflicting observations for {key}" for key, values in signatures.items() if len(values) > 1)
    absent = sorted(set(expected) - covered)
    return QualificationReport(scope=scope, status=Readiness.REJECTED if errors or conflicts else (
        Readiness.INCOMPLETE if absent or missing or not expected else Readiness.READY_FOR_REVIEW),
        required_case_count=len(expected), covered_case_ids=sorted(covered), missing_case_ids=absent,
        missing_evidence=sorted(set(missing)), scope_errors=sorted(set(errors)), conflicts=conflicts,
        synthetic=any(item.evidence_class == EvidenceClass.SYNTHETIC for item in records))


if __name__ == "__main__":
    catalog = load_gap_catalog()
    print(json.dumps(protocol_review_report(build_protocol_manifest(catalog), catalog), indent=2))
