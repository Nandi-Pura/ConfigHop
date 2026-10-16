import hashlib
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from confighop_api.access_audit import SESSION_COOKIE
from confighop_api.main import create_app
from confighop_api.services import ProjectStore


FIXTURE = Path(__file__).parent / "fixtures/paloalto/pa_complex_synthetic.xml"
SOURCE = ("10.0.0.10", 443)
TARGET = ("10.0.0.20", 443)
HEADERS = {"X-ConfigHop-Client": "web"}


def system_info(serial: str, model: str = "PA-5410", version: str = "11.1.2") -> bytes:
    return (f'<response status="success"><result><system><hostname>fw-{serial}</hostname>'
        f'<serial>{serial}</serial><model>{model}</model><sw-version>{version}</sw-version>'
        '</system></result></response>').encode()


def active_config(marker: str = "one") -> bytes:
    return (f'<response status="success"><result><config><devices><entry name="localhost.localdomain">'
        f'<deviceconfig><system><hostname>{marker}</hostname></system></deviceconfig>'
        '</entry></devices></config></result></response>').encode()


def mocked_client(responses: list[bytes], expected_actions: list[tuple[str, str | None]]) -> httpx.AsyncClient:
    documents = iter(responses)
    actions = iter(expected_actions)

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-PAN-KEY"] == "secret-key"
        assert request.url.scheme == "https"
        form = parse_qs(request.content.decode())
        assert (form["type"][0], form.get("action", [None])[0]) == next(actions)
        if form["type"][0] == "config":
            assert form["xpath"] == ["/config"]
        return httpx.Response(200, content=next(documents))

    return httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://10.0.0.20")


def source_client() -> httpx.AsyncClient:
    return mocked_client([system_info("source-serial"), FIXTURE.read_bytes(),
        FIXTURE.read_bytes(), system_info("source-serial")],
        [("op", None), ("export", None), ("export", None), ("op", None)])


def target_client(*, first: bytes | None = None, second: bytes | None = None,
    serial: str = "target-serial", model: str = "PA-5410", version: str = "11.1.2") -> httpx.AsyncClient:
    return mocked_client([system_info(serial, model, version), first or active_config(),
        second or active_config(), system_info(serial, model, version)],
        [("op", None), ("config", "show"), ("config", "show"), ("op", None)])


def probe_result(inner: str = "") -> bytes:
    return f'<response status="success"><result>{inner}</result></response>'.encode()


def preflight_client(*, candidate: bytes | None = None, summary: bytes | None = None,
    locks: bytes | None = None, jobs: bytes | None = None, running: bytes | None = None,
    running_again: bytes | None = None, serial: str = "target-serial") -> httpx.AsyncClient:
    documents = iter([system_info(serial), running or active_config(), candidate or active_config(),
        summary or probe_result(), locks or probe_result(), jobs or probe_result(),
        running_again or running or active_config(), system_info(serial)])
    expected = iter([
        ("op", None, "<show><system><info></info></system></show>"),
        ("config", "show", None), ("config", "get", None),
        ("op", None, "<show><config><list><change-summary/></list></config></show>"),
        ("op", None, "<show><commit-locks/></show>"),
        ("op", None, "<show><jobs><pending/></jobs></show>"),
        ("config", "show", None), ("op", None, "<show><system><info></info></system></show>"),
    ])

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-PAN-KEY"] == "secret-key"
        form = parse_qs(request.content.decode())
        assert (form["type"][0], form.get("action", [None])[0],
            form.get("cmd", [None])[0]) == next(expected)
        assert form["type"][0] in {"config", "op"}
        return httpx.Response(200, content=next(documents))

    return httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://10.0.0.20")


def prepare_project(client: TestClient) -> tuple[str, str]:
    project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
    base = f"/api/v1/projects/{project_id}"
    assert client.post(base + "/source/collect", json={"host": SOURCE[0], "port": 443,
        "api_key": "secret-key"}, headers=HEADERS).status_code == 200
    assert client.put(base + "/target-profile", json={"profile_id": "paloalto-pa-5410",
        "panos_train": "11.1"}, headers=HEADERS).status_code == 200
    return project_id, base


def target_body(*, serial: str = "target-serial", model: str = "PA-5410") -> dict:
    return {"host": TARGET[0], "port": 443, "api_key": "secret-key",
        "expected_serial": serial, "expected_model": model}


def test_collect_target_baseline_binds_read_only_hash_and_audit(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs: target_client())
    root = tmp_path / "projects"
    with TestClient(create_app(ProjectStore(root), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        project_id, base = prepare_project(client)
        response = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS)
        assert response.status_code == 200
        baseline = response.json()
        assert baseline["serial"] == "target-serial"
        assert baseline["model"] == "PA-5410"
        assert baseline["sha256"] == hashlib.sha256(
            b'<config><devices><entry name="localhost.localdomain"><deviceconfig><system>'
            b'<hostname>one</hostname></system></deviceconfig></entry></devices></config>').hexdigest()
        assert client.get(base + "/target/baseline").json() == baseline
        assert "secret-key" not in str(client.get(base + "/deployment-events").json())
        audit = client.get(base + "/audit").json()["events"]
        assert [event["outcome"] for event in audit if event["action"] == "TARGET_BASELINE_COLLECT"] == [
            "STARTED", "SUCCEEDED"]
        assert "secret-key" not in str(audit)
        assert client.get(base).json()["active_package_id"] is None
        owner_cookie = client.cookies.get(SESSION_COOKIE)
    with TestClient(create_app(ProjectStore(root), allowed_target_endpoints={TARGET},
        audit_path=tmp_path / "audit.sqlite3")) as client:
        assert client.get(base + "/target/baseline").status_code == 403
        client.cookies.set(SESSION_COOKIE, owner_cookie)
        assert client.get(base + "/target/baseline").json() == baseline


@pytest.mark.parametrize("expected_serial,device_serial,expected_model,device_model,code", [
    ("source-serial", "target-serial", "PA-5410", "PA-5410", "SOURCE_TARGET_SAME_SERIAL"),
    ("other-serial", "target-serial", "PA-5410", "PA-5410", "TARGET_SERIAL_MISMATCH"),
    ("target-serial", "target-serial", "PA-3410", "PA-5410", "TARGET_MODEL_MISMATCH"),
    ("target-serial", "target-serial", "PA-5410", "PA-3410", "TARGET_MODEL_MISMATCH"),
])
def test_target_identity_mismatch_does_not_bind(monkeypatch, tmp_path,
    expected_serial, device_serial, expected_model, device_model, code):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs:
        target_client(serial=device_serial, model=device_model))
    with TestClient(create_app(ProjectStore(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        response = client.post(base + "/target/baseline/collect", json=target_body(
            serial=expected_serial, model=expected_model), headers=HEADERS)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == code
        assert client.get(base + "/target/baseline").status_code == 409


def test_target_config_drift_does_not_replace_previous_baseline(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    target_clients = iter([target_client(), target_client(second=active_config("two"))])
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs:
        next(target_clients))
    with TestClient(create_app(ProjectStore(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        first = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS).json()
        failed = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS)
        assert failed.status_code == 409
        assert failed.json()["error"]["code"] == "TARGET_CONFIG_CHANGED"
        assert client.get(base + "/target/baseline").json() == first


def test_target_endpoint_requires_separate_allowlist(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    with TestClient(create_app(ProjectStore(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints=set(), audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        response = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "XML_API_ENDPOINT_NOT_ALLOWED"
        assert client.get(base + "/target/baseline").status_code == 409


def test_target_baseline_requires_source_serial(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs: target_client())
    with TestClient(create_app(ProjectStore(tmp_path / "projects"), allowed_target_endpoints={TARGET},
        audit_path=tmp_path / "audit.sqlite3")) as client:
        project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        base = f"/api/v1/projects/{project_id}"
        assert client.put(base + "/source", content=FIXTURE.read_bytes(), headers={**HEADERS,
            "Content-Type": "application/xml"}).status_code == 200
        assert client.put(base + "/target-profile", json={"profile_id": "paloalto-pa-5410",
            "panos_train": "11.1"}, headers=HEADERS).status_code == 200
        response = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SOURCE_SERIAL_UNVERIFIED"


def test_target_panos_train_mismatch_does_not_bind(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs:
        target_client(version="10.2.8"))
    with TestClient(create_app(ProjectStore(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        response = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "TARGET_PANOS_TRAIN_MISMATCH"
        assert client.get(base + "/target/baseline").status_code == 409


def test_read_only_preflight_reports_incomplete_without_authorizing_deployment(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    target_clients = iter([target_client(), preflight_client()])
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs:
        next(target_clients))
    with TestClient(create_app(ProjectStore(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        assert client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS).status_code == 200
        response = client.post(base + "/target/preflight/check", json=target_body(), headers=HEADERS)
        assert response.status_code == 200
        report = response.json()
        assert report["status"] == "INCOMPLETE"
        assert report["deployment_allowed"] is False
        assert report["checks"]["candidate_matches_running"] == "CLEAR"
        assert report["checks"]["pending_jobs_empty"] == "CLEAR"
        assert report["checks"]["ha_state"] == "NOT_CHECKED"
        assert client.get(base).json()["active_package_id"] is None
        audit = client.get(base + "/audit").json()["events"]
        assert [event["outcome"] for event in audit if event["action"] == "TARGET_PREFLIGHT_CHECK"] == [
            "STARTED", "COMPLETED"]
        assert "secret-key" not in str(report) + str(audit)


@pytest.mark.parametrize("override,check", [
    ({"candidate": active_config("other")}, "candidate_matches_running"),
    ({"summary": probe_result("<entry/>")}, "change_summary_empty"),
    ({"locks": probe_result("<entry/>")}, "commit_locks_empty"),
    ({"jobs": probe_result("<job><status>ACT</status></job>")}, "pending_jobs_empty"),
    ({"running": active_config("changed")}, "baseline_unchanged"),
])
def test_preflight_blocks_unsafe_target_state(monkeypatch, tmp_path, override, check):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    target_clients = iter([target_client(), preflight_client(**override)])
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs:
        next(target_clients))
    with TestClient(create_app(ProjectStore(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        assert client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS).status_code == 200
        response = client.post(base + "/target/preflight/check", json=target_body(), headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["status"] == "BLOCKED"
        assert response.json()["checks"][check] == "BLOCKED"
        assert response.json()["deployment_allowed"] is False


def test_preflight_rejects_unrecognized_probe_response(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    target_clients = iter([target_client(), preflight_client(locks=b'<response status="success"/>')])
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs:
        next(target_clients))
    with TestClient(create_app(ProjectStore(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        assert client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS).status_code == 200
        response = client.post(base + "/target/preflight/check", json=target_body(), headers=HEADERS)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "XML_API_INVALID_PREFLIGHT"


def test_preflight_rejects_candidate_api_error(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    target_clients = iter([target_client(), preflight_client(candidate=b'<response status="error"/>')])
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs:
        next(target_clients))
    with TestClient(create_app(ProjectStore(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        assert client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS).status_code == 200
        response = client.post(base + "/target/preflight/check", json=target_body(), headers=HEADERS)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "XML_API_CANDIDATE_CONFIG_FAILED"


def test_preflight_baseline_drift_detaches_current_draft(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    target_clients = iter([target_client(), preflight_client(running=active_config("changed"))])
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs:
        next(target_clients))
    with TestClient(create_app(ProjectStore(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        project_id, base = prepare_project(client)
        assert client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS).status_code == 200
        assert client.put(base + "/source-profile", json={"profile_id": "paloalto-pa-5220",
            "panos_train": "11.1"}, headers=HEADERS).status_code == 200
        candidate_response = client.post(base + "/candidate", json={"mappings": [
            {"source_interface": "ethernet1/12", "target_interface": "ethernet1/8"}],
            "allow_review": True}, headers=HEADERS)
        assert candidate_response.status_code == 200
        assert candidate_response.json()["candidate_available"] is True
        package_id = client.get(base).json()["active_package_id"]
        assert package_id is not None
        response = client.post(base + "/target/preflight/check", json=target_body(), headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["checks"]["baseline_unchanged"] == "BLOCKED"
        assert client.get(base).json()["active_package_id"] is None
        assert client.app.state.store.database.package(package_id).status == "INVALIDATED"
        assert client.get(base).json()["candidate_available"] is True
        assert any(event["reason"] == "TARGET_BASELINE_DRIFT" for event in
            client.get(base + "/deployment-events").json())
