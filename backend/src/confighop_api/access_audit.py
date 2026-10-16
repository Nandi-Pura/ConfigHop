import hashlib
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


SESSION_COOKIE = "confighop_session"
SESSION_SECONDS = 8 * 60 * 60


class ProjectAccess:
    def __init__(self):
        self.sessions: dict[str, float] = {}
        self.owners: dict[str, str] = {}

    @staticmethod
    def fingerprint(token: str | None) -> str:
        return hashlib.sha256((token or "").encode()).hexdigest()

    def create_owner(self, project_id: str, token: str | None) -> str:
        now = time.monotonic()
        self.sessions = {key: expiry for key, expiry in self.sessions.items() if expiry > now}
        if not token or self.sessions.get(self.fingerprint(token), 0) <= now:
            token = secrets.token_urlsafe(32)
        digest = self.fingerprint(token)
        self.sessions[digest] = now + SESSION_SECONDS
        self.owners[project_id] = digest
        return token

    def allows(self, project_id: str, token: str | None) -> bool:
        digest = self.fingerprint(token)
        owner = self.owners.get(project_id)
        return bool(token and owner and secrets.compare_digest(owner, digest)
            and self.sessions.get(digest, 0) > time.monotonic())


class AuditStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.touch(mode=0o600, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""CREATE TABLE IF NOT EXISTS source_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT NOT NULL,
            recorded_at_utc TEXT NOT NULL,
            project_id TEXT NOT NULL,
            actor_sha256 TEXT NOT NULL,
            action TEXT NOT NULL,
            outcome TEXT NOT NULL,
            error_code TEXT,
            source_sha256 TEXT
        )""")
        self.connection.execute("CREATE INDEX IF NOT EXISTS source_events_project ON source_events(project_id, sequence)")
        self.connection.commit()

    def record(self, *, project_id: str, actor_sha256: str, action: str, outcome: str,
        operation_id: str | None = None, error_code: str | None = None,
        source_sha256: str | None = None) -> str:
        operation_id = operation_id or str(uuid4())
        with self.connection:
            self.connection.execute("""INSERT INTO source_events
                (operation_id, recorded_at_utc, project_id, actor_sha256, action, outcome, error_code, source_sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (operation_id,
                datetime.now(timezone.utc).isoformat(), project_id, actor_sha256,
                action, outcome, error_code, source_sha256))
        return operation_id

    def events(self, project_id: str, *, after: int = 0, limit: int = 100) -> list[dict]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM source_events WHERE project_id = ? AND sequence > ? ORDER BY sequence LIMIT ?",
            (project_id, after, limit))]

    def close(self) -> None:
        self.connection.close()
