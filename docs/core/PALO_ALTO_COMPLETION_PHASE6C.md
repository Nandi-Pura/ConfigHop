# Palo Alto completion Phase 6C: evidence strategy rebaseline

## 1. Purpose

The Phase 6B vendor request package is merged and frozen. Its three requests have not been submitted: this project currently has no authorized Palo Alto Networks support-channel access. This is an access constraint, not evidence about firewall behavior. Phase 6C defers vendor submission as an optional future evidence path, defines a controlled lab alternative, and removes these unresolved targets from the immediate product roadmap. No request or technical gap is closed.

## 2. Current production state

The catalog has 11 documentation-verified Palo Alto models. PA-3410 and PA-5410 are the only renderer-supported targets. PA-1410, PA-1420, PA-3220, PA-3250, PA-3260, PA-5220, PA-5250, PA-5260, and PA-5280 remain analysis-only. The Phase 5 catalog has 13 blocking, `EVIDENCE_PARTIAL` gaps: three P0 and ten P1. No model was promoted in Phase 6C.

## 3. Technical blocking versus roadmap blocking

The three P0 gaps block deterministic candidate rendering for their affected target models and port groups. They do not block PA-3410 or PA-5410 work, other ConfigHop domains or vendors, UI, parsing, semantic diff, migration-plan UX, or improvements to the existing supported path. `blocking = true` remains accurate for the affected targets; it does not mean the entire product roadmap must wait for TAC access.

## 4. Unresolved P0 gaps

| Gap | Affected models and exact groups | Missing facts and rendering hazard | State |
| --- | --- | --- | --- |
| `PAN-GAP-PA1400-MULTIGIG` | PA-1410: `pa1410-Multi-Gig PoE 9-12`; PA-1420: `pa1420-Multi-Gig 5-8`, `pa1420-Multi-Gig PoE 9-12` | Whether speed and duplex are auto-only or configurable on supported trains; exact 2.5G/5G values and exported XML if configurable; independent omitted/default versus explicit-auto behavior and handling of manual nodes. Current English hardware documentation lists physical rates but is silent on an auto-only rule; a 2023 official Chinese edition says auto-only. Without a current model-specific rule, preserving or normalizing source values is unsafe. | P0, `EVIDENCE_PARTIAL`, `blocking = true` |
| `PAN-GAP-PA3200-AUTO-RJ45` | PA-3220: `pa3220-RJ45 1-12`; PA-3250: `pa3250-RJ45 1-12`; PA-3260: `pa3260-RJ45 1-12` | For PAN-OS 10.1, 10.2, 11.0, and 11.1, whether each speed and duplex node is omitted, explicit `auto`, or otherwise represented, and whether manual nodes are rejected, ignored, normalized, or retained without effect. Generic preservation could emit an invalid auto-only target candidate. | P0, `EVIDENCE_PARTIAL`, `blocking = true` |
| `PAN-GAP-PA5200-AUTO-RJ45` | PA-5220: `pa5220-RJ45 1-4`; PA-5250: `pa5250-RJ45 1-4`; PA-5260: `pa5260-RJ45 1-4`; PA-5280: `pa5280-RJ45 1-4` | The same independent speed/duplex XML, default, and manual-value questions across PAN-OS 10.1–11.2, including whether the 11.2 CLI presentation change affected XML. Generic source-value preservation could be invalid. | P0, `EVIDENCE_PARTIAL`, `blocking = true` |

These are the same ten frozen P0 port-group identities protected by Phase 6A and 6B. The canonical gap manifest retains `VENDOR_CONFIRMATION_NEEDED` as its existing next requirement. This Phase 6C planning decision does not add a claim that device validation was scheduled or performed.

## 5. Vendor path

The three Phase 6B requests remain valid and unchanged: `PAN-VC-PA1400-MULTIGIG`, `PAN-VC-PA3200-AUTO-RJ45`, and `PAN-VC-PA5200-AUTO-RJ45`. All are `REQUEST_READY`, all responses are `NOT_RECEIVED`, and the request manifest's `closure_state` remains `AWAITING_VENDOR`; that value records response state, not an active project dependency. No request has been submitted because authorized support-channel access is currently unavailable. Vendor confirmation may be resumed when access exists, but it is not required before unrelated roadmap work proceeds. The prepared questions are retained as future evidence work, not abandoned or answered.

## 6. Controlled lab validation as an alternate future path

If authorized exact-model lab access becomes available, a synthetic configuration can establish model-specific behavior without using production backups or a customer network. Before each experiment, record the exact hardware model, a safe serial-free model identifier, exact PAN-OS version/train, port identity and hardware class, known initial/default configuration, and planned change. Capture the action, candidate configuration, load/commit acceptance or failure output, before/after exported XML, re-import result, any normalization, timestamp, tester, and artifact hash or safe reference. Retain sanitized evidence outside private customer material.

Use one controlled change at a time and include both accepted and rejected/default cases. A successful load alone does not prove export stability, re-importability, default omission, or failure boundaries. A result from PA-3220 does not qualify PA-3250/3260; PA-5220 does not qualify PA-5250/5260/5280; PA-1410 does not qualify PA-1420. Authoritative evidence that explicitly establishes shared semantics could justify a broader scope in a later review. No lab experiment is scheduled or executed by Phase 6C.

## 7. Future PA-3200 lab plan

For each of PA-3220, PA-3250, and PA-3260 on RJ45 ethernet1/1–ethernet1/12, use a supported PAN-OS train from 10.1, 10.2, 11.0, or 11.1 and a synthetic interface. Export the untouched default, then independently test explicit `auto` and a manual value for `link-speed` and `link-duplex`. For each change, record load/commit acceptance or rejection, resulting export, re-import result, and any normalization or ignored value. Repeat at version boundaries needed to establish a deterministic rule. Do not infer sibling-model behavior from one device. This is a future plan only.

## 8. Future PA-5200 lab plan

For each of PA-5220, PA-5250, PA-5260, and PA-5280 on RJ45 ethernet1/1–ethernet1/4, test untouched defaults, explicit `auto`, manual speed, and manual duplex separately with synthetic configuration. Capture accepted/rejected XML, export, re-import, and normalization. Include the PAN-OS 11.2 boundary where practical to determine whether its CLI option presentation change affected configuration XML or only the CLI. Record exact model and version; do not generalize one model's result to the other three. This is a future plan only.

## 9. Future PA-1400 lab plan

For PA-1410 Multi-Gig ports 9–12 and both PA-1420 Multi-Gig groups (5–8 and 9–12), test default speed and duplex independently, explicit `auto`, and manual 2.5G and 5G values only if the model accepts them. Record rejected or normalized manual nodes, accepted/exported XML, re-import, and version boundaries across supported trains. Compare PoE-capable and non-PoE groups only for speed/duplex behavior; general PoE configuration remains a separate P1 gap. The current English and 2023 Chinese documentation scope discrepancy remains unresolved until evidence clarifies it. This is a future plan only.

## 10. Evidence acceptance bar

A future `DEVICE_VALIDATED` claim requires retained, verifiable controlled evidence for the exact model, port class, and PAN-OS scope: accepted representation, independent speed and duplex defaults, export and re-import behavior, and the failure or normalization boundary for unsupported values. An official current exact-model document or authoritative vendor response may instead supply equivalent deterministic semantics. Any evidence and gap-state update belongs to a later reviewed milestone. No `EVIDENCE_READY` transition or renderer operation follows from this plan.

## 11. Roadmap decision

No further Phase 6B.x work is required now. Continue the broader ConfigHop roadmap with PA-3410, PA-5410, and other currently supported work. The nine unresolved models remain intentionally analysis-only and fail closed as rendering targets. Their evidence work can resume independently when a reopen condition is met; the lack of TAC access does not hold the product roadmap.

## 12. Reopen conditions

Reopen one or more P0 gaps when (1) an authoritative Palo Alto Networks technical response becomes available, (2) controlled exact-model lab access becomes available, (3) new official documentation supplies deterministic exact semantics, or (4) project requirements explicitly prioritize renderer support for one of the nine analysis-only models. Reopening authorizes evidence review, not automatic target promotion.

## 13. Non-goals

Phase 6C performs no vendor submission, device testing, renderer implementation, profile promotion, transformation, compatibility, API, frontend, or Switch work. It does not alter the Phase 5/6A/6B artifacts, technical gap statuses, request lifecycle, evidence registry, or version numbers.

## 14. Next product milestone

Recommend **ConfigHop — Palo Alto Supported-Target Hardening**, focused on PA-3410 and PA-5410. Candidate work includes parser completeness, semantic diff, migration-plan output, candidate validation, reference safety, unsupported-feature surfacing, and evidence display within the existing supported scope. This milestone is recommended, not started here.
