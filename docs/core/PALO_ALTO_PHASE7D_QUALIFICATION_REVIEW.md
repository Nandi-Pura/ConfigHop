# Phase 7D evidence qualification review

## Current decision

The canonical catalog contains 13 blocking `EVIDENCE_PARTIAL` gaps: three P0 and ten P1. Eight PA-3200/5200 gaps have controlled protocols; five PA-1400 gaps remain parked. No device observations or new authoritative answers were supplied. All 1,668 cases are `NOT_RUN`; coverage is `INCOMPLETE`. No gap is closed.

## Target inventory and case coverage

| Canonical gap | Priority | Exact models/groups | Planned cases |
| --- | --- | --- | ---: |
| PAN-GAP-PA3200-AUTO-RJ45 | P0 | PA-3220/3250/3260 RJ45 1–12 | 144 |
| PAN-GAP-PA3200-OPTICAL-1G | P1 | PA-3220 SFP 13–16 | 48 |
| PAN-GAP-PA3200-OPTICAL-MIXED | P1 | PA-3220 SFP+ 17–20; PA-3250/3260 SFP+ 13–20 | 288 |
| PAN-GAP-PA3200-QSFP-40G | P1 | PA-3260 QSFP+ 21–24 | 48 |
| PAN-GAP-PA5200-AUTO-RJ45 | P0 | PA-5220/5250/5260/5280 RJ45 1–4 | 240 |
| PAN-GAP-PA5200-OPTICAL | P1 | PA-5220/5250/5260/5280 SFP+ 5–20 | 480 |
| PAN-GAP-PA5200-QSFP-40G | P1 | PA-5220 QSFP 21–24 | 60 |
| PAN-GAP-PA5200-QSFP-40-100G | P1 | PA-5250/5260/5280 QSFP 21–24 | 360 |

The manifest preserves exact registry group IDs, including `pa3260-QSFP+ 21-24` and `pa5220-QSFP 21-24`. It contains 20 model/group scopes and 12 field/action definitions, expanded across supported trains and applicable optic rates. Case IDs use canonical gap/model/train/group/action/field/rate SHA-256 identities. Patch version and exact interface must be supplied with future observations; no patch or interface behavior is generalized from planning.

## Parked inventory

`PAN-GAP-PA1400-BASE-RJ45` (P1), `PAN-GAP-PA1400-HA1-REMAP` (P1), `PAN-GAP-PA1400-MULTIGIG` (P0), `PAN-GAP-PA1400-OPTICAL` (P1), and `PAN-GAP-PA1400-POE` (P1) remain visible. They have no Phase 7D device protocol scope. PA-1410/1420 remain ANALYSIS_ONLY; no Multi-Gig, PoE, or HA implementation follows.

## Required evidence and unresolved dimensions

Every target gap requires exact-model speed and duplex semantics: omission/default versus explicit auto, manual candidate acceptance/rejection, load versus commit, exported node presence/value, normalization, and re-import. Optical cases additionally require installed transceiver/rate context. Hardware rates and source XML cannot establish accepted target representation. The PA-5200 11.2 CLI-versus-XML boundary remains unanswered.

`evidence_inventory` projects required facts, evidence class requirements, references, unresolved dimensions, priorities, and blocking states directly from the frozen gap catalog. It reports current runtime support separately from historical analysis-only catalog metadata. The latter remains a frozen historical artifact.

## Scope and sufficiency assessment

The offline assessment validates requested exact model, patch/hotfix version, train, interface, port group, optic rate, protocol case, field, media, recorded outcomes, artifact references/hashes, sanitization, author, reviewer, timestamp, and provenance. Incomplete coverage identifies missing case IDs and fields. Scope mismatches or contradictory outcomes reject readiness. Different patches within the same train are distinct scopes.

Complete synthetic metadata can exercise `READY_FOR_REVIEW`, with `synthetic=true`, `device_validated=false`, and `production_state_changed=false`. This is a structural test result, never a technical qualification. Negative device outcomes can contribute to boundary coverage when later-stage non-applicability is justified. Missing duplex, export, or re-import coverage remains incomplete.

Actual evidence supplied: **0**. Actual experiments executed: **0**. Observed device outcomes: **none**. Current missing evidence: all 1,668 planned case observations or equivalent precisely scoped authoritative statements. Current contradictions: none supplied; the framework tests conflict detection with synthetic metadata.

## Provenance and independent review

Future human review must record author, independent reviewer, observation/review times, artifact references/hashes, source class, technical reasoning, explicit decision and qualified scope. No reviewer or vendor answer is fabricated here. Artifact identifiers and hashes do not prove technical validity; retained sanitized evidence must be examined independently.

## Vendor option

The existing three requests remain `REQUEST_READY` / `NOT_RECEIVED`; the manifest retains `AWAITING_VENDOR`. Authoritative exact-model documents or engineering statements are an optional future route, subject to the same semantic coverage and scope bar. Community material may inform hypotheses but cannot independently establish review readiness or close gaps. TAC access is not required to complete this framework milestone.

## Frozen runtime and evidence boundaries

PA-3410/5410 remain SUPPORTED. PA-3220/3250/3260/5220/5250/5260/5280 remain SCOPED. PA-1410/1420 remain ANALYSIS_ONLY. PAN-OS support rules, same-train restrictions, renderer operations, candidate XML, API, Firewall UI, Switch, and Phase 7C deployment plans are unchanged.

The gap catalog, vendor request manifest, and evidence registry remain untouched. SCOPED non-interference rendering does not prove canonical speed/duplex serialization, and candidate validation does not prove physical verification. No `EVIDENCE_READY` or `DEVICE_VALIDATED` transition is performed.

## Reproducible checks and next milestone

Validate the manifest against canonical sources, run Phase 7D synthetic tests, frozen Phase 5/6A/6B oracles, direct Core security, Phase 7B optical, and Phase 7C identity/deployment tests. The controlled validation companion document defines the future lab procedure; this report is planning evidence only.

Recommend Phase 7E — Evidence Intake Readiness & Qualification Gate Hardening. It is not started here. Any future evidence collection or support promotion requires separate authorization and review.
