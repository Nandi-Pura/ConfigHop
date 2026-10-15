# ConfigHop local API v0.4

The FastAPI package `confighop_api` is a local adapter around `confighop_core`. Core v0.1 parses PAN-OS XML, v0.2 previews manual physical interface mappings, and v0.3 renders and validates a preservation-first candidate. Routes do not implement migration logic.

## Install and run

From `backend` on Python 3.12+:

```powershell
python -m pip install -e ".[api,dev]"
python -m uvicorn confighop_api.main:app --host 127.0.0.1 --port 8000 --reload
```

This is an unauthenticated single-user MVP. Bind only to localhost. CORS defaults to `http://localhost:5173` and `http://127.0.0.1:5173`; `CONFIGHOP_CORS_ORIGINS` accepts a comma-separated override. Mutation requests require `X-ConfigHop-Client: web`, a local-browser guard rather than authentication. OpenAPI is available locally; add that header when trying mutations in Swagger. Responses use `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

PAN-OS source collection stays disabled until `CONFIGHOP_SOURCE_ENDPOINTS` contains an exact IP and port allowlist, for example `10.20.30.40:443,[fd00::10]:443`. Hostnames, loopback, link-local, multicast, unspecified addresses, and endpoints outside the allowlist are rejected. The client uses HTTPS certificate verification, ignores proxy environment variables, rejects redirects, and applies connect/read/write/pool plus whole-collection timeouts. A request may include a PEM CA certificate for a private appliance CA. The API key and CA certificate are request-scoped and are not added to project state.

Projects have unpredictable IDs and isolated directories under a process-lifetime temporary root. There is no database. Deleting a project or stopping the backend removes its source and candidate. No endpoint accepts a filesystem path from the client.

## Endpoints

| Method | Path after `/api/v1` | Purpose |
|---|---|---|
| GET | `/health`, `/capabilities` | Service status and truthful feature list |
| POST, GET, DELETE | `/projects`, `/projects/{id}` | Create, inspect, delete project session |
| PUT, GET | `/projects/{id}/source` | Stream raw PAN-OS XML upload; explicitly download original XML |
| POST | `/projects/{id}/source/connection/test` | Read source identity through the same allowlisted TLS policy without changing project source |
| POST | `/projects/{id}/source/collect` | Collect source XML through a server-allowlisted PAN-OS endpoint |
| GET | `/projects/{id}/source/provenance` | Read source origin, hash, time, and available device identity |
| GET | `/projects/{id}/inventory` | UI-focused counts, physical rows, parser warnings |
| GET | `/hardware-profiles`, `/hardware-profiles/{id}` | Available target profile summaries and interface names |
| PUT | `/projects/{id}/target-profile` | Select profile and invalidate preview/candidate |
| POST, GET | `/projects/{id}/preview` | Core v0.2 domain result |
| POST, GET | `/projects/{id}/candidate` | Core v0.3 render result metadata, never XML body |
| GET | `/projects/{id}/candidate/download` | Download validated candidate XML |
| GET | `/projects/{id}/semantic-diff` | Validated interface-oriented changes |

Upload example:

```powershell
curl.exe -X PUT "http://127.0.0.1:8000/api/v1/projects/PROJECT_ID/source" -H "X-ConfigHop-Client: web" -H "X-ConfigHop-Filename: source.xml" -H "Content-Type: application/xml" --data-binary "@source.xml"
```

Upload uses raw request streaming, checks `Content-Length` and actual bytes against 100 MiB, parses a temporary file, then atomically replaces the old source. Failed upload leaves the previous valid source intact. The filename header is display metadata only. Source and candidate XML are available only through explicit XML endpoints; normal JSON returns counts, statuses, findings, and interface-oriented metadata. Errors use `{ "error": { "code": "...", "message": "..." } }` without XML, paths, or tracebacks.

Connection test and collect accept JSON fields `host`, `port`, `api_key`, and optional `ca_certificate_pem`. Connection test reads system identity once, reports `CA_VERIFIED` only after a verified HTTPS response, and leaves project source unchanged. Collect reads system identity, exports twice, reads identity again, and promotes the source only when the identity and both byte streams remain equal. The resulting provenance uses `API_COLLECTED`, but its snapshot kind remains `UNVERIFIED` until a supported PAN-OS lab proves the export is the running configuration on that software train. Error codes distinguish allowlist, credential, TLS, transport, timeout, size, XML, identity-change, and configuration-change failures without returning the device response body.

The built-in `paloalto-synthetic-64` profile contains a synthetic interface namespace for development. It is not a PA-5410 catalog or compatibility claim. `READY` is within modeled preview scope only. `REVIEW_REQUIRED` needs explicit `allow_review`; `BLOCKED` preview and renderer findings remain normal HTTP 200 domain outcomes, while missing state and invalid transport requests use HTTP errors.

No live firewall test, durable database, background worker, push/commit operation, or production deployment is included. Keep private source files and candidates out of the repository.
