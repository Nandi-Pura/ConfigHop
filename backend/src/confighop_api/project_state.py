import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .artifacts import ArtifactIntegrityError, ArtifactKeyError, EncryptedArtifactStore


RENDERER_VERSION = "0.7.0"


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


class TargetBaseline(BaseModel):
    baseline_id: str = Field(default_factory=lambda: str(uuid4()))
    serial: str = Field(min_length=1)
    model: str = Field(min_length=1)
    hostname: str = Field(min_length=1)
    panos_version: str = Field(min_length=1)
    multi_vsys: bool | None = None
    operational_mode: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_format: Literal["AES_256_GCM_V1"] | None = None
    artifact_size_bytes: int | None = Field(default=None, ge=1)
    observed_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewDecision(BaseModel):
    review_id: str
    project_id: str
    source_package_id: str
    input_sha256: str
    candidate_sha256: str
    deployable_candidate_sha256: str | None = None
    accepted_finding_codes: list[str]
    actor_sha256: str
    decided_at_utc: datetime
    decision_sha256: str


def make_review_decision(*, project_id: str, source_package_id: str,
    input_sha256: str, candidate_sha256: str, accepted_finding_codes: list[str],
    actor_sha256: str, deployable_candidate_sha256: str | None = None) -> ReviewDecision:
    decided_at_utc = datetime.now(timezone.utc)
    review_id = str(uuid4())
    payload = dict(review_id=review_id, project_id=project_id,
        source_package_id=source_package_id, input_sha256=input_sha256,
        candidate_sha256=candidate_sha256,
        accepted_finding_codes=sorted(set(accepted_finding_codes)),
        actor_sha256=actor_sha256, decided_at_utc=decided_at_utc.isoformat())
    if deployable_candidate_sha256 is not None:
        payload["deployable_candidate_sha256"] = deployable_candidate_sha256
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ReviewDecision(**payload, decision_sha256=digest)


def review_decision_digest(decision: ReviewDecision) -> str:
    payload = decision.model_dump(mode="json", exclude={"decision_sha256"}, exclude_none=True)
    payload["decided_at_utc"] = decision.decided_at_utc.isoformat()
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


DeploymentStatus = Literal[
    "DRAFT_UNDEPLOYABLE", "PREFLIGHT_PASSED", "BACKUP_CAPTURED", "IMPORTED",
    "CANDIDATE_LOADED", "VALIDATING", "VALIDATED", "AWAITING_COMMIT_APPROVAL",
    "COMMIT_QUEUED", "COMMIT_RUNNING", "VERIFYING", "SUCCEEDED",
    "FAILED_SAFE", "FAILED_NEEDS_OPERATOR", "STATUS_UNKNOWN", "CANCELLED",
    "RECOVERY_REQUESTED", "BACKUP_LOADED", "RECOVERY_VALIDATING",
    "RECOVERY_COMMITTING", "RECOVERED", "INVALIDATED",
]

_NEXT_STATE = {
    "DRAFT_UNDEPLOYABLE": "PREFLIGHT_PASSED",
    "PREFLIGHT_PASSED": "BACKUP_CAPTURED",
    "BACKUP_CAPTURED": "IMPORTED",
    "IMPORTED": "CANDIDATE_LOADED",
    "CANDIDATE_LOADED": "VALIDATING",
    "VALIDATING": "VALIDATED",
    "VALIDATED": "AWAITING_COMMIT_APPROVAL",
    "AWAITING_COMMIT_APPROVAL": "COMMIT_QUEUED",
    "COMMIT_QUEUED": "COMMIT_RUNNING",
    "COMMIT_RUNNING": "VERIFYING",
    "VERIFYING": "SUCCEEDED",
    "RECOVERY_REQUESTED": "BACKUP_LOADED",
    "BACKUP_LOADED": "RECOVERY_VALIDATING",
    "RECOVERY_VALIDATING": "RECOVERY_COMMITTING",
    "RECOVERY_COMMITTING": "RECOVERED",
}
_FAILABLE = frozenset(_NEXT_STATE) - {"DRAFT_UNDEPLOYABLE"}
_RECOVERABLE = {"FAILED_SAFE", "FAILED_NEEDS_OPERATOR", "STATUS_UNKNOWN"}
_FROZEN = {"BACKUP_CAPTURED", "IMPORTED", "CANDIDATE_LOADED", "VALIDATING",
    "VALIDATED", "AWAITING_COMMIT_APPROVAL", "COMMIT_QUEUED", "COMMIT_RUNNING",
    "VERIFYING", "SUCCEEDED", "FAILED_SAFE", "FAILED_NEEDS_OPERATOR",
    "STATUS_UNKNOWN", "RECOVERY_REQUESTED", "BACKUP_LOADED",
    "RECOVERY_VALIDATING", "RECOVERY_COMMITTING", "RECOVERED"}


class TargetPackageChange(BaseModel):
    scope: str
    object_name: str
    action: Literal["ADDED", "REPLACED"]


class TargetPackageFinding(BaseModel):
    code: str
    severity: Literal["INFO", "WARNING", "ERROR"]
    scope: str
    message: str
    requires_acceptance: bool = False


class DeploymentPackage(BaseModel):
    package_id: str
    project_id: str
    source_snapshot_id: str
    source_sha256: str
    input_sha256: str
    mapping_sha256: str
    renderer_version: str = RENDERER_VERSION
    source_profile_id: str | None = None
    target_profile_id: str | None = None
    source_panos_train: str | None = None
    target_panos_train: str | None = None
    target_baseline_sha256: str | None = None
    target_serial: str | None = None
    candidate_sha256: str | None = None
    deployable_candidate_sha256: str | None = None
    target_changes: list[TargetPackageChange] = Field(default_factory=list)
    target_preservation: dict[str, Literal["PRESERVED"]] = Field(default_factory=dict)
    target_findings: list[TargetPackageFinding] = Field(default_factory=list)
    review_id: str | None = None
    review_sha256: str | None = None
    backup_sha256: str | None = None
    running_backup_sha256: str | None = None
    candidate_backup_sha256: str | None = None
    import_sha256: str | None = None
    loaded_candidate_sha256: str | None = None
    change_summary_sha256: str | None = None
    validation_sha256: str | None = None
    validation_job_id: str | None = None
    ambiguous_operation: Literal["IMPORT", "LOAD", "VALIDATE"] | None = None
    approval_sha256: str | None = None
    commit_job_id: str | None = None
    commit_result_sha256: str | None = None
    post_verification_sha256: str | None = None
    recovery_load_sha256: str | None = None
    recovery_validation_sha256: str | None = None
    recovery_commit_job_id: str | None = None
    recovery_verification_sha256: str | None = None
    status: DeploymentStatus = "DRAFT_UNDEPLOYABLE"
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
    from_state: DeploymentStatus | None = None
    to_state: DeploymentStatus | None = None
    evidence_sha256: str | None = None
    recorded_at_utc: datetime


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mapping_hash(mappings: list) -> str:
    def compact(value):
        if isinstance(value, dict):
            return {key: compact(item) for key, item in value.items() if item is not None}
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value

    payload = [compact(item.model_dump(mode="json") if hasattr(item, "model_dump") else item)
        for item in mappings]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def package_input_hash(*, source_sha256: str, source_profile_id: str | None,
    target_profile_id: str | None, source_panos_train: str | None,
    target_panos_train: str | None, mapping_sha256: str,
    target_baseline_sha256: str | None, candidate_sha256: str | None = None,
    review_sha256: str | None = None, deployable_candidate_sha256: str | None = None,
    renderer_version: str = RENDERER_VERSION) -> str:
    payload = dict(source_sha256=source_sha256, source_profile_id=source_profile_id,
        target_profile_id=target_profile_id, source_panos_train=source_panos_train,
        target_panos_train=target_panos_train, mapping_sha256=mapping_sha256,
        target_baseline_sha256=target_baseline_sha256, candidate_sha256=candidate_sha256,
        review_sha256=review_sha256, deployable_candidate_sha256=deployable_candidate_sha256,
        renderer_version=renderer_version)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ProjectDatabase:
    def __init__(self, root: Path, artifacts: EncryptedArtifactStore | None = None):
        self.root = root
        self.artifacts = artifacts
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = root / "projects.sqlite3"
        path.touch(mode=0o600, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, 2, 3, 4):
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
            CREATE TABLE IF NOT EXISTS review_decisions (
                review_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                review_json TEXT NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(project_id));
            CREATE TABLE IF NOT EXISTS deployment_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
                package_id TEXT, action TEXT NOT NULL, outcome TEXT NOT NULL,
                reason TEXT, input_sha256 TEXT, recorded_at_utc TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS deployment_events_project ON deployment_events(project_id, sequence);
        """)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(deployment_events)")}
        for name in ("from_state", "to_state", "evidence_sha256"):
            if name not in columns:
                self.connection.execute(f"ALTER TABLE deployment_events ADD COLUMN {name} TEXT")
        self.connection.execute("PRAGMA user_version = 4")
        self.connection.commit()

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

    def bind_target_baseline(self, project_id: str, state: dict, reason: str | None) -> None:
        with self.connection:
            if reason and state.get("active_package_id"):
                self._invalidate_package(state["active_package_id"], reason)
                state["active_package_id"] = None
            self.connection.execute("UPDATE projects SET state_json=? WHERE project_id=?",
                (json.dumps(state, sort_keys=True), project_id))
            if self.connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise sqlite3.IntegrityError("Project metadata is unavailable")
            self._event(project_id, None, "TARGET_BASELINE_OBSERVED", "SUCCEEDED",
                reason, state["target_baseline"]["sha256"])

    def detach_active_package(self, project_id: str, reason: str) -> None:
        with self.connection:
            row = self.connection.execute("SELECT state_json FROM projects WHERE project_id=?",
                (project_id,)).fetchone()
            if row is None:
                raise ValueError("Project metadata is unavailable")
            state = json.loads(row[0])
            package_id = state.get("active_package_id")
            if package_id is None:
                return
            self._invalidate_package(package_id, reason)
            state["active_package_id"] = None
            self.connection.execute("UPDATE projects SET state_json=? WHERE project_id=?",
                (json.dumps(state, sort_keys=True), project_id))

    def snapshots(self, project_id: str) -> list[SourceSnapshot]:
        return [SourceSnapshot.model_validate_json(row[0]) for row in self.connection.execute(
            "SELECT snapshot_json FROM source_snapshots WHERE project_id=? ORDER BY rowid", (project_id,))]

    def snapshot(self, snapshot_id: str) -> SourceSnapshot | None:
        row = self.connection.execute("SELECT snapshot_json FROM source_snapshots WHERE snapshot_id=?",
            (snapshot_id,)).fetchone()
        return SourceSnapshot.model_validate_json(row[0]) if row else None

    def save_package(self, package: DeploymentPackage, *, state: dict | None = None) -> None:
        if package.status != "DRAFT_UNDEPLOYABLE":
            raise ValueError("New deployment packages must begin as drafts")
        with self.connection:
            self.connection.execute("INSERT INTO deployment_packages VALUES(?, ?, ?)",
                (package.package_id, package.project_id, package.model_dump_json()))
            if state is not None:
                self.connection.execute("UPDATE projects SET state_json=? WHERE project_id=?",
                    (json.dumps(state, sort_keys=True), package.project_id))
                if self.connection.execute("SELECT changes()").fetchone()[0] != 1:
                    raise sqlite3.IntegrityError("Project metadata is unavailable")
            self._event(package.project_id, package.package_id, "PACKAGE_CREATED", package.status,
                None, package.input_sha256, to_state=package.status)

    def save_review(self, decision: ReviewDecision) -> None:
        if not secrets.compare_digest(decision.decision_sha256, review_decision_digest(decision)):
            raise ValueError("Review decision integrity check failed")
        with self.connection:
            row = self.connection.execute("SELECT state_json FROM projects WHERE project_id=?",
                (decision.project_id,)).fetchone()
            package = self.package(decision.source_package_id)
            if row is None or package is None or package.project_id != decision.project_id or (
                json.loads(row[0]).get("active_package_id") != decision.source_package_id or
                package.status != "DRAFT_UNDEPLOYABLE" or
                package.input_sha256 != decision.input_sha256 or
                package.candidate_sha256 != decision.candidate_sha256 or
                (decision.deployable_candidate_sha256 is not None and
                    package.deployable_candidate_sha256 != decision.deployable_candidate_sha256)
            ):
                raise ValueError("Review no longer matches the active draft")
            self.connection.execute("INSERT INTO review_decisions VALUES(?, ?, ?)",
                (decision.review_id, decision.project_id, decision.model_dump_json()))
            self._event(decision.project_id, decision.source_package_id, "REVIEW_RECORDED",
                "SUCCEEDED", None, decision.input_sha256,
                evidence_sha256=decision.decision_sha256)

    def update_draft_package(self, package: DeploymentPackage, *,
        expected_input_sha256: str, action: str, evidence_sha256: str | None = None) -> None:
        with self.connection:
            current = self.package(package.package_id)
            row = self.connection.execute("SELECT state_json FROM projects WHERE project_id=?",
                (package.project_id,)).fetchone()
            if current is None or row is None or current.project_id != package.project_id or (
                json.loads(row[0]).get("active_package_id") != package.package_id or
                current.status != "DRAFT_UNDEPLOYABLE" or
                current.input_sha256 != expected_input_sha256 or
                package.status != "DRAFT_UNDEPLOYABLE"):
                raise ValueError("Active draft changed before it could be updated")
            self.connection.execute("UPDATE deployment_packages SET package_json=? WHERE package_id=?",
                (package.model_dump_json(), package.package_id))
            self._event(package.project_id, package.package_id, action, "SUCCEEDED", None,
                package.input_sha256, evidence_sha256=evidence_sha256)

    def review(self, review_id: str) -> ReviewDecision | None:
        row = self.connection.execute("SELECT review_json FROM review_decisions WHERE review_id=?",
            (review_id,)).fetchone()
        return ReviewDecision.model_validate_json(row[0]) if row else None

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
        if package.status in _FROZEN:
            self._event(package.project_id, package_id, "PACKAGE_DETACHED", "SUCCEEDED",
                reason, package.input_sha256, from_state=package.status, to_state=package.status)
            return
        old_status = package.status
        package.status = "INVALIDATED"
        package.invalidated_reason = reason
        self.connection.execute("UPDATE deployment_packages SET package_json=? WHERE package_id=?",
            (package.model_dump_json(), package_id))
        self._event(package.project_id, package_id, "PACKAGE_INVALIDATED", "SUCCEEDED",
            reason, package.input_sha256, from_state=old_status, to_state="INVALIDATED")

    def transition_package(self, package_id: str, to_state: DeploymentStatus, *,
        expected_input_sha256: str, evidence_sha256: str | None = None,
        job_id: str | None = None, running_backup_sha256: str | None = None,
        candidate_backup_sha256: str | None = None,
        change_summary_sha256: str | None = None,
        ambiguous_operation: Literal["IMPORT", "LOAD", "VALIDATE"] | None = None) -> DeploymentPackage:
        with self.connection:
            package = self.package(package_id)
            if package is None:
                raise ValueError("Deployment package was not found")
            if not secrets.compare_digest(package.input_sha256, expected_input_sha256):
                raise ValueError("Deployment package input fingerprint changed")
            old_status = package.status
            allowed = {"FAILED_SAFE", "FAILED_NEEDS_OPERATOR", "STATUS_UNKNOWN", "CANCELLED"} if old_status in _FAILABLE else set()
            if old_status in _NEXT_STATE:
                allowed.add(_NEXT_STATE[old_status])
            if old_status in _RECOVERABLE:
                allowed.add("RECOVERY_REQUESTED")
            if to_state not in allowed:
                raise ValueError("Invalid deployment state transition")
            project_row = self.connection.execute("SELECT state_json FROM projects WHERE project_id=?",
                (package.project_id,)).fetchone()
            if project_row is None:
                raise ValueError("Project was not found")
            if (json.loads(project_row[0]).get("active_package_id") != package_id and
                to_state not in {"FAILED_SAFE", "FAILED_NEEDS_OPERATOR", "STATUS_UNKNOWN",
                    "RECOVERY_REQUESTED", "BACKUP_LOADED", "RECOVERY_VALIDATING",
                    "RECOVERY_COMMITTING", "RECOVERED"}):
                raise ValueError("Detached deployment package cannot advance normally")
            evidence_fields = {
                "BACKUP_CAPTURED": "backup_sha256", "IMPORTED": "import_sha256",
                "CANDIDATE_LOADED": "loaded_candidate_sha256",
                "VALIDATED": "validation_sha256",
                "COMMIT_QUEUED": "approval_sha256", "VERIFYING": "commit_result_sha256",
                "SUCCEEDED": "post_verification_sha256",
                "BACKUP_LOADED": "recovery_load_sha256",
                "RECOVERY_VALIDATING": "recovery_validation_sha256",
                "RECOVERED": "recovery_verification_sha256",
            }
            evidence_field = evidence_fields.get(to_state)
            if evidence_field:
                if not evidence_sha256 or len(evidence_sha256) != 64 or any(
                    character not in "0123456789abcdef" for character in evidence_sha256):
                    raise ValueError("A SHA-256 evidence digest is required")
                setattr(package, evidence_field, evidence_sha256)
            if to_state == "BACKUP_CAPTURED":
                if not running_backup_sha256 or not candidate_backup_sha256:
                    raise ValueError("Running and candidate backup hashes are required")
                package.running_backup_sha256 = running_backup_sha256
                package.candidate_backup_sha256 = candidate_backup_sha256
            if to_state == "CANDIDATE_LOADED":
                if not change_summary_sha256:
                    raise ValueError("A change-summary digest is required")
                package.change_summary_sha256 = change_summary_sha256
            if to_state == "STATUS_UNKNOWN":
                if ambiguous_operation is None:
                    raise ValueError("The ambiguous operation is required")
                package.ambiguous_operation = ambiguous_operation
            if to_state in {"COMMIT_RUNNING", "RECOVERY_COMMITTING"}:
                if not job_id or len(job_id) > 128:
                    raise ValueError("A commit job ID is required")
                if to_state == "COMMIT_RUNNING":
                    package.commit_job_id = job_id
                else:
                    package.recovery_commit_job_id = job_id
            if to_state == "RECOVERY_REQUESTED" and not package.backup_sha256:
                raise ValueError("A captured backup is required for recovery")
            if to_state == "PREFLIGHT_PASSED" and not all((package.target_baseline_sha256,
                package.target_serial, package.deployable_candidate_sha256, package.review_sha256)):
                raise ValueError("Target baseline, deployable candidate, and review are required")
            if old_status == "DRAFT_UNDEPLOYABLE":
                state = json.loads(project_row[0])
                baseline = state.get("target_baseline") or {}
                current_input_sha256 = package_input_hash(
                    source_sha256=(state.get("source_provenance") or {}).get("sha256", ""),
                    source_profile_id=state.get("source_profile_id"),
                    target_profile_id=state.get("profile_id"),
                    source_panos_train=state.get("source_panos_train"),
                    target_panos_train=state.get("target_panos_train"),
                    mapping_sha256=mapping_hash(state.get("mappings", [])),
                    target_baseline_sha256=baseline.get("sha256"),
                    candidate_sha256=(state.get("candidate") or {}).get("candidate_sha256"),
                    review_sha256=package.review_sha256,
                    deployable_candidate_sha256=package.deployable_candidate_sha256,
                    renderer_version=package.renderer_version)
                if state.get("active_package_id") != package_id or not baseline or (
                    baseline.get("sha256") != package.target_baseline_sha256 or
                    baseline.get("serial") != package.target_serial or
                    (state.get("source_provenance") or {}).get("sha256") != package.source_sha256 or
                    current_input_sha256 != package.input_sha256 or
                    (state.get("candidate") or {}).get("candidate_sha256") != package.candidate_sha256
                ):
                    raise ValueError("Project inputs no longer match the package")
                review = self.review(package.review_id) if package.review_id else None
                unreviewed_input_sha256 = package_input_hash(
                    source_sha256=package.source_sha256,
                    source_profile_id=package.source_profile_id,
                    target_profile_id=package.target_profile_id,
                    source_panos_train=package.source_panos_train,
                    target_panos_train=package.target_panos_train,
                    mapping_sha256=package.mapping_sha256,
                    target_baseline_sha256=package.target_baseline_sha256,
                    candidate_sha256=package.candidate_sha256,
                    renderer_version=package.renderer_version)
                if review is None or review.project_id != package.project_id or (
                    review.decision_sha256 != package.review_sha256 or
                    review_decision_digest(review) != review.decision_sha256 or
                    review.input_sha256 != unreviewed_input_sha256 or
                    review.candidate_sha256 != package.candidate_sha256 or
                    (review.deployable_candidate_sha256 is not None and
                        review.deployable_candidate_sha256 != package.deployable_candidate_sha256)):
                    raise ValueError("Review decision does not match package inputs")
            self.verify_package_artifacts(package)
            package.status = to_state
            self.connection.execute("UPDATE deployment_packages SET package_json=? WHERE package_id=?",
                (package.model_dump_json(), package_id))
            self._event(package.project_id, package_id, "DEPLOYMENT_STATE_CHANGED", "SUCCEEDED",
                None, package.input_sha256, from_state=old_status, to_state=to_state,
                evidence_sha256=evidence_sha256)
            return package

    def record_validation_job(self, package_id: str, job_id: str, *,
        expected_input_sha256: str) -> DeploymentPackage:
        if not job_id.isdigit() or len(job_id) > 32:
            raise ValueError("A valid validation job ID is required")
        with self.connection:
            package = self.package(package_id)
            if package is None or package.status != "VALIDATING" or not secrets.compare_digest(
                package.input_sha256, expected_input_sha256):
                raise ValueError("Validation package state changed")
            package.validation_job_id = job_id
            self.connection.execute("UPDATE deployment_packages SET package_json=? WHERE package_id=?",
                (package.model_dump_json(), package_id))
            self._event(package.project_id, package_id, "VALIDATION_JOB_RECORDED", "SUCCEEDED",
                None, package.input_sha256)
            return package

    def package(self, package_id: str) -> DeploymentPackage | None:
        row = self.connection.execute("SELECT package_json FROM deployment_packages WHERE package_id=?", (package_id,)).fetchone()
        return DeploymentPackage.model_validate_json(row[0]) if row else None

    def verify_package_artifacts(self, package: DeploymentPackage) -> None:
        snapshot = self.snapshot(package.source_snapshot_id)
        if snapshot is None or snapshot.project_id != package.project_id or snapshot.sha256 != package.source_sha256:
            raise ValueError("Source snapshot no longer matches the package")
        snapshot_path = self.root / package.project_id / "snapshots" / package.source_snapshot_id / "source.xml"
        if not snapshot_path.is_file() or sha256_file(snapshot_path) != package.source_sha256:
            raise ValueError("Source snapshot integrity check failed")
        candidate_path = self.root / package.project_id / "packages" / package.package_id / "candidate.xml"
        if not candidate_path.is_file() or sha256_file(candidate_path) != package.candidate_sha256:
            raise ValueError("Package artifact integrity check failed")
        if package.deployable_candidate_sha256:
            deployable_path = self.root / package.project_id / "packages" / package.package_id / "deployable.xml"
            if deployable_path.is_file():
                if sha256_file(deployable_path) != package.deployable_candidate_sha256:
                    raise ValueError("Deployable artifact integrity check failed")
            elif self.artifacts is not None:
                try:
                    self.artifacts.read_deployable(package.project_id, package.package_id,
                        package.deployable_candidate_sha256, max_plaintext_bytes=100 * 1024 * 1024)
                except (ArtifactIntegrityError, ArtifactKeyError) as exc:
                    raise ValueError("Deployable artifact integrity check failed") from exc
            else:
                raise ValueError("Deployable artifact integrity check failed")
        if package.running_backup_sha256 or package.candidate_backup_sha256:
            if not package.running_backup_sha256 or not package.candidate_backup_sha256 or self.artifacts is None:
                raise ValueError("Backup artifact metadata is incomplete")
            try:
                self.artifacts.read_backup(package.project_id, package.package_id, "running",
                    package.running_backup_sha256, max_plaintext_bytes=100 * 1024 * 1024)
                self.artifacts.read_backup(package.project_id, package.package_id, "candidate",
                    package.candidate_backup_sha256, max_plaintext_bytes=100 * 1024 * 1024)
            except (ArtifactIntegrityError, ArtifactKeyError) as exc:
                raise ValueError("Backup artifact integrity check failed") from exc

    def events(self, project_id: str) -> list[DeploymentEvent]:
        return [DeploymentEvent.model_validate(dict(row)) for row in self.connection.execute(
            "SELECT * FROM deployment_events WHERE project_id=? ORDER BY sequence", (project_id,))]

    def _event(self, project_id: str, package_id: str | None, action: str, outcome: str,
        reason: str | None, input_sha256: str | None, *,
        from_state: DeploymentStatus | None = None, to_state: DeploymentStatus | None = None,
        evidence_sha256: str | None = None) -> None:
        self.connection.execute("""INSERT INTO deployment_events
            (project_id, package_id, action, outcome, reason, input_sha256, from_state, to_state,
                evidence_sha256, recorded_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (project_id, package_id, action, outcome,
            reason, input_sha256, from_state, to_state, evidence_sha256,
            datetime.now(timezone.utc).isoformat()))

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
            self.connection.execute("DELETE FROM review_decisions WHERE project_id=?", (project_id,))
            self.connection.execute("DELETE FROM projects WHERE project_id=?", (project_id,))

    def close(self) -> None:
        self.connection.close()
