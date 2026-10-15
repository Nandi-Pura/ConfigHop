from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from confighop_core.evidence.qualification_protocol import (
    ArtifactReference, CaseType, DOCS, EvidenceClass, ExecutionStatus, ObservationRecord,
    Outcome, ProtocolManifest, QualificationScope, Readiness, XMLField,
    assess_serialization_evidence, build_protocol_manifest, evidence_inventory,
    load_gap_catalog, protocol_cases, protocol_review_report, validate_protocol_manifest,
)
from confighop_core.hardware.registry import get_profile
from confighop_core.evidence import registry


TARGET_GAPS = {
    "PAN-GAP-PA3200-AUTO-RJ45", "PAN-GAP-PA3200-OPTICAL-1G", "PAN-GAP-PA3200-OPTICAL-MIXED",
    "PAN-GAP-PA3200-QSFP-40G", "PAN-GAP-PA5200-AUTO-RJ45", "PAN-GAP-PA5200-OPTICAL",
    "PAN-GAP-PA5200-QSFP-40G", "PAN-GAP-PA5200-QSFP-40-100G",
}


@pytest.fixture
def protocol():
    catalog = load_gap_catalog()
    manifest = ProtocolManifest.model_validate_json((DOCS / "palo_alto_phase7d_qualification_protocol.json").read_text())
    return catalog, manifest


@pytest.fixture
def scope():
    return QualificationScope(gap_id="PAN-GAP-PA5200-OPTICAL", hardware_model="PA-5220",
        exact_panos_version="11.1.4", panos_train="11.1", port_group_id="pa5220-SFP+ 5-20",
        interface_name="ethernet1/5", optic_rate="10G")


def synthetic_records(protocol, scope):
    catalog, manifest = protocol
    cases = [case for case in protocol_cases(manifest, catalog) if
        (case.gap_id, case.hardware_model, case.port_group_id, case.panos_train, case.optic_rate) ==
        (scope.gap_id, scope.hardware_model, scope.port_group_id, scope.panos_train, scope.optic_rate)]
    records = []
    for case in cases:
        absent = case.case_type == CaseType.DEFAULT_ABSENT
        boundary = case.case_type == CaseType.ACCEPTANCE_REJECTION
        normalized = case.case_type == CaseType.EXPORT_NORMALIZATION
        manual = case.case_type == CaseType.EXPLICIT_MANUAL
        value = None if absent else "synthetic-invalid" if boundary else (
            "10000" if case.xml_field == XMLField.SPEED else "full") if manual else "auto"
        records.append(ObservationRecord(**scope.model_dump(), evidence_record_id=f"synthetic-{case.id}",
            protocol_case_id=case.id, xml_field=case.xml_field, media_type="SFP_PLUS",
            transceiver_context="Synthetic test-only transceiver metadata; no device observed",
            initial_node_presence=False, attempted_node_presence=not absent, attempted_node_value=value,
            load_result=Outcome.LOAD_REJECTED if boundary else Outcome.LOAD_ACCEPTED,
            commit_result=Outcome.NOT_APPLICABLE if boundary else Outcome.COMMIT_ACCEPTED,
            export_result=Outcome.NOT_APPLICABLE if boundary else Outcome.NODE_OMITTED if absent else (
                Outcome.EXPORTED_NORMALIZED if normalized else Outcome.EXPORTED_UNCHANGED),
            exported_node_presence=None if boundary else not absent,
            exported_node_value=None if boundary or absent else "synthetic-normalized" if normalized else value,
            normalization_observed=None if boundary else normalized,
            reimport_result=Outcome.NOT_APPLICABLE if boundary else Outcome.REIMPORT_ACCEPTED,
            reimported_node_presence=None if boundary else not absent,
            reimported_node_value=None if boundary or absent else "synthetic-normalized" if normalized else value,
            reimport_stable=None if boundary else True,
            not_applicable_reason="Synthetic load rejection prevents later stages" if boundary else None,
            artifacts=[ArtifactReference(reference="artifact://synthetic/metadata", sha256="0" * 64, redaction_status="SANITIZED")],
            observation_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), tester_identifier="synthetic-author",
            reviewer_identifier="synthetic-designated-reviewer", provenance="Synthetic metadata only; no technical qualification",
            evidence_class=EvidenceClass.SYNTHETIC, execution_status=ExecutionStatus.OBSERVATION_RECORDED))
    return records


def test_inventory_and_manifest_match_frozen_sources(protocol):
    catalog, manifest = protocol
    inventory = evidence_inventory(catalog)
    assert len(inventory) == 13 and Counter(item.priority for item in inventory) == {"P0": 3, "P1": 10}
    assert {item.gap_id for item in inventory if item.protocol_scope == "TARGETED"} == TARGET_GAPS
    assert sum(item.protocol_scope == "PARKED" for item in inventory) == 5
    assert all(item.blocking and item.gap_status == "EVIDENCE_PARTIAL" for item in inventory)
    assert manifest == build_protocol_manifest(catalog)
    assert {item.hardware_model for item in manifest.scopes} == {
        "PA-3220", "PA-3250", "PA-3260", "PA-5220", "PA-5250", "PA-5260", "PA-5280"}
    assert len(manifest.scopes) == 20
    for item in manifest.scopes:
        profile = get_profile(f"paloalto-{item.hardware_model.lower()}")
        group = next(group for group in profile.interface_groups if group.id == item.port_group_id)
        assert item.interface_names == group.interface_names
        assert item.panos_trains == (["10.1", "10.2", "11.0", "11.1"] if profile.series == "PA-3200"
            else ["10.1", "10.2", "11.0", "11.1", "11.2"])
        assert item.optic_rates == ([None] if group.media_capabilities == ["RJ45"] else group.speed_capabilities)


def test_protocol_cases_are_independent_unobserved_and_deterministic(protocol):
    catalog, manifest = protocol
    cases = protocol_cases(manifest, catalog)
    assert len(cases) == 1668 and len({case.id for case in cases}) == len(cases)
    assert all(case.execution_status == "NOT_RUN" and case.expected_device_outcome == "UNDETERMINED" for case in cases)
    assert {case.case_type for case in cases} == set(CaseType)
    assert {case.xml_field for case in cases} == set(XMLField)
    for scope in manifest.scopes:
        scoped = [case for case in cases if case.port_group_id == scope.port_group_id]
        assert {case.xml_field for case in scoped} == set(XMLField)
    assert cases == protocol_cases(manifest, catalog)
    report = protocol_review_report(manifest, catalog)
    assert report == protocol_review_report(manifest, catalog)
    assert report["status"] == "INCOMPLETE" and report["cases_not_run"] == 1668
    assert report["evidence_supplied"] == 0
    assert {item["gap_id"] for item in report["gap_coverage"]} == TARGET_GAPS


@pytest.mark.parametrize("field,value", [("panos_trains", ["12.1"]), ("optic_rates", ["25G"]),
    ("interface_names", ["ethernet1/99"]), ("hardware_model", "PA-5410"), ("port_group_id", "wrong-group")])
def test_snapshot_drift_is_rejected(protocol, field, value):
    catalog, manifest = protocol
    changed = manifest.model_copy(deep=True)
    setattr(changed.scopes[0], field, value)
    with pytest.raises(ValueError, match="diverges"):
        validate_protocol_manifest(changed, catalog)


@pytest.mark.parametrize("field,value", [("hardware_model", "PA-5250"), ("port_group_id", "wrong-group"),
    ("interface_name", "ethernet1/1"), ("panos_train", "12.1"), ("optic_rate", "100G"),
    ("exact_panos_version", "11.1")])
def test_invalid_qualification_scope_is_rejected(protocol, scope, field, value):
    catalog, manifest = protocol
    changed = scope.model_copy(update={field: value})
    result = assess_serialization_evidence(changed, [], manifest, catalog)
    assert result.status == Readiness.REJECTED and result.scope_errors


def test_complete_synthetic_packet_is_only_ready_for_human_review(protocol, scope):
    catalog, manifest = protocol
    records = synthetic_records(protocol, scope)
    before = [item.model_dump() for item in records]
    report = assess_serialization_evidence(scope, records, manifest, catalog)
    assert report.status == Readiness.READY_FOR_REVIEW and report.required_case_count == 12
    assert report.synthetic and not report.device_validated and not report.production_state_changed
    assert not report.missing_case_ids and not report.scope_errors
    assert [item.model_dump() for item in records] == before
    assert report == assess_serialization_evidence(scope, records, manifest, catalog)
    assert report == assess_serialization_evidence(scope, list(reversed(records)), manifest, catalog)
    assert any(item.load_result == Outcome.LOAD_REJECTED for item in records)


@pytest.mark.parametrize("field,value,reason", [("exact_panos_version", None, "exact_panos_version"),
    ("port_group_id", None, "port_group_id"), ("export_result", Outcome.NOT_OBSERVED, "export_result"),
    ("reimport_result", Outcome.NOT_OBSERVED, "reimport_result"), ("artifacts", [], "artifact provenance"),
    ("provenance", None, "provenance")])
def test_missing_metadata_stays_incomplete(protocol, scope, field, value, reason):
    catalog, manifest = protocol
    records = synthetic_records(protocol, scope)
    records[0] = records[0].model_copy(update={field: value})
    report = assess_serialization_evidence(scope, records, manifest, catalog)
    assert report.status == Readiness.INCOMPLETE
    assert any(reason in item for item in report.missing_evidence)


def test_speed_only_or_no_observations_cannot_cover_duplex(protocol, scope):
    catalog, manifest = protocol
    records = [item for item in synthetic_records(protocol, scope) if item.xml_field == XMLField.SPEED]
    report = assess_serialization_evidence(scope, records, manifest, catalog)
    assert report.status == Readiness.INCOMPLETE and len(report.missing_case_ids) == 6
    assert assess_serialization_evidence(scope, [], manifest, catalog).status == Readiness.INCOMPLETE


def test_unpopulated_record_is_incomplete_with_specific_missing_dimensions(protocol, scope):
    catalog, manifest = protocol
    case = synthetic_records(protocol, scope)[0]
    blank = ObservationRecord(evidence_record_id="synthetic-blank", protocol_case_id=case.protocol_case_id)
    report = assess_serialization_evidence(scope, [blank], manifest, catalog)
    assert report.status == Readiness.INCOMPLETE
    for field in ("exact_panos_version", "port_group_id", "xml_field", "export_result", "reimport_result", "artifact provenance"):
        assert any(field in reason for reason in report.missing_evidence)


def test_internally_contradictory_export_and_load_are_rejected(protocol, scope):
    catalog, manifest = protocol
    records = synthetic_records(protocol, scope)
    accepted = next(item for item in records if item.export_result == Outcome.EXPORTED_UNCHANGED)
    wrong = accepted.model_copy(update={"normalization_observed": True})
    assert assess_serialization_evidence(scope, [wrong], manifest, catalog).status == Readiness.REJECTED
    wrong = accepted.model_copy(update={"load_result": Outcome.LOAD_REJECTED})
    assert assess_serialization_evidence(scope, [wrong], manifest, catalog).status == Readiness.REJECTED


def test_reimport_acceptance_does_not_imply_roundtrip_stability(protocol, scope):
    catalog, manifest = protocol
    records = synthetic_records(protocol, scope)
    accepted = next(item for item in records if item.export_result == Outcome.EXPORTED_UNCHANGED)
    missing = accepted.model_copy(update={"reimport_stable": None})
    result = assess_serialization_evidence(scope, [missing], manifest, catalog)
    assert result.status == Readiness.INCOMPLETE and any("reimport_stable" in item for item in result.missing_evidence)
    contradictory = accepted.model_copy(update={"reimported_node_value": "synthetic-different", "reimport_stable": True})
    assert assess_serialization_evidence(scope, [contradictory], manifest, catalog).status == Readiness.REJECTED


@pytest.mark.parametrize("kind", [CaseType.EXPORT_NORMALIZATION, CaseType.REIMPORT_STABILITY])
def test_unexecuted_export_or_reimport_case_cannot_count_as_covered(protocol, scope, kind):
    catalog, manifest = protocol
    cases = {case.id: case for case in protocol_cases(manifest, catalog)}
    records = synthetic_records(protocol, scope)
    skipped = set()
    for record in records:
        if cases[record.protocol_case_id].case_type != kind:
            continue
        skipped.add(record.protocol_case_id)
        record.load_result = Outcome.LOAD_REJECTED
        record.commit_result = Outcome.NOT_APPLICABLE
        record.export_result = Outcome.NOT_APPLICABLE
        record.exported_node_presence = record.exported_node_value = None
        record.normalization_observed = None
        record.reimport_result = Outcome.NOT_APPLICABLE
        record.reimported_node_presence = record.reimported_node_value = None
        record.reimport_stable = None
        record.not_applicable_reason = "Synthetic rejected load prevented export and re-import"
    result = assess_serialization_evidence(scope, records, manifest, catalog)
    assert result.status == Readiness.INCOMPLETE
    assert set(result.missing_case_ids) == skipped
    assert skipped.isdisjoint(result.covered_case_ids)
    assert not result.scope_errors
    assert any(kind.value in reason for reason in result.missing_evidence)
    assert any(record.load_result == Outcome.LOAD_REJECTED for record in records)


@pytest.mark.parametrize("field,value", [("hardware_model", "PA-5250"), ("exact_panos_version", "10.2.4"),
    ("exact_panos_version", "11.1.5"), ("panos_train", "11.2"), ("interface_name", "ethernet1/6")])
def test_observations_cannot_be_generalized_across_exact_scope(protocol, scope, field, value):
    catalog, manifest = protocol
    records = synthetic_records(protocol, scope)
    records[0] = records[0].model_copy(update={field: value})
    report = assess_serialization_evidence(scope, records, manifest, catalog)
    assert report.status == Readiness.REJECTED
    assert any(f"scope mismatch: {field}" in item for item in report.scope_errors)


def test_conflicting_observations_are_rejected(protocol, scope):
    catalog, manifest = protocol
    records = synthetic_records(protocol, scope)
    conflict = records[0].model_copy(update={"evidence_record_id": "synthetic-conflict", "load_result": Outcome.LOAD_REJECTED})
    result = assess_serialization_evidence(scope, [*records, conflict], manifest, catalog)
    assert result.status == Readiness.REJECTED and result.conflicts


def test_community_material_and_unjustified_skipped_stages_do_not_qualify(protocol, scope):
    catalog, manifest = protocol
    records = synthetic_records(protocol, scope)
    records[0] = records[0].model_copy(update={"evidence_class": EvidenceClass.COMMUNITY})
    assert assess_serialization_evidence(scope, records, manifest, catalog).status == Readiness.REJECTED
    records = synthetic_records(protocol, scope)
    records[0] = records[0].model_copy(update={"reimport_result": Outcome.NOT_APPLICABLE})
    assert assess_serialization_evidence(scope, records, manifest, catalog).status == Readiness.REJECTED


@pytest.mark.parametrize("reference", ["file:///private.xml", "artifact://../private", "https://user:password@example.com/a"])
def test_artifact_references_are_metadata_only_and_safe(reference):
    with pytest.raises(ValidationError):
        ArtifactReference(reference=reference, sha256="0" * 64)


def test_frozen_support_and_vendor_state(protocol):
    catalog, _ = protocol
    assert all(gap["status"] == "EVIDENCE_PARTIAL" and gap["blocking"] for gap in catalog["gaps"])
    vendor = json.loads((DOCS / "palo_alto_vendor_confirmation_requests.json").read_text())
    assert all(item["request_status"] == "REQUEST_READY" and item["response_status"] == "NOT_RECEIVED"
        for item in vendor["requests"])
    for model in ("PA-3220", "PA-3250", "PA-3260", "PA-5220", "PA-5250", "PA-5260", "PA-5280"):
        assert get_profile(f"paloalto-{model.lower()}").target_render_support == "SCOPED"
    for model in ("PA-1410", "PA-1420"):
        assert get_profile(f"paloalto-{model.lower()}").target_render_support == "ANALYSIS_ONLY"
    for model in ("PA-3410", "PA-5410"):
        assert get_profile(f"paloalto-{model.lower()}").target_render_support == "SUPPORTED"


@pytest.mark.parametrize("path,digest", [
    (DOCS / "palo_alto_evidence_gaps.json", "592ca75a46a01b24b3b36f215089a6feaa0621b358f519fee3568247d1ed4680"),
    (DOCS / "palo_alto_vendor_confirmation_requests.json", "c03601bf0610f7f5bdf0282b0136d431aefbe2586d047d671eb08e420c6b952b"),
    (Path(registry.__file__), "8069ac61f85c78ac32aa992eef7ffdb6f2b6ad534feac49028571abe4714440f"),
])
def test_frozen_artifacts_match_phase7c_text_snapshot(path, digest):
    assert sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest() == digest
