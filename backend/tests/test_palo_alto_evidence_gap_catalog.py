import json
from pathlib import Path

from confighop_core.evidence.registry import EVIDENCE
from confighop_core.hardware.registry import list_profiles
from confighop_core.models.hardware import ProfileStatus, TargetRenderSupport


MANIFEST = Path(__file__).resolve().parents[2] / "docs/core/palo_alto_evidence_gaps.json"
ANALYSIS = {"PA-1410", "PA-1420", "PA-3220", "PA-3250", "PA-3260", "PA-5220", "PA-5250", "PA-5260", "PA-5280"}
SUPPORTED = {"PA-3410", "PA-5410"}
FIELDS = {"id", "title", "series", "source_phases", "affected_models", "affected_port_groups", "semantic_area", "gap_types", "blocking", "status", "priority", "existing_evidence_ids", "current_known_behavior", "evidence_limit", "missing_fact", "why_blocking", "resolution_requirements", "required_evidence", "next_action", "future_renderer_dependency", "notes"}
FROZEN_EXPECTED_GROUPS = frozenset({
    "pa1410-Multi-Gig PoE 9-12",
    "pa1410-RJ45 1-8",
    "pa1410-SFP 13-18",
    "pa1410-SFP+ 19-22",
    "pa1420-Multi-Gig 5-8",
    "pa1420-Multi-Gig PoE 9-12",
    "pa1420-RJ45 1-4",
    "pa1420-SFP 13-14",
    "pa1420-SFP+ 15-22",
    "pa3220-RJ45 1-12",
    "pa3220-SFP 13-16",
    "pa3220-SFP+ 17-20",
    "pa3250-RJ45 1-12",
    "pa3250-SFP+ 13-20",
    "pa3260-QSFP+ 21-24",
    "pa3260-RJ45 1-12",
    "pa3260-SFP+ 13-20",
    "pa5220-QSFP 21-24",
    "pa5220-RJ45 1-4",
    "pa5220-SFP+ 5-20",
    "pa5250-QSFP 21-24",
    "pa5250-RJ45 1-4",
    "pa5250-SFP+ 5-20",
    "pa5260-QSFP 21-24",
    "pa5260-RJ45 1-4",
    "pa5260-SFP+ 5-20",
    "pa5280-QSFP 21-24",
    "pa5280-RJ45 1-4",
    "pa5280-SFP+ 5-20",
})


def test_evidence_gap_catalog():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["catalog"] == {"verified_models": 11, "renderer_supported_models": sorted(SUPPORTED), "analysis_only_models": sorted(ANALYSIS)}
    profiles = {p.model: p for p in list_profiles(vendor="palo_alto", profile_status=ProfileStatus.VERIFIED)}
    assert set(profiles) == ANALYSIS | SUPPORTED
    assert {m for m, p in profiles.items() if p.target_render_support == TargetRenderSupport.SUPPORTED} == SUPPORTED
    assert {m for m, p in profiles.items() if p.target_render_support == TargetRenderSupport.ANALYSIS_ONLY} == ANALYSIS
    registry_groups = {group.id for model in ANALYSIS for group in profiles[model].interface_groups}
    assert len(FROZEN_EXPECTED_GROUPS) == 29
    assert registry_groups == FROZEN_EXPECTED_GROUPS
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
        assert set(gap["source_phases"]) <= {"PHASE2", "PHASE3", "PHASE4", "PHASE5_RESEARCH", "PHASE6A_RESEARCH"}
        assert gap["existing_evidence_ids"] and set(gap["existing_evidence_ids"]) <= EVIDENCE.keys()
        assert all(gap[key] for key in ("current_known_behavior", "evidence_limit", "missing_fact", "why_blocking", "required_evidence", "next_action", "future_renderer_dependency"))
        assert gap["blocking"] is True and gap["status"] in {"OPEN", "EVIDENCE_PARTIAL", "EVIDENCE_READY"}
        assert set(gap["affected_models"]) <= ANALYSIS
        groups = set(gap["affected_port_groups"])
        assert groups <= FROZEN_EXPECTED_GROUPS
        assert groups <= registry_groups
        assert {model for model in gap["affected_models"]} == {profiles[model].model for model in ANALYSIS if any(group.id in groups for group in profiles[model].interface_groups)}
        covered |= groups
        blocked_models |= set(gap["affected_models"])
        assert "DEVICE_VALIDATED" not in json.dumps(gap)
        assert gap.get("device_validated") is not True
    assert covered == FROZEN_EXPECTED_GROUPS
    assert blocked_models == ANALYSIS
    assert {g.split("-")[0] for g in covered} == {"pa1410", "pa1420", "pa3220", "pa3250", "pa3260", "pa5220", "pa5250", "pa5260", "pa5280"}
