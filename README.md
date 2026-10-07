# ConfigHop

ConfigHop is a local network configuration migration workbench. The Firewall path accepts PAN-OS XML, parses a real source inventory, previews manual physical interface mappings, and generates a preservation-first candidate XML through a FastAPI service. The Switch workspace remains a frontend mock.

ConfigHop includes verified PA-3410 and PA-5410 hardware profiles alongside a synthetic development profile. Candidate validation proves modeled transformations and XML preservation within the implemented scope; it does not prove PAN-OS import or production deployment safety. There is no live firewall connection.

## Run locally

Use Python 3.12 or newer. In `backend`:

```powershell
python -m pip install -e ".[api,dev]"
python -m uvicorn confighop_api.main:app --host 127.0.0.1 --port 8000 --reload
```

In the repository root, in a second terminal:

```powershell
npm ci
npm run dev
```

Open `http://localhost:5173`. The frontend defaults to `http://127.0.0.1:8000/api/v1`; override it with `VITE_CONFIGHOP_API_URL` if needed. This unauthenticated MVP must be bound to localhost. Project files live only in a temporary server workspace and disappear when the server stops or a project is deleted.

## Test

```powershell
cd backend
python -m pytest -q
python -m compileall src
```

From the repository root, run `npm test` and `npm run build`.

Core v0.1 parses PAN-OS XML, v0.2 previews exact interface dependencies, and v0.3 renders and validates a patched candidate. App v0.5 adds PA-3410 and PA-5410 hardware and PAN-OS compatibility checks. v0.6 adds documentation-verified PA-5410 native QSFP target speed rendering for ports 41–44 with an explicit 40G or 100G choice. Breakout conversion and cross-vendor conversion remain roadmap work. See [core v0.6](docs/core/CORE_V0_6.md), [API v0.6](docs/api/API_V0_6.md), and [app v0.6](docs/app/APP_V0_6.md). Private XML and generated candidates belong in ignored `local-samples/` and `local-output/` directories.
