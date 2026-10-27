import asyncio
import hashlib
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from confighop_core.models.transformation import SemanticMigrationDiff
from confighop_core.evidence.registry import EVIDENCE
from confighop_core.hardware.registry import list_profiles as list_hardware_profiles
from confighop_core.compatibility import CompatibilityAssessment

from .schemas import (
    CandidateMetadata, CandidateRequest, ErrorView, HealthView, InventoryView,
    PreviewRequest, PreviewView, ProfileDetail, ProfileSummary, ProjectView, SelectProfileRequest, SourceView,
)
from .services import (
    PROFILE_ID, ProjectStore, ServiceError, candidate_metadata, generate_candidate, inventory_view,
    profile_detail, profile_summary, project_deployment_plan, project_view, require_inventory, require_live, select_profile,
    select_source_profile, assess_project,
    update_preview, upload_source,
)
from .switch import switch_router
from .firewall import firewall_router


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _overall(preview_status: str, compatibility: CompatibilityAssessment | None) -> str:
    statuses = {preview_status, compatibility.status.value if compatibility else preview_status}
    return "BLOCKED" if "BLOCKED" in statuses else "REVIEW_REQUIRED" if "REVIEW_REQUIRED" in statuses else "READY"


def create_app(store: ProjectStore | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store or ProjectStore()
        if store is None:
            try:
                app.state.store.acquire_process_lock()
            except RuntimeError:
                app.state.store.close()
                raise
        async def expire_idle() -> None:
            while True:
                await asyncio.sleep(60)
                await app.state.store.reap_expired()
        expiry_task = asyncio.create_task(expire_idle())
        try:
            yield
        finally:
            expiry_task.cancel()
            with suppress(asyncio.CancelledError):
                await expiry_task
            app.state.store.close()

    app = FastAPI(title="ConfigHop Local API", version="0.7.0",
        description="Local single-user API without authentication. Bind to 127.0.0.1 only.", lifespan=lifespan)
    origins = [item.strip() for item in os.getenv("CONFIGHOP_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173").split(",") if item.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-ConfigHop-Client", "X-ConfigHop-Filename"])
    app.include_router(switch_router())
    app.include_router(firewall_router())

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.url.path.startswith(('/api/v1/switch-projects', '/api/v1/firewall-projects')) and request.method in {'POST', 'PUT'}:
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 3 * 1024 * 1024:
                    return _error('SOURCE_TOO_LARGE', 'Configuration request exceeds the 3 MB transport limit.', 413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        if request.method in {"POST", "PUT", "DELETE"} and request.url.path.startswith("/api/v1/"):
            if request.headers.get("x-confighop-client") != "web":
                response = _error("CLIENT_HEADER_REQUIRED", "X-ConfigHop-Client: web is required.", 400)
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ServiceError)
    async def service_error(_request: Request, exc: ServiceError):
        return _error(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return _error("INVALID_REQUEST", "Request shape is invalid.", 400)

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, _exc: Exception):
        return _error("INTERNAL_ERROR", "The local service could not complete the request.", 500)

    def current_store(request: Request) -> ProjectStore:
        return request.app.state.store

    @app.get("/api/v1/health", response_model=HealthView)
    async def health():
        return HealthView()

    @app.get("/api/v1/capabilities")
    async def capabilities():
        profiles = list_hardware_profiles()
        return {"domains": {"firewall": {"palo_alto_xml_inventory": True,
            "manual_interface_mapping": True, "dependency_preview": True, "panos_candidate_renderer": True},
            "switch": {"backend_enabled": True, "limited_pair": "IOS_XE_17.12_TO_AOS_CX_10.15", "hardware_optional_for_inspection": True}},
            "verified_hardware_profiles": [p.id for p in profiles if p.profile_status == "verified"],
            "synthetic_hardware_profiles": [p.id for p in profiles if p.profile_status == "synthetic"],
            "candidate_render_profiles": [p.id for p in profiles if p.profile_status == "verified" and p.target_render_support == "SUPPORTED"],
            "analysis_only_target_profiles": [p.id for p in profiles if p.target_render_support == "ANALYSIS_ONLY"]}

    @app.post("/api/v1/projects", response_model=ProjectView)
    async def create_project(request: Request):
        return project_view(await current_store(request).create())

    @app.get("/api/v1/projects/{project_id}", response_model=ProjectView)
    async def get_project(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_live(project)
            return project_view(project)

    @app.delete("/api/v1/projects/{project_id}", status_code=204)
    async def delete_project(project_id: str, request: Request):
        await current_store(request).delete(project_id)

    @app.put("/api/v1/projects/{project_id}/source", response_model=SourceView)
    async def put_source(project_id: str, request: Request):
        return await upload_source(current_store(request), current_store(request).get(project_id),
            request, request.headers.get("x-confighop-filename"))

    async def xml_stream(project, path: Path):
        async with project.lock:
            if project.deleted or not path.is_file():
                return
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    yield chunk
            project.touch()

    @app.get("/api/v1/projects/{project_id}/source")
    async def get_source(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_inventory(project)
            filename = project.source_filename or "source.xml"
        return StreamingResponse(xml_stream(project, project.source_path), media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/api/v1/projects/{project_id}/inventory", response_model=InventoryView)
    async def get_inventory(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            return inventory_view(require_inventory(project))

    @app.get("/api/v1/hardware-profiles", response_model=list[ProfileSummary])
    async def list_profiles():
        return [profile_summary(profile.id) for profile in list_hardware_profiles()]

    @app.get("/api/v1/hardware-profiles/{profile_id}", response_model=ProfileDetail)
    async def get_profile(profile_id: str):
        return profile_detail(profile_id)

    @app.get("/api/v1/evidence")
    async def list_evidence():
        return list(EVIDENCE.values())

    @app.get("/api/v1/evidence/{evidence_id}")
    async def get_evidence(evidence_id: str):
        if evidence_id not in EVIDENCE:
            raise ServiceError("EVIDENCE_NOT_FOUND", "Evidence record was not found.", 404)
        return EVIDENCE[evidence_id]

    @app.put("/api/v1/projects/{project_id}/source-profile", response_model=ProjectView)
    async def set_source_profile(project_id: str, body: SelectProfileRequest, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            return select_source_profile(project, body.profile_id, body.panos_train)

    @app.put("/api/v1/projects/{project_id}/target-profile", response_model=ProjectView)
    async def set_profile(project_id: str, body: SelectProfileRequest, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            return select_profile(project, body.profile_id, body.panos_train)

    @app.post("/api/v1/projects/{project_id}/compatibility", response_model=CompatibilityAssessment)
    async def post_compatibility(project_id: str, body: PreviewRequest, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            return assess_project(project, body.mappings)

    @app.get("/api/v1/projects/{project_id}/compatibility", response_model=CompatibilityAssessment)
    async def get_compatibility(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_live(project)
            if project.compatibility is None:
                raise ServiceError("COMPATIBILITY_NOT_AVAILABLE", "Compatibility assessment is not available.", 409)
            return project.compatibility

    @app.post("/api/v1/projects/{project_id}/preview", response_model=PreviewView)
    async def post_preview(project_id: str, body: PreviewRequest, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            preview = await update_preview(project, body.mappings)
            return PreviewView(**preview.model_dump(), platform_assessment=project.compatibility.platform if project.compatibility else None,
                hardware_assessment=project.compatibility.hardware if project.compatibility else None,
                overall_status=_overall(preview.status.value, project.compatibility),
                deployment_plan=project_deployment_plan(project))

    @app.get("/api/v1/projects/{project_id}/preview", response_model=PreviewView)
    async def get_preview(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_live(project)
            if project.preview is None:
                raise ServiceError("PREVIEW_NOT_AVAILABLE", "Preview is not available.", 409)
            return PreviewView(**project.preview.model_dump(), platform_assessment=project.compatibility.platform if project.compatibility else None,
                hardware_assessment=project.compatibility.hardware if project.compatibility else None,
                overall_status=_overall(project.preview.status.value, project.compatibility),
                deployment_plan=project_deployment_plan(project))

    @app.post("/api/v1/projects/{project_id}/candidate", response_model=CandidateMetadata)
    async def post_candidate(project_id: str, body: CandidateRequest, request: Request):
        store = current_store(request)
        async with store.lock:
            project = store.get(project_id)
            async with project.lock:
                return await generate_candidate(project, body.mappings, body.allow_review, store)

    @app.get("/api/v1/projects/{project_id}/candidate", response_model=CandidateMetadata)
    async def get_candidate(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_live(project)
            return candidate_metadata(project)

    @app.get("/api/v1/projects/{project_id}/candidate/download")
    async def download_candidate(project_id: str, request: Request):
        store = current_store(request)
        project = store.get(project_id)
        async with project.lock:
            require_live(project)
            if project.candidate is None or not project.candidate.validation.valid:
                raise ServiceError("CANDIDATE_NOT_AVAILABLE", "Validated candidate is not available.", 409)
            digest = project.candidate.candidate_sha256 or ""
            try:
                with project.candidate_path.open("rb") as stream:
                    body = stream.read(store.max_candidate_bytes + 1)
            except OSError as exc:
                raise ServiceError("CANDIDATE_NOT_AVAILABLE", "Validated candidate is not available.", 409) from exc
            if (len(body) > store.max_candidate_bytes or len(body) != project.candidate.candidate_size_bytes
                    or hashlib.sha256(body).hexdigest() != digest):
                raise ServiceError("CANDIDATE_NOT_AVAILABLE", "Validated candidate is not available.", 409)
        return Response(content=body, media_type="application/xml",
            headers={"Content-Disposition": 'attachment; filename="confighop-candidate.xml"', "ETag": digest})

    @app.get("/api/v1/projects/{project_id}/semantic-diff", response_model=SemanticMigrationDiff)
    async def get_semantic_diff(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_live(project)
            if project.candidate is None or not project.candidate.validation.valid:
                raise ServiceError("CANDIDATE_NOT_AVAILABLE", "Validated candidate is not available.", 409)
            return project.candidate.semantic_diff

    return app


app = create_app()
