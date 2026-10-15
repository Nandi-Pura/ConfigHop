from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from confighop_api.main import _source_endpoints, create_app
from confighop_api.services import ProjectStore

MUTATION = {"X-ConfigHop-Client": "web"}
ENDPOINT = ("10.0.0.10", 443)
FIXTURE = Path(__file__).parent / "fixtures" / "paloalto" / "pa_complex_synthetic.xml"


def system_info() -> bytes:
    return (b'<response status="success"><result><system><hostname>old-fw</hostname>'
        b'<serial>0123456789</serial><model>PA-5410</model><sw-version>11.1.2</sw-version>'
        b'</system></result></response>')


def scripted_transport(documents: list[bytes]) -> httpx.MockTransport:
    responses = iter(documents)

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-PAN-KEY"] == "test-secret"
        return httpx.Response(200, content=next(responses))

    return httpx.MockTransport(responder)


def create_project(client: TestClient) -> str:
    response = client.post("/api/v1/projects", headers=MUTATION)
    assert response.status_code == 200
    return response.json()["project_id"]


def collect_body(api_key: str = "test-secret") -> dict:
    return {"host": ENDPOINT[0], "port": ENDPOINT[1], "api_key": api_key}


def test_source_endpoint_configuration_parses_ipv4_and_ipv6():
    assert _source_endpoints("10.0.0.10:443, [fd00::10]:8443") == {
        ("10.0.0.10", 443), ("fd00::10", 8443)}


@pytest.mark.parametrize("value", ["hostname.example:443", "127.0.0.1:443", "10.0.0.10", "10.0.0.10:0"])
def test_source_endpoint_configuration_rejects_unsafe_or_invalid_entries(value):
    with pytest.raises(ValueError, match="Invalid CONFIGHOP_SOURCE_ENDPOINTS entry"):
        _source_endpoints(value)


def test_collect_endpoint_is_disabled_without_server_allowlist():
    store = ProjectStore()
    with TestClient(create_app(store, allowed_source_endpoints=set())) as client:
        project_id = create_project(client)
        response = client.post(f"/api/v1/projects/{project_id}/source/collect",
            json=collect_body("secret-disabled-key"), headers=MUTATION)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "XML_API_ENDPOINT_NOT_ALLOWED"
        assert "secret-disabled-key" not in response.text
        assert client.get("/api/v1/capabilities").json()["domains"]["firewall"]["panos_xml_api_collect"] is False
        assert client.get(f"/api/v1/projects/{project_id}").json()["source_available"] is False


def test_collect_endpoint_rejects_invalid_ca_without_echoing_it():
    store = ProjectStore()
    with TestClient(create_app(store, allowed_source_endpoints={ENDPOINT})) as client:
        project_id = create_project(client)
        body = collect_body("secret-ca-key")
        body["ca_certificate_pem"] = "secret-invalid-ca"
        response = client.post(f"/api/v1/projects/{project_id}/source/collect",
            json=body, headers=MUTATION)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "XML_API_CA_INVALID"
        assert "secret" not in response.text


def test_collect_endpoint_rejects_empty_api_key_without_echoing_request():
    store = ProjectStore()
    with TestClient(create_app(store, allowed_source_endpoints={ENDPOINT})) as client:
        project_id = create_project(client)
        response = client.post(f"/api/v1/projects/{project_id}/source/collect",
            json=collect_body(""), headers=MUTATION)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"
        assert "api_key" not in response.text


def test_collect_endpoint_promotes_source_without_persisting_api_key(monkeypatch):
    document = FIXTURE.read_bytes()
    captured = {}

    def fake_client(host, port, *, allowed_endpoints, ca_pem):
        captured.update(host=host, port=port, allowed_endpoints=allowed_endpoints, ca_pem=ca_pem)
        return httpx.AsyncClient(base_url=f"https://{host}:{port}",
            transport=scripted_transport([system_info(), document, document, system_info()]))

    monkeypatch.setattr("confighop_api.services.create_source_client", fake_client)
    store = ProjectStore()
    with TestClient(create_app(store, allowed_source_endpoints={ENDPOINT})) as client:
        project_id = create_project(client)
        response = client.post(f"/api/v1/projects/{project_id}/source/collect",
            json=collect_body(), headers=MUTATION)
        assert response.status_code == 200
        assert response.json()["provenance"]["origin"] == "API_COLLECTED"
        assert response.json()["provenance"]["serial"] == "0123456789"
        assert captured == {"host": ENDPOINT[0], "port": ENDPOINT[1],
            "allowed_endpoints": {ENDPOINT}, "ca_pem": None}
        assert client.get("/api/v1/capabilities").json()["domains"]["firewall"]["panos_xml_api_collect"] is True
        assert "test-secret" not in response.text
        assert "test-secret" not in repr(store.get(project_id))


def test_connection_test_reads_identity_without_changing_project(monkeypatch):
    captured = {}

    def fake_client(host, port, *, allowed_endpoints, ca_pem):
        captured.update(host=host, port=port, allowed_endpoints=allowed_endpoints, ca_pem=ca_pem)
        return httpx.AsyncClient(base_url=f"https://{host}:{port}",
            transport=scripted_transport([system_info()]))

    monkeypatch.setattr("confighop_api.services.create_source_client", fake_client)
    store = ProjectStore()
    with TestClient(create_app(store, allowed_source_endpoints={ENDPOINT})) as client:
        project_id = create_project(client)
        response = client.post(f"/api/v1/projects/{project_id}/source/connection/test",
            json=collect_body(), headers=MUTATION)
        assert response.status_code == 200
        assert response.json()["host"] == ENDPOINT[0]
        assert response.json()["port"] == ENDPOINT[1]
        assert response.json()["tls_verification"] == "CA_VERIFIED"
        assert response.json()["identity"] == {"hostname": "old-fw", "serial": "0123456789",
            "model": "PA-5410", "panos_version": "11.1.2"}
        assert response.json()["tested_at_utc"].endswith("Z")
        assert client.get(f"/api/v1/projects/{project_id}").json()["source_available"] is False
        assert "test-secret" not in response.text
        assert "test-secret" not in repr(store.get(project_id))


def test_failed_collect_endpoint_keeps_uploaded_source(monkeypatch):
    def denied_client(host, port, *, allowed_endpoints, ca_pem):
        return httpx.AsyncClient(base_url=f"https://{host}:{port}",
            transport=httpx.MockTransport(lambda _request: httpx.Response(403, content=b"secret response")))

    monkeypatch.setattr("confighop_api.services.create_source_client", denied_client)
    store = ProjectStore()
    with TestClient(create_app(store, allowed_source_endpoints={ENDPOINT})) as client:
        project_id = create_project(client)
        uploaded = client.put(f"/api/v1/projects/{project_id}/source", content=FIXTURE.read_bytes(),
            headers={**MUTATION, "Content-Type": "application/xml", "X-ConfigHop-Filename": "before.xml"})
        assert uploaded.status_code == 200
        prior_provenance = uploaded.json()["provenance"]

        response = client.post(f"/api/v1/projects/{project_id}/source/collect",
            json=collect_body("secret-denied-key"), headers=MUTATION)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "XML_API_AUTH_FAILED"
        assert "secret" not in response.text
        assert client.get(f"/api/v1/projects/{project_id}/source").content == FIXTURE.read_bytes()
        assert client.get(f"/api/v1/projects/{project_id}/source/provenance").json() == prior_provenance
