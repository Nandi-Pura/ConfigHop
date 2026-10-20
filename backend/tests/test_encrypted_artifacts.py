import base64
import hashlib
from uuid import uuid4

import pytest

from confighop_api.artifacts import (
    ARTIFACT_FORMAT, ArtifactIntegrityError, ArtifactKeyError, EncryptedArtifactStore,
    decode_artifact_key,
)


KEY = b"target-baseline-test-key-32byte!"
PLAINTEXT = b"<config><shared><marker>not-on-disk</marker></shared></config>"


def identities() -> tuple[str, str]:
    return str(uuid4()), str(uuid4())


def test_decode_artifact_key_requires_exactly_32_bytes():
    assert decode_artifact_key(base64.b64encode(KEY).decode()) == KEY
    assert decode_artifact_key(None) is None
    assert decode_artifact_key("  ") is None

    with pytest.raises(ArtifactKeyError, match="valid base64"):
        decode_artifact_key("not-base64!")
    with pytest.raises(ArtifactKeyError, match="exactly 32 bytes"):
        decode_artifact_key(base64.b64encode(b"short").decode())


def test_encrypted_target_baseline_round_trip_hides_plaintext(tmp_path):
    project_id, baseline_id = identities()
    digest = hashlib.sha256(PLAINTEXT).hexdigest()
    store = EncryptedArtifactStore(tmp_path, KEY)

    path = store.write_target_baseline(project_id, baseline_id, PLAINTEXT, digest)

    payload = path.read_bytes()
    assert path.name == f"{baseline_id}.xml.aesgcm"
    assert PLAINTEXT not in payload
    assert b"not-on-disk" not in payload
    assert store.read_target_baseline(project_id, baseline_id, digest,
        max_plaintext_bytes=1024) == PLAINTEXT


def test_encryption_uses_a_fresh_nonce_for_each_write(tmp_path):
    project_id, baseline_id = identities()
    digest = hashlib.sha256(PLAINTEXT).hexdigest()
    store = EncryptedArtifactStore(tmp_path, KEY)

    path = store.write_target_baseline(project_id, baseline_id, PLAINTEXT, digest)
    first = path.read_bytes()
    store.write_target_baseline(project_id, baseline_id, PLAINTEXT, digest)

    assert path.read_bytes() != first


def test_tampered_ciphertext_is_rejected(tmp_path):
    project_id, baseline_id = identities()
    digest = hashlib.sha256(PLAINTEXT).hexdigest()
    store = EncryptedArtifactStore(tmp_path, KEY)
    path = store.write_target_baseline(project_id, baseline_id, PLAINTEXT, digest)
    payload = bytearray(path.read_bytes())
    payload[-1] ^= 1
    path.write_bytes(payload)

    with pytest.raises(ArtifactIntegrityError, match="authentication failed"):
        store.read_target_baseline(project_id, baseline_id, digest, max_plaintext_bytes=1024)


def test_wrong_key_or_authenticated_metadata_is_rejected(tmp_path):
    project_id, baseline_id = identities()
    digest = hashlib.sha256(PLAINTEXT).hexdigest()
    store = EncryptedArtifactStore(tmp_path, KEY)
    store.write_target_baseline(project_id, baseline_id, PLAINTEXT, digest)

    with pytest.raises(ArtifactIntegrityError, match="authentication failed"):
        EncryptedArtifactStore(tmp_path, b"another-target-baseline-key-32!!").read_target_baseline(
            project_id, baseline_id, digest, max_plaintext_bytes=1024)
    with pytest.raises(ArtifactIntegrityError, match="authentication failed"):
        store.read_target_baseline(project_id, baseline_id, "0" * 64, max_plaintext_bytes=1024)


def test_missing_key_and_invalid_identity_fail_closed(tmp_path):
    project_id, baseline_id = identities()
    digest = hashlib.sha256(PLAINTEXT).hexdigest()
    store = EncryptedArtifactStore(tmp_path, None)

    assert store.available is False
    with pytest.raises(ArtifactKeyError, match="not configured"):
        store.write_target_baseline(project_id, baseline_id, PLAINTEXT, digest)
    with pytest.raises(ArtifactIntegrityError, match="identity is invalid"):
        EncryptedArtifactStore(tmp_path, KEY).target_baseline_path("../escape", baseline_id)


def test_artifact_format_is_stable():
    assert ARTIFACT_FORMAT == "AES_256_GCM_V1"


def test_encrypted_deployable_round_trip_and_tamper_detection(tmp_path):
    project_id, package_id = identities()
    digest = hashlib.sha256(PLAINTEXT).hexdigest()
    store = EncryptedArtifactStore(tmp_path, KEY)

    path = store.write_deployable(project_id, package_id, PLAINTEXT, digest)

    assert path.name == "deployable.xml.aesgcm"
    assert PLAINTEXT not in path.read_bytes()
    assert store.read_deployable(project_id, package_id, digest,
        max_plaintext_bytes=1024) == PLAINTEXT
    payload = bytearray(path.read_bytes())
    payload[-1] ^= 1
    path.write_bytes(payload)
    with pytest.raises(ArtifactIntegrityError, match="authentication failed"):
        store.read_deployable(project_id, package_id, digest, max_plaintext_bytes=1024)
