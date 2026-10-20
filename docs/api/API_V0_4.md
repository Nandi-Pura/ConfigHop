# ConfigHop local API v0.4

The FastAPI package `confighop_api` is a local adapter around `confighop_core`. Core v0.1 parses PAN-OS XML, v0.2 previews manual physical interface mappings, and v0.3 renders and validates a preservation-first candidate. Routes do not implement migration logic.

## Install and run

From `backend` on Python 3.12+:

```powershell
python -m pip install -e ".[api,dev]"
$env:CONFIGHOP_ARTIFACT_KEY_B64 = python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
python -m uvicorn confighop_api.main:app --host 127.0.0.1 --port 8000 --reload
```

This is a local single-user MVP with browser-session project ownership. Bind only to localhost. Creating a project sets a random `HttpOnly`, `SameSite=Strict` session cookie scoped to `/api/v1` (also `Secure` on HTTPS). All project routes require the creating session; knowledge of the project ID alone does not grant access. Sessions last eight hours, refreshed when that session creates another project. The backend retains only token hashes and their expiry, including across restart. Account login, operator identity, and RBAC are still unavailable. An existing project remains accessible after backend restart while its browser cookie has not expired. Clearing cookies or session expiry makes that project inaccessible through the API; account recovery is not implemented.

CORS defaults to `http://localhost:5173` and `http://127.0.0.1:5173`; `CONFIGHOP_CORS_ORIGINS` accepts explicit comma-separated origins, with credentials enabled. Wildcard origins are rejected. The frontend sends `credentials: include` and uses the same localhost hostname as its backend by default. Custom `VITE_CONFIGHOP_API_URL` must keep the frontend and API on the same site for the Strict cookie to work. Mutation requests still require `X-ConfigHop-Client: web`. Responses use `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

PAN-OS source collection stays disabled until `CONFIGHOP_SOURCE_ENDPOINTS` contains an exact IP and port allowlist, for example `10.20.30.40:443,[fd00::10]:443`. Hostnames, loopback, link-local, multicast, unspecified addresses, and endpoints outside the allowlist are rejected. The client uses HTTPS certificate verification, ignores proxy environment variables, rejects redirects, and applies connect/read/write/pool plus whole-collection timeouts. A request may include a PEM CA certificate for a private appliance CA. The API key and CA certificate are request-scoped and are not added to project state.

Target baseline collection and preflight diagnostics use a separate `CONFIGHOP_TARGET_ENDPOINTS` exact IP/port allowlist. They are disabled when the setting is empty. Collection additionally requires `CONFIGHOP_ARTIFACT_KEY_B64`, a stable base64-encoded 32-byte key. The same direct HTTPS and CA-verification policy applies; source allowlisting does not authorize a target. These routes only read device state. They do not stage, validate, or commit. PAN-OS documents `type=config&action=show` for active configuration and `action=get` for candidate configuration ([XML API request types](https://docs.paloaltonetworks.com/ngfw/api/pan-os-xml-api-request-types-and-actions)); the commands for change summary and commit locks are also documented ([operational commands](https://docs.paloaltonetworks.com/ngfw/api/pan-os-xml-api-request-types-and-actions/run-operational-mode-commands-api)). Response shape and semantics still require lab confirmation on the supported train.

The normal server stores project metadata, owner hashes, snapshot metadata, draft packages, internal review records, and deployment events in `.confighop/projects/projects.sqlite3`. Source snapshots live in separate versioned files under `.confighop/projects/<project-id>/snapshots/`; candidate XML is also kept in the project directory, with a separate immutable copy under each package directory. Target running baselines live under each project's `target-baselines/` directory as AES-256-GCM authenticated ciphertext. The authenticated metadata binds the project ID, baseline ID, plaintext hash, artifact kind, and format so a file cannot be silently moved between projects or metadata records. Set `CONFIGHOP_PROJECT_DATA_DIR` to a stable server-controlled directory to change the project location. Audit metadata remains in separate SQLite at `.confighop/audit.sqlite3`; set `CONFIGHOP_AUDIT_DB` to change it. Paths are relative to the backend working directory unless absolute. Tests that inject `ProjectStore()` use a temporary root. Run one API process; multi-worker coordination is not implemented. Source XML, generated candidate XML, SQLite databases, and audit data are not yet encrypted at rest, so protect and back up the data directory using local filesystem controls. No endpoint accepts a filesystem path from the client.

## Endpoints

| Method | Path after `/api/v1` | Purpose |
|---|---|---|
| GET | `/health`, `/capabilities` | Service status and truthful feature list |
| POST, GET, DELETE | `/projects`, `/projects/{id}` | Create, inspect, delete project session |
| PUT, GET | `/projects/{id}/source` | Stream raw PAN-OS XML upload; explicitly download original XML |
| POST | `/projects/{id}/source/connection/test` | Read source identity through the same allowlisted TLS policy without changing project source |
| POST | `/projects/{id}/source/collect` | Collect source XML through a server-allowlisted PAN-OS endpoint |
| POST | `/projects/{id}/target/baseline/collect` | Read target identity and active config twice; bind metadata/hash only after consistency checks |
| GET | `/projects/{id}/target/baseline` | Read bound target identity/hash metadata; no raw target XML |
| POST | `/projects/{id}/target/preflight/check` | Read-only diagnostic report; always `BLOCKED` or `INCOMPLETE`, never deployment approval |
| GET | `/projects/{id}/source/provenance` | Read source origin, hash, time, and available device identity |
| GET | `/projects/{id}/audit?after=0&limit=100` | Owner-session audit metadata, ordered by sequence; limit 1 to 500 |
| GET | `/projects/{id}/snapshots` | Metadata for immutable source versions; raw XML is served only by the active source endpoint |
| GET | `/projects/{id}/deployment-package` | Current local draft package metadata; verifies its immutable artifacts, with no deployment authority |
| GET | `/projects/{id}/deployment-events` | Durable package and snapshot lifecycle events |
| GET | `/projects/{id}/inventory` | UI-focused counts, physical rows, parser warnings |
| GET | `/hardware-profiles`, `/hardware-profiles/{id}` | Available target profile summaries and interface names |
| PUT | `/projects/{id}/target-profile` | Select profile and invalidate preview/candidate |
| POST, GET | `/projects/{id}/preview` | Core v0.2 domain result |
| POST, GET | `/projects/{id}/candidate` | Core v0.3 render result metadata, never XML body |
| GET | `/projects/{id}/candidate/download` | Download validated candidate XML |
| GET | `/projects/{id}/semantic-diff` | Validated interface-oriented changes |

Upload example:

```powershell
curl.exe -c confighop.cookies -X POST "http://127.0.0.1:8000/api/v1/projects" -H "X-ConfigHop-Client: web"
curl.exe -b confighop.cookies -X PUT "http://127.0.0.1:8000/api/v1/projects/PROJECT_ID/source" -H "X-ConfigHop-Client: web" -H "X-ConfigHop-Filename: source.xml" -H "Content-Type: application/xml" --data-binary "@source.xml"
```

Upload uses raw request streaming, checks `Content-Length` and actual bytes against 100 MiB, and parses a temporary file. A successful upload or collect creates a new source snapshot and atomically switches the project's active snapshot pointer in SQLite. Older snapshots remain unchanged. Failed upload or collect leaves the active snapshot intact. The filename header is display metadata only. On restart the backend checks source and candidate hashes. A corrupt source is reported as `SOURCE_INTEGRITY_FAILED`; the owner may upload a fresh source. A corrupt candidate is withdrawn. Source and candidate XML are available only through explicit XML endpoints; normal JSON returns counts, statuses, findings, and interface-oriented metadata. Errors use `{ "error": { "code": "...", "message": "..." } }` without XML, paths, or tracebacks.

Candidate generation creates a durable `DRAFT_UNDEPLOYABLE` package tied to the source snapshot, source/target profiles, PAN-OS trains, canonical mapping hash, candidate hash, and renderer version. It is not a deployable target candidate and cannot be staged or committed. Changing source, mappings, or profiles invalidates the active draft and records an event. Target baseline collection can bind a target identity, configuration hash, and encrypted artifact metadata to the project; a changed baseline detaches or invalidates its active package while retaining the source-derived candidate. The current candidate is still source-derived and is not rebuilt on that target baseline yet.

IMP-01 also adds an internal, durable deployment state machine with ordered transitions, artifact hash checks, evidence digests, and an immutable review-decision record bound to package inputs. A reviewed target-derived candidate, full target preflight, manual dashboard review, approval token, backup, and all device mutation operations are still unimplemented. These internal methods are not exposed as staging or commit routes. A package detached by input drift cannot advance through the normal deployment path; recovery requires a previously captured backup. On restart, an active package with a missing or modified artifact is withdrawn. Older drafts created before package-local candidate copies are likewise withdrawn and must be regenerated. Deployment events describe snapshot/package lifecycle and internal state changes; the separate source audit records sensitive artifact access and connection/collection attempts, including target baseline collection.

Target baseline collection requires an API-collected source with a known serial, a selected target profile, operator-confirmed target serial and model, and a configured artifact key. It verifies the key exists before contacting the target, then reads identity, active configuration twice, and identity again. Any mismatch is rejected. Metadata and SHA-256 are stored in project state; normalized target `<config>` bytes are atomically persisted as AES-256-GCM ciphertext with a fresh 12-byte nonce. Raw target XML is never returned, and API key/CA text are not persisted. Recollection replaces the old encrypted baseline only after the new artifact and metadata are durable. Key rotation and recovery for a lost key are not implemented. A changed baseline detaches or invalidates the active package; the source-derived candidate remains available.

The separate diagnostic preflight call rereads target identity and active configuration, fetches the candidate configuration, and queries change summary, commit locks, and pending jobs. A difference, nonempty result, malformed response, or target drift blocks the check; drift also detaches the current package. An empty result is treated only as no rows observed for that check, not as whole-device clearance. The report explicitly marks HA, Panorama ownership, multi-vsys, minimum software release, recovery path, and target-local preservation `NOT_CHECKED`. Even if all implemented checks are clear, the overall status is `INCOMPLETE` and `deployment_allowed` is always `false`. Its audit outcome is `COMPLETED`, meaning the diagnostic request finished, not that preflight passed. No durable `PREFLIGHT_PASSED` transition occurs. The UI does not yet offer this route, and device testing is deferred until the offline implementation gate is complete.

The web UI treats `GET /projects/{id}/source` as sensitive artifact access. Upload, collect, and project restore do not call it automatically. The endpoint is called only after an explicit `Reveal source XML` or `Download source XML` action; hiding the preview removes the raw text from browser state. Authorization is enforced on the backend and each source GET records `STARTED` and `ACCESS_GRANTED` before returning artifact bytes. `ACCESS_GRANTED` means access was permitted, not proof the browser received the entire file.

Connection tests and collection record `STARTED` followed by `SUCCEEDED` or `FAILED`. Denied project access records `DENIED`. Events include UTC time, operation ID, project ID, actor token hash, source hash when available, action, outcome, and stable error code; API keys, CA text, raw XML, cookies, request bodies, and device response bodies are excluded. An interrupted operation can leave `STARTED` without a terminal event. A failed audit write returns `503 AUDIT_UNAVAILABLE`; source XML is withheld if either required access event cannot be saved. If terminal auditing fails after a collect operation, reload project metadata before retrying because collection may already have completed. Audit rows survive project deletion and backend shutdown, but the project audit API only serves live projects owned by the current session. Retention, encryption, authenticated human attribution, and full deployment audit remain future work.

Connection test and collect accept JSON fields `host`, `port`, `api_key`, and optional `ca_certificate_pem`. Connection test reads system identity once, reports `CA_VERIFIED` only after a verified HTTPS response, and leaves project source unchanged. Collect reads system identity, exports twice, reads identity again, and promotes the source only when the identity and both byte streams remain equal. The resulting provenance uses `API_COLLECTED`, but its snapshot kind remains `UNVERIFIED` until a supported PAN-OS lab proves the export is the running configuration on that software train. Error codes distinguish allowlist, credential, TLS, transport, timeout, size, XML, identity-change, and configuration-change failures without returning the device response body.

The built-in `paloalto-synthetic-64` profile contains a synthetic interface namespace for development. It is not a PA-5410 catalog or compatibility claim. `READY` is within modeled preview scope only. `REVIEW_REQUIRED` needs explicit `allow_review`; `BLOCKED` preview and renderer findings remain normal HTTP 200 domain outcomes, while missing state and invalid transport requests use HTTP errors.

Browser authorization UAT is reproducible with `backend/tests/uat_project_access.py` using Playwright against isolated Vite `127.0.0.1:5174` and FastAPI `127.0.0.1:8011` processes. Set frontend `VITE_CONFIGHOP_API_URL=http://127.0.0.1:8011/api/v1`, backend `CONFIGHOP_CORS_ORIGINS=http://127.0.0.1:5174`, and leave `CONFIGHOP_SOURCE_ENDPOINTS` empty. It uploads a synthetic fixture and exercises reveal/hide/download/restore, audit retrieval, and rejection of a separate browser context.

No live firewall test, background worker, push/commit operation, or production deployment is included. Keep cookie jars, private source files, candidates, and databases out of the repository.
