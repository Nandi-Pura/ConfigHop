import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from confighop_api.access_audit import SESSION_COOKIE
from confighop_api.main import create_app
from confighop_api.project_state import ProjectDatabase, package_input_hash
from confighop_api.services import PROFILE_ID, ProjectStore


FIXTURE = Path(__file__).parent / "fixtures/paloalto/pa_complex_synthetic.xml"
HEADERS = {"X-ConfigHop-Client": "web"}


def app_for(root: Path):
    return create_app(ProjectStore(root / "projects"), audit_path=root / "audit.sqlite3")


def upload(client, project_id: str, body: bytes):
    return client.put(f"/api/v1/projects/{project_id}/source", content=body,
        headers={**HEADERS, "Content-Type": "application/xml", "X-ConfigHop-Filename": "source.xml"})


def test_restart_preserves_owned_project_candidate_and_immutable_snapshot(tmp_path):
    first_source = FIXTURE.read_bytes()
    next_source = first_source + b"\n"
    with TestClient(app_for(tmp_path)) as client:
        project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        token = client.cookies.get(SESSION_COOKIE)
        base = f"/api/v1/projects/{project_id}"
        assert upload(client, project_id, first_source).status_code == 200
        first_snapshot = client.get(base).json()["active_snapshot_id"]
        assert client.put(base + "/target-profile", json={"profile_id": PROFILE_ID}, headers=HEADERS).status_code == 200
        candidate = client.post(base + "/candidate", json={"mappings": [
            {"source_interface": "ethernet1/12", "target_interface": "ethernet1/50"}]}, headers=HEADERS)
        assert candidate.status_code == 200 and candidate.json()["candidate_available"]
        package = client.get(base + "/deployment-package").json()
        assert package["source_snapshot_id"] == first_snapshot
        assert package["target_baseline_sha256"] is None
        assert package["status"] == "DRAFT_UNDEPLOYABLE"
        candidate_xml = client.get(base + "/candidate/download").content

    with TestClient(app_for(tmp_path)) as client:
        client.cookies.set(SESSION_COOKIE, token)
        assert client.get(base).json()["active_snapshot_id"] == first_snapshot
        assert client.get(base).json()["candidate_available"]
        assert client.get(base + "/candidate/download").content == candidate_xml
        assert client.get(base + "/source").content == first_source
        assert upload(client, project_id, b"<config>invalid").status_code == 422
        assert client.get(base).json()["active_package_id"] == package["package_id"]
        assert client.get(base + "/source").content == first_source
        assert upload(client, project_id, next_source).status_code == 200
        assert client.get(base).json()["candidate_available"] is False
        assert client.get(base).json()["active_package_id"] is None
        snapshots = client.get(base + "/snapshots").json()
        assert [item["sha256"] for item in snapshots] == [
            hashlib.sha256(first_source).hexdigest(), hashlib.sha256(next_source).hexdigest()]
        old_path = tmp_path / "projects" / project_id / "snapshots" / first_snapshot / "source.xml"
        assert old_path.read_bytes() == first_source
        assert client.get(base + "/source").content == next_source
        events = client.get(base + "/deployment-events").json()
        assert [item["action"] for item in events].count("SOURCE_SNAPSHOT_CREATED") == 2
        assert any(item["action"] == "PACKAGE_INVALIDATED" and item["reason"] == "SOURCE_CHANGED"
            for item in events)
        client.cookies.clear()
        assert client.get(base).status_code == 403

    with TestClient(app_for(tmp_path)) as client:
        client.cookies.set(SESSION_COOKIE, token)
        assert client.get(base).json()["source_provenance"]["sha256"] == hashlib.sha256(next_source).hexdigest()
        assert client.get(base + "/source").content == next_source


def test_tampered_source_snapshot_fails_closed_after_restart(tmp_path):
    with TestClient(app_for(tmp_path)) as client:
        project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        token = client.cookies.get(SESSION_COOKIE)
        assert upload(client, project_id, FIXTURE.read_bytes()).status_code == 200
        snapshot_id = client.get(f"/api/v1/projects/{project_id}").json()["active_snapshot_id"]
    snapshot_path = tmp_path / "projects" / project_id / "snapshots" / snapshot_id / "source.xml"
    snapshot_path.write_bytes(b"<config>tampered</config>")
    with TestClient(app_for(tmp_path)) as client:
        client.cookies.set(SESSION_COOKIE, token)
        state = client.get(f"/api/v1/projects/{project_id}").json()
        assert state["state"] == "SOURCE_INTEGRITY_FAILED"
        assert state["source_available"] is False
        response = client.get(f"/api/v1/projects/{project_id}/source")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SOURCE_INTEGRITY_FAILED"
        assert b"tampered" not in response.content
        assert upload(client, project_id, FIXTURE.read_bytes()).status_code == 200
        assert client.get(f"/api/v1/projects/{project_id}/source").content == FIXTURE.read_bytes()


def test_mapping_change_invalidates_draft_and_changes_fingerprint(tmp_path):
    with TestClient(app_for(tmp_path)) as client:
        project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        base = f"/api/v1/projects/{project_id}"
        assert upload(client, project_id, FIXTURE.read_bytes()).status_code == 200
        assert client.put(base + "/target-profile", json={"profile_id": PROFILE_ID}, headers=HEADERS).status_code == 200
        first = client.post(base + "/candidate", json={"mappings": [
            {"source_interface": "ethernet1/12", "target_interface": "ethernet1/50"}]}, headers=HEADERS)
        assert first.json()["candidate_available"]
        package = client.get(base + "/deployment-package").json()
        preview = client.post(base + "/preview", json={"mappings": [
            {"source_interface": "ethernet1/12", "target_interface": "ethernet1/51"}]}, headers=HEADERS)
        assert preview.status_code == 200
        assert client.get(base + "/deployment-package").status_code == 409
        assert client.get(base + "/candidate/download").status_code == 409
        events = client.get(base + "/deployment-events").json()
        assert any(item["package_id"] == package["package_id"] and
            item["action"] == "PACKAGE_INVALIDATED" for item in events)
        next_candidate = client.post(base + "/candidate", json={"mappings": [
            {"source_interface": "ethernet1/12", "target_interface": "ethernet1/51"}]}, headers=HEADERS)
        assert next_candidate.json()["candidate_available"]
        new_package = client.get(base + "/deployment-package").json()
        assert new_package["input_sha256"] != package["input_sha256"]
        assert client.put(base + "/target-profile", json={"profile_id": PROFILE_ID}, headers=HEADERS).status_code == 200
        assert client.get(base + "/deployment-package").status_code == 409
        assert any(item["package_id"] == new_package["package_id"] and
            item["reason"] == "TARGET_PROFILE_CHANGED" for item in client.get(base + "/deployment-events").json())


def test_target_baseline_changes_package_fingerprint():
    values = dict(source_sha256="a" * 64, source_profile_id="source", target_profile_id="target",
        source_panos_train="11.1", target_panos_train="11.1", mapping_sha256="b" * 64)
    assert package_input_hash(**values, target_baseline_sha256="c" * 64) != (
        package_input_hash(**values, target_baseline_sha256="d" * 64))


def test_snapshot_database_failure_keeps_old_source(monkeypatch, tmp_path):
    with TestClient(app_for(tmp_path), raise_server_exceptions=False) as client:
        project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        base = f"/api/v1/projects/{project_id}"
        first = FIXTURE.read_bytes()
        assert upload(client, project_id, first).status_code == 200
        snapshot_id = client.get(base).json()["active_snapshot_id"]

        def fail_save(_self, _snapshot, _state):
            raise RuntimeError("metadata unavailable")

        monkeypatch.setattr(ProjectDatabase, "save_snapshot", fail_save)
        response = upload(client, project_id, first + b"\n")
        assert response.status_code == 500
        assert client.get(base).json()["active_snapshot_id"] == snapshot_id
        assert client.get(base + "/source").content == first
        assert len(client.get(base + "/snapshots").json()) == 1


def test_tampered_candidate_is_withdrawn_after_restart(tmp_path):
    with TestClient(app_for(tmp_path)) as client:
        project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        token = client.cookies.get(SESSION_COOKIE)
        base = f"/api/v1/projects/{project_id}"
        assert upload(client, project_id, FIXTURE.read_bytes()).status_code == 200
        assert client.put(base + "/target-profile", json={"profile_id": PROFILE_ID}, headers=HEADERS).status_code == 200
        assert client.post(base + "/candidate", json={"mappings": [
            {"source_interface": "ethernet1/12", "target_interface": "ethernet1/50"}]},
            headers=HEADERS).json()["candidate_available"]
    candidate_path = tmp_path / "projects" / project_id / "candidate.xml"
    candidate_path.write_bytes(b"<config>tampered</config>")
    with TestClient(app_for(tmp_path)) as client:
        client.cookies.set(SESSION_COOKIE, token)
        assert client.get(base).json()["candidate_available"] is False
        assert client.get(base + "/candidate/download").status_code == 409
        assert client.get(base + "/deployment-package").status_code == 409
        assert any(item["reason"] == "CANDIDATE_INTEGRITY_FAILED"
            for item in client.get(base + "/deployment-events").json())
