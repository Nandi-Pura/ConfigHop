# ConfigHop

ConfigHop is a local network configuration migration workbench. The Firewall path accepts PAN-OS XML, parses a real source inventory, previews manual physical interface mappings, and generates a preservation-first candidate XML through a FastAPI service. The Switch workspace remains a frontend mock.

The current target profile is synthetic development data. Candidate validation proves modeled transformations and XML preservation within the implemented scope; it does not prove real hardware compatibility, PAN-OS import, or production deployment safety. There is no live firewall connection.

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

Core v0.1 parses PAN-OS XML, v0.2 previews exact interface dependencies, and v0.3 renders and validates a patched candidate. See [API v0.4](docs/api/API_V0_4.md) and [app integration v0.4](docs/app/APP_V0_4.md). Private XML and generated candidates belong in ignored `local-samples/` and `local-output/` directories.