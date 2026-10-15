import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from confighop_core.models.transformation import SemanticMigrationDiff
from confighop_core.evidence.registry import EVIDENCE
from confighop_core.hardware.registry import list_profiles as list_hardware_profiles
from confighop_core.compatibility import CompatibilityAssessment

from .schemas import (
    CandidateMetadata, CandidateRequest, ErrorView, HealthView, InventoryView,
    PreviewRequest, PreviewView, ProfileDetail, ProfileSummary, ProjectView, SelectProfileRequest,
    SourceCollectRequest, SourceConnectionRequest, SourceConnectionTestView, SourceProvenance, SourceView,
)
from .services import (
    PROFILE_ID, ProjectStore, ServiceError, candidate_metadata, collect_source, generate_candidate, inventory_view,
    profile_detail, profile_summary, project_deployment_plan, project_view, require_inventory, require_live, select_profile,
    select_source_profile, assess_project, test_source_connection,
    update_preview, upload_source,
)
from .panos_xml import XmlApiError, normalize_source_endpoint


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _overall(preview_status: str, compatibility: CompatibilityAssessment | None) -> str:
    statuses = {preview_status, compatibility.status.value if compatibility else preview_status}
    return "BLOCKED" if "BLOCKED" in statuses else "REVIEW_REQUIRED" if "REVIEW_REQUIRED" in statuses else "READY"


def _source_endpoints(value: str) -> set[tuple[str, int]]:
    endpoints: set[tuple[str, int]] = set()
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        if item.startswith("["):
            closing = item.find("]")
            if closing < 0 or closing + 1 >= len(item) or item[closing + 1] != ":":
                raise ValueError("Invalid CONFIGHOP_SOURCE_ENDPOINTS entry.")
            host, port_text = item[1:closing], item[closing + 2:]
        else:
            try:
                host, port_text = item.rsplit(":", 1)
            except ValueError as exc:
                raise ValueError("Invalid CONFIGHOP_SOURCE_ENDPOINTS entry.") from exc
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError("Invalid CONFIGHOP_SOURCE_ENDPOINTS entry.") from exc
        try:
            endpoints.add(normalize_source_endpoint(host, port))
        except XmlApiError:
            raise ValueError("Invalid CONFIGHOP_SOURCE_ENDPOINTS entry.") from None
    return endpoints


def create_app(store: ProjectStore | None = None, *,
    allowed_source_endpoints: set[tuple[str, int]] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store or ProjectStore()
        app.state.allowed_source_endpoints = (allowed_source_endpoints if allowed_source_endpoints is not None
            else _source_endpoints(os.getenv("CONFIGHOP_SOURCE_ENDPOINTS", "")))
        try:
            yield
        finally:
            app.state.store.close()

    app = FastAPI(title="ConfigHop Local API", version="0.7.0",
        description="Local single-user API without authentication. Bind to 127.0.0.1 only.", lifespan=lifespan)
    origins = [item.strip() for item in os.getenv("CONFIGHOP_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173").split(",") if item.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-ConfigHop-Client", "X-ConfigHop-Filename"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
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
    async def capabilities(request: Request):
        profiles = list_hardware_profiles()
        return {"domains": {"firewall": {"palo_alto_xml_inventory": True,
            "manual_interface_mapping": True, "dependency_preview": True, "panos_candidate_renderer": True,
            "panos_xml_api_collect": bool(request.app.state.allowed_source_endpoints)},
            "switch": {"backend_enabled": False}},
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

    @app.post("/api/v1/projects/{project_id}/source/collect", response_model=SourceView)
    async def post_collect_source(project_id: str, body: SourceCollectRequest, request: Request):
        return await collect_source(current_store(request), current_store(request).get(project_id),
            host=body.host, port=body.port, api_key=body.api_key.get_secret_value(),
            ca_pem=body.ca_certificate_pem,
            allowed_endpoints=request.app.state.allowed_source_endpoints)

    @app.post("/api/v1/projects/{project_id}/source/connection/test", response_model=SourceConnectionTestView)
    async def post_test_source_connection(project_id: str, body: SourceConnectionRequest, request: Request):
        current_store(request).get(project_id)
        return await test_source_connection(host=body.host, port=body.port,
            api_key=body.api_key.get_secret_value(), ca_pem=body.ca_certificate_pem,
            allowed_endpoints=request.app.state.allowed_source_endpoints)

    async def xml_stream(project, path: Path):
        async with project.lock:
            if project.deleted or not path.is_file():
                return
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    yield chunk

    @app.get("/api/v1/projects/{project_id}/source")
    async def get_source(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_inventory(project)
            filename = project.source_filename or "source.xml"
        return StreamingResponse(xml_stream(project, project.source_path), media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/api/v1/projects/{project_id}/source/provenance", response_model=SourceProvenance)
    async def get_source_provenance(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_inventory(project)
            if project.source_provenance is None:
                raise ServiceError("SOURCE_PROVENANCE_NOT_AVAILABLE", "Source provenance is not available.", 409)
            return project.source_provenance

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
        project = current_store(request).get(project_id)
        async with project.lock:
            return await generate_candidate(project, body.mappings, body.allow_review)

    @app.get("/api/v1/projects/{project_id}/candidate", response_model=CandidateMetadata)
    async def get_candidate(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_live(project)
            return candidate_metadata(project)

    @app.get("/api/v1/projects/{project_id}/candidate/download")
    async def download_candidate(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_live(project)
            if project.candidate is None or not project.candidate.validation.valid or not project.candidate_path.is_file():
                raise ServiceError("CANDIDATE_NOT_AVAILABLE", "Validated candidate is not available.", 409)
            digest = project.candidate.candidate_sha256 or ""
        return StreamingResponse(xml_stream(project, project.candidate_path), media_type="application/xml",
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
