# ConfigHop

**Beta / Technical Preview.** ConfigHop is an offline, engineer-reviewed software workbench. It does not connect to devices or certify a migration for production use.

ConfigHop is a local network configuration migration workbench. The Firewall workspace supports PAN-OS XML inventory, manual physical interface mapping, and preservation-first PAN-OS candidate XML; a separate [bounded FortiOS 7.4 ↔ PAN-OS 11.1 subset](docs/phase9b-firewall-translation.md) supports cross-vendor Firewall translation. The Switch workspace translates documented Cisco IOS XE and Aruba AOS-CX subsets in both directions, with engineer-approved interface mapping, semantic findings, and review-gated export.

ConfigHop includes 11 documentation-verified Palo Alto hardware profiles across PA-1400, PA-3200, PA-3400, PA-5200, and PA-5400, alongside a synthetic development profile. PA-3410 and PA-5410 have `SUPPORTED` target rendering; PA-3220, PA-3250, PA-3260, PA-5220, PA-5250, PA-5260, and PA-5280 have `SCOPED` target rendering with interface-specific conditions; PA-1410 and PA-1420 are `ANALYSIS_ONLY`. All 11 profiles support source and target analysis within their documented PAN-OS train rules. `SCOPED` does not mean unrestricted candidate support, and individual ports may require explicit optic or link-field conditions. Candidate validation proves modeled transformations and XML preservation within the implemented scope; it does not prove PAN-OS import or production deployment safety. There is no live firewall connection.

Back up the original configuration before attempting a migration. Review every candidate and its findings with a network engineer before use; never deploy generated output without device-specific validation. Unsupported semantics intentionally block validated export. Physical device acceptance, configuration import, packet-flow equivalence, and production suitability have not been verified. Do not paste credentials or customer network configurations into public issues, screenshots, or other public reports; use sanitized synthetic reproductions.

## Switch translation scope

- [Cisco IOS XE 17.12.x, 17.15.x, or 17.18.x → Aruba AOS-CX 10.10.x, 10.13.x, or 10.16.x](docs/phase11a-os-based-switch-translation.md): a limited OS-to-OS feature subset with optional hardware context.
- [Aruba AOS-CX 10.13.x → Cisco IOS XE 17.18.x](docs/phase11b-switch-completion.md): a separate limited reverse subset.
- [Legacy IOS XE 17.12.x → AOS-CX 10.15.x](docs/phase9a-switch-migration.md): requires the exact JL663A hardware profile.

Physical interface mapping requires Network Engineer approval; bulk mapping assists but does not certify device-specific port existence. Supported constructs produce bounded native target CLI. Unsupported statements are reported or block export. Candidates require semantic review, and review-gated export checks the current revision and digest. Credentials and AAA may require manual reentry; stacking, VSF, and StackWise require a separate manual plan. Synthetic test success does not establish device compatibility or deployment safety. See the [Switch support matrix](docs/phase11a-switch-support-matrix.json) for the exact release and feature boundaries.

## Run locally

Use Python 3.12 or newer and Node.js 22. In `backend`:

```powershell
python -m pip install -e ".[api,dev]"
python -m uvicorn confighop_api.main:app --host 127.0.0.1 --port 8000 --reload
```

In the repository root, in a second terminal:

```powershell
npm ci
npm run dev
```

Open `http://localhost:5173`. The frontend defaults to `http://127.0.0.1:8000/api/v1`; override it with `VITE_CONFIGHOP_API_URL` if needed. This unauthenticated MVP must be bound to localhost with one backend worker. Same-vendor PAN-OS projects use [finite temporary-storage and idle-expiry limits](docs/phase11b-projectstore-capacity.md). Project files are removed on deletion or clean server shutdown; an abrupt crash can leave temporary files requiring manual review.

`npm ci` uses the committed JavaScript lockfile. Python dependencies use version ranges and are not locked, so a later installation may resolve different versions; use an isolated environment and record installed versions when validating a candidate.

## Test

```powershell
cd backend
python -m pytest -q
python -m compileall src
```

From the repository root, run `npm test` and `npm run build`.

Core v0.1 parses PAN-OS XML, v0.2 previews exact interface dependencies, and v0.3 renders and validates a patched candidate. App v0.5 adds PA-3410 and PA-5410 hardware and PAN-OS compatibility checks. v0.6 adds documentation-verified PA-5410 native QSFP target speed rendering for ports 41–44 with an explicit 40G or 100G choice. v0.7 adds a model-specific hardware registry and PAN-OS support rules. The bounded cross-vendor Switch paths above are implemented; Firewall translation remains focused on PAN-OS and the documented FortiOS subset. Other cross-vendor paths, advanced features, and breakout conversion beyond documented hardware-specific behavior remain unsupported. See [core v0.7](docs/core/CORE_V0_7.md), [API v0.7](docs/api/API_V0_7.md), and [app v0.7](docs/app/APP_V0_7.md). Private XML and generated candidates belong in ignored `local-samples/` and `local-output/` directories.

## License

ConfigHop's first-party code, tests, documentation, fixtures, screenshots, and artwork are available under the [MIT License](LICENSE), based on the owner's confirmed distribution rights and contributor permissions. Contributors retain their own copyrights; this license does not transfer ownership. Third-party dependencies, including `lucide-react`, retain their separate upstream licenses and notices.
