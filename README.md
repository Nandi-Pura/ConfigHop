# ConfigHop

<img src="public/brand/confighop-logo.svg" alt="ConfigHop" width="180" />

Network Configuration Migration

ConfigHop is an open-source network configuration migration workbench for moving configurations across hardware platforms and network vendors. The current frontend uses mock data; it does not perform production migrations.

Example migration scenarios: Palo Alto PA-3410 → PA-5410, Cisco Catalyst → HPE Aruba CX, and Palo Alto → Fortinet.

## Stack

- React
- TypeScript
- Vite
- Lucide React
- CSS (no component framework)

## Run

```bash
npm install
npm run dev
```

Production build:

```bash
npm run build
```

## Included interactions

- Source/target platform selectors
- Local configuration file upload
- Paste-from-clipboard support
- Interface mapping search and filters
- Manual target interface mapping
- Auto-map suggestions
- Table / hardware mapping views
- Migration readiness state
- Generate Migration action
- Result tabs (overview, raw comparison, semantic changes, interface mapping, migration plan, candidate config, findings)
- LocalStorage Save/Load Project

All data and migration logic are mocked locally in the browser. No backend or API is included.
