import asyncio
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from confighop_core.models.switch_migration import SwitchCandidate, SwitchMigrationIR
from confighop_core.parsers.cisco_iosxe.migration import MAX_SWITCH_BYTES, parse_migration
from confighop_core.switch_migration import render_switch
from .services import ServiceError


class SourceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_os: Literal['IOS_XE']
    source_version: str = Field(max_length=32)
    text: str = Field(min_length=1, max_length=MAX_SWITCH_BYTES)


class SwitchPreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    target_os: Literal['AOS_CX']
    target_version: str = Field(max_length=32)
    capability_id: Literal['hpe-aruba-jl663a'] | None = None
    mappings: dict[str, StrictInt] = Field(default_factory=dict, max_length=48)


class SwitchExportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    acknowledge_review: bool = False


class SwitchProjectView(BaseModel):
    project_id: str
    revision: int
    inventory: SwitchMigrationIR
    settings: SwitchPreviewRequest | None = None


class SwitchPreviewView(BaseModel):
    project_id: str
    revision: int
    candidate: SwitchCandidate


class SwitchExportView(BaseModel):
    filename: str = 'confighop-aos-cx-candidate.cfg'
    text: str
    sha256: str
    revision: int


@dataclass
class Session:
    inventory: SwitchMigrationIR
    touched: float = field(default_factory=monotonic)
    revision: int = 0
    settings: SwitchPreviewRequest | None = None
    candidate: SwitchCandidate | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def switch_router() -> APIRouter:
    router = APIRouter(prefix='/api/v1/switch-projects', tags=['Limited Switch migration v1'])
    sessions: dict[str, Session] = {}

    def get(project_id):
        for key in list(sessions):
            if monotonic() - sessions[key].touched > 3600:
                del sessions[key]
        session = sessions.get(project_id)
        if session is None:
            raise ServiceError('PROJECT_NOT_FOUND', 'Switch session expired or was not found. Upload the source again.', 404)
        session.touched = monotonic()
        return session

    def view(project_id, session):
        return SwitchProjectView(project_id=project_id, revision=session.revision, inventory=session.inventory, settings=session.settings)

    @router.post('', response_model=SwitchProjectView)
    async def inspect(body: SourceRequest):
        for key in list(sessions):
            if monotonic() - sessions[key].touched > 3600:
                del sessions[key]
        if len(sessions) >= 32:
            raise ServiceError('SESSION_LIMIT', 'Close an existing Switch session before uploading another.', 429)
        try:
            inventory = parse_migration(body.text, body.source_version)
        except ValueError:
            raise ServiceError('INVALID_SWITCH_SOURCE', 'Expected a plain-text IOS XE source within the 2 MB and 20,000-line limits.', 400) from None
        project_id = str(uuid4())
        sessions[project_id] = Session(inventory=inventory)
        return view(project_id, sessions[project_id])

    @router.get('/{project_id}', response_model=SwitchProjectView)
    async def inventory(project_id: str):
        return view(project_id, get(project_id))

    @router.delete('/{project_id}', status_code=204)
    async def delete(project_id: str):
        session = get(project_id)
        async with session.lock:
            sessions.pop(project_id, None)

    @router.put('/{project_id}/preview', response_model=SwitchPreviewView)
    async def preview(project_id: str, body: SwitchPreviewRequest):
        session = get(project_id)
        async with session.lock:
            if sessions.get(project_id) is not session:
                raise ServiceError('PROJECT_NOT_FOUND', 'Switch session was removed.', 404)
            if body.revision <= session.revision:
                raise ServiceError('STALE_REVISION', 'Preview revision must be newer than the current session revision.', 409)
            session.revision, session.candidate, session.settings = body.revision, None, body
            candidate = render_switch(session.inventory, body.mappings, body.target_version, body.capability_id)
            session.candidate = candidate
            return SwitchPreviewView(project_id=project_id, revision=session.revision, candidate=candidate)

    @router.post('/{project_id}/export', response_model=SwitchExportView)
    async def export(project_id: str, body: SwitchExportRequest):
        session = get(project_id)
        async with session.lock:
            if sessions.get(project_id) is not session:
                raise ServiceError('PROJECT_NOT_FOUND', 'Switch session was removed.', 404)
            candidate = session.candidate
            if not candidate or session.revision != body.revision or candidate.sha256 != body.sha256:
                raise ServiceError('STALE_CANDIDATE', 'Export requires the current preview revision and digest.', 409)
            if candidate.status == 'BLOCKED':
                raise ServiceError('CANDIDATE_BLOCKED', 'Resolve blocking findings before export.', 409)
            if candidate.status == 'REVIEW_REQUIRED' and not body.acknowledge_review:
                raise ServiceError('REVIEW_ACK_REQUIRED', 'Acknowledge current review findings before export.', 409)
            return SwitchExportView(text=candidate.text, sha256=candidate.sha256, revision=session.revision)

    return router
