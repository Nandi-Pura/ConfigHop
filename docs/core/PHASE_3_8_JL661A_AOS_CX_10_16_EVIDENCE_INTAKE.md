# Phase 3.8 — JL661A / AOS-CX 10.16 Manual Evidence Intake

**Scope:** `CX6300M_48G_POE` / `JL661A`, standalone, AOS-CX `10.16`.

**Decision:** Not qualified. This intake is review material only. It does not add evidence records, capabilities, compatibility rules, renderer behavior, or generated configuration.

## Review rules

- `PROVEN`: official source retrieved/reviewed at cited locator with exact model/train applicability.
- `PARTIALLY_PROVEN`: official source supports narrower claim; never promote to exact-train or command applicability.
- `MISSING`: required official proof not retrievable or reviewed.
- Reviewer replaces `UNASSIGNED`, records review date, preserves local copy where licensing permits, cites exact locator before code changes.
- Minimum-version proof is **not** exact-train qualification. Series-level command documentation is **not** automatically model/train-scoped applicability.

## Current evidence boundary

| Existing ID | Status here | What it supports | What it does not support |
|---|---|---|---|
| `ARUBA-EVD-CX6300-1012-RN` | PARTIALLY_PROVEN | `JL661A` identity; minimum AOS-CX `10.04.3000`, as registry records. | `10.16` qualification; command applicability; exact ports/types. |
| `ARUBA-EVD-LIFECYCLE-1016` | UNREVIEWED | Registry assertion: 10.16 LSR through July 2029. | Reviewed lifecycle proof. |
| `ARUBA-EVD-CX6300-1016` | UNREVIEWED | Registry assertion only. | Reviewed exact-SKU qualification; official URL inaccessible in Phase 3.7. |

## Evidence checklist

| ID | Required claim | Status | Exact missing proof / obtain from |
|---|---|---|---|
| `P38-01` | `JL661A` supported on exact AOS-CX `10.16`. | MISSING | 10.16 release notes or Support Portal compatibility/download record explicitly listing `JL661A`/CX 6300M and 10.16. |
| `P38-02` | VLAN creation and VLAN-ID syntax applies. | MISSING | AOS-CX 10.16 CLI entry `vlan <VLAN-ID>`, applicable to CX 6300/JL661A. |
| `P38-03` | Access interface mode and access-VLAN syntax applies. | MISSING | Interface L2 mode plus `vlan access <VLAN-ID>` entries, applicability/restrictions. |
| `P38-04` | Trunk interface mode and native-VLAN syntax applies. | MISSING | Interface L2 mode plus `vlan trunk native <VLAN-ID>` entries. |
| `P38-05` | Allowed VLAN range syntax applies. | MISSING | `vlan trunk allowed <range>` grammar/example, CX 6300 applicability. |
| `P38-06` | Administrative enable/disable syntax applies. | MISSING | Interface-context `shutdown` and `no shutdown` entries. |
| `P38-07` | JL661A port IDs/types exact. | MISSING | Official JL661A datasheet, installation guide, or hardware spec mapping ports and types. |
| `P38-08` | Official lifecycle/support status for 10.16. | MISSING | Official lifecycle notice naming 10.16, release classification, dates/status. |

Required sources: HPE Aruba Networking official AOS-CX 10.16 CLI guide; JL661A official hardware document; official 10.16 release notes or Support Portal; official lifecycle notice/Support Portal. Do not use community examples.

## Evidence record worksheets

### P38-01 — Exact-train hardware qualification

| Field | Value |
|---|---|
| Evidence ID | `P38-01` |
| Official publisher | HPE Aruba Networking — required |
| Document title | Not yet obtained |
| Exact URL or local document reference | Required: `https://www.arubanetworks.com/techdocs/AOS-CX/10.16/RN/index.html` or authenticated Aruba Support Portal record; not reviewed here |
| Document version/publication date | Unknown |
| Page, section, or command-reference entry | Required: Supported Hardware Platforms / exact `JL661A` entry |
| Exact model/SKU scope | Required: `JL661A` / Aruba 6300M 48G Class 4 PoE 4SFP56 |
| Exact OS release/train scope | Required: AOS-CX `10.16` (and build if scoped) |
| Claim supported | Exact `JL661A` qualification on 10.16 |
| Known limitations | `ARUBA-EVD-CX6300-1012-RN` records only minimum `10.04.3000`; not exact-train proof. 10.16 URL inaccessible in Phase 3.7. |
| Reviewer / review status | `UNASSIGNED` / `MISSING` |

### P38-02 through P38-06 — Basic L2 commands

| Field | `P38-02` | `P38-03` | `P38-04` | `P38-05` | `P38-06` |
|---|---|---|---|---|---|
| Evidence ID | `P38-02` | `P38-03` | `P38-04` | `P38-05` | `P38-06` |
| Official publisher | HPE Aruba Networking — required | HPE Aruba Networking — required | HPE Aruba Networking — required | HPE Aruba Networking — required | HPE Aruba Networking — required |
| Document title | Not yet obtained: AOS-CX 10.16 CLI guide | Same | Same | Same | Same |
| Exact URL or local document reference | Required: official AOS-CX 10.16 CLI guide; save permitted local review copy | Same | Same | Same | Same |
| Document version/publication date | Unknown | Unknown | Unknown | Unknown | Unknown |
| Page, section, or command-reference entry | `vlan <VLAN-ID>` | L2 mode; `vlan access <VLAN-ID>` | L2 mode; `vlan trunk native <VLAN-ID>` | `vlan trunk allowed <range>` | `shutdown`; `no shutdown` |
| Exact model/SKU scope | Required: CX 6300/JL661A or explicit coverage | Same | Same | Same | Same |
| Exact OS release/train scope | Required: AOS-CX 10.16 | Same | Same | Same | Same |
| Claim supported | VLAN creation / ID | Access mode / VLAN | Trunk mode / native VLAN | Allowed VLAN range | Administrative disable / enable |
| Known limitations | Existing renderer/test strings not authoritative; no command guide reviewed. | Same | Same | Same | Same |
| Reviewer / review status | `UNASSIGNED` / `MISSING` | `UNASSIGNED` / `MISSING` | `UNASSIGNED` / `MISSING` | `UNASSIGNED` / `MISSING` | `UNASSIGNED` / `MISSING` |

### P38-07 — Port layout

| Field | Value |
|---|---|
| Evidence ID | `P38-07` |
| Official publisher | HPE Aruba Networking — required |
| Document title | Not yet obtained: JL661A product datasheet, installation guide, or hardware specification |
| Exact URL or local document reference | Required: official `JL661A` document; catalog code is not a citation |
| Document version/publication date | Unknown |
| Page, section, or command-reference entry | Required: front-panel/port map or specification table |
| Exact model/SKU scope | `JL661A` only |
| Exact OS release/train scope | Hardware layout; record document release. No OS claim unless document makes one. |
| Claim supported | Exact `1/1/1`–`1/1/48`, `1/1/49`–`1/1/52` numbering; copper/SFP56 types |
| Known limitations | Current catalog models these IDs/types, but Phase 3.7 did not retrieve reviewed official model-specific port reference. |
| Reviewer / review status | `UNASSIGNED` / `MISSING` |

### P38-08 — AOS-CX 10.16 lifecycle

| Field | Value |
|---|---|
| Evidence ID | `P38-08` |
| Official publisher | HPE Aruba Networking — required |
| Document title | Not yet obtained: AOS-CX 10.16 lifecycle/support notice |
| Exact URL or local document reference | Required: official lifecycle notice or authenticated Support Portal record. Registry URL `https://www.arubanetworks.com/support-services/end-of-life-policy/` was not reviewed for this claim here. |
| Document version/publication date | Unknown |
| Page, section, or command-reference entry | Required: 10.16 release classification and support/EOS dates |
| Exact model/SKU scope | AOS-CX product lifecycle; not model-specific |
| Exact OS release/train scope | AOS-CX `10.16` |
| Claim supported | Official lifecycle/support status |
| Known limitations | Registry `ARUBA-EVD-LIFECYCLE-1016` is existing assertion, not reviewed proof for this intake. Lifecycle proof cannot qualify JL661A on 10.16. |
| Reviewer / review status | `UNASSIGNED` / `MISSING` |

## Qualification gate

Before a separate qualification change, reviewer must mark `P38-01` and `P38-02`–`P38-07` **PROVEN**, with official locators, exact scope, and named reviewer. `P38-08` establishes release-support context; it cannot substitute for `P38-01`. Do not create `READY` evidence from this report.

## Non-changes

- Compatibility remains `REVIEW_REQUIRED` for `aruba-cx-6300m-48g-poe-jl661a` with `aos-cx-10.16`.
- No capability claim, evidence-registry record, renderer, PAN-OS behavior, test, or configuration changed.
- No schema change: `SwitchEvidence` is evaluated-evidence registry; worksheet-only fields belong in this intake until documents are reviewed.
