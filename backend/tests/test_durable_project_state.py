import hashlib
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from confighop_api.access_audit import SESSION_COOKIE
from confighop_api.main import create_app
from confighop_api.project_state import (
    ProjectDatabase, TargetBaseline, make_review_decision, package_input_hash,
)
from confighop_api.services import PROFILE_ID, ProjectStore, record_target_baseline


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


def test_target_baseline_drift_invalidates_only_the_package_and_survives_restart(tmp_path):
    with TestClient(app_for(tmp_path)) as client:
        project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        token = client.cookies.get(SESSION_COOKIE)
        base = f"/api/v1/projects/{project_id}"
        assert upload(client, project_id, FIXTURE.read_bytes()).status_code == 200
        assert client.put(base + "/target-profile", json={"profile_id": PROFILE_ID}, headers=HEADERS).status_code == 200
        body = {"mappings": [{"source_interface": "ethernet1/12", "target_interface": "ethernet1/50"}]}
        assert client.post(base + "/candidate", json=body, headers=HEADERS).json()["candidate_available"]
        old_package = client.get(base + "/deployment-package").json()
        project = client.app.state.store.get(project_id)
        first = TargetBaseline(serial="target-serial", model="PA-5410", hostname="new-fw",
            panos_version="11.1.2", sha256="a" * 64)
        record_target_baseline(project, first)
        assert client.get(base + "/deployment-package").status_code == 409
        assert client.get(base).json()["candidate_available"] is True
        assert client.app.state.store.database.package(old_package["package_id"]).status == "INVALIDATED"
        assert client.post(base + "/candidate", json=body, headers=HEADERS).json()["candidate_available"]
        bound = client.get(base + "/deployment-package").json()
        assert bound["target_baseline_sha256"] == first.sha256
        assert bound["target_serial"] == first.serial
        record_target_baseline(project, first.model_copy(update={"baseline_id": str(uuid4())}))
        assert client.get(base).json()["active_package_id"] == bound["package_id"]
        second = first.model_copy(update={"baseline_id": str(uuid4()), "sha256": "b" * 64})
        record_target_baseline(project, second)
        assert client.get(base + "/deployment-package").status_code == 409
        assert client.get(base).json()["candidate_available"] is True
        assert any(event["reason"] == "TARGET_BASELINE_CHANGED" and
            event["package_id"] == bound["package_id"] for event in client.get(base + "/deployment-events").json())

    with TestClient(app_for(tmp_path)) as client:
        client.cookies.set(SESSION_COOKIE, token)
        project = client.app.state.store.get(project_id)
        assert project.target_baseline.sha256 == "b" * 64
        assert client.get(base).json()["candidate_available"] is True


def test_draft_cannot_advance_without_target_candidate_and_review(tmp_path):
    with TestClient(app_for(tmp_path)) as client:
        project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        base = f"/api/v1/projects/{project_id}"
        assert upload(client, project_id, FIXTURE.read_bytes()).status_code == 200
        assert client.put(base + "/target-profile", json={"profile_id": PROFILE_ID}, headers=HEADERS).status_code == 200
        record_target_baseline(client.app.state.store.get(project_id), TargetBaseline(
            serial="target-serial", model="PA-5410", hostname="new-fw", panos_version="11.1.2",
            sha256="a" * 64))
        assert client.post(base + "/candidate", json={"mappings": [
            {"source_interface": "ethernet1/12", "target_interface": "ethernet1/50"}]},
            headers=HEADERS).json()["candidate_available"]
        package = client.get(base + "/deployment-package").json()
        database = client.app.state.store.database
        with pytest.raises(ValueError, match="review are required"):
            database.transition_package(package["package_id"], "PREFLIGHT_PASSED",
                expected_input_sha256=package["input_sha256"])
        with pytest.raises(ValueError, match="Invalid deployment state transition"):
            database.transition_package(package["package_id"], "COMMIT_QUEUED",
                expected_input_sha256=package["input_sha256"])
        assert database.package(package["package_id"]).status == "DRAFT_UNDEPLOYABLE"


def test_state_transitions_are_ordered_durable_and_preserve_frozen_package(tmp_path):
    with TestClient(app_for(tmp_path)) as client:
        project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        token = client.cookies.get(SESSION_COOKIE)
        base = f"/api/v1/projects/{project_id}"
        assert upload(client, project_id, FIXTURE.read_bytes()).status_code == 200
        assert client.put(base + "/target-profile", json={"profile_id": PROFILE_ID}, headers=HEADERS).status_code == 200
        project = client.app.state.store.get(project_id)
        record_target_baseline(project, TargetBaseline(serial="target-serial", model="PA-5410",
            hostname="new-fw", panos_version="11.1.2", sha256="a" * 64))
        assert client.post(base + "/candidate", json={"mappings": [
            {"source_interface": "ethernet1/12", "target_interface": "ethernet1/50"}]},
            headers=HEADERS).json()["candidate_available"]
        database = client.app.state.store.database
        old_package = database.package(project.active_package_id)
        decision = make_review_decision(project_id=project_id,
            source_package_id=old_package.package_id, input_sha256=old_package.input_sha256,
            candidate_sha256=old_package.candidate_sha256,
            accepted_finding_codes=[], actor_sha256="f" * 64)
        database.save_review(decision)
        review_hash = decision.decision_sha256
        deployable_xml = b"<config><devices><entry name='synthetic-target'/></devices></config>"
        target_candidate_hash = hashlib.sha256(deployable_xml).hexdigest()
        reviewed = old_package.model_copy(update={
            "package_id": str(uuid4()), "review_id": decision.review_id,
            "review_sha256": review_hash,
            "deployable_candidate_sha256": target_candidate_hash,
            "input_sha256": package_input_hash(source_sha256=old_package.source_sha256,
                source_profile_id=old_package.source_profile_id,
                target_profile_id=old_package.target_profile_id,
                source_panos_train=old_package.source_panos_train,
                target_panos_train=old_package.target_panos_train,
                mapping_sha256=old_package.mapping_sha256,
                target_baseline_sha256=old_package.target_baseline_sha256,
                candidate_sha256=old_package.candidate_sha256,
                review_sha256=review_hash, deployable_candidate_sha256=target_candidate_hash),
        })
        database.invalidate_package(old_package.package_id, "REVIEW_CHANGED")
        package_dir = project.workspace / "packages" / reviewed.package_id
        package_dir.mkdir(parents=True)
        shutil.copyfile(project.candidate_path, package_dir / "candidate.xml")
        (package_dir / "deployable.xml").write_bytes(deployable_xml)
        state = project.export_state()
        state["active_package_id"] = reviewed.package_id
        database.save_package(reviewed, state=state)
        project.active_package_id = reviewed.package_id
        with pytest.raises(ValueError, match="fingerprint changed"):
            database.transition_package(reviewed.package_id, "PREFLIGHT_PASSED",
                expected_input_sha256="0" * 64)
        passed = database.transition_package(reviewed.package_id, "PREFLIGHT_PASSED",
            expected_input_sha256=reviewed.input_sha256)
        assert passed.status == "PREFLIGHT_PASSED"
        with pytest.raises(ValueError, match="evidence digest is required"):
            database.transition_package(reviewed.package_id, "BACKUP_CAPTURED",
                expected_input_sha256=reviewed.input_sha256)
        captured = database.transition_package(reviewed.package_id, "BACKUP_CAPTURED",
            expected_input_sha256=reviewed.input_sha256, evidence_sha256="e" * 64)
        assert captured.backup_sha256 == "e" * 64
        record_target_baseline(project, project.target_baseline.model_copy(update={
            "baseline_id": str(uuid4()), "sha256": "b" * 64}))
        assert client.get(base + "/deployment-package").status_code == 409
        assert database.package(reviewed.package_id).status == "BACKUP_CAPTURED"
        assert (package_dir / "candidate.xml").is_file()
        with pytest.raises(ValueError, match="Detached deployment package cannot advance normally"):
            database.transition_package(reviewed.package_id, "IMPORTED",
                expected_input_sha256=reviewed.input_sha256, evidence_sha256="d" * 64)
        assert any(event["action"] == "PACKAGE_DETACHED" and
            event["package_id"] == reviewed.package_id for event in client.get(base + "/deployment-events").json())

    with TestClient(app_for(tmp_path)) as client:
        client.cookies.set(SESSION_COOKIE, token)
        database = client.app.state.store.database
        assert database.package(reviewed.package_id).status == "BACKUP_CAPTURED"
        events = database.events(project_id)
        assert any(event.from_state == "PREFLIGHT_PASSED" and event.to_state == "BACKUP_CAPTURED" and
            event.evidence_sha256 == "e" * 64 for event in events)
        unknown = database.transition_package(reviewed.package_id, "STATUS_UNKNOWN",
            expected_input_sha256=reviewed.input_sha256)
        assert unknown.status == "STATUS_UNKNOWN"
        recovery = database.transition_package(reviewed.package_id, "RECOVERY_REQUESTED",
            expected_input_sha256=reviewed.input_sha256)
        assert recovery.status == "RECOVERY_REQUESTED"
        with pytest.raises(ValueError, match="Invalid deployment state transition"):
            database.transition_package(reviewed.package_id, "RECOVERED",
                expected_input_sha256=reviewed.input_sha256, evidence_sha256="f" * 64)


def test_package_artifact_tamper_does_not_make_draft_usable_after_restart(tmp_path):
    with TestClient(app_for(tmp_path)) as client:
        project_id = client.post("/api/v1/projects", headers=HEADERS).json()["project_id"]
        token = client.cookies.get(SESSION_COOKIE)
        base = f"/api/v1/projects/{project_id}"
        assert upload(client, project_id, FIXTURE.read_bytes()).status_code == 200
        assert client.put(base + "/target-profile", json={"profile_id": PROFILE_ID}, headers=HEADERS).status_code == 200
        assert client.post(base + "/candidate", json={"mappings": [
            {"source_interface": "ethernet1/12", "target_interface": "ethernet1/50"}]},
            headers=HEADERS).json()["candidate_available"]
        package_id = client.get(base).json()["active_package_id"]
    artifact = tmp_path / "projects" / project_id / "packages" / package_id / "candidate.xml"
    artifact.write_bytes(b"<config>tampered package</config>")
    with TestClient(app_for(tmp_path)) as client:
        client.cookies.set(SESSION_COOKIE, token)
        assert client.get(base).json()["candidate_available"] is True
        assert client.get(base).json()["active_package_id"] is None
        assert client.get(base + "/deployment-package").status_code == 409
        assert client.app.state.store.database.package(package_id).status == "INVALIDATED"
        assert any(event["reason"] == "PACKAGE_INTEGRITY_FAILED" for event in
            client.get(base + "/deployment-events").json())


def test_v1_project_database_adds_transition_columns(tmp_path):
    root = tmp_path / "database"
    root.mkdir()
    with sqlite3.connect(root / "projects.sqlite3") as connection:
        connection.execute("""CREATE TABLE deployment_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
            package_id TEXT, action TEXT NOT NULL, outcome TEXT NOT NULL,
            reason TEXT, input_sha256 TEXT, recorded_at_utc TEXT NOT NULL)""")
        connection.execute("PRAGMA user_version = 1")
    database = ProjectDatabase(root)
    try:
        columns = {row[1] for row in database.connection.execute("PRAGMA table_info(deployment_events)")}
        assert {"from_state", "to_state", "evidence_sha256"} <= columns
        assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 4
    finally:
        database.close()
