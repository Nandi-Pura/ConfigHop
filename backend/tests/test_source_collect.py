import asyncio
import hashlib
from pathlib import Path

import httpx
import pytest

from confighop_api.services import ProjectStore, ServiceError, collect_source_from_client, inventory_summary
from confighop_core import parse_palo_alto_xml


FIXTURE = Path(__file__).parent / "fixtures" / "paloalto" / "pa_complex_synthetic.xml"


def system_info(serial: str = "0123456789") -> bytes:
    return (f'<response status="success"><result><system><hostname>old-fw</hostname>'
        f'<serial>{serial}</serial><model>PA-5410</model><sw-version>11.1.2</sw-version>'
        f'</system></result></response>').encode()


def scripted_transport(documents: list[bytes]) -> httpx.MockTransport:
    responses = iter(documents)

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-PAN-KEY"] == "test-secret"
        assert "test-secret" not in str(request.url)
        return httpx.Response(200, content=next(responses))

    return httpx.MockTransport(responder)


def test_collect_promotes_stable_export_with_unverified_snapshot_kind():
    document = FIXTURE.read_bytes()
    store = ProjectStore()

    async def run():
        project = await store.create()
        async with httpx.AsyncClient(base_url="https://source.example.test/",
            transport=scripted_transport([system_info(), document, document, system_info()])) as client:
            result = await collect_source_from_client(store, project, client, "test-secret")
        assert project.source_path.read_bytes() == document
        assert project.source_provenance == result.provenance
        uploaded_inventory = parse_palo_alto_xml(FIXTURE)
        assert project.inventory.model_dump() == uploaded_inventory.model_dump()
        assert result.inventory_summary == inventory_summary(uploaded_inventory)
        assert result.provenance.origin == "API_COLLECTED"
        assert result.provenance.snapshot_kind == "UNVERIFIED"
        assert result.provenance.sha256 == hashlib.sha256(document).hexdigest()
        assert result.provenance.serial == "0123456789"
        assert result.provenance.model == "PA-5410"
        assert result.provenance.panos_version == "11.1.2"
        assert result.provenance.hostname == "old-fw"
        assert not list(project.workspace.glob("collect-*.tmp"))

    try:
        asyncio.run(run())
    finally:
        store.close()


@pytest.mark.parametrize("responses,code", [
    ([system_info(), b'<response status="error"><msg>denied</msg></response>'], "XML_API_RESPONSE_WRAPPER"),
    ([system_info(), FIXTURE.read_bytes(), b'<config><devices><entry name="different"/></devices></config>', system_info()], "SOURCE_CONFIG_CHANGED"),
    ([system_info(), FIXTURE.read_bytes(), FIXTURE.read_bytes(), system_info("different")], "SOURCE_IDENTITY_CHANGED"),
])
def test_failed_recollect_keeps_existing_source_and_provenance(responses, code):
    document = FIXTURE.read_bytes()
    store = ProjectStore()

    async def run():
        project = await store.create()
        async with httpx.AsyncClient(base_url="https://source.example.test/",
            transport=scripted_transport([system_info(), document, document, system_info()])) as client:
            await collect_source_from_client(store, project, client, "test-secret")
        prior = project.source_provenance
        prior_inventory = project.inventory
        async with httpx.AsyncClient(base_url="https://source.example.test/",
            transport=scripted_transport(responses)) as client:
            with pytest.raises(ServiceError) as error:
                await collect_source_from_client(store, project, client, "test-secret")
        assert error.value.code == code
        assert project.source_path.read_bytes() == document
        assert project.source_provenance == prior
        assert project.inventory is prior_inventory
        assert not list(project.workspace.glob("collect-*.tmp"))

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_collect_operation_timeout_keeps_existing_source():
    document = FIXTURE.read_bytes()
    store = ProjectStore()

    async def delayed_response(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(200, content=system_info())

    async def run():
        project = await store.create()
        async with httpx.AsyncClient(base_url="https://source.example.test/",
            transport=scripted_transport([system_info(), document, document, system_info()])) as client:
            await collect_source_from_client(store, project, client, "test-secret")
        prior = project.source_provenance
        async with httpx.AsyncClient(base_url="https://source.example.test/",
            transport=httpx.MockTransport(delayed_response)) as client:
            with pytest.raises(ServiceError) as error:
                await collect_source_from_client(store, project, client, "test-secret",
                    operation_timeout_seconds=0.001)
        assert error.value.code == "XML_API_OPERATION_TIMEOUT"
        assert error.value.status == 504
        assert project.source_path.read_bytes() == document
        assert project.source_provenance == prior

    try:
        asyncio.run(run())
    finally:
        store.close()
