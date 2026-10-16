import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field


class DeviceIdentity(BaseModel):
    hostname: str
    serial: str
    model: str
    panos_version: str
    observed_at_utc: datetime
    verification: str = "COLLECT_CONSISTENCY"


class SourceSnapshot(BaseModel):
    snapshot_id: str
    project_id: str
    filename: str
    size_bytes: int
    sha256: str
    origin: str
    snapshot_kind: str
    received_at_utc: datetime
    identity: DeviceIdentity | None = None


class DeploymentPackage(BaseModel):
    package_id: str
    project_id: str
    source_snapshot_id: str
    source_sha256: str
    input_sha256: str
    mapping_sha256: str
    source_profile_id: str | None = None
    target_profile_id: str | None = None
    source_panos_train: str | None = None
    target_panos_train: str | None = None
    target_baseline_sha256: str | None = None
    candidate_sha256: str | None = None
    status: str = "DRAFT_UNDEPLOYABLE"
    invalidated_reason: str | None = None
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeploymentEvent(BaseModel):
    sequence: int
    project_id: str
    package_id: str | None = None
    action: str
    outcome: str
    reason: str | None = None
    input_sha256: str | None = None
    recorded_at_utc: datetime


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mapping_hash(mappings: list) -> str:
    payload = [item.model_dump(mode="json", exclude_none=True) for item in mappings]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def package_input_hash(*, source_sha256: str, source_profile_id: str | None,
    target_profile_id: str | None, source_panos_train: str | None,
    target_panos_train: str | None, mapping_sha256: str,
    target_baseline_sha256: str | None, renderer_version: str = "0.7.0") -> str:
    payload = dict(source_sha256=source_sha256, source_profile_id=source_profile_id,
        target_profile_id=target_profile_id, source_panos_train=source_panos_train,
        target_panos_train=target_panos_train, mapping_sha256=mapping_sha256,
        target_baseline_sha256=target_baseline_sha256, renderer_version=renderer_version)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ProjectDatabase:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = root / "projects.sqlite3"
        path.touch(mode=0o600, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.connection.close()
            raise ValueError("Unsupported project database schema version")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY, state_json TEXT NOT NULL,
                owner_sha256 TEXT, owner_expires_at REAL);
            CREATE TABLE IF NOT EXISTS source_snapshots (
                snapshot_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                snapshot_json TEXT NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(project_id));
            CREATE TABLE IF NOT EXISTS deployment_packages (
                package_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                package_json TEXT NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(project_id));
            CREATE TABLE IF NOT EXISTS deployment_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
                package_id TEXT, action TEXT NOT NULL, outcome TEXT NOT NULL,
                reason TEXT, input_sha256 TEXT, recorded_at_utc TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS deployment_events_project ON deployment_events(project_id, sequence);
        """)
        if version == 0:
            self.connection.execute("PRAGMA user_version = 1")

    def projects(self) -> list[dict]:
        return [json.loads(row[0]) for row in self.connection.execute("SELECT state_json FROM projects")]

    def save_project(self, project_id: str, state: dict) -> None:
        with self.connection:
            self.connection.execute("""INSERT INTO projects(project_id, state_json) VALUES(?, ?)
                ON CONFLICT(project_id) DO UPDATE SET state_json=excluded.state_json""",
                (project_id, json.dumps(state, sort_keys=True)))

    def save_snapshot(self, snapshot: SourceSnapshot, state: dict) -> None:
        with self.connection:
            previous_package_id = self.connection.execute("SELECT json_extract(state_json, '$.active_package_id') FROM projects WHERE project_id=?",
                (snapshot.project_id,)).fetchone()
            if previous_package_id and previous_package_id[0]:
                self._invalidate_package(previous_package_id[0], "SOURCE_CHANGED")
            self.connection.execute("INSERT INTO source_snapshots VALUES(?, ?, ?)",
                (snapshot.snapshot_id, snapshot.project_id, snapshot.model_dump_json()))
            self.connection.execute("UPDATE projects SET state_json=? WHERE project_id=?",
                (json.dumps(state, sort_keys=True), snapshot.project_id))
            if self.connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise sqlite3.IntegrityError("Project metadata is unavailable")
            self._event(snapshot.project_id, None, "SOURCE_SNAPSHOT_CREATED", "SUCCEEDED",
                None, snapshot.sha256)

    def snapshots(self, project_id: str) -> list[SourceSnapshot]:
        return [SourceSnapshot.model_validate_json(row[0]) for row in self.connection.execute(
            "SELECT snapshot_json FROM source_snapshots WHERE project_id=? ORDER BY rowid", (project_id,))]

    def snapshot(self, snapshot_id: str) -> SourceSnapshot | None:
        row = self.connection.execute("SELECT snapshot_json FROM source_snapshots WHERE snapshot_id=?",
            (snapshot_id,)).fetchone()
        return SourceSnapshot.model_validate_json(row[0]) if row else None

    def save_package(self, package: DeploymentPackage) -> None:
        with self.connection:
            self.connection.execute("INSERT INTO deployment_packages VALUES(?, ?, ?)",
                (package.package_id, package.project_id, package.model_dump_json()))
            self._event(package.project_id, package.package_id, "PACKAGE_CREATED", package.status,
                None, package.input_sha256)

    def invalidate_package(self, package_id: str, reason: str) -> None:
        with self.connection:
            self._invalidate_package(package_id, reason)

    def _invalidate_package(self, package_id: str, reason: str) -> None:
        row = self.connection.execute("SELECT package_json FROM deployment_packages WHERE package_id=?", (package_id,)).fetchone()
        if row is None:
            return
        package = DeploymentPackage.model_validate_json(row[0])
        if package.status == "INVALIDATED":
            return
        if package.status != "DRAFT_UNDEPLOYABLE":
            raise ValueError("Only an unstaged draft package can be invalidated")
        package.status = "INVALIDATED"
        package.invalidated_reason = reason
        self.connection.execute("UPDATE deployment_packages SET package_json=? WHERE package_id=?",
            (package.model_dump_json(), package_id))
        self._event(package.project_id, package_id, "PACKAGE_INVALIDATED", "SUCCEEDED",
            reason, package.input_sha256)

    def package(self, package_id: str) -> DeploymentPackage | None:
        row = self.connection.execute("SELECT package_json FROM deployment_packages WHERE package_id=?", (package_id,)).fetchone()
        return DeploymentPackage.model_validate_json(row[0]) if row else None

    def events(self, project_id: str) -> list[DeploymentEvent]:
        return [DeploymentEvent.model_validate(dict(row)) for row in self.connection.execute(
            "SELECT * FROM deployment_events WHERE project_id=? ORDER BY sequence", (project_id,))]

    def _event(self, project_id: str, package_id: str | None, action: str, outcome: str,
        reason: str | None, input_sha256: str | None) -> None:
        self.connection.execute("""INSERT INTO deployment_events
            (project_id, package_id, action, outcome, reason, input_sha256, recorded_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (project_id, package_id, action, outcome,
            reason, input_sha256, datetime.now(timezone.utc).isoformat()))

    def owners(self) -> dict[str, tuple[str, float]]:
        return {row[0]: (row[1], row[2]) for row in self.connection.execute(
            "SELECT project_id, owner_sha256, owner_expires_at FROM projects WHERE owner_sha256 IS NOT NULL")}

    def save_owner(self, project_id: str, digest: str, expires_at: float) -> None:
        with self.connection:
            self.connection.execute("UPDATE projects SET owner_sha256=?, owner_expires_at=? WHERE project_id=?",
                (digest, expires_at, project_id))

    def refresh_owners(self, digest: str, expires_at: float) -> None:
        with self.connection:
            self.connection.execute("UPDATE projects SET owner_expires_at=? WHERE owner_sha256=?",
                (expires_at, digest))

    def delete_project(self, project_id: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM source_snapshots WHERE project_id=?", (project_id,))
            self.connection.execute("DELETE FROM deployment_packages WHERE project_id=?", (project_id,))
            self.connection.execute("DELETE FROM projects WHERE project_id=?", (project_id,))

    def close(self) -> None:
        self.connection.close()
