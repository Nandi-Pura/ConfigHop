import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs
from xml.etree import ElementTree

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
ARTIFACT_KEY = b"target-baseline-test-key-32byte!"


def target_store(path: Path) -> ProjectStore:
    return ProjectStore(path, artifact_key=ARTIFACT_KEY)


def system_info(serial: str, model: str = "PA-5410", version: str = "11.1.2") -> bytes:
    return (f'<response status="success"><result><system><hostname>fw-{serial}</hostname>'
        f'<serial>{serial}</serial><model>{model}</model><sw-version>{version}</sw-version>'
        '<multi-vsys>off</multi-vsys><operational-mode>normal</operational-mode>'
        '</system></result></response>').encode()


def active_config(marker: str = "one") -> bytes:
    return (f'<response status="success"><result><config><devices><entry name="localhost.localdomain">'
        f'<deviceconfig><system><hostname>{marker}</hostname></system></deviceconfig>'
        '<vsys><entry name="vsys1"/></vsys></entry></devices></config></result></response>').encode()


def package_target_config() -> bytes:
    return (b'<response status="success"><result><config version="11.1.0">'
        b'<mgt-config><users><entry name="target-admin"/></users></mgt-config>'
        b'<devices><entry name="localhost.localdomain"><deviceconfig><system>'
        b'<hostname>fw-target-serial</hostname></system><high-availability><enabled>no</enabled>'
        b'</high-availability></deviceconfig><network><profiles><interface-management-profile>'
        b'<entry name="example-mgmt"/></interface-management-profile></profiles></network>'
        b'<vsys><entry name="vsys1"/></vsys></entry></devices></config></result></response>')


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


def single_vsys_source_client() -> httpx.AsyncClient:
    root = ElementTree.fromstring(FIXTURE.read_bytes())
    vsys = root.find("./devices/entry/vsys")
    second = vsys.find("./entry[@name='vsys2']")
    vsys.remove(second)
    document = ElementTree.tostring(root, encoding="utf-8")
    return mocked_client([system_info("source-serial"), document, document,
        system_info("source-serial")],
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


def prepare_passed_target_package(client: TestClient, base: str) -> dict:
    assert client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS).status_code == 200
    assert client.put(base + "/source-profile", json={"profile_id": "paloalto-pa-5220",
        "panos_train": "11.1"}, headers=HEADERS).status_code == 200
    candidate = client.post(base + "/candidate", json={"mappings": [
        {"source_interface": "ethernet1/12", "target_interface": "ethernet1/8"}],
        "allow_review": True}, headers=HEADERS)
    assert candidate.status_code == 200 and candidate.json()["candidate_available"] is True
    built_response = client.post(base + "/target/package/build", headers=HEADERS)
    assert built_response.status_code == 200, built_response.text
    built = built_response.json()
    accepted = sorted({item["code"] for item in built["target_findings"]
        if item["requires_acceptance"]})
    reviewed = client.post(base + "/target/package/review", json={
        "confirmed_target_hostname": "fw-target-serial",
        "accepted_finding_codes": accepted}, headers=HEADERS)
    assert reviewed.status_code == 200, reviewed.text
    preflight = client.post(base + "/target/preflight/check", json={
        **target_body(), "recovery_path_confirmed": True}, headers=HEADERS)
    assert preflight.status_code == 200 and preflight.json()["status"] == "PASSED"
    return built


def stage_client(deployable: bytes, *, baseline: bytes = b"", import_timeout: bool = False) -> httpx.AsyncClient:
    count = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        assert request.headers["X-PAN-KEY"] == "secret-key"
        if count == 1:
            return httpx.Response(200, content=system_info("target-serial"))
        if count in {2, 3}:
            return httpx.Response(200, content=baseline or active_config())
        if count == 4:
            assert "multipart/form-data" in request.headers["content-type"]
            assert deployable in request.content
            if import_timeout:
                raise httpx.ReadTimeout("private timeout", request=request)
            return httpx.Response(200, content=(
                b'<response status="success"><result><msg><line>Imported</line></msg></result></response>'))
        form = parse_qs(request.content.decode())
        if count == 5:
            assert form["cmd"][0].startswith("<load><config><from>confighop-")
            return httpx.Response(200, content=(
                b'<response status="success"><result><msg><line>Loaded</line></msg></result></response>'))
        if count == 6:
            assert form["action"] == ["get"]
            return httpx.Response(200, content=(b'<response status="success"><result>' +
                deployable + b'</result></response>'))
        if count == 7:
            assert form["cmd"] == ["<show><config><list><change-summary/></list></config></show>"]
            return httpx.Response(200, content=(
                b'<response status="success"><result><change-summary><entry name="vsys1"/>'
                b'</change-summary></result></response>'))
        if count == 8:
            assert form["cmd"] == ["<validate><full></full></validate>"]
            return httpx.Response(200, content=(
                b'<response status="success"><result><job>42</job></result></response>'))
        assert form["cmd"] == ["<show><jobs><id>42</id></jobs></show>"]
        state = b'<status>FIN</status><result>OK</result>'
        return httpx.Response(200, content=(b'<response status="success"><result><job><id>42</id>' +
            state + b'</job></result></response>'))

    return httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://10.0.0.20")


def reconcile_client(*, running: bytes, candidate: bytes,
    summary: bytes = b'<response status="success"><result/></response>') -> httpx.AsyncClient:
    documents = iter([system_info("target-serial"), running, candidate, summary])
    expected = iter([("op", None), ("config", "show"), ("config", "get"), ("op", None)])

    def respond(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        assert (form["type"][0], form.get("action", [None])[0]) == next(expected)
        return httpx.Response(200, content=next(documents))

    return httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://10.0.0.20")


def config_response(config: bytes) -> bytes:
    return b'<response status="success"><result>' + config + b'</result></response>'


def config_document(value: bytes) -> bytes:
    root = ElementTree.fromstring(value)
    config = root.find("./result/config") if root.tag == "response" else root
    return ElementTree.tostring(config, encoding="utf-8")


def commit_client(*, baseline: bytes, deployable: bytes, job_failed: bool = False,
    commit_timeout: bool = False) -> httpx.AsyncClient:
    baseline = config_document(baseline)
    count = 0
    changed = (b'<response status="success"><result><change-summary>'
        b'<entry name="vsys1"/></change-summary></result></response>')

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        if count == 1:
            return httpx.Response(200, content=system_info("target-serial"))
        if count == 2:
            return httpx.Response(200, content=config_response(baseline))
        if count == 3:
            return httpx.Response(200, content=config_response(deployable))
        if count == 4:
            return httpx.Response(200, content=changed)
        if count == 5:
            if commit_timeout:
                raise httpx.ReadTimeout("private timeout", request=request)
            form = parse_qs(request.content.decode())
            assert form == {"type": ["commit"], "cmd": ["<commit></commit>"]}
            return httpx.Response(200, content=(
                b'<response status="success"><result><job>84</job></result></response>'))
        if count == 6:
            outcome = b"FAIL" if job_failed else b"OK"
            return httpx.Response(200, content=(b'<response status="success"><result><job>'
                b'<id>84</id><status>FIN</status><result>' + outcome +
                b'</result></job></result></response>'))
        if count == 7:
            return httpx.Response(200, content=system_info("target-serial"))
        if count in {8, 9}:
            return httpx.Response(200, content=config_response(deployable))
        return httpx.Response(200, content=probe_result())

    return httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://10.0.0.20")


def recovery_client(*, backup: bytes, deployed: bytes) -> httpx.AsyncClient:
    backup = config_document(backup)
    count = 0
    changed = (b'<response status="success"><result><change-summary>'
        b'<entry name="vsys1"/></change-summary></result></response>')

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        if count in {1, 16}:
            return httpx.Response(200, content=system_info("target-serial"))
        if count == 2:
            assert "multipart/form-data" in request.headers["content-type"]
            assert backup in request.content
            return httpx.Response(200, content=(
                b'<response status="success"><result><msg>Imported</msg></result></response>'))
        form = parse_qs(request.content.decode())
        if count == 3:
            assert form["cmd"][0].startswith("<load><config><from>confighop-")
            return httpx.Response(200, content=(
                b'<response status="success"><result><msg>Loaded</msg></result></response>'))
        if count == 4:
            return httpx.Response(200, content=config_response(backup))
        if count == 5:
            return httpx.Response(200, content=changed)
        if count == 6:
            return httpx.Response(200, content=(
                b'<response status="success"><result><job>77</job></result></response>'))
        if count == 7:
            return httpx.Response(200, content=(b'<response status="success"><result><job>'
                b'<id>77</id><status>FIN</status><result>OK</result></job></result></response>'))
        if count == 8:
            return httpx.Response(200, content=config_response(deployed))
        if count == 9:
            return httpx.Response(200, content=config_response(backup))
        if count == 10:
            return httpx.Response(200, content=changed)
        if count == 11:
            return httpx.Response(200, content=(
                b'<response status="success"><result><job>88</job></result></response>'))
        if count == 12:
            return httpx.Response(200, content=(b'<response status="success"><result><job>'
                b'<id>88</id><status>FIN</status><result>OK</result></job></result></response>'))
        if count in {13, 14}:
            return httpx.Response(200, content=config_response(backup))
        return httpx.Response(200, content=probe_result())

    return httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://10.0.0.20")


def recovery_no_commit_client(*, backup: bytes) -> httpx.AsyncClient:
    backup = config_document(backup)
    count = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        if count in {1, 11}:
            return httpx.Response(200, content=system_info("target-serial"))
        if count == 2:
            return httpx.Response(200, content=(
                b'<response status="success"><result><msg>Imported</msg></result></response>'))
        if count == 3:
            return httpx.Response(200, content=(
                b'<response status="success"><result><msg>Loaded</msg></result></response>'))
        if count in {4, 8, 9}:
            return httpx.Response(200, content=config_response(backup))
        if count in {5, 10}:
            return httpx.Response(200, content=probe_result())
        if count == 6:
            return httpx.Response(200, content=(
                b'<response status="success"><result><job>77</job></result></response>'))
        return httpx.Response(200, content=(b'<response status="success"><result><job>'
            b'<id>77</id><status>FIN</status><result>OK</result></job></result></response>'))

    return httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://10.0.0.20")


def prepare_validated_package(client: TestClient, store: ProjectStore, project_id: str,
    base: str, target_clients: list[httpx.AsyncClient], target_config: bytes) -> tuple[dict, bytes]:
    built = prepare_passed_target_package(client, base)
    deployable = store.artifacts.read_deployable(project_id, built["package_id"],
        built["deployable_candidate_sha256"], max_plaintext_bytes=store.max_source_bytes)
    target_clients.append(stage_client(deployable, baseline=target_config))
    staged = client.post(base + "/target/stage", json={**target_body(),
        "confirmed_target_hostname": "fw-target-serial"}, headers=HEADERS)
    assert staged.status_code == 200 and staged.json()["status"] == "VALIDATED"
    return built, deployable


def test_collect_target_baseline_binds_read_only_hash_and_audit(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs: target_client())
    root = tmp_path / "projects"
    with TestClient(create_app(target_store(root), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        project_id, base = prepare_project(client)
        response = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS)
        assert response.status_code == 200
        baseline = response.json()
        assert baseline["serial"] == "target-serial"
        assert baseline["model"] == "PA-5410"
        assert baseline["artifact_format"] == "AES_256_GCM_V1"
        assert baseline["artifact_size_bytes"] > 0
        assert baseline["sha256"] == hashlib.sha256(
            b'<config><devices><entry name="localhost.localdomain"><deviceconfig><system>'
            b'<hostname>one</hostname></system></deviceconfig><vsys><entry name="vsys1" />'
            b'</vsys></entry></devices></config>').hexdigest()
        assert client.get(base + "/target/baseline").json() == baseline
        assert "secret-key" not in str(client.get(base + "/deployment-events").json())
        audit = client.get(base + "/audit").json()["events"]
        assert [event["outcome"] for event in audit if event["action"] == "TARGET_BASELINE_COLLECT"] == [
            "STARTED", "SUCCEEDED"]
        assert "secret-key" not in str(audit)
        assert client.get(base).json()["active_package_id"] is None
        artifact = root / project_id / "target-baselines" / f'{baseline["baseline_id"]}.xml.aesgcm'
        assert artifact.is_file()
        encrypted = artifact.read_bytes()
        assert b"<config" not in encrypted
        assert b"<hostname>one</hostname>" not in encrypted
        owner_cookie = client.cookies.get(SESSION_COOKIE)
    with TestClient(create_app(target_store(root), allowed_target_endpoints={TARGET},
        audit_path=tmp_path / "audit.sqlite3")) as client:
        assert client.get(base + "/target/baseline").status_code == 403
        client.cookies.set(SESSION_COOKIE, owner_cookie)
        assert client.get(base + "/target/baseline").json() == baseline
        assert client.app.state.store.artifacts.read_target_baseline(project_id,
            baseline["baseline_id"], baseline["sha256"], max_plaintext_bytes=1024).startswith(b"<config")


def test_target_collect_requires_artifact_key_before_device_read(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())

    def reject_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("Target device must not be read without an artifact encryption key.")

    target = httpx.AsyncClient(transport=httpx.MockTransport(reject_request),
        base_url="https://10.0.0.20")
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs: target)
    with TestClient(create_app(ProjectStore(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        response = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS)

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "ARTIFACT_KEY_REQUIRED"
        assert client.get(base + "/target/baseline").status_code == 409


def test_successful_recollect_replaces_encrypted_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs: target_client())
    root = tmp_path / "projects"
    with TestClient(create_app(target_store(root), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        project_id, base = prepare_project(client)
        first = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS).json()
        old_path = root / project_id / "target-baselines" / f'{first["baseline_id"]}.xml.aesgcm'
        assert old_path.is_file()

        second = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS).json()

        assert second["baseline_id"] != first["baseline_id"]
        assert old_path.exists() is False
        assert (root / project_id / "target-baselines" /
            f'{second["baseline_id"]}.xml.aesgcm').is_file()


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
    with TestClient(create_app(target_store(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
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
    with TestClient(create_app(target_store(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        first = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS).json()
        failed = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS)
        assert failed.status_code == 409
        assert failed.json()["error"]["code"] == "TARGET_CONFIG_CHANGED"
        assert client.get(base + "/target/baseline").json() == first


def test_target_endpoint_requires_separate_allowlist(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    with TestClient(create_app(target_store(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints=set(), audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        response = client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "XML_API_ENDPOINT_NOT_ALLOWED"
        assert client.get(base + "/target/baseline").status_code == 409


def test_target_baseline_requires_source_serial(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_target_client", lambda *args, **kwargs: target_client())
    with TestClient(create_app(target_store(tmp_path / "projects"), allowed_target_endpoints={TARGET},
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
    with TestClient(create_app(target_store(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
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
    with TestClient(create_app(target_store(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        assert client.post(base + "/target/baseline/collect", json=target_body(), headers=HEADERS).status_code == 200
        response = client.post(base + "/target/preflight/check", json=target_body(), headers=HEADERS)
        assert response.status_code == 200
        report = response.json()
        assert report["status"] == "BLOCKED"
        assert report["deployment_allowed"] is False
        assert report["checks"]["candidate_matches_running"] == "CLEAR"
        assert report["checks"]["pending_jobs_empty"] == "CLEAR"
        assert report["checks"]["ha_state"] == "CLEAR"
        assert report["checks"]["multi_vsys"] == "CLEAR"
        assert report["checks"]["manual_review"] == "BLOCKED"
        assert client.get(base).json()["active_package_id"] is None
        audit = client.get(base + "/audit").json()["events"]
        assert [event["outcome"] for event in audit if event["action"] == "TARGET_PREFLIGHT_CHECK"] == [
            "STARTED", "COMPLETED"]
        assert "secret-key" not in str(report) + str(audit)


def test_target_package_review_and_complete_preflight_pass_offline(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client",
        lambda *args, **kwargs: single_vsys_source_client())
    target_config = package_target_config()
    target_clients = iter([
        target_client(first=target_config, second=target_config),
        preflight_client(running=target_config, candidate=target_config),
    ])
    monkeypatch.setattr("confighop_api.services.create_target_client",
        lambda *args, **kwargs: next(target_clients))
    root = tmp_path / "projects"
    with TestClient(create_app(target_store(root), allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3")) as client:
        project_id, base = prepare_project(client)
        assert client.post(base + "/target/baseline/collect", json=target_body(),
            headers=HEADERS).status_code == 200
        assert client.put(base + "/source-profile", json={"profile_id": "paloalto-pa-5220",
            "panos_train": "11.1"}, headers=HEADERS).status_code == 200
        candidate = client.post(base + "/candidate", json={"mappings": [
            {"source_interface": "ethernet1/12", "target_interface": "ethernet1/8"}],
            "allow_review": True}, headers=HEADERS)
        assert candidate.status_code == 200
        assert candidate.json()["candidate_available"] is True

        built_response = client.post(base + "/target/package/build", headers=HEADERS)
        assert built_response.status_code == 200
        built = built_response.json()
        assert built["deployable_candidate_sha256"]
        assert built["target_preservation"]
        assert set(built["target_preservation"].values()) == {"PRESERVED"}
        assert not any(item["severity"] == "ERROR" for item in built["target_findings"])
        encrypted_path = root / project_id / "packages" / built["package_id"] / "deployable.xml.aesgcm"
        assert encrypted_path.is_file()
        assert b"target-admin" not in encrypted_path.read_bytes()

        accepted = sorted({item["code"] for item in built["target_findings"]
            if item["requires_acceptance"]})
        wrong_host = client.post(base + "/target/package/review", json={
            "confirmed_target_hostname": "wrong-target",
            "accepted_finding_codes": accepted}, headers=HEADERS)
        assert wrong_host.status_code == 409
        assert wrong_host.json()["error"]["code"] == "TARGET_HOSTNAME_CONFIRMATION_MISMATCH"
        incomplete_review = client.post(base + "/target/package/review", json={
            "confirmed_target_hostname": "fw-target-serial",
            "accepted_finding_codes": []}, headers=HEADERS)
        assert incomplete_review.status_code == 409
        assert incomplete_review.json()["error"]["code"] == "TARGET_PACKAGE_REVIEW_INCOMPLETE"
        reviewed_response = client.post(base + "/target/package/review", json={
            "confirmed_target_hostname": "fw-target-serial",
            "accepted_finding_codes": accepted}, headers=HEADERS)
        assert reviewed_response.status_code == 200
        reviewed = reviewed_response.json()
        assert reviewed["review_id"]
        assert reviewed["review_sha256"]

        preflight = client.post(base + "/target/preflight/check", json={
            **target_body(), "recovery_path_confirmed": True}, headers=HEADERS)
        assert preflight.status_code == 200
        report = preflight.json()
        assert report["status"] == "PASSED"
        assert report["deployment_allowed"] is True
        assert report["blockers"] == []
        assert set(report["checks"].values()) == {"CLEAR"}
        assert client.get(base + "/deployment-package").json()["status"] == "PREFLIGHT_PASSED"
        actions = [item["action"] for item in client.get(base + "/deployment-events").json()]
        assert "TARGET_PACKAGE_BUILT" in actions
        assert "TARGET_PACKAGE_REVIEWED" in actions


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
    with TestClient(create_app(target_store(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
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
    with TestClient(create_app(target_store(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
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
    with TestClient(create_app(target_store(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
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
    with TestClient(create_app(target_store(tmp_path / "projects"), allowed_source_endpoints={SOURCE},
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


def test_target_stage_is_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: source_client())
    with TestClient(create_app(target_store(tmp_path / "projects"),
        allowed_source_endpoints={SOURCE}, allowed_target_endpoints={TARGET},
        audit_path=tmp_path / "audit.sqlite3")) as client:
        _, base = prepare_project(client)
        capabilities = client.get("/api/v1/capabilities").json()["domains"]["firewall"]
        assert capabilities["deployment_mode"] == "disabled"
        assert capabilities["panos_target_stage_validate"] is False
        response = client.post(base + "/target/stage", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial"}, headers=HEADERS)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "LIVE_DEPLOYMENT_DISABLED"


def test_stage_captures_encrypted_backups_loads_exact_candidate_and_validates_job(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: single_vsys_source_client())
    target_config = package_target_config()
    target_clients = [target_client(first=target_config, second=target_config),
        preflight_client(running=target_config, candidate=target_config)]
    monkeypatch.setattr("confighop_api.services.create_target_client",
        lambda *args, **kwargs: target_clients.pop(0))
    root = tmp_path / "projects"
    store = target_store(root)
    with TestClient(create_app(store, allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3",
        deployment_mode="lab")) as client:
        project_id, base = prepare_project(client)
        built = prepare_passed_target_package(client, base)
        deployable = store.artifacts.read_deployable(project_id, built["package_id"],
            built["deployable_candidate_sha256"], max_plaintext_bytes=store.max_source_bytes)
        target_clients.append(stage_client(deployable, baseline=target_config))

        response = client.post(base + "/target/stage", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial"}, headers=HEADERS)

        assert response.status_code == 200, response.text
        report = response.json()
        assert report["status"] == "VALIDATED"
        assert report["validation_job_id"] == "42"
        assert report["commit_created"] is False
        package = client.get(base + "/deployment-package").json()
        assert package["status"] == "VALIDATED"
        assert package["running_backup_sha256"] == package["candidate_backup_sha256"]
        assert package["loaded_candidate_sha256"] == built["deployable_candidate_sha256"]
        for kind in ("running", "candidate"):
            encrypted = root / project_id / "packages" / built["package_id"] / "backups" / f"{kind}.xml.aesgcm"
            assert encrypted.is_file()
            assert b"<config" not in encrypted.read_bytes()
        events = client.get(base + "/deployment-events").json()
        states = [event["to_state"] for event in events if event["action"] == "DEPLOYMENT_STATE_CHANGED"]
        assert states[-5:] == ["BACKUP_CAPTURED", "IMPORTED", "CANDIDATE_LOADED", "VALIDATING", "VALIDATED"]
        audit = client.get(base + "/audit").json()
        assert "secret-key" not in str(events) + str(audit) + response.text
        assert [item["outcome"] for item in audit["events"] if item["action"] == "TARGET_STAGE"] == [
            "STARTED", "SUCCEEDED"]


def test_import_timeout_enters_status_unknown_without_retry(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: single_vsys_source_client())
    target_config = package_target_config()
    target_clients = [target_client(first=target_config, second=target_config),
        preflight_client(running=target_config, candidate=target_config)]
    monkeypatch.setattr("confighop_api.services.create_target_client",
        lambda *args, **kwargs: target_clients.pop(0))
    root = tmp_path / "projects"
    store = target_store(root)
    with TestClient(create_app(store, allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3",
        deployment_mode="lab")) as client:
        project_id, base = prepare_project(client)
        built = prepare_passed_target_package(client, base)
        deployable = store.artifacts.read_deployable(project_id, built["package_id"],
            built["deployable_candidate_sha256"], max_plaintext_bytes=store.max_source_bytes)
        target_clients.append(stage_client(deployable, baseline=target_config, import_timeout=True))

        response = client.post(base + "/target/stage", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial"}, headers=HEADERS)

        assert response.status_code == 504
        assert response.json()["error"]["code"] == "XML_API_TIMEOUT"
        package = client.get(base + "/deployment-package").json()
        assert package["status"] == "STATUS_UNKNOWN"
        assert package["ambiguous_operation"] == "IMPORT"
        assert package["running_backup_sha256"] and package["candidate_backup_sha256"]
        target_clients.append(reconcile_client(running=target_config, candidate=target_config))
        reconciled = client.post(base + "/target/stage/reconcile", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial"}, headers=HEADERS)
        assert reconciled.status_code == 200, reconciled.text
        assert reconciled.json()["reconciliation"] == "STILL_AMBIGUOUS"
        assert reconciled.json()["commit_created"] is False
        assert client.get(base + "/deployment-package").json()["status"] == "STATUS_UNKNOWN"
        internal = store.database.package(built["package_id"])
        internal.ambiguous_operation = "RECOVERY_LOAD"
        with store.database.connection:
            store.database.connection.execute(
                "UPDATE deployment_packages SET package_json=? WHERE package_id=?",
                (internal.model_dump_json(), internal.package_id))
        blocked_retry = client.post(base + "/target/recovery", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial",
            "recovery_confirmation": "RECOVER fw-target-serial"}, headers=HEADERS)
        assert blocked_retry.status_code == 409
        assert blocked_retry.json()["error"]["code"] == "RECOVERY_RESULT_UNKNOWN"


def test_one_time_approval_commit_polls_terminal_job_and_verifies_running(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: single_vsys_source_client())
    target_config = package_target_config()
    target_clients = [target_client(first=target_config, second=target_config),
        preflight_client(running=target_config, candidate=target_config)]
    monkeypatch.setattr("confighop_api.services.create_target_client",
        lambda *args, **kwargs: target_clients.pop(0))
    store = target_store(tmp_path / "projects")
    with TestClient(create_app(store, allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3",
        deployment_mode="lab")) as client:
        project_id, base = prepare_project(client)
        _, deployable = prepare_validated_package(client, store, project_id, base,
            target_clients, target_config)
        approval = client.post(base + "/target/commit/approval", json={
            "expected_serial": "target-serial", "expected_model": "PA-5410",
            "confirmed_target_hostname": "fw-target-serial"}, headers=HEADERS)
        assert approval.status_code == 200, approval.text
        old_token = approval.json()["approval_token"]
        reissued = client.post(base + "/target/commit/approval", json={
            "expected_serial": "target-serial", "expected_model": "PA-5410",
            "confirmed_target_hostname": "fw-target-serial"}, headers=HEADERS)
        token = reissued.json()["approval_token"]
        assert token != old_token
        stored = store.database.package(approval.json()["package_id"])
        with pytest.raises(ValueError, match="token is invalid"):
            store.database.consume_commit_approval(stored.package_id, old_token,
                expected_input_sha256=stored.input_sha256,
                actor_sha256=stored.approval_actor_sha256)
        assert token not in str(client.get(base + "/deployment-events").json())
        target_clients.append(commit_client(baseline=target_config, deployable=deployable))
        committed = client.post(base + "/target/commit", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial", "approval_token": token},
            headers=HEADERS)
        assert committed.status_code == 200, committed.text
        assert committed.json()["status"] == "SUCCEEDED"
        assert committed.json()["commit_job_id"] == "84"
        package = client.get(base + "/deployment-package").json()
        assert "approval_token_sha256" not in package
        assert "approval_actor_sha256" not in package
        assert package["approval_used_at_utc"] is not None
        assert package["commit_result_sha256"] and package["post_verification_sha256"]
        replay = client.post(base + "/target/commit", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial", "approval_token": token},
            headers=HEADERS)
        assert replay.status_code == 409
        audit = client.get(base + "/audit").json()["events"]
        assert token not in str(audit)


def test_commit_job_failure_after_enqueue_never_reports_success(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: single_vsys_source_client())
    target_config = package_target_config()
    target_clients = [target_client(first=target_config, second=target_config),
        preflight_client(running=target_config, candidate=target_config)]
    monkeypatch.setattr("confighop_api.services.create_target_client",
        lambda *args, **kwargs: target_clients.pop(0))
    store = target_store(tmp_path / "projects")
    with TestClient(create_app(store, allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3",
        deployment_mode="lab")) as client:
        project_id, base = prepare_project(client)
        _, deployable = prepare_validated_package(client, store, project_id, base,
            target_clients, target_config)
        approval = client.post(base + "/target/commit/approval", json={
            "expected_serial": "target-serial", "expected_model": "PA-5410",
            "confirmed_target_hostname": "fw-target-serial"}, headers=HEADERS).json()
        package = store.database.package(approval["package_id"])
        package.approval_expires_at_utc = datetime.now(timezone.utc) - timedelta(seconds=1)
        with store.database.connection:
            store.database.connection.execute(
                "UPDATE deployment_packages SET package_json=? WHERE package_id=?",
                (package.model_dump_json(), package.package_id))
        with pytest.raises(ValueError, match="expired"):
            store.database.consume_commit_approval(package.package_id, approval["approval_token"],
                expected_input_sha256=package.input_sha256,
                actor_sha256=package.approval_actor_sha256)
        token = client.post(base + "/target/commit/approval", json={
            "expected_serial": "target-serial", "expected_model": "PA-5410",
            "confirmed_target_hostname": "fw-target-serial"}, headers=HEADERS).json()["approval_token"]
        target_clients.append(commit_client(baseline=target_config, deployable=deployable,
            job_failed=True))
        response = client.post(base + "/target/commit", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial", "approval_token": token},
            headers=HEADERS)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "XML_API_COMMIT_JOB_FAILED"
        package = client.get(base + "/deployment-package").json()
        assert package["status"] == "FAILED_NEEDS_OPERATOR"
        assert package["commit_job_id"] == "84"
        assert package["post_verification_sha256"] is None
        target_clients.append(recovery_no_commit_client(backup=target_config))
        recovered = client.post(base + "/target/recovery", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial",
            "recovery_confirmation": "RECOVER fw-target-serial"}, headers=HEADERS)
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["status"] == "RECOVERED"
        assert recovered.json()["recovery_commit_job_id"] is None


def test_lost_commit_connection_is_reconciled_read_only_then_recovered(monkeypatch, tmp_path):
    monkeypatch.setattr("confighop_api.services.create_source_client", lambda *args, **kwargs: single_vsys_source_client())
    target_config = package_target_config()
    target_clients = [target_client(first=target_config, second=target_config),
        preflight_client(running=target_config, candidate=target_config)]
    monkeypatch.setattr("confighop_api.services.create_target_client",
        lambda *args, **kwargs: target_clients.pop(0))
    store = target_store(tmp_path / "projects")
    with TestClient(create_app(store, allowed_source_endpoints={SOURCE},
        allowed_target_endpoints={TARGET}, audit_path=tmp_path / "audit.sqlite3",
        deployment_mode="lab")) as client:
        project_id, base = prepare_project(client)
        _, deployable = prepare_validated_package(client, store, project_id, base,
            target_clients, target_config)
        token = client.post(base + "/target/commit/approval", json={
            "expected_serial": "target-serial", "expected_model": "PA-5410",
            "confirmed_target_hostname": "fw-target-serial"}, headers=HEADERS).json()["approval_token"]
        target_clients.append(commit_client(baseline=target_config, deployable=deployable,
            commit_timeout=True))
        response = client.post(base + "/target/commit", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial", "approval_token": token},
            headers=HEADERS)
        assert response.status_code == 504
        package = client.get(base + "/deployment-package").json()
        assert package["status"] == "STATUS_UNKNOWN"
        assert package["ambiguous_operation"] == "COMMIT"

        target_clients.append(reconcile_client(running=target_config, candidate=target_config))
        reconciled = client.post(base + "/target/commit/reconcile", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial"}, headers=HEADERS)
        assert reconciled.status_code == 200, reconciled.text
        assert reconciled.json()["reconciliation"] == "RUNNING_UNCHANGED"
        assert client.get(base + "/deployment-package").json()["status"] == "STATUS_UNKNOWN"

        target_clients.append(recovery_client(backup=target_config, deployed=deployable))
        recovered = client.post(base + "/target/recovery", json={**target_body(),
            "confirmed_target_hostname": "fw-target-serial",
            "recovery_confirmation": "RECOVER fw-target-serial"}, headers=HEADERS)
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["status"] == "RECOVERED"
        assert recovered.json()["recovery_commit_job_id"] == "88"
        assert recovered.json()["recovery_validation_sha256"]
        assert recovered.json()["recovery_verification_sha256"]
