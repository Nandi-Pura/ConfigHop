"""Browser UAT for the target package review UI with deterministic API responses."""

import json
import time

from playwright.sync_api import Route, sync_playwright


PROJECT_ID = "uat-target-project"
PROFILE = {
    "id": "paloalto-pa-5410",
    "vendor": "Palo Alto Networks",
    "model": "PA-5410",
    "series": "PA-5400",
    "profile_status": "verified",
    "target_render_support": "SCOPED",
    "interface_count": 0,
    "verified_at": "2026-10-20T00:00:00Z",
    "candidate_ready_interface_count": 0,
    "native_interface_count": 0,
    "conditional_interface_count": 0,
    "breakout_interface_count": 0,
    "supported_panos_trains": ["11.1"],
    "evidence_ids": [],
    "interfaces": [],
    "port_details": [],
    "first_supported_release": "11.1.0",
    "notes": None,
}
BASELINE = {
    "baseline_id": "baseline-1",
    "serial": "TARGET1",
    "model": "PA-5410",
    "hostname": "target-fw",
    "panos_version": "11.1.4",
    "multi_vsys": False,
    "operational_mode": "normal",
    "sha256": "b" * 64,
    "artifact_format": "AES_256_GCM_V1",
    "artifact_size_bytes": 2048,
    "observed_at_utc": "2026-10-20T00:00:00Z",
}
PACKAGE = {
    "package_id": "package-1",
    "target_baseline_sha256": "b" * 64,
    "target_serial": "TARGET1",
    "candidate_sha256": "c" * 64,
    "deployable_candidate_sha256": "d" * 64,
    "target_changes": [
        {"scope": "devices/device/vsys/entry/rulebase/security/rules", "object_name": "Allow-DNS", "action": "ADDED"},
        {"scope": "devices/device/network/virtual-router", "object_name": "default", "action": "REPLACED"},
    ],
    "target_preservation": {
        "management_plane": "PRESERVED",
        "ha_and_panorama": "PRESERVED",
        "management_profiles": "PRESERVED",
        "certificates_and_keys": "PRESERVED",
    },
    "target_findings": [
        {"code": "TARGET_LOCAL_SCOPES_PRESERVED", "severity": "INFO", "scope": "target", "message": "Protected target-local scopes are unchanged.", "requires_acceptance": False},
        {"code": "TARGET_POLICY_ORDER_REVIEW_REQUIRED", "severity": "WARNING", "scope": "vsys1/rulebase", "message": "Review final security and NAT rule order.", "requires_acceptance": True},
    ],
    "review_id": None,
    "review_sha256": None,
    "running_backup_sha256": None,
    "candidate_backup_sha256": None,
    "loaded_candidate_sha256": None,
    "change_summary_sha256": None,
    "validation_sha256": None,
    "validation_job_id": None,
    "ambiguous_operation": None,
    "approval_sha256": None,
    "approval_expires_at_utc": None,
    "approval_used_at_utc": None,
    "commit_job_id": None,
    "commit_result_sha256": None,
    "post_verification_sha256": None,
    "recovery_load_sha256": None,
    "recovery_validation_sha256": None,
    "recovery_commit_job_id": None,
    "recovery_verification_sha256": None,
    "status": "DRAFT",
}


def fulfill(route: Route, body, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


def main():
    state = {"baseline": False, "package": False, "reviewed": False, "staged": False,
        "approved": False, "committed": False, "ambiguous": False,
        "commit_ambiguous": False, "recovered": False,
        "connection_attempts": 0}
    request_bodies = []

    def api_route(route: Route):
        request = route.request
        path = request.url.split("/api/v1", 1)[-1]
        if request.post_data:
            request_bodies.append({"path": path, "body": json.loads(request.post_data)})
        if path == "/capabilities":
            return fulfill(route, {"domains": {"firewall": {
                "panos_target_stage_validate": True, "panos_target_commit_recovery": True,
                "deployment_mode": "lab"}}})
        if path == "/hardware-profiles":
            return fulfill(route, [PROFILE])
        if path == "/evidence":
            return fulfill(route, [])
        if path == f"/hardware-profiles/{PROFILE['id']}":
            return fulfill(route, PROFILE)
        if path == f"/projects/{PROJECT_ID}":
            return fulfill(route, {
                "project_id": PROJECT_ID, "source_available": False, "source_filename": None,
                "source_size_bytes": None, "source_sha256": None, "source_provenance": None,
                "source_profile_id": None, "source_panos_train": None,
                "target_profile_id": PROFILE["id"], "target_panos_train": "11.1",
                "preview_available": True, "candidate_available": True,
                "candidate_sha256": "c" * 64, "candidate_size_bytes": 20 * 1024 * 1024,
                "active_package_id": "package-1",
            })
        if path == f"/projects/{PROJECT_ID}/preview":
            return fulfill(route, {"mappings": [], "impacts": [], "findings": [],
                "summary": {"submitted_mappings": 0, "valid_mappings": 0, "derived_subinterface_mappings": 0,
                    "zone_reference_changes": 0, "virtual_router_reference_changes": 0,
                    "static_route_reference_changes": 0, "nat_reference_changes": 0,
                    "aggregate_membership_changes": 0, "review_findings": 0, "blocking_findings": 0},
                "status": "READY", "overall_status": "READY", "platform_assessment": None,
                "hardware_assessment": None, "deployment_plan": None})
        if path == f"/projects/{PROJECT_ID}/candidate":
            return fulfill(route, {
                "status": "READY", "candidate_available": True, "candidate_sha256": "c" * 64,
                "candidate_size_bytes": 20 * 1024 * 1024, "preview_status": "READY", "plan_status": "READY",
                "validation": None, "semantic_diff": None, "findings": [], "plan": None,
                "summary": {"submitted_mappings": 0, "valid_mappings": 0, "derived_subinterface_mappings": 0,
                    "zone_reference_changes": 0, "virtual_router_reference_changes": 0,
                    "static_route_reference_changes": 0, "nat_reference_changes": 0,
                    "aggregate_membership_changes": 0, "review_findings": 0, "blocking_findings": 0},
                "source_profile_id": None, "target_profile_id": PROFILE["id"], "source_profile_status": None,
                "target_profile_status": "verified", "target_render_support": "SCOPED",
                "effective_panos_version": "11.1", "platform_assessment_status": "READY",
                "hardware_assessment_status": "READY", "evidence_ids": [], "deployment_plan": None,
            })
        if path == f"/projects/{PROJECT_ID}/target/baseline":
            time.sleep(0.15)
            return fulfill(route, BASELINE) if state["baseline"] else fulfill(route, {"error": {"code": "TARGET_BASELINE_NOT_FOUND", "message": "No target baseline."}}, 409)
        if path == f"/projects/{PROJECT_ID}/deployment-package":
            time.sleep(0.15)
            if not state["package"]:
                return fulfill(route, {"error": {"code": "PACKAGE_NOT_FOUND", "message": "No package."}}, 409)
            body = {**PACKAGE}
            if state["reviewed"]:
                body.update({"review_id": "review-1", "review_sha256": "e" * 64, "status": "PREFLIGHT_PASSED"})
            if state["staged"]:
                body.update({"review_id": "review-1", "review_sha256": "e" * 64,
                    "running_backup_sha256": "1" * 64, "candidate_backup_sha256": "2" * 64,
                    "loaded_candidate_sha256": "d" * 64, "change_summary_sha256": "3" * 64,
                    "validation_sha256": "4" * 64, "validation_job_id": "42",
                    "status": "VALIDATED"})
            if state["ambiguous"]:
                body.update({"review_id": "review-1", "review_sha256": "e" * 64,
                    "running_backup_sha256": "1" * 64, "candidate_backup_sha256": "2" * 64,
                    "ambiguous_operation": "IMPORT", "status": "STATUS_UNKNOWN"})
            if state["approved"]:
                body.update({"review_id": "review-1", "review_sha256": "e" * 64,
                    "running_backup_sha256": "1" * 64, "candidate_backup_sha256": "2" * 64,
                    "loaded_candidate_sha256": "d" * 64, "change_summary_sha256": "3" * 64,
                    "validation_sha256": "4" * 64, "validation_job_id": "42",
                    "approval_expires_at_utc": "2026-10-27T10:10:00Z",
                    "status": "AWAITING_COMMIT_APPROVAL"})
            if state["committed"]:
                body.update({"review_id": "review-1", "review_sha256": "e" * 64,
                    "running_backup_sha256": "1" * 64, "candidate_backup_sha256": "2" * 64,
                    "validation_sha256": "4" * 64, "commit_job_id": "84",
                    "commit_result_sha256": "5" * 64, "post_verification_sha256": "6" * 64,
                    "status": "SUCCEEDED"})
            if state["commit_ambiguous"]:
                body.update({"review_id": "review-1", "review_sha256": "e" * 64,
                    "running_backup_sha256": "1" * 64, "candidate_backup_sha256": "2" * 64,
                    "validation_sha256": "4" * 64, "approval_used_at_utc": "2026-10-27T10:00:00Z",
                    "ambiguous_operation": "COMMIT", "status": "STATUS_UNKNOWN"})
            if state["recovered"]:
                body.update({"review_id": "review-1", "review_sha256": "e" * 64,
                    "running_backup_sha256": "1" * 64, "candidate_backup_sha256": "2" * 64,
                    "recovery_load_sha256": "7" * 64, "recovery_validation_sha256": "8" * 64,
                    "recovery_commit_job_id": "88", "recovery_verification_sha256": "9" * 64,
                    "status": "RECOVERED"})
            return fulfill(route, body)
        if path == f"/projects/{PROJECT_ID}/target/connection/test":
            state["connection_attempts"] += 1
            if state["connection_attempts"] == 1:
                return fulfill(route, {"error": {"code": "TARGET_CONNECTION_FAILED", "message": "Synthetic connection failure."}}, 502)
            return fulfill(route, {"host": "192.0.2.20", "port": 443, "tested_at_utc": "2026-10-20T00:00:00Z",
                "tls_verification": "CA_VERIFIED", "identity": {"hostname": "target-fw", "serial": "TARGET1",
                    "model": "PA-5410", "panos_version": "11.1.4", "multi_vsys": False, "operational_mode": "normal"}})
        if path == f"/projects/{PROJECT_ID}/target/baseline/collect":
            state["baseline"] = True
            return fulfill(route, BASELINE)
        if path == f"/projects/{PROJECT_ID}/target/package/build":
            state["package"] = True
            return fulfill(route, PACKAGE)
        if path == f"/projects/{PROJECT_ID}/target/package/review":
            state["reviewed"] = True
            return fulfill(route, {**PACKAGE, "review_id": "review-1", "review_sha256": "e" * 64, "status": "REVIEWED"})
        if path == f"/projects/{PROJECT_ID}/target/preflight/check":
            return fulfill(route, {"target_serial": "TARGET1", "package_id": "package-1",
                "observed_at_utc": "2026-10-20T00:00:00Z", "status": "PASSED",
                "checks": {"identity_matches": "CLEAR", "baseline_unchanged": "CLEAR", "ha_clear": "CLEAR",
                    "panorama_clear": "CLEAR", "multi_vsys_clear": "CLEAR", "minimum_release": "CLEAR",
                    "capability_matrix": "CLEAR", "recovery_path": "CLEAR", "manual_review": "CLEAR"},
                "blockers": [], "deployment_allowed": True})
        if path == f"/projects/{PROJECT_ID}/target/stage":
            state["staged"] = True
            return fulfill(route, {"package_id": "package-1", "status": "VALIDATED",
                "running_backup_sha256": "1" * 64, "candidate_backup_sha256": "2" * 64,
                "loaded_candidate_sha256": "d" * 64, "change_summary_sha256": "3" * 64,
                "validation_sha256": "4" * 64, "validation_job_id": "42",
                "ambiguous_operation": None, "commit_created": False,
                "message": "Candidate staged and validated. No commit was created."})
        if path == f"/projects/{PROJECT_ID}/target/stage/reconcile":
            return fulfill(route, {"package_id": "package-1", "status": "STATUS_UNKNOWN",
                "running_backup_sha256": "1" * 64, "candidate_backup_sha256": "2" * 64,
                "loaded_candidate_sha256": "b" * 64, "change_summary_sha256": None,
                "validation_sha256": None, "validation_job_id": None,
                "ambiguous_operation": "IMPORT", "commit_created": False,
                "reconciliation": "STILL_AMBIGUOUS",
                "message": "The import may exist, but read-only checks cannot prove it. Do not retry automatically."})
        if path == f"/projects/{PROJECT_ID}/target/commit/approval":
            state["approved"] = True
            return fulfill(route, {"package_id": "package-1", "status": "AWAITING_COMMIT_APPROVAL",
                "target_serial": "TARGET1", "approval_token": "memory-only-approval-token-1234567890",
                "approval_expires_at_utc": "2026-10-27T10:10:00Z",
                "message": "One-time approval issued."})
        if path == f"/projects/{PROJECT_ID}/target/commit":
            state["committed"] = True
            return fulfill(route, {"package_id": "package-1", "status": "SUCCEEDED",
                "commit_job_id": "84", "commit_result_sha256": "5" * 64,
                "post_verification_sha256": "6" * 64, "ambiguous_operation": None,
                "message": "Commit job finished and active configuration matches."})
        if path == f"/projects/{PROJECT_ID}/target/commit/reconcile":
            return fulfill(route, {"package_id": "package-1", "status": "STATUS_UNKNOWN",
                "commit_job_id": None, "commit_result_sha256": None,
                "post_verification_sha256": None, "ambiguous_operation": "COMMIT",
                "reconciliation": "STILL_AMBIGUOUS",
                "message": "No retry was performed."})
        if path == f"/projects/{PROJECT_ID}/target/recovery":
            state["recovered"] = True
            return fulfill(route, {"package_id": "package-1", "status": "RECOVERED",
                "recovery_load_sha256": "7" * 64, "recovery_validation_sha256": "8" * 64,
                "recovery_commit_job_id": "88", "recovery_verification_sha256": "9" * 64,
                "ambiguous_operation": None, "message": "Backup validated and verified."})
        return fulfill(route, {"error": {"code": "UNEXPECTED_UAT_ROUTE", "message": path}}, 500)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page_errors = []
        console_errors = []
        expected_http_failures = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on("console", lambda message: console_errors.append(message.text)
            if message.type == "error" and not message.text.startswith("Failed to load resource") else None)
        page.on("response", lambda response: expected_http_failures.append(response.status)
            if response.status in {409, 502} else None)
        page.route("**/api/v1/**", api_route)
        page.add_init_script("""localStorage.setItem('confighop-project', JSON.stringify({
            project_id: 'uat-target-project', project_name: 'Target UAT', source_filename: null,
            target_profile_id: 'paloalto-pa-5410', mappings: []
        }))""")
        page.goto("http://127.0.0.1:5174/", wait_until="networkidle")
        page.get_by_label("Target vendor").select_option(label="Palo Alto Networks")
        page.get_by_role("button", name="Load Project", exact=True).click()
        panel = page.locator("section", has_text="Target Migration Review")
        panel.get_by_text("Loading target baseline and package state.", exact=True).wait_for()
        panel.get_by_text("No target baseline yet.", exact=False).wait_for()

        panel.get_by_label("Management IP").fill("192.0.2.20")
        panel.get_by_label("Port").fill("443")
        panel.get_by_label("XML API key").fill("request-only-key")
        panel.get_by_label("CA certificate PEM", exact=False).fill("test-ca")
        panel.get_by_role("button", name="Test Target Connection").click()
        panel.get_by_text("Synthetic connection failure.", exact=False).wait_for()
        panel.get_by_role("button", name="Test Target Connection").click()
        panel.locator(".target-identity").get_by_text("target-fw", exact=True).wait_for()
        panel.get_by_role("button", name="Collect Running Target Baseline").click()
        panel.get_by_text("AES_256_GCM_V1", exact=True).wait_for()
        assert panel.get_by_label("XML API key").input_value() == ""

        panel.get_by_role("button", name="Build Target Package").click()
        panel.get_by_text("TARGET_POLICY_ORDER_REVIEW_REQUIRED", exact=False).wait_for()
        approve = panel.get_by_role("button", name="Approve Reviewed Package")
        assert approve.is_disabled()
        panel.locator(".target-finding.warning input").check()
        hostname_confirmation = panel.get_by_label("Confirm target hostname")
        hostname_confirmation.fill("target-fw")
        assert approve.is_enabled()
        hostname_confirmation.focus()
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.textContent") == "Approve Reviewed Package"
        approve.click()
        panel.get_by_text("Manual review recorded", exact=True).wait_for()

        panel.get_by_label("Management IP").fill("192.0.2.20")
        panel.get_by_label("XML API key").fill("request-only-key-2")
        panel.get_by_role("button", name="Test Target Connection").click()
        panel.locator(".target-identity").get_by_text("target-fw", exact=True).wait_for()
        panel.get_by_text("I confirm tested out-of-band", exact=False).click()
        panel.get_by_role("button", name="Run Final Preflight").click()
        panel.get_by_text("All implemented offline gates are clear.", exact=False).wait_for()
        assert panel.get_by_label("XML API key").input_value() == ""

        panel.get_by_label("Management IP").fill("192.0.2.20")
        panel.get_by_label("XML API key").fill("request-only-key-3")
        panel.get_by_role("button", name="Test Target Connection").click()
        panel.locator(".target-identity").get_by_text("target-fw", exact=True).wait_for()
        panel.get_by_label("Type STAGE", exact=False).fill("STAGE target-fw")
        stage_button = panel.get_by_role("button", name="Stage and Validate Candidate")
        assert stage_button.is_enabled()
        stage_button.click()
        panel.get_by_text("Candidate validated, commit not created", exact=True).wait_for()
        panel.get_by_text("Staging complete", exact=True).wait_for()
        assert panel.get_by_label("XML API key").input_value() == ""

        approval_input = panel.get_by_label("Type APPROVE COMMIT", exact=False)
        approval_input.fill("APPROVE COMMIT target-fw")
        approval_input.focus()
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.textContent") == "Issue One-time Commit Approval"
        page.keyboard.press("Enter")
        panel.get_by_text("Approval ready", exact=True).wait_for()
        panel.get_by_label("Management IP").fill("192.0.2.20")
        panel.get_by_label("XML API key").fill("request-only-key-commit")
        panel.get_by_role("button", name="Test Target Connection").click()
        panel.locator(".target-identity").get_by_text("target-fw", exact=True).wait_for()
        commit_button = panel.get_by_role("button", name="Commit Validated Candidate")
        assert commit_button.is_enabled()
        commit_button.focus()
        page.keyboard.press("Enter")
        panel.get_by_text("Commit verified", exact=True).wait_for()
        assert panel.get_by_label("XML API key").input_value() == ""

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(100)
        overflow = panel.evaluate("element => element.scrollWidth - element.clientWidth")
        assert overflow <= 1
        assert expected_http_failures == [409, 409, 502]
        assert not page_errors, page_errors
        assert not console_errors, console_errors
        assert any(item["path"].endswith("/target/package/review") and item["body"]["confirmed_target_hostname"] == "target-fw" for item in request_bodies)
        assert any(item["path"].endswith("/target/preflight/check") and item["body"]["recovery_path_confirmed"] is True for item in request_bodies)
        assert any(item["path"].endswith("/target/stage") and item["body"]["confirmed_target_hostname"] == "target-fw" for item in request_bodies)
        assert "request-only-key" not in json.dumps(PACKAGE)

        state.update({"staged": False, "approved": False, "committed": False,
            "ambiguous": True, "commit_ambiguous": False, "recovered": False})
        ambiguous_page = context.new_page()
        ambiguous_page.on("pageerror", lambda error: page_errors.append(str(error)))
        ambiguous_page.on("console", lambda message: console_errors.append(message.text)
            if message.type == "error" and not message.text.startswith("Failed to load resource") else None)
        ambiguous_page.route("**/api/v1/**", api_route)
        ambiguous_page.add_init_script("""localStorage.setItem('confighop-project', JSON.stringify({
            project_id: 'uat-target-project', project_name: 'Target UAT', source_filename: null,
            target_profile_id: 'paloalto-pa-5410', mappings: []
        }))""")
        ambiguous_page.goto("http://127.0.0.1:5174/", wait_until="networkidle")
        ambiguous_page.get_by_label("Target vendor").select_option(label="Palo Alto Networks")
        ambiguous_page.get_by_role("button", name="Load Project", exact=True).click()
        ambiguous_panel = ambiguous_page.locator("section", has_text="Target Migration Review")
        ambiguous_panel.get_by_text("Device result is unknown", exact=True).wait_for()
        ambiguous_panel.get_by_label("Management IP").fill("192.0.2.20")
        ambiguous_panel.get_by_label("XML API key").fill("request-only-key-4")
        ambiguous_panel.get_by_role("button", name="Test Target Connection").click()
        ambiguous_panel.locator(".target-identity").get_by_text("target-fw", exact=True).wait_for()
        ambiguous_panel.get_by_role("button", name="Run Read-only Stage Reconciliation").click()
        ambiguous_panel.get_by_text("Still Ambiguous", exact=True).wait_for()
        assert ambiguous_panel.get_by_text("Do not retry automatically.", exact=False).is_visible()
        assert ambiguous_panel.get_by_label("XML API key").input_value() == ""
        assert sum(item["path"].endswith("/target/stage") for item in request_bodies) == 1
        assert sum(item["path"].endswith("/target/stage/reconcile") for item in request_bodies) == 1
        ambiguous_page.close()

        state.update({"ambiguous": False, "commit_ambiguous": True, "recovered": False})
        recovery_page = context.new_page()
        recovery_page.on("pageerror", lambda error: page_errors.append(str(error)))
        recovery_page.on("console", lambda message: console_errors.append(message.text)
            if message.type == "error" and not message.text.startswith("Failed to load resource") else None)
        recovery_page.route("**/api/v1/**", api_route)
        recovery_page.add_init_script("""localStorage.setItem('confighop-project', JSON.stringify({
            project_id: 'uat-target-project', project_name: 'Target UAT', source_filename: null,
            target_profile_id: 'paloalto-pa-5410', mappings: []
        }))""")
        recovery_page.goto("http://127.0.0.1:5174/", wait_until="networkidle")
        recovery_page.get_by_label("Target vendor").select_option(label="Palo Alto Networks")
        recovery_page.get_by_role("button", name="Load Project", exact=True).click()
        recovery_panel = recovery_page.locator("section", has_text="Target Migration Review")
        recovery_panel.get_by_text("Commit result is unknown", exact=True).wait_for()
        recovery_panel.get_by_label("Management IP").fill("192.0.2.20")
        recovery_panel.get_by_label("XML API key").fill("request-only-key-recovery")
        recovery_panel.get_by_role("button", name="Test Target Connection").click()
        recovery_panel.locator(".target-identity").get_by_text("target-fw", exact=True).wait_for()
        recovery_panel.get_by_role("button", name="Run Read-only Commit Reconciliation").click()
        recovery_panel.get_by_text("Still Ambiguous", exact=True).wait_for()
        recovery_panel.get_by_label("Management IP").fill("192.0.2.20")
        recovery_panel.get_by_label("XML API key").fill("request-only-key-recovery-2")
        recovery_panel.get_by_role("button", name="Test Target Connection").click()
        recovery_input = recovery_panel.get_by_label("Type RECOVER", exact=False)
        recovery_input.fill("RECOVER target-fw")
        recovery_input.focus()
        recovery_page.keyboard.press("Tab")
        assert recovery_page.evaluate("document.activeElement.textContent") == "Run Validated Recovery"
        recovery_page.keyboard.press("Enter")
        recovery_panel.get_by_text("Recovery verified", exact=True).wait_for()
        assert recovery_panel.get_by_label("XML API key").input_value() == ""
        recovery_page.close()
        print(json.dumps({"target_ui_flow": "passed", "empty_loading_error_success": True,
            "keyboard_focus": True, "mobile_overflow_px": overflow, "page_errors": page_errors,
            "console_errors": console_errors, "expected_http_failures": expected_http_failures,
            "stage_validate": True, "ambiguous_reconcile": True, "blind_retry": False,
            "commit_verified": True, "recovery_verified": True,
            "api_requests": len(request_bodies)}))
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
