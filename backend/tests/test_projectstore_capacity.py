import asyncio
import re
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from confighop_api.main import create_app
from confighop_api.services import PROFILE_ID, ProjectStore, ServiceError, upload_source
from confighop_core import parse_palo_alto_xml
from confighop_core.models.mapping import InterfaceMapping


SOURCE = (Path(__file__).parent / 'fixtures' / 'paloalto' / 'pa_complex_synthetic.xml').read_bytes()
HEADERS = {'X-ConfigHop-Client': 'web'}
MiB = 1024 * 1024


def store(**settings):
    return ProjectStore(free_floor_bytes=0, **settings)


def create(client):
    response = client.post('/api/v1/projects', headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()['project_id']


def upload(client, project_id, data=SOURCE):
    return client.put(f'/api/v1/projects/{project_id}/source', content=data, headers=HEADERS)


def candidate(client, project_id):
    assert client.put(f'/api/v1/projects/{project_id}/target-profile',
        json={'profile_id': PROFILE_ID}, headers=HEADERS).status_code == 200
    return client.post(f'/api/v1/projects/{project_id}/candidate',
        json={'mappings': [{'source_interface': 'ethernet1/12', 'target_interface': 'ethernet1/50'}]},
        headers=HEADERS)


def test_two_projects_third_rejected_and_delete_reclaims_slot():
    capacity = store()
    with TestClient(create_app(capacity)) as client:
        first, second = create(client), create(client)
        denied = client.post('/api/v1/projects', headers=HEADERS)
        assert denied.status_code == 429 and denied.json()['error']['code'] == 'PROJECT_LIMIT_REACHED'
        assert client.delete(f'/api/v1/projects/{first}', headers=HEADERS).status_code == 204
        assert create(client) not in {first, second}


def test_shutdown_removes_owned_temporary_root():
    capacity = store()
    root = Path(capacity.root.name)
    with TestClient(create_app(capacity)) as client:
        project_id = create(client)
        assert upload(client, project_id).status_code == 200
        assert root.exists()
    assert not root.exists()


def test_workspace_creation_failure_has_stable_storage_error(monkeypatch):
    from confighop_api import services
    capacity = store()
    original = services.Path.mkdir
    def fail_project_mkdir(path, *args, **kwargs):
        if Path(path).parent == Path(capacity.root.name):
            raise OSError('synthetic disk failure')
        return original(path, *args, **kwargs)
    with TestClient(create_app(capacity)) as client:
        monkeypatch.setattr(services.Path, 'mkdir', fail_project_mkdir)
        denied = client.post('/api/v1/projects', headers=HEADERS)
        assert denied.status_code == 507
        assert denied.json()['error']['code'] == 'TEMP_STORAGE_UNAVAILABLE'
        assert 'synthetic' not in denied.text


def test_concurrent_creation_never_exceeds_cap():
    async def run():
        capacity = store()
        try:
            attempts = await asyncio.gather(*(capacity.create() for _ in range(8)), return_exceptions=True)
            assert sum(not isinstance(item, Exception) for item in attempts) == 2
            assert all(isinstance(item, ServiceError) and item.code == 'PROJECT_LIMIT_REACHED'
                for item in attempts[2:])
        finally:
            capacity.close()
    asyncio.run(run())


def test_exact_idle_boundary_and_active_operation():
    now = [0.0]
    async def run():
        capacity = store(clock=lambda: now[0])
        try:
            project = await capacity.create()
            now[0] = 24 * 60 * 60 - 1
            assert capacity.get(project.project_id) is project
            now[0] += 24 * 60 * 60
            async with project.lock:
                await capacity.reap_expired()
                assert project.workspace.exists()
                capacity.get(project.project_id)
            now[0] += 24 * 60 * 60
            with pytest.raises(ServiceError, match='expired') as error:
                capacity.get(project.project_id)
            assert error.value.code == 'PROJECT_EXPIRED'
            await capacity.reap_expired()
            assert not project.workspace.exists()
            assert len([p for p in capacity.projects.values() if not p.deleted]) == 0
        finally:
            capacity.close()
    asyncio.run(run())


def test_reservation_accepts_exact_byte_and_rejects_one_over():
    async def run():
        capacity = store(project_bytes=100, aggregate_bytes=100)
        try:
            project = await capacity.create()
            capacity.reserve(project, 100, 0, 0, 0)
            assert capacity.reservations[project.project_id] == 100
            with pytest.raises(ServiceError) as error:
                capacity.reserve(project, 101, 0, 0, 0)
            assert error.value.code == 'PROJECT_CAPACITY_EXCEEDED'
            capacity.project_bytes = 101
            with pytest.raises(ServiceError) as error:
                capacity.reserve(project, 101, 0, 0, 0)
            assert error.value.code == 'STORE_CAPACITY_EXCEEDED'
        finally:
            capacity.close()
    asyncio.run(run())


class StreamRequest:
    def __init__(self, data, pause=None, started=None):
        self.headers = {}
        self.data, self.pause, self.started = data, pause, started

    async def stream(self):
        yield self.data
        if self.started:
            self.started.set()
        if self.pause:
            await self.pause.wait()


def test_concurrent_uploads_reserve_aggregate_bytes():
    async def run(limit):
        capacity = store(aggregate_bytes=limit, project_bytes=2 * len(SOURCE))
        try:
            first, second = await capacity.create(), await capacity.create()
            results = await asyncio.gather(
                upload_source(capacity, first, StreamRequest(SOURCE), None),
                upload_source(capacity, second, StreamRequest(SOURCE), None),
                return_exceptions=True)
            assert sum(not isinstance(item, Exception) for item in results) == (2 if limit == 2 * len(SOURCE) else 1)
            if limit < 2 * len(SOURCE):
                assert any(isinstance(item, ServiceError) and item.code == 'STORE_CAPACITY_EXCEEDED' for item in results)
            assert capacity.reservations == {}
        finally:
            capacity.close()
    asyncio.run(run(2 * len(SOURCE)))
    asyncio.run(run(2 * len(SOURCE) - 1))


def test_replacement_quota_failure_retains_source_and_candidate():
    capacity = store()
    with TestClient(create_app(capacity)) as client:
        project_id = create(client)
        assert upload(client, project_id).status_code == 200
        rendered = candidate(client, project_id)
        assert rendered.status_code == 200 and rendered.json()['candidate_available']
        old_candidate = client.get(f'/api/v1/projects/{project_id}/candidate/download').content
        capacity.project_bytes = capacity.usage()[1][project_id] + len(SOURCE) - 1
        denied = upload(client, project_id)
        assert denied.status_code == 507 and denied.json()['error']['code'] == 'PROJECT_CAPACITY_EXCEEDED'
        assert client.get(f'/api/v1/projects/{project_id}/source').content == SOURCE
        assert client.get(f'/api/v1/projects/{project_id}/candidate/download').content == old_candidate
        assert not list(capacity.get(project_id).workspace.glob('upload-*.tmp'))
        assert capacity.reservations == {}


def test_smaller_and_larger_replacements_release_reservations():
    capacity = store()
    with TestClient(create_app(capacity)) as client:
        project_id = create(client)
        assert upload(client, project_id).status_code == 200
        smaller = SOURCE.rstrip()
        if smaller == SOURCE:
            smaller = SOURCE.replace(b'\n', b'', 1)
        assert upload(client, project_id, smaller).status_code == 200
        assert upload(client, project_id, SOURCE).status_code == 200
        assert client.get(f'/api/v1/projects/{project_id}/source').content == SOURCE
        assert capacity.usage()[1][project_id] == len(SOURCE)
        assert capacity.reservations == {}


def test_source_and_candidate_size_errors_are_gated():
    capacity = store(max_candidate_bytes=1)
    with TestClient(create_app(capacity)) as client:
        project_id = create(client)
        capacity.max_source_bytes = len(SOURCE) - 1
        oversize = upload(client, project_id)
        assert oversize.status_code == 413 and oversize.json()['error']['code'] == 'SOURCE_TOO_LARGE'
        capacity.max_source_bytes = 100 * MiB
        assert upload(client, project_id).status_code == 200
        denied = candidate(client, project_id)
        assert denied.status_code == 507 and denied.json()['error']['code'] == 'CANDIDATE_CAPACITY_EXCEEDED'
        assert client.get(f'/api/v1/projects/{project_id}/candidate/download').status_code == 409
        assert not capacity.get(project_id).candidate_path.exists()


def test_candidate_exact_output_boundary_and_one_byte_over():
    capacity = store()
    with TestClient(create_app(capacity)) as client:
        project_id = create(client)
        assert upload(client, project_id).status_code == 200
        first = candidate(client, project_id)
        assert first.status_code == 200 and first.json()['candidate_available']
        size = first.json()['candidate_size_bytes']
        capacity.max_candidate_bytes = size
        exact = candidate(client, project_id)
        assert exact.status_code == 200 and exact.json()['candidate_size_bytes'] == size
        capacity.max_candidate_bytes = size - 1
        over = candidate(client, project_id)
        assert over.status_code == 507 and over.json()['error']['code'] == 'CANDIDATE_CAPACITY_EXCEEDED'
        assert client.get(f'/api/v1/projects/{project_id}/candidate/download').status_code == 409


def test_candidate_growth_is_reserved_beyond_source_bytes():
    compact = re.sub(rb'>\s+<', b'><', SOURCE).replace(b' />', b'/>')
    capacity = store()
    with TestClient(create_app(capacity)) as client:
        project_id = create(client)
        assert upload(client, project_id, compact).status_code == 200
        rendered = candidate(client, project_id)
        assert rendered.status_code == 200 and rendered.json()['candidate_available']
        output_size = rendered.json()['candidate_size_bytes']
        assert output_size > len(compact)
        capacity.project_bytes = len(compact) + output_size - 1
        denied = candidate(client, project_id)
        assert denied.status_code == 507 and denied.json()['error']['code'] == 'PROJECT_CAPACITY_EXCEEDED'
        assert client.get(f'/api/v1/projects/{project_id}/candidate/download').status_code == 409


def test_candidate_validation_stages_inside_project(monkeypatch):
    from confighop_core.renderers.palo_alto import renderer
    original = renderer.tempfile.TemporaryDirectory
    locations = []
    def recorded(*args, **kwargs):
        locations.append(kwargs.get('dir'))
        return original(*args, **kwargs)
    monkeypatch.setattr(renderer.tempfile, 'TemporaryDirectory', recorded)
    capacity = store()
    with TestClient(create_app(capacity)) as client:
        project_id = create(client)
        assert upload(client, project_id).status_code == 200
        assert candidate(client, project_id).json()['candidate_available']
        project = capacity.get(project_id)
        assert Path(project.workspace) in [Path(value) for value in locations if value is not None]
        assert {item.name for item in project.workspace.iterdir()} == {'source.xml', 'candidate.xml'}


def test_disk_floor_and_failed_deletion_keep_accounting(monkeypatch):
    from confighop_api import services
    capacity = store()
    with TestClient(create_app(capacity)) as client:
        project_id = create(client)
        assert upload(client, project_id).status_code == 200
        original = services.shutil.disk_usage
        monkeypatch.setattr(services.shutil, 'disk_usage', lambda path: SimpleNamespace(free=0))
        denied = upload(client, project_id)
        assert denied.status_code == 507 and denied.json()['error']['code'] == 'TEMP_STORAGE_UNAVAILABLE'
        monkeypatch.setattr(services.shutil, 'disk_usage', original)
        assert client.get(f'/api/v1/projects/{project_id}/source').content == SOURCE
        before = capacity.usage()[0]
        original_delete = services.shutil.rmtree
        monkeypatch.setattr(services.shutil, 'rmtree', lambda path: (_ for _ in ()).throw(OSError('synthetic failure')))
        failed = client.delete(f'/api/v1/projects/{project_id}', headers=HEADERS)
        assert failed.status_code == 507 and failed.json()['error']['code'] == 'TEMP_STORAGE_UNAVAILABLE'
        assert capacity.projects[project_id].cleanup_debt
        assert capacity.usage()[0] >= before
        monkeypatch.setattr(services.shutil, 'rmtree', original_delete)


def test_partially_failed_deletion_keeps_predelete_accounting(monkeypatch):
    from confighop_api import services
    capacity = store(aggregate_bytes=len(SOURCE))
    with TestClient(create_app(capacity)) as client:
        project_id = create(client)
        assert upload(client, project_id).status_code == 200
        original_delete = services.shutil.rmtree
        def partial_delete(path):
            (Path(path) / 'source.xml').unlink()
            raise OSError('synthetic partial deletion')
        monkeypatch.setattr(services.shutil, 'rmtree', partial_delete)
        failed = client.delete(f'/api/v1/projects/{project_id}', headers=HEADERS)
        assert failed.status_code == 507
        assert capacity.usage()[0] == len(SOURCE)
        second = create(client)
        assert upload(client, second).status_code == 507
        assert not capacity.projects[project_id].workspace.joinpath('source.xml').exists()
        monkeypatch.setattr(services.shutil, 'rmtree', original_delete)


def test_cancelled_upload_removes_partial_file_and_reservation():
    async def run():
        capacity = store()
        pause, started = asyncio.Event(), asyncio.Event()
        try:
            project = await capacity.create()
            task = asyncio.create_task(upload_source(capacity, project, StreamRequest(SOURCE, pause, started), None))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert capacity.reservations == {}
            assert not list(project.workspace.glob('upload-*.tmp'))
            assert not project.source_path.exists()
        finally:
            capacity.close()
    asyncio.run(run())


def test_quota_accounting_failure_returns_stable_503(monkeypatch):
    capacity = store()
    with TestClient(create_app(capacity)) as client:
        project_id = create(client)
        monkeypatch.setattr(capacity, '_bytes', lambda path: (_ for _ in ()).throw(OSError('synthetic stat failure')))
        denied = upload(client, project_id)
        assert denied.status_code == 503 and denied.json()['error']['code'] == 'QUOTA_RESERVATION_UNAVAILABLE'
        assert 'synthetic' not in denied.text


def test_cancelled_render_waits_for_worker_and_removes_output(monkeypatch):
    from confighop_api import services
    mapping = InterfaceMapping(source_interface='ethernet1/12', target_interface='ethernet1/50')
    started, release = threading.Event(), threading.Event()
    def slow_render(*args, **kwargs):
        kwargs['reserve_output'](20)
        args[4].write_bytes(b'x' * 20)
        started.set()
        release.wait(5)
        return None
    monkeypatch.setattr(services, 'render_panos_candidate', slow_render)
    async def run():
        capacity = store()
        try:
            project = await capacity.create()
            project.source_path.write_bytes(SOURCE)
            project.inventory = parse_palo_alto_xml(project.source_path)
            project.profile_id = PROFILE_ID
            async def render():
                async with capacity.lock, project.lock:
                    return await services.generate_candidate(project, [mapping], False, capacity)
            task = asyncio.create_task(render())
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not project.candidate_path.exists()
            assert project.candidate is None and capacity.reservations == {}
        finally:
            release.set()
            capacity.close()
    asyncio.run(run())


def test_process_lock_rejects_second_worker_for_same_checkout():
    first, second = store(), store()
    try:
        first.acquire_process_lock()
        with pytest.raises(RuntimeError, match='Only one ConfigHop backend worker'):
            second.acquire_process_lock()
    finally:
        first.close()
        second.close()
