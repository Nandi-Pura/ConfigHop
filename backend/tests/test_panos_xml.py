import asyncio
import ssl

import httpx
import pytest

from confighop_api.panos_xml import XmlApiError, create_source_client, export_configuration, read_system_info


def test_source_client_enforces_verified_direct_connection(monkeypatch):
    captured = {}

    def capture_client(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(httpx, "AsyncClient", capture_client)
    result = create_source_client("10.0.0.10", 443, allowed_endpoints={('10.0.0.10', 443)})
    assert result == captured
    assert captured["base_url"] == "https://10.0.0.10:443"
    assert captured["trust_env"] is False
    assert captured["follow_redirects"] is False
    assert captured["verify"].check_hostname is True
    assert captured["verify"].verify_mode == ssl.CERT_REQUIRED
    assert captured["timeout"].connect == 5.0
    assert captured["timeout"].read == 20.0
    assert captured["timeout"].write == 5.0
    assert captured["timeout"].pool == 5.0
    assert captured["limits"].max_connections == 1


def test_source_client_brackets_allowed_ipv6_literal(monkeypatch):
    captured = {}
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: captured.update(kwargs))
    create_source_client("fd00::10", 8443, allowed_endpoints={("fd00::10", 8443)})
    assert captured["base_url"] == "https://[fd00::10]:8443"


@pytest.mark.parametrize("host,port,allowed,code", [
    ("source.example.test", 443, {("source.example.test", 443)}, "XML_API_ENDPOINT_INVALID"),
    ("http://10.0.0.10", 443, {("10.0.0.10", 443)}, "XML_API_ENDPOINT_INVALID"),
    ("127.0.0.1", 443, {("127.0.0.1", 443)}, "XML_API_ENDPOINT_INVALID"),
    ("169.254.169.254", 443, {("169.254.169.254", 443)}, "XML_API_ENDPOINT_INVALID"),
    ("::1", 443, {("::1", 443)}, "XML_API_ENDPOINT_INVALID"),
    ("::ffff:127.0.0.1", 443, {("::ffff:127.0.0.1", 443)}, "XML_API_ENDPOINT_INVALID"),
    ("10.0.0.10", 443, {("10.0.0.11", 443)}, "XML_API_ENDPOINT_NOT_ALLOWED"),
    ("10.0.0.10", 443, {("10.0.0.10", 8443)}, "XML_API_ENDPOINT_NOT_ALLOWED"),
    ("10.0.0.10", 0, {("10.0.0.10", 0)}, "XML_API_ENDPOINT_INVALID"),
    ("10.0.0.10", 65536, {("10.0.0.10", 65536)}, "XML_API_ENDPOINT_INVALID"),
    ("10.0.0.10", True, {("10.0.0.10", True)}, "XML_API_ENDPOINT_INVALID"),
])
def test_source_client_rejects_unapproved_or_unsafe_endpoint(host, port, allowed, code):
    with pytest.raises(XmlApiError) as error:
        create_source_client(host, port, allowed_endpoints=allowed)
    assert error.value.code == code


def test_source_client_rejects_invalid_ca_without_content_in_error():
    invalid = "secret-invalid-ca"
    with pytest.raises(XmlApiError) as error:
        create_source_client("10.0.0.10", 443,
            allowed_endpoints={("10.0.0.10", 443)}, ca_pem=invalid)
    assert error.value.code == "XML_API_CA_INVALID"
    assert invalid not in str(error.value)


def export_with_response(response: httpx.Response, *, url: str = "https://source.example.test/",
    max_bytes: int = 1024) -> tuple[bytes, httpx.Request]:
    seen: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    async def run() -> bytes:
        async with httpx.AsyncClient(base_url=url, transport=httpx.MockTransport(responder)) as client:
            return await export_configuration(client, "test-secret", max_bytes=max_bytes)

    result = asyncio.run(run())
    return result, seen[0]


def test_export_uses_post_header_and_preserves_xml_bytes():
    document = b'<config version="11.1"><devices><entry name="test"/></devices></config>'
    result, request = export_with_response(httpx.Response(200, content=document))
    assert result == document
    assert request.method == "POST"
    assert request.url.path == "/api/"
    assert "test-secret" not in str(request.url)
    assert request.headers["X-PAN-KEY"] == "test-secret"
    assert dict(httpx.QueryParams(request.content.decode())) == {"type": "export", "category": "configuration"}


@pytest.mark.parametrize("response,code", [
    (httpx.Response(200, content=b'<response status="error"><msg>secret</msg></response>'), "XML_API_RESPONSE_WRAPPER"),
    (httpx.Response(200, content=b"<config>"), "XML_API_INVALID_EXPORT"),
    (httpx.Response(200, content=b'<!DOCTYPE config [<!ENTITY leak SYSTEM "file:///secret">]><config>&leak;</config>'), "XML_API_INVALID_EXPORT"),
    (httpx.Response(200, content=b"<foo/>"), "XML_API_INVALID_EXPORT"),
    (httpx.Response(200, content=b"<config/>"), "XML_API_INCOMPLETE_EXPORT"),
    (httpx.Response(302, headers={"Location": "https://other.example.test/api/"}), "XML_API_REDIRECT"),
    (httpx.Response(403, content=b"secret"), "XML_API_AUTH_FAILED"),
])
def test_export_rejects_untrusted_response_without_exposing_body(response, code):
    with pytest.raises(XmlApiError) as error:
        export_with_response(response)
    assert error.value.code == code
    assert "secret" not in str(error.value)


def test_export_enforces_streamed_size_limit():
    with pytest.raises(XmlApiError) as error:
        export_with_response(httpx.Response(200, content=b"<config>" + b"a" * 100 + b"</config>"), max_bytes=32)
    assert error.value.code == "XML_API_EXPORT_TOO_LARGE"


def test_export_maps_certificate_verification_failure_without_exposing_detail():
    def responder(request: httpx.Request) -> httpx.Response:
        try:
            raise ssl.SSLCertVerificationError("secret certificate detail")
        except ssl.SSLCertVerificationError as exc:
            raise httpx.ConnectError("secret transport detail", request=request) from exc

    async def run():
        async with httpx.AsyncClient(base_url="https://source.example.test/",
            transport=httpx.MockTransport(responder)) as client:
            await export_configuration(client, "test-secret")

    with pytest.raises(XmlApiError) as error:
        asyncio.run(run())
    assert error.value.code == "XML_API_TLS_FAILED"
    assert "secret" not in str(error.value)


def test_export_maps_interrupted_stream_without_partial_result():
    class InterruptedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'<config><devices><entry name="partial"/>'
            raise httpx.ReadError("secret stream detail")

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=InterruptedStream())

    async def run():
        async with httpx.AsyncClient(base_url="https://source.example.test/",
            transport=httpx.MockTransport(responder)) as client:
            await export_configuration(client, "test-secret")

    with pytest.raises(XmlApiError) as error:
        asyncio.run(run())
    assert error.value.code == "XML_API_TRANSPORT_ERROR"
    assert "secret" not in str(error.value)


def test_export_rejects_plain_http_before_transport_call():
    called = False

    def responder(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, content=b"<config/>")

    async def run():
        async with httpx.AsyncClient(base_url="http://source.example.test/",
            transport=httpx.MockTransport(responder)) as client:
            await export_configuration(client, "test-secret")

    with pytest.raises(XmlApiError) as error:
        asyncio.run(run())
    assert error.value.code == "XML_API_TLS_REQUIRED"
    assert not called


def test_system_info_reads_required_identity_without_key_in_url():
    seen: list[httpx.Request] = []
    document = (b'<response status="success"><result><system><hostname>old-fw</hostname>'
        b'<serial>0123456789</serial><model>PA-5410</model><sw-version>11.1.2</sw-version>'
        b'</system></result></response>')

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=document)

    async def run():
        async with httpx.AsyncClient(base_url="https://source.example.test/",
            transport=httpx.MockTransport(responder)) as client:
            return await read_system_info(client, "test-secret")

    identity = asyncio.run(run())
    assert (identity.hostname, identity.serial, identity.model, identity.panos_version) == (
        "old-fw", "0123456789", "PA-5410", "11.1.2")
    assert dict(httpx.QueryParams(seen[0].content.decode())) == {
        "type": "op", "cmd": "<show><system><info></info></system></show>"}
    assert "test-secret" not in str(seen[0].url)


@pytest.mark.parametrize("document,code", [
    (b'<response status="error"><msg>secret</msg></response>', "XML_API_SYSTEM_INFO_FAILED"),
    (b'<response status="success"><result><system><serial>1</serial></system></result></response>', "XML_API_INVALID_SYSTEM_INFO"),
    (b'<response status="success"><result/></response>', "XML_API_INVALID_SYSTEM_INFO"),
    (b'<response', "XML_API_INVALID_SYSTEM_INFO"),
])
def test_system_info_rejects_bad_response_without_exposing_body(document, code):
    async def run():
        async with httpx.AsyncClient(base_url="https://source.example.test/",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=document))) as client:
            await read_system_info(client, "test-secret")

    with pytest.raises(XmlApiError) as error:
        asyncio.run(run())
    assert error.value.code == code
    assert "secret" not in str(error.value)
