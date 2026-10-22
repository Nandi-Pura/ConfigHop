# ConfigHop

ConfigHop is a local network configuration migration workbench. The Firewall workspace supports PAN-OS XML inventory, manual physical interface mapping, and preservation-first PAN-OS candidate XML; a separate [bounded FortiOS 7.4 ↔ PAN-OS 11.1 subset](docs/phase9b-firewall-translation.md) supports cross-vendor Firewall translation. The Switch workspace translates documented Cisco IOS XE and Aruba AOS-CX subsets in both directions, with engineer-approved interface mapping, semantic findings, and review-gated export.

ConfigHop includes 11 documentation-verified Palo Alto hardware profiles across PA-1400, PA-3200, PA-3400, PA-5200, and PA-5400, alongside a synthetic development profile. PA-3410 and PA-5410 support candidate rendering; the nine new models support source analysis and target analysis only. Candidate validation proves modeled transformations and XML preservation within the implemented scope; it does not prove PAN-OS import or production deployment safety. There is no live firewall connection.

## Switch translation scope

- [Cisco IOS XE 17.12.x, 17.15.x, or 17.18.x → Aruba AOS-CX 10.10.x, 10.13.x, or 10.16.x](docs/phase11a-os-based-switch-translation.md): a limited OS-to-OS feature subset with optional hardware context.
- [Aruba AOS-CX 10.13.x → Cisco IOS XE 17.18.x](docs/phase11b-switch-completion.md): a separate limited reverse subset.
- [Legacy IOS XE 17.12.x → AOS-CX 10.15.x](docs/phase9a-switch-migration.md): requires the exact JL663A hardware profile.

Physical interface mapping requires Network Engineer approval; bulk mapping assists but does not certify device-specific port existence. Supported constructs produce bounded native target CLI. Unsupported statements are reported or block export. Candidates require semantic review, and review-gated export checks the current revision and digest. Credentials and AAA may require manual reentry; stacking, VSF, and StackWise require a separate manual plan. Synthetic test success does not establish device compatibility or deployment safety. See the [Switch support matrix](docs/phase11a-switch-support-matrix.json) for the exact release and feature boundaries.

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

Core v0.1 parses PAN-OS XML, v0.2 previews exact interface dependencies, and v0.3 renders and validates a patched candidate. App v0.5 adds PA-3410 and PA-5410 hardware and PAN-OS compatibility checks. v0.6 adds documentation-verified PA-5410 native QSFP target speed rendering for ports 41–44 with an explicit 40G or 100G choice. v0.7 adds a model-specific hardware registry and PAN-OS support rules. The bounded cross-vendor Switch paths above are implemented; Firewall translation remains focused on PAN-OS and the documented FortiOS subset. Other cross-vendor paths, advanced features, and breakout conversion beyond documented hardware-specific behavior remain unsupported. See [core v0.7](docs/core/CORE_V0_7.md), [API v0.7](docs/api/API_V0_7.md), and [app v0.7](docs/app/APP_V0_7.md). Private XML and generated candidates belong in ignored `local-samples/` and `local-output/` directories.
