import json
from pathlib import Path

from confighop_core.hardware.registry import list_profiles
from confighop_core.models.hardware import ProfileStatus, TargetRenderSupport


ROOT = Path(__file__).resolve().parents[2]
REQUESTS = ROOT / "docs/core/palo_alto_vendor_confirmation_requests.json"
GAPS = ROOT / "docs/core/palo_alto_evidence_gaps.json"
EXPECTED = {
    "PAN-VC-PA1400-MULTIGIG": {
        "gap": "PAN-GAP-PA1400-MULTIGIG",
        "models": {"PA-1410", "PA-1420"},
        "groups": {"pa1410-Multi-Gig PoE 9-12", "pa1420-Multi-Gig 5-8", "pa1420-Multi-Gig PoE 9-12"},
        "trains": {"11.0", "11.1", "11.2", "12.1.2+", "12.2"},
        "questions": 9,
    },
    "PAN-VC-PA3200-AUTO-RJ45": {
        "gap": "PAN-GAP-PA3200-AUTO-RJ45",
        "models": {"PA-3220", "PA-3250", "PA-3260"},
        "groups": {"pa3220-RJ45 1-12", "pa3250-RJ45 1-12", "pa3260-RJ45 1-12"},
        "trains": {"10.1", "10.2", "11.0", "11.1"},
        "questions": 6,
    },
    "PAN-VC-PA5200-AUTO-RJ45": {
        "gap": "PAN-GAP-PA5200-AUTO-RJ45",
        "models": {"PA-5220", "PA-5250", "PA-5260", "PA-5280"},
        "groups": {"pa5220-RJ45 1-4", "pa5250-RJ45 1-4", "pa5260-RJ45 1-4", "pa5280-RJ45 1-4"},
        "trains": {"10.1", "10.2", "11.0", "11.1", "11.2"},
        "questions": 7,
    },
}
REQUIRED_FIELDS = {
    "id", "gap_id", "title", "request_status", "response_status", "priority",
    "affected_models", "affected_port_groups", "panos_scope", "known_facts",
    "unresolved_questions", "requested_vendor_artifacts", "acceptance_criteria",
    "insufficient_response_examples", "submission_body", "response_intake_requirements", "notes",
}


def test_phase6b_request_package_and_frozen_production_state():
    data = json.loads(REQUESTS.read_text(encoding="utf-8"))
    gaps = json.loads(GAPS.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["closure_state"] == "AWAITING_VENDOR"
    assert set(data["allowed_closure_states"]) == {
        "AWAITING_VENDOR", "PARTIALLY_CONFIRMED", "READY_FOR_RENDERER_DESIGN", "BLOCKED_BY_VENDOR_AMBIGUITY",
    }
    assert set(data["allowed_request_statuses"]) == {"REQUEST_READY", "SUBMITTED", "RESPONSE_RECEIVED", "EVALUATED"}
    assert set(data["allowed_response_statuses"]) == {
        "NOT_RECEIVED", "SUFFICIENT", "PARTIAL", "CONFLICTING", "OUT_OF_SCOPE", "UNVERIFIABLE",
    }
    requests = data["requests"]
    assert len(requests) == 3
    assert {r["id"] for r in requests} == set(EXPECTED)
    assert len(set().union(*(e["groups"] for e in EXPECTED.values()))) == 10
    p0 = {g["id"]: g for g in gaps["gaps"] if g["priority"] == "P0"}
    assert set(p0) == {e["gap"] for e in EXPECTED.values()}
    assert len(gaps["gaps"]) == 13
    assert sum(g["priority"] == "P1" for g in gaps["gaps"]) == 10
    assert all(g["status"] == "EVIDENCE_PARTIAL" for g in gaps["gaps"])

    for request in requests:
        expected = EXPECTED[request["id"]]
        assert REQUIRED_FIELDS <= request.keys()
        assert request["gap_id"] == expected["gap"]
        assert request["priority"] == "P0"
        assert request["request_status"] == "REQUEST_READY"
        assert request["response_status"] == "NOT_RECEIVED"
        assert set(request["affected_models"]) == expected["models"]
        assert set(request["affected_port_groups"]) == expected["groups"]
        assert set(request["panos_scope"]) == expected["trains"]
        assert len(request["unresolved_questions"]) == expected["questions"]
        assert all(request[key] for key in REQUIRED_FIELDS - {"id", "gap_id", "request_status", "response_status", "priority"})
        assert set(request["acceptance_criteria"]) == {"SUFFICIENT", "PARTIAL", "CONFLICTING"}
        assert all(request["acceptance_criteria"].values())
        assert "link-speed" in request["submission_body"]
        assert "link-duplex" in request["submission_body"]
        assert "XML" in request["submission_body"]
        assert "default" in request["submission_body"]
        assert "manual" in request["submission_body"]
        assert all(model in request["submission_body"] for model in expected["models"])
        assert all(train in request["submission_body"] for train in expected["trains"])
        assert all(request.get(field) is None for field in (
            "case_number", "submission_url", "submitted_at", "vendor_responder", "response_received_at", "vendor_answer",
        ))
        gap = p0[expected["gap"]]
        assert gap["priority"] == "P0"
        assert gap["status"] == "EVIDENCE_PARTIAL"
        assert gap["blocking"] is True
        assert gap["resolution_requirements"] == ["VENDOR_CONFIRMATION_NEEDED"]
        assert set(gap["affected_models"]) == expected["models"]
        assert set(gap["affected_port_groups"]) == expected["groups"]

    pa5200 = next(r for r in requests if r["id"] == "PAN-VC-PA5200-AUTO-RJ45")
    assert "11.2" in pa5200["submission_body"] and "only CLI presentation" in pa5200["submission_body"]
    pa1400 = next(r for r in requests if r["id"] == "PAN-VC-PA1400-MULTIGIG")
    assert all(term in pa1400["submission_body"] for term in ("English", "Chinese", "2.5G", "5G"))
    assert gaps["catalog"] == {
        "verified_models": 11,
        "renderer_supported_models": ["PA-3410", "PA-5410"],
        "analysis_only_models": ["PA-1410", "PA-1420", "PA-3220", "PA-3250", "PA-3260", "PA-5220", "PA-5250", "PA-5260", "PA-5280"],
    }
    profiles = list_profiles(vendor="palo_alto", profile_status=ProfileStatus.VERIFIED)
    assert {p.model for p in profiles if p.target_render_support == TargetRenderSupport.SUPPORTED} == {"PA-3410", "PA-5410"}
    assert {p.model for p in profiles if p.target_render_support == TargetRenderSupport.SCOPED} == {
        "PA-3220", "PA-3250", "PA-3260", "PA-5220", "PA-5250", "PA-5260", "PA-5280",
    }
    assert {p.model for p in profiles if p.target_render_support == TargetRenderSupport.ANALYSIS_ONLY} == {"PA-1410", "PA-1420"}
