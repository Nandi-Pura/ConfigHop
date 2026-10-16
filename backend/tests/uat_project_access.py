"""Browser verification against isolated localhost Vite and FastAPI processes."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        owner = browser.new_context(accept_downloads=True)
        page = owner.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:5174/", wait_until="networkidle")
        page.get_by_label("Target vendor").select_option(label="Palo Alto Networks")
        page.locator('input[type="file"]').set_input_files(
            str(Path(__file__).parent / "fixtures/paloalto/pa_complex_synthetic.xml"))
        page.get_by_text("Raw XML hidden", exact=True).wait_for()
        page.get_by_role("button", name="Save Project", exact=True).click()
        project_id = page.evaluate("JSON.parse(localStorage.getItem('confighop-project')).project_id")
        assert "confighop_session" not in page.evaluate("document.cookie")
        cookies = owner.cookies("http://127.0.0.1:8011/api/v1")
        session = next(cookie for cookie in cookies if cookie["name"] == "confighop_session")
        assert session["httpOnly"] and session["sameSite"] == "Strict"

        page.get_by_role("button", name="Reveal source XML").click()
        page.get_by_text("Raw source XML visible", exact=True).wait_for()
        page.get_by_role("button", name="Hide XML", exact=True).click()
        page.get_by_text("Raw XML hidden", exact=True).wait_for()
        with page.expect_download() as downloaded:
            page.get_by_role("button", name="Download source XML", exact=True).click()
        assert downloaded.value.failure() is None
        audit = page.evaluate("""async project => {
            const response = await fetch(`http://127.0.0.1:8011/api/v1/projects/${project}/audit`, {credentials:'include'});
            return {status: response.status, body: await response.json()};
        }""", project_id)
        assert audit["status"] == 200
        assert sum(event["outcome"] == "ACCESS_GRANTED" for event in audit["body"]["events"]) == 2

        other = browser.new_context()
        other_page = other.new_page()
        other_page.goto("http://127.0.0.1:5174/", wait_until="networkidle")
        denied = other_page.evaluate("""async project => {
            const response = await fetch(`http://127.0.0.1:8011/api/v1/projects/${project}/source`, {credentials:'include'});
            return {status: response.status, body: await response.json()};
        }""", project_id)
        assert denied["status"] == 403
        assert denied["body"]["error"]["code"] == "PROJECT_ACCESS_DENIED"
        page.get_by_role("button", name="Load Project", exact=True).click()
        page.get_by_text("Project session restored; raw XML hidden.", exact=False).wait_for()
        assert not errors
        print(json.dumps({"real_local_backend": True, "upload_reveal_hide_download_restore": "passed",
            "http_only_cookie": True, "other_browser_context": 403,
            "artifact_access_events": 2, "javascript_errors": errors}))
        other.close()
        owner.close()
        browser.close()


if __name__ == "__main__":
    main()
