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
where needed; an owner statement cannot override that holder's rights. At
the Phase 12C review, no approval scope or contribution grants were documented;
`REL01_LICENSE_GATE_BLOCKED`
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
| Other contributors | Prior approval is now owner-reported for Gearry and Udin; its MIT/public distribution scope is not documented | BLOCKED |
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
| PR #28 exact-head CI | [Run 40709714425](https://github.com/Nandi-Pura/ConfigHop/actions/runs/40709714425) passed at `f1da3bd5f14c81a16b45522c8576404e3cb6da83`; verify again after any edit | PASS |
| Repository visibility | GitHub repository metadata says private | PASS |

## Phase 12D: targeted owner-gate investigation

The current advertised branches and PR head/merge refs contain 109 reachable
commits, 1,409 objects, 717 blobs, and no tags. The four Git author strings
below are attribution evidence, not a count of legal copyright holders. Email
addresses and private rights documents are deliberately omitted.

| Git author identity | Relevant reachable changes | Rights evidence | Minimum clarification | Status |
|---|---|---|---|---|
| Nandi Nugraha (62 commits) | Backend, frontend, tests, docs, fixtures, screenshots; historical SVG addition `a995058` | Git attribution only | Confirm legal holder, relevant years, employment/client terms, AI-assisted or adapted material, and asset rights | NOT_VERIFIED |
| Nandi Pura (28 commits) | PR merge commits, e.g. `9f3fd68`; no distinct file patch in the ordinary commit walk | Git attribution only; may be an alias | Confirm relationship to the first identity; do not count as a separate holder without evidence | NOT_VERIFIED |
| Partomuan Gearry Andreas Josua (13 commits) | Backend/API, frontend, tests, docs, e.g. `cfb1339` | No contribution license, assignment, or permission located | Confirm contributor permission or applicable employer/client authority for MIT distribution | BLOCKED |
| chaerudin79 (6 commits) | Switch/Aruba frontend, tests, docs, e.g. `ae4c5bb` | No contribution license, assignment, or permission located | Confirm contributor permission or applicable employer/client authority for MIT distribution | BLOCKED |

No repository record establishes which work was AI-assisted, original, copied,
or adapted. AI assistance alone neither proves third-party ownership nor proves
copyrightability or originality. The owner must state the relevant development
facts; commit authorship is insufficient.

| Asset class | Reachable examples | Provenance and minimum missing evidence | Redistribution status |
|---|---|---|---|
| Python code | `backend/src/` | Multiple author identities; rights/assignment and adapted-source facts missing | NOT_VERIFIED |
| Frontend code | `src/` | Multiple author identities; rights/assignment and adapted-source facts missing | NOT_VERIFIED |
| Tests | `backend/tests/`, `src/*.test.mjs`, `src/*.browser.mjs` | Multiple author identities; test-code rights missing | NOT_VERIFIED |
| Documentation | `README.md`, `docs/`, PR #20's reachable head | Author attribution exists; external text/contract rights need confirmation | NOT_VERIFIED |
| Configuration fixtures | `backend/tests/fixtures/` | Synthetic-looking labels do not prove creation or permission; attest origin and absence of customer data | NOT_VERIFIED |
| Screenshots | `artifacts/` | Browser-generated files; confirm depicted assets and privacy before redistribution | NOT_VERIFIED |
| Historical SVGs | `public/brand/confighop-logo.svg`, `public/brand/confighop-mark.svg`, `public/favicon.svg`; added `a995058`, removed `16f2ca5` | Still reachable after deletion; confirm creator and distribution right | BLOCKED |
| Icons | `lucide-react` dependency | Installed package declares ISC; preserve its license rather than applying MIT to it | THIRD_PARTY_LICENSE_VERIFIED for this package |
| Other third-party assets | No bundled font or vendored package found in tracked source | Review release bundle and transitive notices before publication | NOT_VERIFIED |

This leaves `REL01_LICENSE_GATE_BLOCKED`. A truthful, short owner confirmation
of the existing contributor approval scope and asset provenance can resolve it; no notarization
or registration is demanded. If a historical asset lacks permission, decide its
treatment separately before public distribution. No history rewrite is authorized.

### Confidential reporting and repository controls

[GitHub documents](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)
external private vulnerability reporting for **public** repositories. It is
not an external route for this private repository. Administrators can create
[draft repository advisories](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/fix-reported-vulnerabilities/create-repository-advisory)
for internal handling; that does not let an outside researcher initiate a
confidential report. No actual contact destination or successful test delivery
was supplied. Options are an owner-controlled security email, a verified
private form, or another owner-approved confidential channel. For any option,
the owner must verify control, external reachability, recipient notification,
attachment/privacy handling, and receipt of a harmless test message. Until then
`REL02_PRIVATE_REPORTING_ROUTE_REQUIRED`; no `SECURITY.md` is warranted.

The PR workflow has `push` and `pull_request` triggers, repository-level
`permissions: contents: read`, checkout of the tested ref, backend/frontend
installation and tests, browser artifact upload, and no `pull_request_target`,
secret reference, or write-token request. The Actions job actually named `test`
passed in run 40709714425. This source review cannot establish repository
settings or the safety of future untrusted fork changes; inspect browser
artifacts before making them public.

Read-only main metadata still reports `protected=false`, required checks empty,
and enforcement `off`. The branch-protection API returned 403 to this
integration. The rulesets API returned 403 with `Upgrade to GitHub Pro or make
this repository public to enable this feature`. [GitHub's branch-protection
documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)
limits private-repository protection to eligible paid plans; this response does
not establish the owner's exact plan or UI capabilities. No setting was changed.

Owner-side checklist (observe first; configure only with separate approval):

| GitHub location | Observed | Proposed minimum and timing |
|---|---|---|
| Settings → Actions → General → Workflow permissions | Admin value not accessible | Read-only default; disallow Actions creating/approving PRs unless required; verify now and before public |
| Settings → Actions → General → Fork pull request workflows | Admin value not accessible | Do not send secrets or write tokens; require approval where available; verify private-fork policy now |
| Settings → Actions → General → Approval for running fork pull request workflows from contributors | Admin value not accessible | Review public-fork approval policy immediately before any visibility change |
| Settings → Actions → General → Actions permissions | Admin value not accessible | Review allowed actions and third-party action trust; preserve current CI behavior |
| Settings → Branches → Branch protection or Settings → Rules → Rulesets | Main metadata says unprotected; plan support unknown | If available while private, require PRs and `test`, prevent force-push and deletion, avoid broad bypass; otherwise resolve plan/visibility prerequisite before publication |
| Security and quality → Advisories / private vulnerability reporting | External route unavailable while private; setting inaccessible | Verify interim private route now; after separately authorized publication, enable PVR and test as an outside reporter |

The private-fork and public-fork controls have different GitHub UI sections;
[GitHub's Actions settings documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)
describes both. `REL04_REPOSITORY_SETTINGS_NOT_VERIFIED` remains open.

### History privacy and preserved gates

No `gitleaks`, `trufflehog`, `detect-secrets`, or `git-secrets` executable was
available locally. A local-only scan of all 717 reachable blobs in the fetched
refs found no private-key block, GitHub token pattern, or AWS access-key pattern;
it printed no candidate values. It does not cover other secret formats, GitHub
unreachable objects, or a dedicated scanner's rules. Thus
`HISTORY_SECRET_CLEARANCE_NOT_VERIFIED` remains a publication blocker.

The README retains Beta/Technical Preview, offline workflow, backup,
engineer-review, sensitive-data, BLOCKED export, and device/packet-flow/
production limitations. The owner-approved Python version ranges and the
2026-10-28 isolated Python 3.12 / pip-audit 2.10.1 result remain unchanged;
future dependency resolution is still not byte-for-byte reproducible.

## Phase 12E: owner-reported contributor approval

The owner states: “Gearry dan Udin sudah disetujui dan tidak perlu diminta izin
terpisah.” This resolves whether to request duplicate approval. It does **not**
establish the text or scope of prior permission. No separate contributor
request is planned merely because these identities appear in Git history.

| Identity and substantive commits | Owner report | Scope of existing approval | Verdict |
|---|---|---|---|
| Partomuan Gearry Andreas Josua (“Gearry”): backend/API, frontend, tests, docs; e.g. `cfb1339`, `d976688` | `OWNER_REPORTED_PREVIOUSLY_APPROVED` | Use within ConfigHop, modification, public redistribution, and MIT terms have not been identified | NOT_VERIFIED for `MIT_RELICENSING_RIGHTS_VERIFIED` |
| `chaerudin79` (“Udin”): Switch/Aruba frontend, tests, docs; e.g. `ae4c5bb`, `ac10db2` | `OWNER_REPORTED_PREVIOUSLY_APPROVED` | Same four scope questions remain unidentified | NOT_VERIFIED for `MIT_RELICENSING_RIGHTS_VERIFIED` |
| Nandi Nugraha and Nandi Pura | Owner-associated author strings; latter appears on merge commits | Legal holder, relevant years, and any employer/client limits remain unconfirmed | NOT_VERIFIED |
| Other identities | No other Git author string in the 110 reachable commits after the Phase 12D change | No additional identity found; this does not prove no uncredited third-party material | NOT_VERIFIED |

The exact remaining rights question is whether the **existing** Gearry/Udin
arrangement already permits use, modification, public distribution, and MIT
licensing of their contributions. The owner can identify that arrangement and
its scope privately; a new permission request is unnecessary if it is already
sufficient. Do not place contracts, contact details, or signatures in this
future-public repository. Also confirm the actual copyright holder and years,
first-party authority and employment limits, fixture and screenshot rights,
and redistribution rights for the reachable historical files
`public/brand/confighop-logo.svg`, `public/brand/confighop-mark.svg`, and
`public/favicon.svg` (added at `a995058`, removed at `16f2ca5`). The MIT text
cannot cure a rights problem in retained history. `REL01_MIT_RIGHTS_NOT_VERIFIED`;
no `LICENSE` is added.

The other owner actions remain: approve and test a confidential interim contact
(`REL02_INTERIM_REPORTING_CHANNEL_REQUIRED`), and inspect Actions fork/token
settings and plan-supported protection for main, including required CI job
`test` (`REL04_REPOSITORY_SETTINGS_NOT_VERIFIED`). Read-only main metadata still
reports no protection or required checks; the settings were not changed.
README Beta guidance, Python version ranges, and the prior Python 3.12 audit
are preserved. No dedicated local secret scanner was available; Phase 12D's
bounded 717-blob pattern scan is not publication clearance. The repository
remains private, and PR #28 remains a draft until independent review.
