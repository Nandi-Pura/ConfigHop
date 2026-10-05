from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from confighop_api.main import create_app
from confighop_api.services import PROFILE_ID, ProjectStore
from confighop_core import parse_palo_alto_xml


FIXTURE = Path(__file__).parent / "fixtures" / "paloalto" / "pa_complex_synthetic.xml"
MUTATION = {"X-ConfigHop-Client": "web"}


@pytest.fixture
def api():
    store = ProjectStore()
    with TestClient(create_app(store)) as client:
        yield client, store


def project(client):
    response = client.post("/api/v1/projects", headers=MUTATION)
    assert response.status_code == 200
    return response.json()["project_id"]


def upload(client, project_id, content=None, filename="synthetic.xml"):
    return client.put(f"/api/v1/projects/{project_id}/source", content=content or FIXTURE.read_bytes(),
        headers={**MUTATION, "Content-Type": "application/xml", "X-ConfigHop-Filename": filename})


def profile(client, project_id):
    response = client.put(f"/api/v1/projects/{project_id}/target-profile",
        json={"profile_id": PROFILE_ID}, headers=MUTATION)
    assert response.status_code == 200


def mappings(target="ethernet1/50"):
    return {"mappings": [{"source_interface": "ethernet1/12", "target_interface": target}]}


def test_api_end_to_end(api, tmp_path):
    client, _store = api
    assert client.get("/api/v1/health").json() == {"status": "ok", "service": "confighop-api", "api_version": "v1"}
    assert client.get("/api/v1/capabilities").json()["domains"]["switch"]["backend_enabled"] is False
    assert client.get("/api/v1/hardware-profiles").json()[0]["profile_status"] == "synthetic"
    assert "ethernet1/50" in client.get(f"/api/v1/hardware-profiles/{PROFILE_ID}").json()["interfaces"]
    project_id = project(client)
    uploaded = upload(client, project_id)
    assert uploaded.status_code == 200
    assert uploaded.json()["inventory_summary"]["physical_interfaces"] > 0
    assert uploaded.headers["Cache-Control"] == "no-store"
    assert uploaded.headers["X-Content-Type-Options"] == "nosniff"
    inventory = client.get(f"/api/v1/projects/{project_id}/inventory").json()
    assert "ethernet1/12" in {row["name"] for row in inventory["physical_interfaces"]}
    assert inventory["summary"]["subinterfaces"] > 0
    source = client.get(f"/api/v1/projects/{project_id}/source")
    assert source.content == FIXTURE.read_bytes()
    assert source.headers["Cache-Control"] == "no-store"
    profile(client, project_id)
    preview = client.post(f"/api/v1/projects/{project_id}/preview", json=mappings(), headers=MUTATION)
    assert preview.status_code == 200
    assert preview.json()["status"] == "READY"
    assert preview.json()["summary"]["derived_subinterface_mappings"] == 5
    assert client.get(f"/api/v1/projects/{project_id}/preview").json() == preview.json()
    candidate = client.post(f"/api/v1/projects/{project_id}/candidate", json=mappings(), headers=MUTATION)
    assert candidate.status_code == 200
    metadata = candidate.json()
    assert metadata["candidate_available"] is True
    assert metadata["validation"]["preservation_audit_ok"] is True
    assert "output_path" not in str(metadata)
    assert "workspace" not in str(metadata)
    assert client.get(f"/api/v1/projects/{project_id}/candidate").json() == metadata
    diff = client.get(f"/api/v1/projects/{project_id}/semantic-diff").json()
    assert any(change["new_value"] == "ethernet1/50" for change in diff["changes"])
    download = client.get(f"/api/v1/projects/{project_id}/candidate/download")
    assert download.status_code == 200
    assert download.headers["Cache-Control"] == "no-store"
    candidate_path = tmp_path / "candidate.xml"
    candidate_path.write_bytes(download.content)
    parsed = parse_palo_alto_xml(candidate_path)
    assert "ethernet1/50" in {item.name for item in parsed.physical_interfaces}


def test_collision_is_domain_response(api):
    client, _store = api
    project_id = project(client)
    source = FIXTURE.read_bytes().replace(b'<entry name="ethernet1/12">',
        b'<entry name="ethernet1/5"><layer3/></entry><entry name="ethernet1/12">', 1)
    assert upload(client, project_id, source).status_code == 200
    profile(client, project_id)
    response = client.post(f"/api/v1/projects/{project_id}/candidate", json=mappings("ethernet1/5"), headers=MUTATION)
    assert response.status_code == 200
    assert response.json()["candidate_available"] is False
    assert "TARGET_PHYSICAL_NAME_COLLISION" in {finding["code"] for finding in response.json()["findings"]}
    unavailable = client.get(f"/api/v1/projects/{project_id}/candidate/download")
    assert unavailable.status_code == 409
    assert unavailable.json()["error"]["code"] == "CANDIDATE_NOT_AVAILABLE"


def test_stream_limit_and_failed_replacement_are_transactional(api):
    client, store = api
    project_id = project(client)
    assert upload(client, project_id).status_code == 200
    old = client.get(f"/api/v1/projects/{project_id}/source").content
    store.max_source_bytes = 1024
    too_large = upload(client, project_id)
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "SOURCE_TOO_LARGE"
    assert client.get(f"/api/v1/projects/{project_id}/source").content == old
    store.max_source_bytes = 100 * 1024 * 1024
    secret = b"synthetic-secret-marker"
    invalid = upload(client, project_id, b"<config>" + secret)
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "SOURCE_PARSE_FAILED"
    assert secret.decode() not in invalid.text
    unsafe = upload(client, project_id, b'<!DOCTYPE config [<!ENTITY x "secret">]><config>&x;</config>')
    assert unsafe.status_code == 422
    assert "secret" not in unsafe.text
    assert client.get(f"/api/v1/projects/{project_id}/source").content == old
    assert not list(store.get(project_id).workspace.glob("upload-*.tmp"))


def test_filename_is_display_only_and_projects_are_isolated(api):
    client, store = api
    first, second = project(client), project(client)
    response = upload(client, first, filename="../../private.xml")
    assert response.status_code == 200
    assert response.json()["filename"] == "private.xml"
    assert store.get(first).source_path.name == "source.xml"
    assert client.get(f"/api/v1/projects/{second}/inventory").json()["error"]["code"] == "SOURCE_REQUIRED"
    assert client.get(f"/api/v1/projects/{second}/candidate/download").json()["error"]["code"] == "CANDIDATE_NOT_AVAILABLE"
    deleted = client.delete(f"/api/v1/projects/{first}", headers=MUTATION)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/projects/{first}").status_code == 404
    assert client.get(f"/api/v1/projects/{second}").status_code == 200


def test_source_and_profile_changes_invalidate_results(api):
    client, _store = api
    project_id = project(client)
    upload(client, project_id)
    profile(client, project_id)
    client.post(f"/api/v1/projects/{project_id}/candidate", json=mappings(), headers=MUTATION)
    assert client.get(f"/api/v1/projects/{project_id}").json()["candidate_available"] is True
    profile(client, project_id)
    state = client.get(f"/api/v1/projects/{project_id}").json()
    assert state["source_available"] is True
    assert state["preview_available"] is False
    assert state["candidate_available"] is False
    client.post(f"/api/v1/projects/{project_id}/candidate", json=mappings(), headers=MUTATION)
    assert upload(client, project_id).status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}/semantic-diff").status_code == 409


def test_client_header_and_cors(api):
    client, _store = api
    missing = client.post("/api/v1/projects")
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "CLIENT_HEADER_REQUIRED"
    allowed = client.options("/api/v1/projects", headers={"Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-confighop-client"})
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    denied = client.options("/api/v1/projects", headers={"Origin": "https://example.invalid",
        "Access-Control-Request-Method": "POST"})
    assert "Access-Control-Allow-Origin" not in denied.headers
