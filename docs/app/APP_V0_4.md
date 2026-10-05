# ConfigHop Firewall app integration v0.4

The approved dark workbench layout remains. Firewall now starts empty and uses the local API: upload PAN-OS XML, inspect real inventory counts and physical rows, choose the explicitly synthetic development target profile, map physical ports manually, preview dependencies, and generate a validated candidate. Switch remains a frontend mock with no backend migration path.

The target selector does not claim PA-5410 support. Automatic mapping and confidence scores are unavailable. The mapping table uses parsed physical interfaces and dependency counts. Readiness follows the Core preview status; `READY` does not mean production safe. A `REVIEW_REQUIRED` candidate needs explicit engineer confirmation. `BLOCKED` results show real findings.

Result tabs use the API candidate metadata, Core semantic diff, preview impacts, plan operations, and parser/preview/renderer findings. Candidate download fetches the validated XML endpoint. Raw Comparison shows real source and candidate XML without invented changed-line highlighting. Changed Only is disabled. Search and reversible Expanded mode remain available.

The reusable virtualized viewer renders only visible lines plus overscan for source, candidate, and raw comparison. Files larger than 10 MiB can still upload to the 100 MiB backend limit, but browser text preview is omitted. Download remains available. Source and candidate XML stay in memory only while displayed; Firewall Save Project stores project ID and safe metadata, never XML. Load rehydrates an active backend session. Sessions expire on backend restart, requiring a new upload. Legacy saved Firewall configuration bodies are removed rather than re-saved or uploaded automatically.

The API defaults to `http://127.0.0.1:8000/api/v1`; see `.env.example`. Backend downtime shows a compact error without crashing Switch. No real hardware catalog, live firewall interaction, policy translation, or production deployment is included.
