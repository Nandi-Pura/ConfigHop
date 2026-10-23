import base64
import binascii
import hashlib
import json
import os
import tempfile
from pathlib import Path
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ARTIFACT_FORMAT = "AES_256_GCM_V1"
_MAGIC = b"CHAE1"
_NONCE_BYTES = 12
_TAG_BYTES = 16


class ArtifactKeyError(ValueError):
    pass


class ArtifactIntegrityError(ValueError):
    pass


def decode_artifact_key(value: str | None) -> bytes | None:
    if value is None or not value.strip():
        return None
    try:
        key = base64.b64decode(value.strip(), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ArtifactKeyError("CONFIGHOP_ARTIFACT_KEY_B64 must be valid base64.") from exc
    if len(key) != 32:
        raise ArtifactKeyError("CONFIGHOP_ARTIFACT_KEY_B64 must decode to exactly 32 bytes.")
    return key


def _uuid_component(value: str) -> str:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise ArtifactIntegrityError("Artifact identity is invalid.") from exc
    if str(parsed) != value:
        raise ArtifactIntegrityError("Artifact identity is invalid.")
    return value


class EncryptedArtifactStore:
    def __init__(self, root: Path, key: bytes | None):
        if key is not None and len(key) != 32:
            raise ArtifactKeyError("Artifact encryption key must be exactly 32 bytes.")
        self.root = root
        self._key = key

    @property
    def available(self) -> bool:
        return self._key is not None

    def require_key(self) -> None:
        if self._key is None:
            raise ArtifactKeyError("Artifact encryption key is not configured.")

    def target_baseline_path(self, project_id: str, baseline_id: str) -> Path:
        project = _uuid_component(project_id)
        baseline = _uuid_component(baseline_id)
        return self.root / project / "target-baselines" / f"{baseline}.xml.aesgcm"

    def _aad(self, project_id: str, baseline_id: str, plaintext_sha256: str) -> bytes:
        if len(plaintext_sha256) != 64 or any(character not in "0123456789abcdef"
            for character in plaintext_sha256):
            raise ArtifactIntegrityError("Artifact plaintext hash is invalid.")
        return json.dumps({"artifact_format": ARTIFACT_FORMAT,
            "artifact_kind": "TARGET_RUNNING_CONFIG", "baseline_id": _uuid_component(baseline_id),
            "plaintext_sha256": plaintext_sha256, "project_id": _uuid_component(project_id)},
            sort_keys=True, separators=(",", ":")).encode()

    def write_target_baseline(self, project_id: str, baseline_id: str, plaintext: bytes,
        plaintext_sha256: str) -> Path:
        self.require_key()
        if hashlib.sha256(plaintext).hexdigest() != plaintext_sha256:
            raise ArtifactIntegrityError("Target baseline plaintext hash does not match metadata.")
        path = self.target_baseline_path(project_id, baseline_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        nonce = os.urandom(_NONCE_BYTES)
        encrypted = AESGCM(self._key).encrypt(nonce, plaintext,
            self._aad(project_id, baseline_id, plaintext_sha256))
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                stream.write(_MAGIC + nonce + encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path

    def read_target_baseline(self, project_id: str, baseline_id: str,
        plaintext_sha256: str, *, max_plaintext_bytes: int) -> bytes:
        self.require_key()
        path = self.target_baseline_path(project_id, baseline_id)
        try:
            if path.stat().st_size > len(_MAGIC) + _NONCE_BYTES + max_plaintext_bytes + _TAG_BYTES:
                raise ArtifactIntegrityError("Encrypted target baseline exceeds the size limit.")
            payload = path.read_bytes()
        except FileNotFoundError as exc:
            raise ArtifactIntegrityError("Encrypted target baseline is unavailable.") from exc
        if len(payload) < len(_MAGIC) + _NONCE_BYTES + _TAG_BYTES or not payload.startswith(_MAGIC):
            raise ArtifactIntegrityError("Encrypted target baseline format is invalid.")
        nonce_start = len(_MAGIC)
        nonce = payload[nonce_start:nonce_start + _NONCE_BYTES]
        try:
            plaintext = AESGCM(self._key).decrypt(nonce, payload[nonce_start + _NONCE_BYTES:],
                self._aad(project_id, baseline_id, plaintext_sha256))
        except InvalidTag as exc:
            raise ArtifactIntegrityError("Encrypted target baseline authentication failed.") from exc
        if len(plaintext) > max_plaintext_bytes or hashlib.sha256(plaintext).hexdigest() != plaintext_sha256:
            raise ArtifactIntegrityError("Target baseline plaintext integrity check failed.")
        return plaintext

    def delete_target_baseline(self, project_id: str, baseline_id: str) -> None:
        self.target_baseline_path(project_id, baseline_id).unlink(missing_ok=True)

    def deployable_path(self, project_id: str, package_id: str) -> Path:
        project = _uuid_component(project_id)
        package = _uuid_component(package_id)
        return self.root / project / "packages" / package / "deployable.xml.aesgcm"

    def _deployable_aad(self, project_id: str, package_id: str,
        plaintext_sha256: str) -> bytes:
        if len(plaintext_sha256) != 64 or any(character not in "0123456789abcdef"
            for character in plaintext_sha256):
            raise ArtifactIntegrityError("Artifact plaintext hash is invalid.")
        return json.dumps({"artifact_format": ARTIFACT_FORMAT,
            "artifact_kind": "TARGET_DEPLOYABLE_CONFIG", "package_id": _uuid_component(package_id),
            "plaintext_sha256": plaintext_sha256, "project_id": _uuid_component(project_id)},
            sort_keys=True, separators=(",", ":")).encode()

    def write_deployable(self, project_id: str, package_id: str, plaintext: bytes,
        plaintext_sha256: str) -> Path:
        self.require_key()
        if hashlib.sha256(plaintext).hexdigest() != plaintext_sha256:
            raise ArtifactIntegrityError("Deployable plaintext hash does not match metadata.")
        path = self.deployable_path(project_id, package_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        nonce = os.urandom(_NONCE_BYTES)
        encrypted = AESGCM(self._key).encrypt(nonce, plaintext,
            self._deployable_aad(project_id, package_id, plaintext_sha256))
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                stream.write(_MAGIC + nonce + encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path

    def read_deployable(self, project_id: str, package_id: str,
        plaintext_sha256: str, *, max_plaintext_bytes: int) -> bytes:
        self.require_key()
        path = self.deployable_path(project_id, package_id)
        try:
            if path.stat().st_size > len(_MAGIC) + _NONCE_BYTES + max_plaintext_bytes + _TAG_BYTES:
                raise ArtifactIntegrityError("Encrypted deployable package exceeds the size limit.")
            payload = path.read_bytes()
        except FileNotFoundError as exc:
            raise ArtifactIntegrityError("Encrypted deployable package is unavailable.") from exc
        if len(payload) < len(_MAGIC) + _NONCE_BYTES + _TAG_BYTES or not payload.startswith(_MAGIC):
            raise ArtifactIntegrityError("Encrypted deployable package format is invalid.")
        nonce_start = len(_MAGIC)
        nonce = payload[nonce_start:nonce_start + _NONCE_BYTES]
        try:
            plaintext = AESGCM(self._key).decrypt(nonce, payload[nonce_start + _NONCE_BYTES:],
                self._deployable_aad(project_id, package_id, plaintext_sha256))
        except InvalidTag as exc:
            raise ArtifactIntegrityError("Encrypted deployable package authentication failed.") from exc
        if len(plaintext) > max_plaintext_bytes or hashlib.sha256(plaintext).hexdigest() != plaintext_sha256:
            raise ArtifactIntegrityError("Deployable plaintext integrity check failed.")
        return plaintext

    def delete_deployable(self, project_id: str, package_id: str) -> None:
        self.deployable_path(project_id, package_id).unlink(missing_ok=True)

    def backup_path(self, project_id: str, package_id: str, kind: str) -> Path:
        if kind not in {"running", "candidate"}:
            raise ArtifactIntegrityError("Backup artifact kind is invalid.")
        project = _uuid_component(project_id)
        package = _uuid_component(package_id)
        return self.root / project / "packages" / package / "backups" / f"{kind}.xml.aesgcm"

    def _backup_aad(self, project_id: str, package_id: str, kind: str,
        plaintext_sha256: str) -> bytes:
        if kind not in {"running", "candidate"}:
            raise ArtifactIntegrityError("Backup artifact kind is invalid.")
        if len(plaintext_sha256) != 64 or any(character not in "0123456789abcdef"
            for character in plaintext_sha256):
            raise ArtifactIntegrityError("Artifact plaintext hash is invalid.")
        return json.dumps({"artifact_format": ARTIFACT_FORMAT,
            "artifact_kind": f"TARGET_{kind.upper()}_BACKUP",
            "package_id": _uuid_component(package_id),
            "plaintext_sha256": plaintext_sha256, "project_id": _uuid_component(project_id)},
            sort_keys=True, separators=(",", ":")).encode()

    def write_backup(self, project_id: str, package_id: str, kind: str,
        plaintext: bytes, plaintext_sha256: str) -> Path:
        self.require_key()
        if hashlib.sha256(plaintext).hexdigest() != plaintext_sha256:
            raise ArtifactIntegrityError("Backup plaintext hash does not match metadata.")
        path = self.backup_path(project_id, package_id, kind)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        nonce = os.urandom(_NONCE_BYTES)
        encrypted = AESGCM(self._key).encrypt(nonce, plaintext,
            self._backup_aad(project_id, package_id, kind, plaintext_sha256))
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                stream.write(_MAGIC + nonce + encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path

    def read_backup(self, project_id: str, package_id: str, kind: str,
        plaintext_sha256: str, *, max_plaintext_bytes: int) -> bytes:
        self.require_key()
        path = self.backup_path(project_id, package_id, kind)
        try:
            if path.stat().st_size > len(_MAGIC) + _NONCE_BYTES + max_plaintext_bytes + _TAG_BYTES:
                raise ArtifactIntegrityError("Encrypted backup exceeds the size limit.")
            payload = path.read_bytes()
        except FileNotFoundError as exc:
            raise ArtifactIntegrityError("Encrypted backup is unavailable.") from exc
        if len(payload) < len(_MAGIC) + _NONCE_BYTES + _TAG_BYTES or not payload.startswith(_MAGIC):
            raise ArtifactIntegrityError("Encrypted backup format is invalid.")
        nonce_start = len(_MAGIC)
        nonce = payload[nonce_start:nonce_start + _NONCE_BYTES]
        try:
            plaintext = AESGCM(self._key).decrypt(nonce, payload[nonce_start + _NONCE_BYTES:],
                self._backup_aad(project_id, package_id, kind, plaintext_sha256))
        except InvalidTag as exc:
            raise ArtifactIntegrityError("Encrypted backup authentication failed.") from exc
        if len(plaintext) > max_plaintext_bytes or hashlib.sha256(plaintext).hexdigest() != plaintext_sha256:
            raise ArtifactIntegrityError("Backup plaintext integrity check failed.")
        return plaintext

    def delete_backups(self, project_id: str, package_id: str) -> None:
        for kind in ("running", "candidate"):
            self.backup_path(project_id, package_id, kind).unlink(missing_ok=True)
