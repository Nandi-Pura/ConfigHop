import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request, Response
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
    TargetBaselineCollectRequest, TargetPreflightView,
)
from .services import (
    PROFILE_ID, ProjectStore, ServiceError, candidate_metadata, check_target_preflight,
    collect_source, collect_target_baseline,
    generate_candidate, inventory_view,
    profile_detail, profile_summary, project_deployment_plan, project_view, require_inventory, require_live, select_profile,
    select_source_profile, assess_project, test_source_connection,
    update_preview, upload_source,
)
from .panos_xml import XmlApiError, normalize_source_endpoint
from .access_audit import AuditStore, ProjectAccess, SESSION_COOKIE, SESSION_SECONDS
from .project_state import DeploymentEvent, DeploymentPackage, SourceSnapshot, TargetBaseline, sha256_file


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _overall(preview_status: str, compatibility: CompatibilityAssessment | None) -> str:
    statuses = {preview_status, compatibility.status.value if compatibility else preview_status}
    return "BLOCKED" if "BLOCKED" in statuses else "REVIEW_REQUIRED" if "REVIEW_REQUIRED" in statuses else "READY"


def _allowed_endpoints(value: str, setting: str) -> set[tuple[str, int]]:
    endpoints: set[tuple[str, int]] = set()
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        if item.startswith("["):
            closing = item.find("]")
            if closing < 0 or closing + 1 >= len(item) or item[closing + 1] != ":":
                raise ValueError(f"Invalid {setting} entry.")
            host, port_text = item[1:closing], item[closing + 2:]
        else:
            try:
                host, port_text = item.rsplit(":", 1)
            except ValueError as exc:
                raise ValueError(f"Invalid {setting} entry.") from exc
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError(f"Invalid {setting} entry.") from exc
        try:
            endpoints.add(normalize_source_endpoint(host, port))
        except XmlApiError:
            raise ValueError(f"Invalid {setting} entry.") from None
    return endpoints


def _source_endpoints(value: str) -> set[tuple[str, int]]:
    return _allowed_endpoints(value, "CONFIGHOP_SOURCE_ENDPOINTS")


def create_app(store: ProjectStore | None = None, *,
    allowed_source_endpoints: set[tuple[str, int]] | None = None,
    allowed_target_endpoints: set[tuple[str, int]] | None = None,
    audit_path: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store if store is not None else ProjectStore(
            Path(os.getenv("CONFIGHOP_PROJECT_DATA_DIR", ".confighop/projects")))
        app.state.allowed_source_endpoints = (allowed_source_endpoints if allowed_source_endpoints is not None
            else _source_endpoints(os.getenv("CONFIGHOP_SOURCE_ENDPOINTS", "")))
        app.state.allowed_target_endpoints = (allowed_target_endpoints if allowed_target_endpoints is not None
            else _allowed_endpoints(os.getenv("CONFIGHOP_TARGET_ENDPOINTS", ""), "CONFIGHOP_TARGET_ENDPOINTS"))
        app.state.access = ProjectAccess(app.state.store.database)
        app.state.audit = AuditStore(audit_path or Path(os.getenv("CONFIGHOP_AUDIT_DB",
            str(store.data_dir / "audit.sqlite3") if store else ".confighop/audit.sqlite3")))
        try:
            yield
        finally:
            app.state.audit.close()
            app.state.store.close()

    app = FastAPI(title="ConfigHop Local API", version="0.7.0",
        description="Local single-user API with browser-session project ownership. Bind to 127.0.0.1 only.", lifespan=lifespan)
    origins = [item.strip() for item in os.getenv("CONFIGHOP_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173").split(",") if item.strip()]
    if "*" in origins:
        raise ValueError("CONFIGHOP_CORS_ORIGINS must list explicit origins for credentialed requests.")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-ConfigHop-Client", "X-ConfigHop-Filename"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await project_request(request, call_next)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        origin = request.headers.get("origin")
        if origin in origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            if "origin" not in response.headers.get("vary", "").lower():
                response.headers["Vary"] = ", ".join(filter(None, [response.headers.get("vary"), "Origin"]))
        return response

    async def project_request(request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.method in {"POST", "PUT", "DELETE"} and request.url.path.startswith("/api/v1/"):
            if request.headers.get("x-confighop-client") != "web":
                return _error("CLIENT_HEADER_REQUIRED", "X-ConfigHop-Client: web is required.", 400)
        parts = request.url.path.split("/")
        if len(parts) < 5 or parts[1:4] != ["api", "v1", "projects"] or not parts[4]:
            if request.url.path == "/api/v1/projects" and request.headers.get("origin") not in [None, *origins]:
                return _error("ORIGIN_NOT_ALLOWED", "Browser origin is not allowed.", 403)
            return await call_next(request)
        if request.headers.get("origin") not in [None, *origins]:
            return _error("ORIGIN_NOT_ALLOWED", "Browser origin is not allowed.", 403)
        project_id = parts[4]
        try:
            project = request.app.state.store.get(project_id)
        except ServiceError as exc:
            return _error(exc.code, exc.message, exc.status)
        token = request.cookies.get(SESSION_COOKIE)
        actor = ProjectAccess.fingerprint(token)
        suffix = "/".join(parts[5:])
        action = {("GET", "source"): "SOURCE_ARTIFACT_ACCESS",
            ("POST", "source/connection/test"): "SOURCE_CONNECTION_TEST",
            ("POST", "source/collect"): "SOURCE_COLLECT",
            ("POST", "target/baseline/collect"): "TARGET_BASELINE_COLLECT",
            ("POST", "target/preflight/check"): "TARGET_PREFLIGHT_CHECK"}.get((request.method, suffix))
        audit = request.app.state.audit
        digest = project.source_provenance.sha256 if project.source_provenance else None
        if not request.app.state.access.allows(project_id, token):
            try:
                audit.record(project_id=project_id, actor_sha256=actor, action=action or "PROJECT_ACCESS",
                    outcome="DENIED", error_code="PROJECT_ACCESS_DENIED", source_sha256=digest)
            except sqlite3.Error:
                return _error("AUDIT_UNAVAILABLE", "Audit storage is unavailable.", 503)
            return _error("PROJECT_ACCESS_DENIED", "Open this project in the browser session that created it.", 403)
        if not action:
            return await call_next(request)
        try:
            operation = audit.record(project_id=project_id, actor_sha256=actor, action=action,
                outcome="STARTED", source_sha256=digest)
        except sqlite3.Error:
            return _error("AUDIT_UNAVAILABLE", "Audit storage is unavailable.", 503)
        try:
            response = await call_next(request)
        except Exception:
            audit.record(project_id=project_id, actor_sha256=actor, action=action,
                outcome="FAILED", operation_id=operation, error_code="INTERNAL_ERROR", source_sha256=digest)
            raise
        digest = project.source_provenance.sha256 if project.source_provenance else None
        try:
            outcome = ("FAILED" if response.status_code >= 400 else
                "ACCESS_GRANTED" if action == "SOURCE_ARTIFACT_ACCESS" else
                "COMPLETED" if action == "TARGET_PREFLIGHT_CHECK" else "SUCCEEDED")
            audit.record(project_id=project_id, actor_sha256=actor, action=action,
                outcome=outcome,
                operation_id=operation, error_code=getattr(request.state, "error_code", None), source_sha256=digest)
        except sqlite3.Error:
            return _error("AUDIT_UNAVAILABLE", "Audit storage is unavailable. Reload project state before retrying.", 503)
        return response

    @app.exception_handler(ServiceError)
    async def service_error(_request: Request, exc: ServiceError):
        _request.state.error_code = exc.code
        return _error(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        _request.state.error_code = "INVALID_REQUEST"
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
            "panos_xml_api_collect": bool(request.app.state.allowed_source_endpoints),
            "panos_target_baseline_collect": bool(request.app.state.allowed_target_endpoints)},
            "switch": {"backend_enabled": False}},
            "verified_hardware_profiles": [p.id for p in profiles if p.profile_status == "verified"],
            "synthetic_hardware_profiles": [p.id for p in profiles if p.profile_status == "synthetic"],
            "candidate_render_profiles": [p.id for p in profiles if p.profile_status == "verified" and p.target_render_support == "SUPPORTED"],
            "analysis_only_target_profiles": [p.id for p in profiles if p.target_render_support == "ANALYSIS_ONLY"]}

    @app.post("/api/v1/projects", response_model=ProjectView)
    async def create_project(request: Request, response: Response):
        project = await current_store(request).create()
        token = request.app.state.access.create_owner(project.project_id, request.cookies.get(SESSION_COOKIE))
        response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict",
            secure=request.url.scheme == "https", max_age=SESSION_SECONDS, path="/api/v1")
        return project_view(project)

    @app.get("/api/v1/projects/{project_id}", response_model=ProjectView)
    async def get_project(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_live(project)
            return project_view(project)

    @app.delete("/api/v1/projects/{project_id}", status_code=204)
    async def delete_project(project_id: str, request: Request):
        await current_store(request).delete(project_id)
        request.app.state.access.owners.pop(project_id, None)

    @app.get("/api/v1/projects/{project_id}/audit")
    async def get_project_audit(project_id: str, request: Request,
        after: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500)):
        return {"events": request.app.state.audit.events(project_id, after=after, limit=limit)}

    @app.get("/api/v1/projects/{project_id}/snapshots", response_model=list[SourceSnapshot])
    async def get_snapshots(project_id: str, request: Request):
        current_store(request).get(project_id)
        return current_store(request).database.snapshots(project_id)

    @app.get("/api/v1/projects/{project_id}/deployment-package", response_model=DeploymentPackage)
    async def get_deployment_package(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        if not project.active_package_id:
            raise ServiceError("PACKAGE_NOT_AVAILABLE", "No current deployment package is available.", 409)
        project.verify_source()
        package = current_store(request).database.package(project.active_package_id)
        if package is None:
            raise ServiceError("PACKAGE_NOT_AVAILABLE", "No current deployment package is available.", 409)
        try:
            current_store(request).database.verify_package_artifacts(package)
        except ValueError:
            raise ServiceError("PACKAGE_INTEGRITY_FAILED", "Deployment package artifact integrity check failed.", 409) from None
        return package

    @app.get("/api/v1/projects/{project_id}/deployment-events", response_model=list[DeploymentEvent])
    async def get_deployment_events(project_id: str, request: Request):
        current_store(request).get(project_id)
        return current_store(request).database.events(project_id)

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

    @app.post("/api/v1/projects/{project_id}/target/baseline/collect", response_model=TargetBaseline)
    async def post_collect_target_baseline(project_id: str, body: TargetBaselineCollectRequest, request: Request):
        return await collect_target_baseline(current_store(request), current_store(request).get(project_id),
            host=body.host, port=body.port, api_key=body.api_key.get_secret_value(),
            ca_pem=body.ca_certificate_pem, expected_serial=body.expected_serial,
            expected_model=body.expected_model,
            allowed_endpoints=request.app.state.allowed_target_endpoints)

    @app.get("/api/v1/projects/{project_id}/target/baseline", response_model=TargetBaseline)
    async def get_target_baseline(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        if project.target_baseline is None:
            raise ServiceError("TARGET_BASELINE_NOT_AVAILABLE", "No target baseline has been collected.", 409)
        return project.target_baseline

    @app.post("/api/v1/projects/{project_id}/target/preflight/check", response_model=TargetPreflightView)
    async def post_check_target_preflight(project_id: str, body: TargetBaselineCollectRequest, request: Request):
        return await check_target_preflight(current_store(request), current_store(request).get(project_id),
            host=body.host, port=body.port, api_key=body.api_key.get_secret_value(),
            ca_pem=body.ca_certificate_pem, expected_serial=body.expected_serial,
            expected_model=body.expected_model,
            allowed_endpoints=request.app.state.allowed_target_endpoints)

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
            project.verify_source()
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
            if project.active_snapshot_id:
                project.verify_source()
            return candidate_metadata(project)

    @app.get("/api/v1/projects/{project_id}/candidate/download")
    async def download_candidate(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_live(project)
            if project.active_snapshot_id:
                project.verify_source()
            if project.candidate is None or not project.candidate.validation.valid or not project.candidate_path.is_file():
                raise ServiceError("CANDIDATE_NOT_AVAILABLE", "Validated candidate is not available.", 409)
            digest = project.candidate.candidate_sha256 or ""
            if sha256_file(project.candidate_path) != digest:
                raise ServiceError("CANDIDATE_INTEGRITY_FAILED", "Candidate artifact integrity check failed.", 409)
        return StreamingResponse(xml_stream(project, project.candidate_path), media_type="application/xml",
            headers={"Content-Disposition": 'attachment; filename="confighop-candidate.xml"', "ETag": digest})

    @app.get("/api/v1/projects/{project_id}/semantic-diff", response_model=SemanticMigrationDiff)
    async def get_semantic_diff(project_id: str, request: Request):
        project = current_store(request).get(project_id)
        async with project.lock:
            require_live(project)
            if project.active_snapshot_id:
                project.verify_source()
            if project.candidate is None or not project.candidate.validation.valid:
                raise ServiceError("CANDIDATE_NOT_AVAILABLE", "Validated candidate is not available.", 409)
            return project.candidate.semantic_diff

    return app


app = create_app()
