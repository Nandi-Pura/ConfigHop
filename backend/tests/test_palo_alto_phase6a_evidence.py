import json
from pathlib import Path

from confighop_core.hardware.registry import list_profiles
from confighop_core.models.hardware import ProfileStatus, TargetRenderSupport


MANIFEST = Path(__file__).resolve().parents[2] / "docs/core/palo_alto_evidence_gaps.json"
P0_GROUPS = {
    "PAN-GAP-PA1400-MULTIGIG": {"pa1410-Multi-Gig PoE 9-12", "pa1420-Multi-Gig 5-8", "pa1420-Multi-Gig PoE 9-12"},
    "PAN-GAP-PA3200-AUTO-RJ45": {"pa3220-RJ45 1-12", "pa3250-RJ45 1-12", "pa3260-RJ45 1-12"},
    "PAN-GAP-PA5200-AUTO-RJ45": {"pa5220-RJ45 1-4", "pa5250-RJ45 1-4", "pa5260-RJ45 1-4", "pa5280-RJ45 1-4"},
}


def test_phase6a_p0_evidence_ceiling():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    gaps = {gap["id"]: gap for gap in data["gaps"]}
    assert {gap["id"] for gap in data["gaps"] if gap["priority"] == "P0"} == P0_GROUPS.keys()
    assert len(set().union(*P0_GROUPS.values())) == 10
    profiles = {p.model: p for p in list_profiles(vendor="palo_alto", profile_status=ProfileStatus.VERIFIED)}
    assert {m for m, p in profiles.items() if p.target_render_support == TargetRenderSupport.SUPPORTED} == {"PA-3410", "PA-5410"}
    assert {m for m, p in profiles.items() if p.target_render_support == TargetRenderSupport.SCOPED} == {"PA-3220", "PA-3250", "PA-3260", "PA-5220", "PA-5250", "PA-5260", "PA-5280"}
    assert {m for m, p in profiles.items() if p.target_render_support == TargetRenderSupport.ANALYSIS_ONLY} == {"PA-1410", "PA-1420"}
    for gap_id, expected_groups in P0_GROUPS.items():
        gap = gaps[gap_id]
        assert set(gap["affected_port_groups"]) == expected_groups
        assert gap["blocking"] is True
        assert gap["status"] == "EVIDENCE_PARTIAL"
        assert gap["resolution_requirements"] == ["VENDOR_CONFIRMATION_NEEDED"]
        assert "PHASE6A_RESEARCH" in gap["source_phases"]
        assert all(gap[key] for key in ("missing_fact", "evidence_limit", "required_evidence", "next_action"))
    assert all("PHASE6A_RESEARCH" not in gap["source_phases"] for gap in data["gaps"] if gap["priority"] == "P1")
