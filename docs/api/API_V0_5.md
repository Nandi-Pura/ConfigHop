# API v0.5 additions

The local `/api/v1` service retains v0.4 project isolation, upload limits, mutation header, and download rules. Profiles now include verified `paloalto-pa-3410`, verified `paloalto-pa-5410`, and development-only `paloalto-synthetic-64`.

New endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/evidence` | Curated official source metadata |
| GET | `/evidence/{evidence_id}` | One evidence record |
| PUT | `/projects/{project_id}/source-profile` | Manual source hardware and PAN-OS train |
| POST | `/projects/{project_id}/compatibility` | Platform and every effective target assignment |
| GET | `/projects/{project_id}/compatibility` | Latest assessment |

`PUT /projects/{project_id}/target-profile` also accepts `panos_train`. Profile detail includes interface groups, per-port candidate support, required conditions, supported PAN-OS trains, and evidence IDs. Preview adds platform/hardware assessments and `overall_status` without changing Core's `MigrationPreview`. Candidate metadata adds profile, PAN-OS, hardware status, and evidence fields. The candidate endpoint returns `candidate_available: false` for blocked verified hardware before calling the renderer. Review findings need `allow_review: true`; errors cannot be overridden.

Changing source XML, either profile, either train, or mappings invalidates prior compatibility, preview, candidate, and semantic diff. Source XML and inventory remain when profile context changes. Runtime evidence lookup is local and does not fetch vendor websites.
