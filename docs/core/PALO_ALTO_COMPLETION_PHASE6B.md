# Palo Alto completion Phase 6B: vendor confirmation request package

## 1. Purpose

Phase 6A is frozen. Its three P0 evidence gaps still require authoritative vendor confirmation. No vendor answer exists. This package prepares three independent requests and a response evaluation contract; it does not submit a request or close any gap.

## 2. Baseline

Starting `main`: `2fd038d031fb31ca45b5b8568468925b03de8f1f`; branch: `feature/paloalto-completion-phase6b-vendor-confirmation`. The production catalog has 11 verified models, two renderer-supported targets (PA-3410, PA-5410), and nine analysis-only targets (PA-1410, PA-1420, PA-3220, PA-3250, PA-3260, PA-5220, PA-5250, PA-5260, PA-5280). Phase 5 freezes 29 exact groups across 13 blocking, `EVIDENCE_PARTIAL` gaps (three P0, ten P1).

| P0 gap | Frozen groups | Status / next requirement |
| --- | --- | --- |
| `PAN-GAP-PA1400-MULTIGIG` | `pa1410-Multi-Gig PoE 9-12`, `pa1420-Multi-Gig 5-8`, `pa1420-Multi-Gig PoE 9-12` | `EVIDENCE_PARTIAL`, blocking, `VENDOR_CONFIRMATION_NEEDED` |
| `PAN-GAP-PA3200-AUTO-RJ45` | `pa3220-RJ45 1-12`, `pa3250-RJ45 1-12`, `pa3260-RJ45 1-12` | `EVIDENCE_PARTIAL`, blocking, `VENDOR_CONFIRMATION_NEEDED` |
| `PAN-GAP-PA5200-AUTO-RJ45` | `pa5220-RJ45 1-4`, `pa5250-RJ45 1-4`, `pa5260-RJ45 1-4`, `pa5280-RJ45 1-4` | `EVIDENCE_PARTIAL`, blocking, `VENDOR_CONFIRMATION_NEEDED` |

## 3. Why vendor confirmation is needed

Phase 6A found official hardware facts and generic PAN-OS configuration controls, but no exact target-model, port, and train serialization/default rules for both link fields. Physical link rates and generic CLI or SDK behavior cannot establish accepted XML, omission defaults, or failure behavior. The renderer therefore lacks a deterministic contract for these targets.

## 4. Request strategy

Prepare one independent request per family because hardware, PAN-OS scope, and unresolved semantics differ. The [machine-readable request manifest](palo_alto_vendor_confirmation_requests.json) is the canonical request text and current state. The copy/paste bodies below are identical to that manifest. No customer configuration is needed.

## 5. PA-3200 request

Request `PAN-VC-PA3200-AUTO-RJ45` maps to `PAN-GAP-PA3200-AUTO-RJ45`. Models: PA-3220, PA-3250, PA-3260. Ports: ethernet1/1-1/12. PAN-OS: 10.1, 10.2, 11.0, 11.1. Groups: `pa3220-RJ45 1-12`, `pa3250-RJ45 1-12`, `pa3260-RJ45 1-12`.

**Known facts**

- Official PA-3200 hardware documentation says RJ45 ethernet1/1-1/12 auto-negotiates both speed and duplex.
- Generic PAN-OS documentation exposes link-speed and link-duplex controls but does not establish exact PA-3200 XML, default, or manual-value behavior.

**Question matrix**

| # | Question |
| ---: | --- |
| 1 | For PA-3220 RJ45 ethernet1/1-1/12, is default/auto link-speed omitted, explicit `<link-speed>auto</link-speed>`, or another accepted/exported representation? |
| 2 | Independently, is default/auto link-duplex omitted, explicit `<link-duplex>auto</link-duplex>`, or another accepted/exported representation? |
| 3 | What happens to a manual link-speed node: rejection, ignoring, normalization to auto, preservation without effect, or another documented behavior? |
| 4 | Independently, what happens to a manual link-duplex node? |
| 5 | Are these answers identical on PA-3220, PA-3250, and PA-3260; if not, what differs? |
| 6 | Are these answers identical across PAN-OS 10.1, 10.2, 11.0, and 11.1; if not, identify exact version boundaries. |

**Requested official artifacts**

- Sanitized official exported interface XML from an exact supported target at default/auto speed and duplex
- Official configuration/API XPath and accepted-value example or Engineering model/port/PAN-OS behavior matrix

**Acceptance**

- `SUFFICIENT`: Verifiable official answer specifies independently accepted/exported speed and duplex nodes, omission/explicit-auto defaults, manual-value acceptance or failure, and applicability to all three models, RJ45 1-12, and all scoped trains, enough for deterministic renderer design.
- `PARTIAL`: Speed or duplex, default, manual-value behavior, or exact model/port/train scope remains unresolved.
- `CONFLICTING`: Verifiable official responses assert incompatible behavior for the same model, port, and train.

**Copy/paste submission body**

> We are validating configuration migration behavior between supported Palo Alto Networks firewall models and need authoritative confirmation of exact PAN-OS configuration semantics. Official PA-3200 hardware documentation says RJ45 ethernet1/1-1/12 auto-negotiates speed and duplex. For PA-3220, PA-3250, and PA-3260 on PAN-OS 10.1, 10.2, 11.0, and 11.1, please answer independently for link-speed and link-duplex: when left at default/auto, is the accepted and exported XML node omitted, explicitly auto, or represented otherwise? If a configuration supplies a manual speed or duplex value, is it rejected, ignored, normalized to auto, preserved without effect, or handled otherwise? Please confirm whether answers apply identically to all three models and trains, or state exact differences and version boundaries. We request a sanitized exact-model exported interface XML showing both defaults and/or an official Engineering model/port/version behavior matrix. Generic CLI syntax does not settle target XML behavior. No customer configuration is included.

## 6. PA-5200 request

Request `PAN-VC-PA5200-AUTO-RJ45` maps to `PAN-GAP-PA5200-AUTO-RJ45`. Models: PA-5220, PA-5250, PA-5260, PA-5280. Ports: ethernet1/1-1/4. PAN-OS: 10.1, 10.2, 11.0, 11.1, 11.2. Groups: `pa5220-RJ45 1-4`, `pa5250-RJ45 1-4`, `pa5260-RJ45 1-4`, `pa5280-RJ45 1-4`.

**Known facts**

- Official PA-5200 hardware documentation says RJ45 ethernet1/1-1/4 auto-negotiates speed and duplex.
- PAN-OS 11.2 CLI change documentation mentions an auto option presentation change; it does not establish a change in configuration XML.
- Generic PAN-OS controls do not establish exact PA-5200 XML, default, or manual-value behavior.

**Question matrix**

| # | Question |
| ---: | --- |
| 1 | What is the accepted/exported link-speed default on RJ45 ethernet1/1-1/4: omitted, explicit auto, or another representation? |
| 2 | Independently, what is the accepted/exported link-duplex default: omitted, explicit auto, or another representation? |
| 3 | What happens to a manual link-speed value: rejection, ignoring, normalization to auto, preservation without effect, or another behavior? |
| 4 | Independently, what happens to a manual link-duplex value? |
| 5 | Are answers identical on PA-5220, PA-5250, PA-5260, and PA-5280; if not, specify differences? |
| 6 | Are answers identical on PAN-OS 10.1, 10.2, 11.0, 11.1, and 11.2; if not, specify boundaries? |
| 7 | Did the PAN-OS 11.2 CLI auto-option presentation change affect configuration XML or only the CLI presentation? Please confirm either outcome explicitly. |

**Requested official artifacts**

- Sanitized official exact-model exported XML showing default/auto speed and duplex
- Official Engineering model/port/PAN-OS behavior matrix, explicitly covering all four models and 11.2

**Acceptance**

- `SUFFICIENT`: Verifiable official answer specifies independently accepted/exported speed and duplex nodes, omission/explicit-auto defaults, manual-value acceptance or failure, all four models/RJ45 1-4/scoped trains, and whether 11.2 changed XML or only CLI presentation, enough for deterministic renderer design.
- `PARTIAL`: Speed or duplex, default, manual-value behavior, model/port/train scope, or 11.2 XML versus CLI question remains unresolved.
- `CONFLICTING`: Verifiable official responses assert incompatible behavior for the same model, port, and train.

**Copy/paste submission body**

> We are validating configuration migration behavior between supported Palo Alto Networks firewall models and need authoritative confirmation of exact PAN-OS configuration semantics. Official PA-5200 documentation says RJ45 ethernet1/1-1/4 auto-negotiates speed and duplex. For PA-5220, PA-5250, PA-5260, and PA-5280 on PAN-OS 10.1, 10.2, 11.0, 11.1, and 11.2, please answer independently for link-speed and link-duplex: when left at default/auto, is the accepted/exported XML node omitted, explicitly auto, or represented otherwise? If a manual speed or duplex value is supplied, is it rejected, ignored, normalized, preserved without effect, or handled otherwise? Please confirm whether all four models and all listed trains behave identically, or identify exact boundaries. PAN-OS 11.2 documentation describes a CLI auto-option presentation change: did this change configuration XML, or only CLI presentation? We do not assume an XML change. Please provide sanitized exact-model exported XML for both fields and/or an Engineering model/port/version matrix. No customer configuration is included.

## 7. PA-1400 request

Request `PAN-VC-PA1400-MULTIGIG` maps to `PAN-GAP-PA1400-MULTIGIG`. Models: PA-1410, PA-1420. Ports: PA-1410 ethernet1/9-1/12; PA-1420 ethernet1/5-1/12. PAN-OS: 11.0, 11.1, 11.2, 12.1.2+, 12.2. Groups: `pa1410-Multi-Gig PoE 9-12`, `pa1420-Multi-Gig 5-8`, `pa1420-Multi-Gig PoE 9-12`.

**Known facts**

- The current official English PA-1400 front-panel page lists 2.5G and 5G physical rates for these ports but does not specify whether speed and duplex settings are auto-only.
- The official Simplified Chinese PA-1400 hardware PDF, copyright 2023, says RJ45 speed and duplex are auto-negotiated only; its applicability to current hardware and PAN-OS trains is unknown.
- Physical rates do not establish configurable values, exported XML, or defaults. The source difference is unresolved, not a proven contradiction.

**Question matrix**

| # | Question |
| ---: | --- |
| 1 | Are link-speed and link-duplex auto-only on PA-1410 ethernet1/9-1/12 and PA-1420 ethernet1/5-1/12? Answer each field independently. |
| 2 | If manual speed is allowed, what exact accepted configuration value represents 2.5G and what exported XML is produced? |
| 3 | If manual speed is allowed, what exact accepted configuration value represents 5G and what exported XML is produced? |
| 4 | For default/auto speed, is link-speed omitted, explicitly auto, or represented otherwise in exported and accepted XML? |
| 5 | For default/auto duplex, is link-duplex omitted, explicitly auto, or represented otherwise in exported and accepted XML? |
| 6 | If manual speed or duplex is unsupported, are such nodes rejected, ignored, normalized to auto, preserved but functionally ignored, or handled another way? |
| 7 | Are the answers identical for PA-1410 and PA-1420, and for PoE-capable versus non-PoE Multi-Gig groups with respect only to speed and duplex? |
| 8 | Do answers vary across PAN-OS 11.0, 11.1, 11.2, 12.1.2+, and 12.2; what are exact boundaries? |
| 9 | Which current authoritative behavior reconciles the English page's silence and the 2023 Chinese reference's auto-only wording? |

**Requested official artifacts**

- Official exact-model, exact-train sanitized exported XML for default/auto and, if supported, manual 2.5G and 5G speed and duplex
- Official Engineering or TAC model/port/PAN-OS behavior matrix and authoritative documentation revision

**Acceptance**

- `SUFFICIENT`: Verifiable official answer resolves auto-only versus manual capability; if manual, exact 2.5G/5G values and exported XML; independent speed and duplex defaults, accepted/failure behavior, exact model/port/train scope, and the source discrepancy, enough for deterministic renderer design.
- `PARTIAL`: Some requested semantics or model/port/train applicability remain unanswered, including a reply that gives only physical rates or only speed.
- `CONFLICTING`: Verifiable official responses assert incompatible behavior for the same model, port, and train.

**Copy/paste submission body**

> We are validating configuration migration behavior between supported Palo Alto Networks firewall models and need authoritative confirmation of exact PAN-OS configuration semantics. For PA-1410 ethernet1/9-1/12 and PA-1420 ethernet1/5-1/12 on PAN-OS 11.0, 11.1, 11.2, 12.1.2+, and 12.2, are link-speed and link-duplex independently auto-only? The current English PA-1400 front-panel page lists 2.5G/5G physical rates but is silent on this restriction; an official Simplified Chinese PA-1400 PDF copyrighted 2023 says RJ45 speed and duplex are auto-negotiated only. Please clarify the currently authoritative model/version behavior without assuming a contradiction. If manual speed is supported, specify the exact accepted 2.5G and 5G values and exported XML for each. For both speed and duplex, specify whether default/auto is an omitted node, explicit auto, or another XML representation; explain rejection, normalization, ignoring, or preservation of unsupported manual values. Please identify differences between PA-1410 and PA-1420, PoE-capable and non-PoE Multi-Gig groups only as to link settings, and PAN-OS trains. An official exact-model sanitized XML export and/or Engineering model/port/version matrix would resolve this. No customer configuration is included.

## 8. Combined escalation summary

If Palo Alto Networks requests consolidation: We seek official exact-model/port/PAN-OS confirmation for independent `link-speed` and `link-duplex` defaults, accepted/exported XML, and manual-value failure behavior on PA-3220/3250/3260 RJ45 1-12 (10.1-11.1), PA-5220/5250/5260/5280 RJ45 1-4 (10.1-11.2), and PA-1410/1420 Multi-Gig groups (11.0, 11.1, 11.2, 12.1.2+, 12.2). The PA-5200 question includes whether the 11.2 CLI option change affected XML. The PA-1400 question includes 2.5G/5G manual values, XML, and reconciliation of the current English page with the 2023 Chinese PDF. Please supply sanitized exact-model exports or an official Engineering matrix; a generic hardware-rate answer does not resolve the migration semantics. The three separate requests remain the precise scope.

## 9. Response acceptance matrix

| Request | Required semantics | `SUFFICIENT` if | `PARTIAL` if | `CONFLICTING` if |
| --- | --- | --- | --- | --- |
| `PAN-VC-PA3200-AUTO-RJ45` | Independent speed/duplex accepted/exported XML, defaults, manual-value behavior, exact model/port/train scope | Verifiable official answer specifies independently accepted/exported speed and duplex nodes, omission/explicit-auto defaults, manual-value acceptance or failure, and applicability to all three models, RJ45 1-12, and all scoped trains, enough for deterministic renderer design. | Speed or duplex, default, manual-value behavior, or exact model/port/train scope remains unresolved. | Verifiable official responses assert incompatible behavior for the same model, port, and train. |
| `PAN-VC-PA5200-AUTO-RJ45` | Independent speed/duplex accepted/exported XML, defaults, manual-value behavior, exact model/port/train scope; 11.2 CLI vs XML boundary | Verifiable official answer specifies independently accepted/exported speed and duplex nodes, omission/explicit-auto defaults, manual-value acceptance or failure, all four models/RJ45 1-4/scoped trains, and whether 11.2 changed XML or only CLI presentation, enough for deterministic renderer design. | Speed or duplex, default, manual-value behavior, model/port/train scope, or 11.2 XML versus CLI question remains unresolved. | Verifiable official responses assert incompatible behavior for the same model, port, and train. |
| `PAN-VC-PA1400-MULTIGIG` | Independent speed/duplex accepted/exported XML, defaults, manual-value behavior, exact model/port/train scope; auto-only vs manual 2.5G/5G, source reconciliation | Verifiable official answer resolves auto-only versus manual capability; if manual, exact 2.5G/5G values and exported XML; independent speed and duplex defaults, accepted/failure behavior, exact model/port/train scope, and the source discrepancy, enough for deterministic renderer design. | Some requested semantics or model/port/train applicability remain unanswered, including a reply that gives only physical rates or only speed. | Verifiable official responses assert incompatible behavior for the same model, port, and train. |

`OUT_OF_SCOPE` means the answer does not address requested models/ports. `UNVERIFIABLE` means official provenance cannot be verified. An answer limited to speed, a generic CLI screenshot, a hardware rate, or a single model generalized without confirmation cannot be `SUFFICIENT`.

## 10. Response provenance

A future official TAC, Engineering, support-portal, updated documentation, or model-specific XML/config response may be considered only after source authenticity is verified. Record vendor, response date, responder role, source title or safe case reference, exact model/port/PAN-OS scope, technical statement, artifact type, and a public URL or private-source marker. If an externally retained raw artifact exists, record its hash or safe reference. A generic anonymous assertion is `UNVERIFIABLE`.

## 11. Sanitization

Do not commit raw private TAC email, support exports, customer configuration, private case URL, credentials, serial numbers, customer names, personal contact data, or support account details. Keep only a reviewed sanitized excerpt and safe provenance metadata needed for traceability. A private case identifier is included only if safe to disclose; otherwise use a redacted marker and externally retained artifact hash/reference. Sanitization must not erase the exact technical answer, model, port, train, source date, and role.

## 12. Response intake workflow

1. Receive the vendor answer externally; repository work begins only after an actual response exists.
2. Verify official provenance and exact scope.
3. Sanitize the response and retain the raw artifact outside Git.
4. Map the evidence to one exact request and gap.
5. Evaluate every requested speed, duplex, default, manual-value, and version question against the acceptance matrix.
6. Set `SUFFICIENT`, `PARTIAL`, `CONFLICTING`, `OUT_OF_SCOPE`, or `UNVERIFIABLE` with a documented reason.
7. In a separate milestone, consider evidence/gap updates only after evaluation; even `SUFFICIENT` alone does not change production support.

## 13. No automatic support promotion

A future sufficient response may justify a later `EVIDENCE_READY` decision, while `blocking = true` remains until a renderer is implemented and qualified. It does not directly promote `TargetRenderSupport` to `SUPPORTED`, prove `DEVICE_VALIDATED`, or authorize candidate rendering.

## 14. Current state

Exactly three requests are `REQUEST_READY`; all three responses are `NOT_RECEIVED`. No case number, submission timestamp, response, or vendor artifact exists. Top-level `closure_state` is `AWAITING_VENDOR`. The canonical gap manifest and evidence registry remain unchanged.

## 15. Next external action

Submit the prepared PA-3200, PA-5200, and PA-1400 requests to Palo Alto Networks TAC / Engineering and retain authoritative responses for sanitized ingestion. This action has not been performed.

## 16. Next repository milestone

**Palo Alto Completion Phase 6B.2 - Vendor Response Intake & Closure** may begin only after an actual vendor response is available. Phase 6B.2 is not started.
