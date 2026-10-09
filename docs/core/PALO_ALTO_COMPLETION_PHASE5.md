# Palo Alto completion Phase 5: evidence gap closure catalog

## 1. Purpose

The 11-model review is complete. This phase consolidates the remaining qualification questions; it changes no renderer, profile, API, or production support state. The canonical row-to-gap mapping and closure actions are in [palo_alto_evidence_gaps.json](palo_alto_evidence_gaps.json). Each manifest port-group ID is the exact production hardware-registry group ID. No physical device was tested.

## 2. Catalog snapshot

| Series | Verified | Renderer-supported | Analysis-only |
| --- | ---: | --- | --- |
| PA-1400 | 2 | — | PA-1410, PA-1420 |
| PA-3200 | 3 | — | PA-3220, PA-3250, PA-3260 |
| PA-3400 | 1 | PA-3410 | — |
| PA-5200 | 4 | — | PA-5220, PA-5250, PA-5260, PA-5280 |
| PA-5400 | 1 | PA-5410 | — |

## 3. Taxonomy

`gap_types` distinguishes exact XML, model acceptance, target hardware state, optic dependency, PoE, HA remap, reference rewrite, operator input, renderer capability, device behavior, and scope boundary. `resolution_requirements` distinguishes official documentation, vendor confirmation, device validation, operator context, renderer modeling, reference modeling, and deliberate exclusion. `OPEN` means evidence is absent; `EVIDENCE_PARTIAL` means a physical or generic behavior is known but exact target semantics are not; `EVIDENCE_READY` means a future deterministic operation can be specified from official evidence; `DEFERRED` means outside scope. All 13 current gaps are blocking and `EVIDENCE_PARTIAL`. `P0` has broad model coverage and a common migration hazard; `P1` has narrower but still blocking scope; `P2` is a lower-unlock follow-up. No gap is currently P2 or evidence-ready.

## 4. PA-1400

PA-1410 and PA-1420 base RJ45 speed and duplex acceptance is unproven. Their Multi-Gig groups need exact 2.5G/5G values, duplex, and omission/default rules. Ports 9–12 additionally need PoE export and reference semantics. The SFP/SFP+ groups need optic-aware link rules and HA1 remap XML/reference behavior. Port 1 ZTP is onboarding metadata, not a separate renderer blocker. These are the nine Phase 4 exact groups.

## 5. PA-3200

PA-3220, PA-3250, and PA-3260 RJ45 groups are auto-negotiated, but omitted versus explicit `auto` speed and duplex XML is unproven. PA-3220 SFP 13–16 is 1G-only and kept separate from the 1G/10G SFP+ groups. PA-3260 QSFP+ 21–24 is 40G-only; PA-5410 numeric speed behavior cannot qualify it. These are the eight Phase 3 exact groups.

## 6. PA-5200

All four models have auto-only RJ45 1–4 and optic-dependent SFP+ 5–20. PA-5220 QSFP 21–24 is 40G-only; the same numbered group on PA-5250/5260/5280 can be 40G or 100G by optic. Exact XML and default/duplex rules remain unknown. These are the 12 Phase 2 exact groups.

## 7. Cross-series patterns

| Pattern | Reusable research question | Exact-model boundary |
| --- | --- | --- |
| Auto negotiation | Is speed/duplex omitted or explicitly `auto`? | PA-3200 and PA-5200 have separate gap IDs; one answer does not prove both. |
| Optic-dependent rate | What XML corresponds to installed 1G/10G optic? | Target optic state and model-specific acceptance remain separate. |
| Fixed QSFP rate | Is 40G `40000`, `auto`, or omitted? | PA-3260 and PA-5220 are separate; PA-5410 is only a comparison. |
| Multi-Gig | How are 2.5G/5G and duplex exported? | Only PA-1400 groups here; each model still needs qualification. |
| PoE | What XML and references control power? | Only PA-1400 ports 9–12; shared budget needs preservation proof. |
| HA remap | How does an optical dataplane port become HA1? | Only PA-1400 optical groups here; rename references are unknown. |

The official hardware pages prove physical capability. The pinned official SDK proves generic direct-child `link-speed` and `link-duplex` serialization. Neither proves exact-model acceptance, default omission, or target optic state.

## 8. New official evidence

No new official evidence was sufficient to close the identified gaps. The registry is unchanged. This catalog cites committed official records and the Phase 2–4 analysis; no unverified source is upgraded to qualification evidence.

## 9. Gap matrix

| Gap ID suffix (`PAN-GAP-…`) | Series | Models | Ports | Semantic area | Status | Blocking | Requirement | Priority |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| PA1400-BASE-RJ45 | 1400 | 2 | base RJ45 | link XML | partial | yes | official docs | P1 |
| PA1400-HA1-REMAP | 1400 | 2 | optical | remap/references | partial | yes | docs/vendor | P1 |
| PA1400-MULTIGIG | 1400 | 2 | Multi-Gig | 2.5G/5G XML | partial | yes | official docs | P0 |
| PA1400-OPTICAL | 1400 | 2 | optical | optic/link XML | partial | yes | docs/operator | P1 |
| PA1400-POE | 1400 | 2 | PoE 9–12 | PoE/references | partial | yes | docs/vendor | P1 |
| PA3200-AUTO-RJ45 | 3200 | 3 | RJ45 1–12 | auto XML | partial | yes | official docs | P0 |
| PA3200-OPTICAL-1G | 3200 | 1 | SFP 13–16 | 1G XML | partial | yes | official docs | P1 |
| PA3200-OPTICAL-MIXED | 3200 | 3 | SFP+ | optic/link XML | partial | yes | docs/operator | P1 |
| PA3200-QSFP-40G | 3200 | 1 | QSFP+ 21–24 | 40G XML | partial | yes | official docs | P1 |
| PA5200-AUTO-RJ45 | 5200 | 4 | RJ45 1–4 | auto XML | partial | yes | official docs | P0 |
| PA5200-OPTICAL | 5200 | 4 | SFP+ 5–20 | optic/link XML | partial | yes | docs/operator | P1 |
| PA5200-QSFP-40-100G | 5200 | 3 | QSFP 21–24 | optic/QSFP XML | partial | yes | docs/operator | P1 |
| PA5200-QSFP-40G | 5200 | 1 | QSFP 21–24 | 40G XML | partial | yes | official docs | P1 |

“Partial” means `EVIDENCE_PARTIAL`. The manifest provides the exact models, registry port-group IDs, evidence IDs, evidence limits, missing facts, and next actions for each row.

## 10. Model readiness

| Model | Current state | Blocking gap IDs (suffix) | Evidence-ready | Operator context | Device validation | Future renderer work |
| --- | --- | --- | --- | --- | --- | --- |
| PA-1410 | analysis-only | PA1400-BASE-RJ45, MULTIGIG, POE, OPTICAL, HA1-REMAP | none | optic/rate | none assigned | link, PoE, HA references |
| PA-1420 | analysis-only | PA1400-BASE-RJ45, MULTIGIG, POE, OPTICAL, HA1-REMAP | none | optic/rate | none assigned | link, PoE, HA references |
| PA-3220 | analysis-only | PA3200-AUTO-RJ45, OPTICAL-1G, OPTICAL-MIXED | none | optic/rate for mixed group | none assigned | link normalization |
| PA-3250 | analysis-only | PA3200-AUTO-RJ45, OPTICAL-MIXED | none | optic/rate | none assigned | link normalization |
| PA-3260 | analysis-only | PA3200-AUTO-RJ45, OPTICAL-MIXED, QSFP-40G | none | optic/rate for mixed group | none assigned | link normalization |
| PA-5220 | analysis-only | PA5200-AUTO-RJ45, OPTICAL, QSFP-40G | none | optic/rate for SFP+ | none assigned | link normalization |
| PA-5250 | analysis-only | PA5200-AUTO-RJ45, OPTICAL, QSFP-40-100G | none | optic/rate | none assigned | link normalization |
| PA-5260 | analysis-only | PA5200-AUTO-RJ45, OPTICAL, QSFP-40-100G | none | optic/rate | none assigned | link normalization |
| PA-5280 | analysis-only | PA5200-AUTO-RJ45, OPTICAL, QSFP-40-100G | none | optic/rate | none assigned | link normalization |

## 11. Evidence closure

For each P0 auto RJ45 gap, obtain an official exact-model XML export or API hierarchy showing both speed and duplex in default, explicit auto, and manual-source migration cases. For PA-1400 Multi-Gig, obtain official PA-1410 and PA-1420 2.5G/5G exports including default behavior. For optical P1 gaps, obtain the exact-model export with the installed optic identified; 1G-only, 1/10G, and 40/100G groups must remain distinct. For fixed QSFP gaps, obtain native 40G exact-model speed and duplex XML. For PoE, obtain official per-port controls, budget behavior, and interface reference paths. For HA1, obtain the remap hierarchy and interface-reference rewrite rule. If public documentation does not expose PoE/HA relationships, seek authoritative vendor confirmation. The manifest names the exact artifact and next action for every gap.

## 12. Device validation plan

No gap is presently assigned `DEVICE_VALIDATION_NEEDED`: missing official or vendor documentation should be sought first. If that evidence cannot establish omission/acceptance, a later milestone may plan a controlled lab comparison per exact model/port class: record model and PAN-OS version, start from an empty synthetic interface, apply default versus explicit auto or qualified optic setting, export and reimport, retain both XML artifacts and acceptance result. Success requires a reproducible accepted representation; any reject or differing export is a failure boundary. Use no production config or network; Phase 5 ran no experiment.

## 13. Operator context

`PA1400-OPTICAL`, `PA3200-OPTICAL-MIXED`, `PA5200-OPTICAL`, and `PA5200-QSFP-40-100G` need the target installed/intended optic and desired rate where multiple rates are possible. A 1G-only PA-3220 SFP and fixed 40G QSFP do not need a rate choice merely because an optic is installed. PoE and HA intent may need future operator input after the exported semantics are known; Phase 5 does not assert a UI field yet.

## 14. Future implementation

After evidence closure, auto-only groups may need controlled remove/set operations for link speed and duplex with preservation inverses. Optical groups may need optic context and qualified speed setting. PoE and HA1 may need semantic parsing, dependency tracking, and reference rewrite or an explicit blocker. None of these operations is implemented here.

## 15. Prioritized backlog

| Priority | Gaps | Affected models/groups | Unlock value and prerequisite | Owner/output |
| --- | --- | --- | --- | --- |
| P0 | PA3200-AUTO-RJ45, PA5200-AUTO-RJ45 | 7 / 7 | Common manual-source hazard across two series; exact-model auto speed+duplex exports needed | Vendor documentation research / XML evidence matrix |
| P0 | PA1400-MULTIGIG | 2 / 3 | Blocks common PA-1400 high-rate ports; 2.5G/5G exports needed | Vendor documentation research / XML evidence matrix |
| P1 | PA1400-BASE-RJ45, PA1400-OPTICAL, PA3200-OPTICAL-1G, PA3200-OPTICAL-MIXED, PA5200-OPTICAL | 9 / 14 distinct group memberships | Qualifies remaining copper/optical classes; exact-model exports and target optic context first | Evidence researcher plus product design / signed-off rules and context contract |
| P1 | PA3200-QSFP-40G, PA5200-QSFP-40G, PA5200-QSFP-40-100G | 5 / 5 | Qualifies QSFP groups; exact-model native 40G and 100G exports first | Vendor documentation research / model-specific matrix |
| P1 | PA1400-POE, PA1400-HA1-REMAP | 2 / 6 memberships | Prevents power/HA reference loss; hierarchy and rename behavior first | Vendor confirmation plus future renderer owner / reference specification |

Counts in the backlog are work-item reach, not additive unique-model totals. Every exact group is covered in the manifest.

## 16. Non-goals

PA-5410 breakout rendering, full Layer 2 semantics, virtual wire, dynamic routing transformation, advanced NAT, PBF, VPN, GlobalProtect, Panorama, PAN-OS upgrades, physical device validation execution, and live deployment remain deferred. No supported profile is promoted or altered.

## 17. Phase 6 recommendation

Start **Phase 6A — Official Evidence Closure** for the P0 XML/default questions and the model-specific optical/QSFP examples. Escalate PoE and HA hierarchy questions to vendor confirmation if public documentation remains insufficient. Plan device-backed work only for acceptance facts still unprovable by authoritative documentation. Renderer implementation should wait for evidence-ready rules and required operator context.
