# Phase 11B: local PAN-OS ProjectStore capacity

This policy applies only to the same-vendor PAN-OS XML workbench. It does not
change the cross-vendor Firewall or Switch session stores, translation scope,
or device-validation status.

| Limit | Value |
|---|---:|
| Active projects | 2 |
| Total store file bytes | 640 MiB |
| File bytes in one project | 320 MiB |
| Source XML | 100 MiB |
| Candidate XML | 100 MiB |
| Idle project lifetime | 24 hours |
| Concurrent store writes | 1 |
| Free space retained on the temporary volume | 1,024 MiB |

MiB means 1,048,576 bytes. A file exactly at a limit is accepted if all other
limits also hold. The file budgets count existing source and candidate files,
uploads, candidate staging, validation copies, and unreclaimed cleanup debt.
The store reserves additional bytes before writing. Source replacement retains
the prior source and candidate if upload or validation fails. Candidate failures
leave no candidate available for export. Idle expiry runs after 24 hours without
a project request; active operations and candidate snapshot creation are protected
by the project lock. A candidate download sends the authorized, digest-checked
snapshot even if the project changes after that check. Each in-flight candidate
download can retain up to 100 MiB in memory until its response completes.
Project access after expiry returns `PROJECT_EXPIRED` (HTTP 404). Expiry
cleanup runs periodically and before creating a project; storage is not reclaimed
until cleanup succeeds.

The service is supported only as one local user, one backend worker, and a
loopback HTTP listener. The documented startup command uses one worker. A
checkout-wide OS file lock rejects a second live worker for the same checkout;
it does not make separate copies or hosts share quotas. The client header is not
authentication. Do not expose this local API to a network.

Quota responses use `PROJECT_LIMIT_REACHED` (429),
`STORE_CAPACITY_EXCEEDED` (507), `PROJECT_CAPACITY_EXCEEDED` (507),
`SOURCE_TOO_LARGE` (413), `CANDIDATE_CAPACITY_EXCEEDED` (507),
`QUOTA_RESERVATION_UNAVAILABLE` (503), and `TEMP_STORAGE_UNAVAILABLE` (507).
Deleting an unused project can relieve the project-count and aggregate limits;
it cannot fix a source or per-project size violation. A failed filesystem
cleanup remains accounted. DELETE can retry cleanup for a workspace known to
the running store, and periodic expiry cleanup also retries it. Repeated failure
still reserves the debt and requires operator attention.

The store root is a Python temporary directory. Normal deletion and clean
service shutdown remove owned files. A crash or forced termination may leave a
directory behind. Inspect its ownership and contents manually before cleanup;
the application does not scan or delete unknown `confighop-*` directories.
The byte limits do not bound in-memory XML trees, CPU time, or allocations by
other applications, and a free-space check cannot prevent another process from
consuming disk afterward. These controls do not certify device import, packet
behavior, or production deployment.
