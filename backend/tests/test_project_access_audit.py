import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from confighop_api.access_audit import AuditStore, ProjectAccess, SESSION_COOKIE
from confighop_api.main import create_app
from confighop_api.services import ProjectStore


HEADERS = {"X-ConfigHop-Client": "web"}
FIXTURE = Path(__file__).parent / "fixtures/paloalto/pa_complex_synthetic.xml"


def create_project(client):
    response = client.post("/api/v1/projects", headers=HEADERS)
    assert response.status_code == 200
    return response.json()["project_id"]


def test_project_cookie_is_required_for_all_project_routes(tmp_path):
    app = create_app(ProjectStore(), audit_path=tmp_path / "audit.sqlite3")
    with TestClient(app) as owner:
        project_id = create_project(owner)
        cookie = owner.cookies.get(SESSION_COOKIE)
        base = f"/api/v1/projects/{project_id}"
        assert owner.put(base + "/source", content=FIXTURE.read_bytes(), headers=HEADERS).status_code == 200
        assert owner.get(base + "/source").content == FIXTURE.read_bytes()
        owner.cookies.clear()
        for method, path in [("GET", ""), ("GET", "/source"), ("GET", "/audit"),
            ("GET", "/inventory"), ("GET", "/candidate/download"),
            ("DELETE", ""), ("POST", "/source/collect"), ("PUT", "/source")]:
            response = owner.request(method, base + path, headers=HEADERS)
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "PROJECT_ACCESS_DENIED"
            assert b"<config" not in response.content
        owner.cookies.set(SESSION_COOKIE, cookie)
        assert owner.get(base + "/source").content == FIXTURE.read_bytes()
        events = owner.get(base + "/audit").json()["events"]
        assert any(event["outcome"] == "DENIED" for event in events)
        assert any(event["outcome"] == "ACCESS_GRANTED" and event["source_sha256"] for event in events)
        assert cookie not in json.dumps(events)


def test_second_session_cannot_read_another_projects_artifact(tmp_path):
    with TestClient(create_app(ProjectStore(), audit_path=tmp_path / "audit.sqlite3")) as client:
        first = create_project(client)
        client.cookies.clear()
        second = create_project(client)
        assert client.get(f"/api/v1/projects/{first}/source").status_code == 403
        assert client.get(f"/api/v1/projects/{second}").status_code == 200
        third = create_project(client)
        assert client.get(f"/api/v1/projects/{second}").status_code == 200
        assert client.get(f"/api/v1/projects/{third}").status_code == 200


def test_session_expires_and_cookie_has_browser_protections(monkeypatch, tmp_path):
    with TestClient(create_app(ProjectStore(), audit_path=tmp_path / "audit.sqlite3")) as client:
        response = client.post("/api/v1/projects", headers=HEADERS)
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api/v1" in cookie
        project_id = response.json()["project_id"]
        monkeypatch.setattr("confighop_api.access_audit.time.monotonic", lambda: float("inf"))
        assert client.get(f"/api/v1/projects/{project_id}").status_code == 403


def test_audit_survives_reopen_and_contains_no_credentials(tmp_path):
    path = tmp_path / "audit.sqlite3"
    with TestClient(create_app(ProjectStore(), audit_path=path)) as client:
        project_id = create_project(client)
        base = f"/api/v1/projects/{project_id}"
        for action in ("connection/test", "collect"):
            response = client.post(base + "/source/" + action, json={
                "host": "10.0.0.10", "port": 443, "api_key": "unique-api-secret",
                "ca_certificate_pem": "unique-ca-secret"}, headers=HEADERS)
            assert response.status_code == 403
        events = client.get(base + "/audit").json()["events"]
        assert [event["outcome"] for event in events] == ["STARTED", "FAILED", "STARTED", "FAILED"]
        assert events[0]["operation_id"] == events[1]["operation_id"]
        assert events[1]["error_code"] == "XML_API_ENDPOINT_NOT_ALLOWED"
        page = client.get(base + "/audit", params={"after": events[1]["sequence"], "limit": 1}).json()["events"]
        assert page == [events[2]]
    audit = AuditStore(path)
    try:
        assert audit.events(project_id) == events
        serialized = json.dumps(events)
        assert all(secret not in serialized for secret in ("unique-api-secret", "unique-ca-secret", "<config"))
    finally:
        audit.close()


def test_artifact_access_is_fail_closed_when_audit_write_fails(monkeypatch, tmp_path):
    with TestClient(create_app(ProjectStore(), audit_path=tmp_path / "audit.sqlite3")) as client:
        project_id = create_project(client)
        base = f"/api/v1/projects/{project_id}"
        assert client.put(base + "/source", content=FIXTURE.read_bytes(), headers=HEADERS).status_code == 200

        def unavailable(*args, **kwargs):
            raise sqlite3.OperationalError("private filesystem path")

        monkeypatch.setattr(AuditStore, "record", unavailable)
        response = client.get(base + "/source")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AUDIT_UNAVAILABLE"
        assert "private filesystem" not in response.text
        assert b"<config" not in response.content
        assert client.post(base + "/source/collect", json={}, headers=HEADERS).status_code == 503


def test_credentialed_cors_and_untrusted_origin(tmp_path):
    with TestClient(create_app(ProjectStore(), audit_path=tmp_path / "audit.sqlite3")) as client:
        project_id = create_project(client)
        base = f"/api/v1/projects/{project_id}"
        trusted = {"Origin": "http://127.0.0.1:5173"}
        response = client.get(base, headers=trusted)
        assert response.headers["access-control-allow-origin"] == trusted["Origin"]
        assert response.headers["access-control-allow-credentials"] == "true"
        client.cookies.clear()
        denied = client.get(base, headers=trusted)
        assert denied.status_code == 403
        assert denied.headers["access-control-allow-origin"] == trusted["Origin"]
        assert client.post("/api/v1/projects", headers={**HEADERS, "Origin": "http://evil.invalid"}).status_code == 403
        assert client.get(base, headers={"Origin": "http://evil.invalid"}).status_code == 403


def test_access_control_stores_only_session_digest():
    access = ProjectAccess()
    token = access.create_owner("project", None)
    assert access.allows("project", token)
    assert not access.allows("project", "incorrect")
    assert token not in repr(vars(access))


def test_artifact_bytes_are_withheld_if_terminal_audit_write_fails(monkeypatch, tmp_path):
    with TestClient(create_app(ProjectStore(), audit_path=tmp_path / "audit.sqlite3")) as client:
        project_id = create_project(client)
        base = f"/api/v1/projects/{project_id}"
        assert client.put(base + "/source", content=FIXTURE.read_bytes(), headers=HEADERS).status_code == 200
        original_record = AuditStore.record

        def fail_terminal(self, **kwargs):
            if kwargs["outcome"] == "ACCESS_GRANTED":
                raise sqlite3.OperationalError("disk unavailable")
            return original_record(self, **kwargs)

        monkeypatch.setattr(AuditStore, "record", fail_terminal)
        response = client.get(base + "/source")
        assert response.status_code == 503
        assert b"<config" not in response.content


def test_https_session_cookie_is_secure(tmp_path):
    with TestClient(create_app(ProjectStore(), audit_path=tmp_path / "audit.sqlite3"),
        base_url="https://testserver") as client:
        response = client.post("/api/v1/projects", headers=HEADERS)
        assert "secure" in response.headers["set-cookie"].lower()
