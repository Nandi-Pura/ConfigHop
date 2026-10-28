# Phase 12 release remediation evidence

This is a private-repository review record, not publication approval. Baseline:
`main` at `9f3fd68eb6f55c5530485b93db2a5a5127e128cd`. PR #27 is merged;
PR #20 remains open and was not changed.

## REL-01: rights gate

The owner selected Apache-2.0 as a direction. No `LICENSE` or `NOTICE` is added
because repository authorship and a Git commit do not prove the authority to
license every contribution or redistribute every historical asset.

| Material | Evidence inspected | Rights status |
|---|---|---|
| Backend, frontend, and test source | Reachable commits include four author identities; no contributor rights grants or owner attestation were found | Unresolved |
| Test configuration fixtures | Tracked fixtures use synthetic labels and documentation IP ranges; origin and redistribution authority were not attested | Unresolved |
| Documentation, including PR #20 | Repository history establishes provenance of changes, not relicensing authority | Unresolved |
| Current icons | Imported through `lucide-react`; its installed package license must remain with that dependency | Third-party dependency; no repository relicensing claim |
| Current fonts | CSS names system/local fonts; no font file is tracked | No bundled font found |
| Screenshots | Tracked browser screenshots use the workbench; rights to every depicted component and the generated images were not attested | Unresolved |
| Historical artwork | Deleted `public/brand/confighop-logo.svg`, `public/brand/confighop-mark.svg`, and `public/favicon.svg` remain reachable in Git history | Unresolved |
| Vendored packages | No vendored dependency directory found in tracked files; npm dependencies are installed from the lockfile | No vendored package found |

The advertised branches and PR head/merge refs yielded 104 reachable commits,
1,388 objects, 711 blobs, and no tags at the audit baseline. Historical deleted
files and PR #20's reachable commit were included. GitHub-retained unreachable
objects and Actions logs could not be fully enumerated. A local pattern scan of
reachable text blobs found no private-key block, GitHub token pattern, or AWS
access-key pattern. It flagged credential-shaped test strings and source-code
identifiers for contextual review. A dedicated history scanner was unavailable;
this is not a secret-clearance claim.

Before creating an Apache-2.0 `LICENSE`, the owner must provide a documented
rights attestation for the first-party material and contributions, identify any
third-party portions and their obligations, and decide the treatment of fixtures,
screenshots, and historical artwork. Obtain separate permission or exclude
material whose rights cannot be established. Do not rewrite history without a
separate owner decision. Review the official text at
<https://www.apache.org/licenses/LICENSE-2.0> when the gate is satisfied.

## REL-02 and REL-04: GitHub controls

No verified private vulnerability-reporting channel or owner-approved security
contact was available. A public `SECURITY.md` would be misleading until the owner
confirms a working private route. A future policy should direct private reports
through that route, request sanitized synthetic reproductions, and forbid
credentials, customer configurations, and sensitive screenshots in public issues.
It should not promise a response time without owner authorization.

The sole workflow uses `push` and `pull_request`, checks out the tested ref, and
needs repository read access to install dependencies, test, build, and upload
browser evidence. It has no `pull_request_target` trigger or repository secret
reference. This branch adds `permissions: contents: read`; it does not change
GitHub repository settings. The owner must inspect **Settings → Actions → General**
for default token permissions, fork PR approval and secret policies, then inspect
branch rules/required checks and **Settings → Security** for private vulnerability
reporting. Record the results before publication. Until then:
`GITHUB_PUBLIC_FORK_SETTINGS_NOT_VERIFIED`.

## REL-05: dependency and installation evidence

Python 3.12 isolated environment: `python -m pip install -e ".[api,dev]"`
completed. Direct requirements are Pydantic 2.x, defusedxml 0.7.x, FastAPI
0.115+, Uvicorn 0.30+, pytest 8–9, and HTTPX 0.27+. Resolved versions were:

```text
annotated-doc 0.0.5; annotated-types 0.8.0; anyio 4.15.1
certifi 2026.10.23; click 8.5.0; colorama 0.4.6
confighop-core 0.7.0; defusedxml 0.7.1; fastapi 0.162.0
h11 0.16.0; httpcore 1.0.9; httpx 0.28.1; idna 3.20
iniconfig 2.3.1; opentelemetry-api 1.45.1; packaging 26.3
pip 26.2.2; pluggy 1.7.0; pydantic 2.14.1
pydantic_core 2.50.1; Pygments 2.21.0; pytest 9.2.0
starlette 1.10.0; typing_extensions 4.16.0
typing-inspection 0.4.4; uvicorn 0.54.0
```

`pip-audit 2.10.1 --path <isolated-venv>/Lib/site-packages` initially found
12 advisory records for installer `pip 25.0.1` and none for application/runtime
packages. The distinct reported IDs were `PYSEC-2026-1795`,
`PYSEC-2026-1796`, `PYSEC-2026-2875`, `PYSEC-2026-2876`,
`PYSEC-2026-196`, and `PYSEC-2026-3721`; the scanner listed patched versions
across 25.3–26.2.0. `pip` is installation tooling, not an application runtime
requirement. After upgrading only that disposable environment's installer to
`pip 26.2.2`, the same audit reported **0 known vulnerabilities in 26 installed
packages**. This does not prove future resolutions are vulnerability-free.
No Python lock or constraints file exists; JavaScript uses `package-lock.json`.
The owner should decide whether to require a patched installer baseline and
whether to add narrowly scoped Python constraints in a separate change. Do not
claim byte-for-byte reproducibility from the current version ranges.

## Open gates

- `REL01_LICENSE_GATE_BLOCKED`: rights attestation and historical asset treatment.
- REL-02: verify a private reporting channel before publishing `SECURITY.md`.
- REL-04: verify GitHub fork/Actions/security settings in the owner account.
- REL-05: current environment audited; future Python resolution remains unlocked.

Repository visibility must remain private. No release, tag, merge, or device
validation is authorized by this record.
