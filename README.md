# ConfigMorph UI Prototype

Greenfield frontend prototype for the ConfigMorph migration workbench.

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
