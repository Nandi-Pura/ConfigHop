import json
from pathlib import Path

from confighop_core.evidence.registry import EVIDENCE
from confighop_core.hardware.registry import list_profiles
from confighop_core.models.hardware import ProfileStatus, TargetRenderSupport


MANIFEST = Path(__file__).resolve().parents[2] / "docs/core/palo_alto_evidence_gaps.json"
ANALYSIS = {"PA-1410", "PA-1420", "PA-3220", "PA-3250", "PA-3260", "PA-5220", "PA-5250", "PA-5260", "PA-5280"}
SUPPORTED = {"PA-3410", "PA-5410"}
FIELDS = {"id", "title", "series", "source_phases", "affected_models", "affected_port_groups", "semantic_area", "gap_types", "blocking", "status", "priority", "existing_evidence_ids", "current_known_behavior", "evidence_limit", "missing_fact", "why_blocking", "resolution_requirements", "required_evidence", "next_action", "future_renderer_dependency", "notes"}


def test_evidence_gap_catalog():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["catalog"] == {"verified_models": 11, "renderer_supported_models": sorted(SUPPORTED), "analysis_only_models": sorted(ANALYSIS)}
    profiles = {p.model: p for p in list_profiles(vendor="palo_alto", profile_status=ProfileStatus.VERIFIED)}
    assert set(profiles) == ANALYSIS | SUPPORTED
    assert {m for m, p in profiles.items() if p.target_render_support == TargetRenderSupport.SUPPORTED} == SUPPORTED
    assert {m for m, p in profiles.items() if p.target_render_support == TargetRenderSupport.ANALYSIS_ONLY} == ANALYSIS
    expected_groups = {group.id for model in ANALYSIS for group in profiles[model].interface_groups}
    assert len(expected_groups) == 29
    gaps = data["gaps"]
    ids = [gap["id"] for gap in gaps]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)
    covered = set()
    blocked_models = set()
    for gap in gaps:
        assert FIELDS <= gap.keys()
        assert gap["id"].startswith("PAN-GAP-")
        assert gap["gap_types"] and set(gap["gap_types"]) <= set(data["allowed_gap_types"])
        assert gap["resolution_requirements"] and set(gap["resolution_requirements"]) <= set(data["allowed_resolution_requirements"])
        assert gap["status"] in data["allowed_statuses"]
        assert gap["priority"] in data["allowed_priorities"]
        assert set(gap["source_phases"]) <= {"PHASE2", "PHASE3", "PHASE4", "PHASE5_RESEARCH"}
        assert gap["existing_evidence_ids"] and set(gap["existing_evidence_ids"]) <= EVIDENCE.keys()
        assert all(gap[key] for key in ("current_known_behavior", "evidence_limit", "missing_fact", "why_blocking", "required_evidence", "next_action", "future_renderer_dependency"))
        assert gap["blocking"] is True and gap["status"] in {"OPEN", "EVIDENCE_PARTIAL", "EVIDENCE_READY"}
        assert set(gap["affected_models"]) <= ANALYSIS
        groups = set(gap["affected_port_groups"])
        assert groups <= expected_groups
        assert {model for model in gap["affected_models"]} == {profiles[model].model for model in ANALYSIS if any(group.id in groups for group in profiles[model].interface_groups)}
        covered |= groups
        blocked_models |= set(gap["affected_models"])
        assert "DEVICE_VALIDATED" not in json.dumps(gap)
        assert gap.get("device_validated") is not True
    assert covered == expected_groups
    assert blocked_models == ANALYSIS
    assert {g.split("-")[0] for g in covered} == {"pa1410", "pa1420", "pa3220", "pa3250", "pa3260", "pa5220", "pa5250", "pa5260", "pa5280"}
