from dataclasses import dataclass
import hashlib
import ipaddress
import re
import ssl
from collections.abc import Collection
from typing import Literal

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from confighop_core.parsers.palo_alto.parser import MAX_XML_BYTES


class XmlApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DeviceIdentity:
    hostname: str
    serial: str
    model: str
    panos_version: str
    multi_vsys: bool | None = None
    operational_mode: str | None = None


@dataclass(frozen=True)
class OperationReceipt:
    response_sha256: str
    job_id: str | None = None


@dataclass(frozen=True)
class JobResult:
    job_id: str
    state: Literal["PENDING", "SUCCEEDED", "FAILED"]
    response_sha256: str


def _endpoint_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if not isinstance(host, str):
        raise XmlApiError("XML_API_ENDPOINT_INVALID", "The device endpoint must be an IP address.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise XmlApiError("XML_API_ENDPOINT_INVALID", "The device endpoint must be an IP address.") from exc
    if (getattr(address, "scope_id", None) is not None
        or getattr(address, "ipv4_mapped", None) is not None
        or address.is_loopback or address.is_link_local
        or address.is_multicast or address.is_unspecified):
        raise XmlApiError("XML_API_ENDPOINT_INVALID", "The device endpoint uses a disallowed IP address.")
    return address


def normalize_source_endpoint(host: str, port: int) -> tuple[str, int]:
    address = _endpoint_ip(host)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise XmlApiError("XML_API_ENDPOINT_INVALID", "The device endpoint has an invalid port.")
    return str(address), port


def create_source_client(host: str, port: int, *,
    allowed_endpoints: Collection[tuple[str, int]], ca_pem: str | None = None) -> httpx.AsyncClient:
    """Create a direct HTTPS client for one explicitly allowed firewall endpoint."""
    normalized_host, port = normalize_source_endpoint(host, port)
    allowed = {normalize_source_endpoint(ip, allowed_port) for ip, allowed_port in allowed_endpoints}
    if (normalized_host, port) not in allowed:
        raise XmlApiError("XML_API_ENDPOINT_NOT_ALLOWED", "The device endpoint is not allowed.")

    try:
        tls = ssl.create_default_context()
        if ca_pem is not None:
            tls.load_verify_locations(cadata=ca_pem)
    except (OSError, ssl.SSLError, ValueError) as exc:
        raise XmlApiError("XML_API_CA_INVALID", "The device CA certificate could not be loaded.") from exc
    address = ipaddress.ip_address(normalized_host)
    authority = f"[{address}]" if address.version == 6 else str(address)
    return httpx.AsyncClient(
        base_url=f"https://{authority}:{port}",
        verify=tls,
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0),
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
    )


def create_target_client(host: str, port: int, *,
    allowed_endpoints: Collection[tuple[str, int]], ca_pem: str | None = None) -> httpx.AsyncClient:
    return create_source_client(host, port, allowed_endpoints=allowed_endpoints, ca_pem=ca_pem)


async def _request_bytes(client: httpx.AsyncClient, api_key: str, payload: dict[str, str], *,
    max_bytes: int) -> bytes:
    if not api_key:
        raise XmlApiError("XML_API_KEY_REQUIRED", "A device API key is required.")
    if client.base_url.scheme != "https":
        raise XmlApiError("XML_API_TLS_REQUIRED", "The device API endpoint must use HTTPS.")
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")

    try:
        async with client.stream("POST", "/api/", data=payload,
            headers={"X-PAN-KEY": api_key, "Accept-Encoding": "identity"}, follow_redirects=False) as response:
            if response.is_redirect:
                raise XmlApiError("XML_API_REDIRECT", "The device API redirected the request.")
            if response.status_code in {401, 403}:
                raise XmlApiError("XML_API_AUTH_FAILED", "The device API rejected the API key or its permissions.")
            if response.status_code != 200:
                raise XmlApiError("XML_API_HTTP_ERROR", "The device API rejected the request.")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise XmlApiError("XML_API_EXPORT_TOO_LARGE", "The API response exceeds the size limit.")
                chunks.append(chunk)
    except httpx.TimeoutException as exc:
        raise XmlApiError("XML_API_TIMEOUT", "The device API request timed out.") from exc
    except httpx.TransportError as exc:
        cause: BaseException | None = exc
        while cause is not None:
            if isinstance(cause, ssl.SSLCertVerificationError):
                raise XmlApiError("XML_API_TLS_FAILED", "The device TLS certificate could not be verified.") from exc
            cause = cause.__cause__
        raise XmlApiError("XML_API_TRANSPORT_ERROR", "The device API connection failed.") from exc
    return b"".join(chunks)


async def _request_multipart(client: httpx.AsyncClient, api_key: str,
    payload: dict[str, str], filename: str, content: bytes, *, max_bytes: int) -> bytes:
    if not api_key:
        raise XmlApiError("XML_API_KEY_REQUIRED", "A device API key is required.")
    if client.base_url.scheme != "https":
        raise XmlApiError("XML_API_TLS_REQUIRED", "The device API endpoint must use HTTPS.")
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    try:
        async with client.stream("POST", "/api/", data=payload,
            files={"file": (filename, content, "application/xml")},
            headers={"X-PAN-KEY": api_key, "Accept-Encoding": "identity"},
            follow_redirects=False) as response:
            if response.is_redirect:
                raise XmlApiError("XML_API_REDIRECT", "The device API redirected the request.")
            if response.status_code in {401, 403}:
                raise XmlApiError("XML_API_AUTH_FAILED", "The device API rejected the API key or its permissions.")
            if response.status_code != 200:
                raise XmlApiError("XML_API_HTTP_ERROR", "The device API rejected the request.")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise XmlApiError("XML_API_RESPONSE_TOO_LARGE", "The API response exceeds the size limit.")
                chunks.append(chunk)
    except httpx.TimeoutException as exc:
        raise XmlApiError("XML_API_TIMEOUT", "The device API request timed out.") from exc
    except httpx.TransportError as exc:
        cause: BaseException | None = exc
        while cause is not None:
            if isinstance(cause, ssl.SSLCertVerificationError):
                raise XmlApiError("XML_API_TLS_FAILED", "The device TLS certificate could not be verified.") from exc
            cause = cause.__cause__
        raise XmlApiError("XML_API_TRANSPORT_ERROR", "The device API connection failed.") from exc
    return b"".join(chunks)


def _success_response(document: bytes, *, invalid_code: str, failed_code: str):
    try:
        root = ElementTree.fromstring(document)
    except (ElementTree.ParseError, DefusedXmlException, ValueError) as exc:
        raise XmlApiError(invalid_code, "The target API returned invalid operation XML.") from exc
    if root.tag != "response" or root.get("status") != "success":
        raise XmlApiError(failed_code, "The target API rejected the operation.")
    result = root.find("./result")
    if result is None:
        raise XmlApiError(invalid_code, "The target API omitted the operation result.")
    return root, result


def _receipt(document: bytes, *, invalid_code: str, failed_code: str,
    allow_job: bool = False) -> OperationReceipt:
    _, result = _success_response(document, invalid_code=invalid_code, failed_code=failed_code)
    job_id = (result.findtext("./job") or "").strip() or None
    if job_id is not None and (not allow_job or not job_id.isdigit() or len(job_id) > 32):
        raise XmlApiError(invalid_code, "The target API returned an invalid job identifier.")
    has_message = bool("".join(result.itertext()).strip())
    if job_id is None and not has_message:
        raise XmlApiError(invalid_code, "The target API returned an empty operation result.")
    return OperationReceipt(hashlib.sha256(document).hexdigest(), job_id)


async def import_configuration(client: httpx.AsyncClient, api_key: str, *,
    filename: str, content: bytes) -> OperationReceipt:
    if not re.fullmatch(r"confighop-[0-9a-f-]{36}\.xml", filename):
        raise ValueError("Import filename is invalid")
    document = await _request_multipart(client, api_key,
        {"type": "import", "category": "configuration"}, filename, content,
        max_bytes=1024 * 1024)
    return _receipt(document, invalid_code="XML_API_INVALID_IMPORT",
        failed_code="XML_API_IMPORT_FAILED")


async def load_configuration(client: httpx.AsyncClient, api_key: str, *,
    filename: str) -> OperationReceipt:
    if not re.fullmatch(r"confighop-[0-9a-f-]{36}\.xml", filename):
        raise ValueError("Load filename is invalid")
    document = await _request_bytes(client, api_key,
        {"type": "op", "cmd": f"<load><config><from>{filename}</from></config></load>"},
        max_bytes=1024 * 1024)
    return _receipt(document, invalid_code="XML_API_INVALID_LOAD",
        failed_code="XML_API_LOAD_FAILED")


async def validate_full(client: httpx.AsyncClient, api_key: str) -> OperationReceipt:
    document = await _request_bytes(client, api_key,
        {"type": "op", "cmd": "<validate><full></full></validate>"},
        max_bytes=1024 * 1024)
    return _receipt(document, invalid_code="XML_API_INVALID_VALIDATION",
        failed_code="XML_API_VALIDATION_FAILED", allow_job=True)


async def read_job(client: httpx.AsyncClient, api_key: str, job_id: str) -> JobResult:
    if not job_id.isdigit() or len(job_id) > 32:
        raise ValueError("Job identifier is invalid")
    document = await _request_bytes(client, api_key,
        {"type": "op", "cmd": f"<show><jobs><id>{job_id}</id></jobs></show>"},
        max_bytes=1024 * 1024)
    _, result = _success_response(document, invalid_code="XML_API_INVALID_JOB",
        failed_code="XML_API_JOB_FAILED")
    job = result.find("./job")
    if job is None or (job.findtext("id") or "").strip() != job_id:
        raise XmlApiError("XML_API_INVALID_JOB", "The target API returned a different job.")
    status = (job.findtext("status") or "").strip().upper()
    outcome = (job.findtext("result") or "").strip().upper()
    if status in {"PEND", "ACT"}:
        state: Literal["PENDING", "SUCCEEDED", "FAILED"] = "PENDING"
    elif status == "FIN" and outcome == "OK":
        state = "SUCCEEDED"
    elif status == "FIN" and outcome in {"FAIL", "WARN"}:
        state = "FAILED"
    else:
        raise XmlApiError("XML_API_INVALID_JOB", "The target API returned an unrecognized job state.")
    return JobResult(job_id, state, hashlib.sha256(document).hexdigest())


async def export_configuration(client: httpx.AsyncClient, api_key: str, *,
    max_bytes: int = MAX_XML_BYTES) -> bytes:
    """Fetch a configuration export; the running/candidate meaning needs lab verification."""
    document = await _request_bytes(client, api_key, {"type": "export", "category": "configuration"},
        max_bytes=max_bytes)

    try:
        root = ElementTree.fromstring(document)
    except (ElementTree.ParseError, DefusedXmlException, ValueError) as exc:
        raise XmlApiError("XML_API_INVALID_EXPORT", "The source API did not return valid XML.") from exc
    if root.tag == "response":
        raise XmlApiError("XML_API_RESPONSE_WRAPPER", "The source API returned a response instead of a configuration file.")
    if root.tag != "config":
        raise XmlApiError("XML_API_INVALID_EXPORT", "The source API did not return a configuration file.")
    if root.find("./devices/entry") is None:
        raise XmlApiError("XML_API_INCOMPLETE_EXPORT", "The configuration export omitted the device entry.")
    return document


async def _read_configuration(client: httpx.AsyncClient, api_key: str, *,
    action: Literal["show", "get"], max_bytes: int) -> bytes:
    invalid_code = "XML_API_INVALID_RUNNING_CONFIG" if action == "show" else "XML_API_INVALID_CANDIDATE_CONFIG"
    failed_code = "XML_API_RUNNING_CONFIG_FAILED" if action == "show" else "XML_API_CANDIDATE_CONFIG_FAILED"
    document = await _request_bytes(client, api_key,
        {"type": "config", "action": action, "xpath": "/config"}, max_bytes=max_bytes)
    try:
        root = ElementTree.fromstring(document)
    except (ElementTree.ParseError, DefusedXmlException, ValueError) as exc:
        raise XmlApiError(invalid_code, "The target API returned invalid configuration XML.") from exc
    if root.tag != "response" or root.get("status") != "success":
        raise XmlApiError(failed_code, "The target API did not return configuration.")
    config = root.find("./result/config")
    if config is None or config.find("./devices/entry") is None:
        raise XmlApiError(invalid_code, "The target API omitted the device configuration.")
    return ElementTree.tostring(config, encoding="utf-8")


async def read_running_configuration(client: httpx.AsyncClient, api_key: str, *,
    max_bytes: int = MAX_XML_BYTES) -> bytes:
    return await _read_configuration(client, api_key, action="show", max_bytes=max_bytes)


async def read_candidate_configuration(client: httpx.AsyncClient, api_key: str, *,
    max_bytes: int = MAX_XML_BYTES) -> bytes:
    return await _read_configuration(client, api_key, action="get", max_bytes=max_bytes)


PreflightProbe = Literal["change_summary", "commit_locks", "pending_jobs"]
_PREFLIGHT_COMMANDS = {
    "change_summary": "<show><config><list><change-summary/></list></config></show>",
    "commit_locks": "<show><commit-locks/></show>",
    "pending_jobs": "<show><jobs><pending/></jobs></show>",
}


async def read_preflight_probe(client: httpx.AsyncClient, api_key: str,
    probe: PreflightProbe) -> bool:
    document = await _request_bytes(client, api_key,
        {"type": "op", "cmd": _PREFLIGHT_COMMANDS[probe]}, max_bytes=1024 * 1024)
    try:
        root = ElementTree.fromstring(document)
    except (ElementTree.ParseError, DefusedXmlException, ValueError) as exc:
        raise XmlApiError("XML_API_INVALID_PREFLIGHT", "The target API returned invalid preflight XML.") from exc
    if root.tag != "response" or root.get("status") != "success":
        raise XmlApiError("XML_API_PREFLIGHT_FAILED", "The target API rejected a read-only preflight check.")
    result = root.find("./result")
    if result is None:
        raise XmlApiError("XML_API_INVALID_PREFLIGHT", "The target API omitted preflight results.")
    return not len(result) and not (result.text or "").strip()


async def read_change_summary(client: httpx.AsyncClient, api_key: str) -> bytes:
    document = await _request_bytes(client, api_key,
        {"type": "op", "cmd": _PREFLIGHT_COMMANDS["change_summary"]}, max_bytes=1024 * 1024)
    _, result = _success_response(document, invalid_code="XML_API_INVALID_CHANGE_SUMMARY",
        failed_code="XML_API_CHANGE_SUMMARY_FAILED")
    if not len(result) and not (result.text or "").strip():
        return b""
    return ElementTree.tostring(result, encoding="utf-8")


async def read_system_info(client: httpx.AsyncClient, api_key: str) -> DeviceIdentity:
    document = await _request_bytes(client, api_key,
        {"type": "op", "cmd": "<show><system><info></info></system></show>"}, max_bytes=1024 * 1024)
    try:
        root = ElementTree.fromstring(document)
    except (ElementTree.ParseError, DefusedXmlException, ValueError) as exc:
        raise XmlApiError("XML_API_INVALID_SYSTEM_INFO", "The source API returned invalid system information.") from exc
    if root.tag != "response" or root.get("status") != "success":
        raise XmlApiError("XML_API_SYSTEM_INFO_FAILED", "The source API did not return successful system information.")
    system = root.find("./result/system")
    if system is None:
        raise XmlApiError("XML_API_INVALID_SYSTEM_INFO", "The source API omitted system information.")

    values: list[str] = []
    for field in ("hostname", "serial", "model", "sw-version"):
        value = (system.findtext(field) or "").strip()
        if not value or len(value) > 128:
            raise XmlApiError("XML_API_INVALID_SYSTEM_INFO", "The source API omitted a required device identity field.")
        values.append(value)
    multi_vsys_text = (system.findtext("multi-vsys") or "").strip().lower()
    if multi_vsys_text in {"on", "yes", "true"}:
        multi_vsys = True
    elif multi_vsys_text in {"off", "no", "false"}:
        multi_vsys = False
    elif multi_vsys_text:
        raise XmlApiError("XML_API_INVALID_SYSTEM_INFO",
            "The source API returned an unrecognized multi-vsys state.")
    else:
        multi_vsys = None
    operational_mode = (system.findtext("operational-mode") or "").strip() or None
    if operational_mode is not None and len(operational_mode) > 128:
        raise XmlApiError("XML_API_INVALID_SYSTEM_INFO",
            "The source API returned an invalid operational mode.")
    return DeviceIdentity(*values, multi_vsys=multi_vsys, operational_mode=operational_mode)
