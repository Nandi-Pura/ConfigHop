import asyncio
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from confighop_core.firewall_migration import FirewallMappings, generate_firewall
from confighop_core.models.firewall import FirewallCandidate, FirewallIR, Vendor
from confighop_core.parsers.fortios import MAX_FIREWALL_BYTES, parse_fortios
from confighop_core.parsers.panos_firewall import parse_panos_firewall

from .services import ServiceError


class FirewallSourceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_os: Vendor
    source_version: str = Field(max_length=32)
    text: str = Field(min_length=1, max_length=MAX_FIREWALL_BYTES)


class FirewallPreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    target_os: Vendor
    target_version: str = Field(max_length=32)
    mappings: FirewallMappings = Field(default_factory=FirewallMappings)


class FirewallExportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    acknowledge_review: bool = False


class FirewallProjectView(BaseModel):
    project_id: str
    revision: int
    inventory: FirewallIR


class FirewallPreviewView(BaseModel):
    project_id: str
    revision: int
    candidate: FirewallCandidate


class FirewallExportView(BaseModel):
    filename: str
    text: str
    sha256: str
    revision: int
    status: Literal['REVIEW_REQUIRED', 'READY_FOR_REVIEW']


@dataclass
class Session:
    inventory: FirewallIR
    touched: float = field(default_factory=monotonic)
    revision: int = 0
    target_os: Vendor | None = None
    candidate: FirewallCandidate | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def firewall_router() -> APIRouter:
    router = APIRouter(prefix='/api/v1/firewall-projects', tags=['Cross-vendor firewall migration'])
    sessions: dict[str, Session] = {}

    def get(project_id: str) -> Session:
        for key in list(sessions):
            if monotonic() - sessions[key].touched > 3600:
                del sessions[key]
        session = sessions.get(project_id)
        if session is None:
            raise ServiceError('PROJECT_NOT_FOUND', 'Firewall session expired or was not found. Upload the source again.', 404)
        session.touched = monotonic()
        return session

    @router.get('/platforms')
    async def platforms():
        return {'pairs': [{'source_os': 'fortios', 'target_os': 'panos'}, {'source_os': 'panos', 'target_os': 'fortios'}],
            'source_limit_bytes': MAX_FIREWALL_BYTES, 'deployment_verified': False}

    @router.post('', response_model=FirewallProjectView)
    async def inspect(body: FirewallSourceRequest):
        if body.source_version != ('7.4' if body.source_os == 'fortios' else '11.1'):
            raise ServiceError('UNSUPPORTED_VERSION', 'Cross-vendor source support is limited to FortiOS 7.4 and PAN-OS 11.1.', 400)
        get_expired = [key for key, session in sessions.items() if monotonic() - session.touched > 3600]
        for key in get_expired:
            del sessions[key]
        if len(sessions) >= 32:
            raise ServiceError('SESSION_LIMIT', 'Close an existing Firewall session before uploading another.', 429)
        try:
            inventory = parse_fortios(body.text, body.source_version) if body.source_os == 'fortios' else parse_panos_firewall(body.text, body.source_version)
        except (ValueError, OSError) as exc:
            raise ServiceError('INVALID_FIREWALL_SOURCE', 'The source configuration could not be parsed safely.', 400) from None
        except Exception as exc:
            from confighop_core.errors import ConfigParseError
            if isinstance(exc, ConfigParseError):
                raise ServiceError('INVALID_FIREWALL_SOURCE', 'The source XML is malformed or unsupported.', 400) from None
            raise
        project_id = str(uuid4())
        sessions[project_id] = Session(inventory=inventory)
        return FirewallProjectView(project_id=project_id, revision=0, inventory=inventory)

    @router.get('/{project_id}', response_model=FirewallProjectView)
    async def inventory(project_id: str):
        session = get(project_id)
        return FirewallProjectView(project_id=project_id, revision=session.revision, inventory=session.inventory)

    @router.delete('/{project_id}', status_code=204)
    async def delete(project_id: str):
        session = get(project_id)
        async with session.lock:
            sessions.pop(project_id, None)

    @router.put('/{project_id}/preview', response_model=FirewallPreviewView)
    async def preview(project_id: str, body: FirewallPreviewRequest):
        session = get(project_id)
        async with session.lock:
            if sessions.get(project_id) is not session:
                raise ServiceError('PROJECT_NOT_FOUND', 'Firewall session was removed.', 404)
            if body.revision <= session.revision:
                raise ServiceError('STALE_REVISION', 'Preview revision must be newer than the current session revision.', 409)
            if body.target_os == session.inventory.source_vendor:
                raise ServiceError('UNSUPPORTED_PAIR', 'Use the existing same-vendor workflow for this pair.', 400)
            if body.target_version != ('7.4' if body.target_os == 'fortios' else '11.1'):
                raise ServiceError('UNSUPPORTED_VERSION', 'Cross-vendor targets are limited to FortiOS 7.4 and PAN-OS 11.1.', 400)
            session.revision, session.candidate, session.target_os = body.revision, None, body.target_os
            candidate = generate_firewall(session.inventory, body.target_os, body.mappings, body.revision, body.target_version)
            session.candidate = candidate
            return FirewallPreviewView(project_id=project_id, revision=body.revision, candidate=candidate)

    @router.post('/{project_id}/export', response_model=FirewallExportView)
    async def export(project_id: str, body: FirewallExportRequest):
        session = get(project_id)
        async with session.lock:
            if sessions.get(project_id) is not session:
                raise ServiceError('PROJECT_NOT_FOUND', 'Firewall session was removed.', 404)
            candidate = session.candidate
            if not candidate or session.revision != body.revision or candidate.sha256 != body.sha256:
                raise ServiceError('STALE_CANDIDATE', 'Export requires the current preview revision and digest.', 409)
            if candidate.status in {'BLOCKED', 'INCOMPLETE'} or not candidate.text:
                raise ServiceError('CANDIDATE_BLOCKED', 'Resolve blocking findings before export.', 409)
            if candidate.status == 'REVIEW_REQUIRED' and not body.acknowledge_review:
                raise ServiceError('REVIEW_ACK_REQUIRED', 'Acknowledge current review findings before export.', 409)
            suffix = 'xml' if session.target_os == 'panos' else 'cfg'
            return FirewallExportView(filename=f'confighop-{session.target_os}-migration-candidate.{suffix}',
                text=candidate.text, sha256=candidate.sha256, revision=session.revision, status=candidate.status)

    return router
