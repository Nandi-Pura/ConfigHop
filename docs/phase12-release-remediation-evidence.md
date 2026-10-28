# Phase 12 release remediation evidence

This is a private-repository review record, not publication approval. Baseline:
`main` at `9f3fd68eb6f55c5530485b93db2a5a5127e128cd`. PR #27 is merged;
PR #20 remains open and was not changed.

The owner selected MIT instead of Apache-2.0 as a **conditional direction**,
GitHub Private Vulnerability Reporting as the **preferred future channel**, and retention of
the current **Python dependency version ranges**. None of these choices is a
copyright attestation, repository-setting change, or claim of reproducible
Python resolution.

## REL-01: rights gate

The owner selected MIT as the simpler candidate. [The official MIT
text](https://opensource.org/license/mit) requires an accurate copyright year and holder and preservation of its notice
in copies or substantial portions. The license itself requires no notarization
or copyright registration. No `LICENSE` is added
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

The rights assessment is more specific than commit attribution:

| Class and reachable path | Apparent source | Rights/obligations evidence | MIT gate |
|---|---|---|---|
| Backend `backend/src/` | Git commits under multiple author identities | No assignment or licensing grant found | **BLOCKED**: attest authority for each contribution |
| Frontend `src/` | Git commits under multiple author identities | No assignment or licensing grant found | **BLOCKED**: attest authority for each contribution |
| Tests `backend/tests/`, `src/*.test.mjs`, `src/*.browser.mjs` | Repository commits | No test-code rights grant found | **BLOCKED**: include tests in attestation |
| Configuration fixtures `backend/tests/fixtures/` | Repository commits; synthetic labels and documentation ranges | Synthetic appearance does not prove origin or redistribution rights | **BLOCKED**: attest fixture origin and permissions |
| Documentation `README.md`, `docs/`, including PR #20 | Repository commits | Git author identity does not prove copyright ownership | **BLOCKED**: attest text and imported excerpts |
| Screenshots `artifacts/` | Browser-test outputs committed to Git | Generated image provenance and depicted-asset rights not attested | **BLOCKED**: attest screenshot distribution rights |
| Historical deleted artwork `public/brand/*.svg`, `public/favicon.svg` | Added at `a995058`, removed at `16f2ca5`; still reachable | No original artwork rights record found | **BLOCKED**: attest rights or decide separately how to treat public history |
| Current icons `lucide-react` | Installed third-party npm package | Installed package declares ISC; it is not repository-owned code | Preserve its own license obligations; do not relicense it |
| Fonts and vendored packages | CSS names local/system fonts; no tracked font file or vendored package directory found | No bundled font/vendor asset identified | **NOT_APPLICABLE** to tracked source; reassess release bundles |

The Git history contains four apparent author identities across the reviewed
refs, including identities other than the repository owner. A concise owner
confirmation can suffice for material the owner actually controls. It must
identify the rights holder and accurate attribution year, specify which code,
tests, documentation, fixtures, screenshots, and historical artwork the owner
created or can license, and disclose other contributors, employment/contractor
limits, and imported material. Obtain permission from another rights holder
where needed; an owner statement cannot override that holder's rights. No
confirmation or contribution grants are present; `REL01_LICENSE_GATE_BLOCKED`
and `MIT_LICENSE_OWNER_CONFIRMATION_REQUIRED`.

The advertised branches and PR head/merge refs yielded 104 reachable commits,
1,388 objects, 711 blobs, and no tags at the audit baseline. Historical deleted
files and PR #20's reachable commit were included. GitHub-retained unreachable
objects and Actions logs could not be fully enumerated. A local pattern scan of
reachable text blobs found no private-key block, GitHub token pattern, or AWS
access-key pattern. It flagged credential-shaped test strings and source-code
identifiers for contextual review. A dedicated history scanner was unavailable;
this is not a secret-clearance claim.

Before creating an MIT `LICENSE`, the owner must give that narrow factual
confirmation, approve the exact holder/year attribution, identify third-party
portions and their obligations, and decide the treatment of fixtures,
screenshots, and historical artwork. Obtain separate permission or exclude
material whose rights cannot be established. Do not rewrite history without a
separate owner decision. Do not describe an unlicensed public repository as
open source.

## REL-02 and REL-04: GitHub controls

No verified private vulnerability-reporting channel or owner-approved security
contact was available. A public `SECURITY.md` would be misleading until the owner
confirms a working private route. A future policy should direct private reports
through that route, request sanitized synthetic reproductions, and forbid
credentials, customer configurations, and sensitive screenshots in public issues.
It should not promise a response time without owner authorization.

The owner prefers GitHub Private Vulnerability Reporting (PVR). [GitHub's
configuration documentation](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)
limits researcher-submitted PVR to **public repositories**. ConfigHop is
currently **private**, so the external researcher form cannot be verified or
activated now. A private draft repository advisory lets administrators discuss
a vulnerability but does not supply an external reporting route. The owner must
choose an interim verified private contact if reports are needed before
publication. After separately authorized publication, an owner/admin must use
**Settings → Security and quality → Advanced Security → Private vulnerability
reporting → Enable**, then verify an external researcher sees **Security and
quality → Advisories → Report a vulnerability**. Only then should `SECURITY.md`
describe that route. No PVR setting was changed in this work.

The sole workflow uses `push` and `pull_request`, checks out the tested ref, and
needs repository read access to install dependencies, test, build, and upload
browser evidence. It has no `pull_request_target` trigger or repository secret
reference. This branch adds `permissions: contents: read`; it does not change
GitHub repository settings. The owner must inspect **Settings → Actions → General**
for default token permissions, fork PR approval and secret policies, then inspect
branch rules/required checks. GitHub's read-only main-branch metadata reports
`protected=false`, no required status checks, and enforcement `off`. The
branch-protection endpoint returned 403 (`Resource not accessible by
integration`); the rulesets endpoint returned 403 (`Upgrade to GitHub Pro or
make this repository public to enable this feature`). This does **not** prove
that every account-level workflow setting is safe. In **Settings → Actions →
General**, the owner must verify default token access is read-only, fork PRs
cannot receive write tokens or secrets, workflow approvals are appropriate,
and Actions cannot create/approve PRs without a need. Verify public-fork
approval policy immediately before any visibility change. In **Settings →
Branches** or **Rules → Rulesets**, enable an available main-branch rule with
the CI test check required before merge, or record the plan/visibility
prerequisite and recheck before publication. Until then:
`GITHUB_PUBLIC_FORK_SETTINGS_NOT_VERIFIED`.

An interim private-reporting option is an owner-approved, monitored security
contact reachable by invited users; the owner must supply and test the actual
address or other private route. No address is assumed, and no `SECURITY.md` is
added until a working route is verified.

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
packages**. A fresh Python 3.12 installation and a second audit on 2026-10-28
resolved the same versions. With `pip-audit 2.10.1 --vulnerability-service pypi
--path <isolated-venv>/Lib/site-packages`, PyPI advisory data reported no known
vulnerabilities for the installed third-party packages; the local editable
`confighop-core 0.7.0` is not on PyPI and cannot be audited by that service.
Only package names and versions were sent for advisory lookup, not repository
source or configurations. This does not prove future resolutions are
vulnerability-free.

The same isolated environment was re-audited on 2026-10-28 with
`pip-audit 2.10.1 --vulnerability-service pypi`: 26 installed distributions,
zero known advisory findings. This is environment evidence, not a lockfile or
a source-code audit.

No Python lock or constraints file exists; JavaScript uses `package-lock.json`.
The owner explicitly retained Python ranges; no lockfile or constraints file
will be added in this phase. CI tests Python 3.12; `backend/pyproject.toml`
declares Python 3.12 or newer. Record exact installed versions for each
candidate validation because future resolution may differ. A patched installer
baseline remains an owner-side installation prerequisite decision. Do not claim
byte-for-byte reproducibility from the current version ranges.

## Open gates

- `REL01_LICENSE_GATE_BLOCKED`: rights attestation and historical asset treatment.
- REL-02: external PVR is unavailable while private; choose an interim private
  route if needed, then separately authorize and verify PVR after publication.
- REL-04: main is unprotected; verify fork/Actions settings and require CI by an
  available branch rule before publication.
- REL-05: current Python environment audited under the approved ranges; future
  resolution remains unlocked by owner policy.
- `HISTORY_SECRET_CLEARANCE_NOT_VERIFIED`: no dedicated full-history scanner ran.

Repository visibility must remain private. No release, tag, merge, or device
validation is authorized by this record.

## Phase 12C decision matrix

| Gate | Evidence | Status |
|---|---|---|
| MIT license direction | Owner selected MIT as candidate; official text reviewed | PASS |
| First-party rights | Git history gives attribution, not legal control; `OWNERSHIP_NOT_VERIFIED` | NOT_VERIFIED |
| Other contributors | Four apparent author identities; no grants found; `PERMISSION_REQUIRED` | BLOCKED |
| Fixtures, screenshots, and artwork | Synthetic appearance and generated output do not establish rights; `OWNERSHIP_NOT_VERIFIED` | NOT_VERIFIED |
| Historical rights | Deleted SVGs remain reachable; no rights record; `OWNERSHIP_NOT_VERIFIED` | NOT_VERIFIED |
| Accurate MIT holder/year and `LICENSE` | Owner confirmation and attribution approval missing; no file added | BLOCKED |
| Third-party dependencies/notices | `lucide-react` declares ISC (`THIRD_PARTY_LICENSE_VERIFIED` for that package); other transitive notice obligations were not exhaustively reviewed | NOT_VERIFIED |
| Private reporting route and `SECURITY.md` | External PVR requires a public repository; no interim contact verified | BLOCKED |
| README Beta guidance | Backup, review, sensitive-data, blocked export, and device limits stated | PASS |
| GitHub fork/Actions settings | Workflow uses read-only token; administration settings inaccessible | NOT_VERIFIED |
| Main branch protection/required checks | Branch metadata reports protection disabled and no required checks | FAIL |
| Python dependency audit | Python 3.12 isolated installation; 2026-10-28 PyPI audit reported no known third-party findings | PASS |
| Python ranges | Owner retained ranges; no Python lock or constraints | PASS |
| History secret clearance | Reachable refs had bounded pattern scan; no dedicated scanner; unreachable objects not enumerable | NOT_VERIFIED |
| PR #28 exact-head CI | Run 40707872777 passed at `6a674159626a831e4eafc5cc34bd29fc7abc5af0`; rerun after this edit | NOT_VERIFIED |
| Repository visibility | GitHub repository metadata says private | PASS |
