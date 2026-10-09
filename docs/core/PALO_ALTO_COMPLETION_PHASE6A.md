# Palo Alto completion Phase 6A: official evidence closure review

## 1. Purpose

Phase 5 is frozen. Phase 6A reviewed only `PAN-GAP-PA3200-AUTO-RJ45`, `PAN-GAP-PA5200-AUTO-RJ45`, and `PAN-GAP-PA1400-MULTIGIG`. The review found no authoritative exact-model serialization/default rule sufficient for `EVIDENCE_READY`. No renderer, profile, API, UI, or device validation work occurred.

## 2. Baseline

Starting `main`: `6e75b2c8e09e36df7250c446b2a82168c9df5444`; branch: `feature/paloalto-completion-phase6a-official-evidence-closure`. The frozen catalog has 11 verified models, 2 renderer-supported (PA-3410 and PA-5410), 9 analysis-only, 13 blocking gaps, and 29 exact port-group rows. The three P0 gaps cover 10 of those rows.

## 3. Evidence standard

Hardware rates establish physical capability. PAN-OS web help and CLI establish generic controls. XML API guidance and the pinned SDK establish generic paths and serialization mechanics. `EVIDENCE_READY` requires the exact model/port and supported-train accepted values, exported XML for both speed and duplex, omission/default behavior, and a known failure boundary sufficient to specify a deterministic renderer operation. None of the three gaps reaches that bar. Generic examples cannot prove model-specific acceptance.

## 4. Search method and log

Reviewed official current hardware references; PAN-OS 10.2 and 11.1 web help; 11.1 CLI hierarchy; 11.2 CLI change log; 11.1 XML API, XPath, CLI-debug, web-debug, API-browser guidance; 11.1 REST Ethernet example; pinned official Python SDK source and serialization test; current English and 2023 Chinese PA-1400 hardware editions; and the committed Phase 2–5 findings. Searches targeted exact model names, `link-speed`, `link-duplex`, `auto`, `2500`, `5000`, omission, and XML export. No customer configuration or live device was consulted. No official public source found an exact-model exported/default representation. Search stopped when further public results repeated hardware rates or generic controls.

## 5. PA-3200 auto-only RJ45

[PA-3200 front panel](https://docs.paloaltonetworks.com/hardware/pa-3200-hardware-reference/pa-3220-series-overview/front-panel-3200-series) proves RJ45 1–12 auto-negotiates speed and duplex on PA-3220/3250/3260. [PAN-OS 10.2 help](https://docs.paloaltonetworks.com/ngfw/help/10-2/network/network-interfaces/layer-3-interface) and [11.1 help](https://docs.paloaltonetworks.com/ngfw/help/11-1/network/network-interfaces/layer-3-interface) expose generic auto and manual controls; the [11.1 CLI hierarchy](https://docs.paloaltonetworks.com/ngfw/pan-os-cli-quick-start/cli-command-hierarchy/pan-os-11-1-configure-cli-command-hierarchy) exposes generic `link-speed` and `link-duplex` values. None says whether PA-3200 exports absent nodes or explicit `auto`, or how manual source values are handled. PAN-OS 12.x cannot prove PA-3200 behavior because those trains are not modeled for this series. Status remains `EVIDENCE_PARTIAL`; next requirement is `VENDOR_CONFIRMATION_NEEDED`. Renderer remove/set behavior remains undefined.

## 6. PA-5200 auto-only RJ45

[PA-5200 front panel](https://docs.paloaltonetworks.com/hardware/pa-5200-hardware-reference/pa-5200-series-firewall-overview/pa-5200-front-panel) proves ports 1–4 auto-negotiate speed and duplex on PA-5220/5250/5260/5280. Generic help/CLI/API/SDK sources do not establish either node's exact export, omission default, or manual-value acceptance. The [11.2 CLI change log](https://docs.paloaltonetworks.com/ngfw/pan-os-cli-quick-start/cli-changes/modified-set-commands-11-2) reports an `auto`-option presentation change for both commands; it does not define PA-5200 XML or how 10.1–11.1 behaved. Status remains `EVIDENCE_PARTIAL`; next requirement is `VENDOR_CONFIRMATION_NEEDED`. Renderer behavior remains undefined.

## 7. PA-1400 Multi-Gig and source discrepancy

The [current English front panel](https://docs.paloaltonetworks.com/hardware/pa-1400-hardware-reference/pa-1400-series-overview/front-panel-1400-series) lists 2.5G/5G physical rates for PA-1410 ports 9–12 and PA-1420 ports 5–12, but does not state an RJ45 auto-only rule. An [official Simplified Chinese hardware PDF](https://docs.paloaltonetworks.com/content/dam/techdocs/zh_CN/pdf/hardware/pa-1400/pa-1400-hardware-reference-zh-cn.pdf), copyrighted 2023, says RJ45 1–12 speed and duplex are auto-negotiated only. Its exact revision/PAN-OS train is not stated; the current English page is silent rather than explicitly contradictory. This is an **OFFICIAL_SOURCE_DISCREPANCY**, not a proved current conflict or a reason to override the English page. Neither source defines 2.5G as `2500`, `2.5G`, `auto`, or omission; neither defines 5G as `5000`, `5G`, `auto`, or omission. Speed configurability, duplex, defaults, and accepted XML remain unknown for 11.0, 11.1, 11.2, 12.1.2+, and 12.2. The generic 11.2 CLI change does not settle them. Status remains `EVIDENCE_PARTIAL`; next requirement is `VENDOR_CONFIRMATION_NEEDED`. PoE remains a separate P1 gap.

## 8. Source acceptance matrix

| Source/title | Official | Version/date | Model scope | Evidence level | Registry acceptance | Gap(s) | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `PAN-HW-PA3200-FRONT` [front panel](https://docs.paloaltonetworks.com/hardware/pa-3200-hardware-reference/pa-3220-series-overview/front-panel-3200-series) | yes | current web | PA-3220/3250/3260 | physical auto-only | existing | 3200 | no XML/default |
| `PAN-HW-PA5200-FRONT` [front panel](https://docs.paloaltonetworks.com/hardware/pa-5200-hardware-reference/pa-5200-series-firewall-overview/pa-5200-front-panel) | yes | current web | PA-5220/5250/5260/5280 | physical auto-only | existing | 5200 | no XML/default |
| `PAN-HW-PA1400-FRONT` [English front panel](https://docs.paloaltonetworks.com/hardware/pa-1400-hardware-reference/pa-1400-series-overview/front-panel-1400-series) | yes | current web | PA-1410/1420 | physical rates | existing | 1400 | silent on auto restriction and XML |
| [Chinese PA-1400 PDF](https://docs.paloaltonetworks.com/content/dam/techdocs/zh_CN/pdf/hardware/pa-1400/pa-1400-hardware-reference-zh-cn.pdf) | yes | Chinese, ©2023; revision unknown | PA-1410/1420 | historical auto-only wording | no new record | 1400 | not current English or XML proof |
| [PAN-OS 10.2 Layer 3 help](https://docs.paloaltonetworks.com/ngfw/help/10-2/network/network-interfaces/layer-3-interface), [11.1 help](https://docs.paloaltonetworks.com/ngfw/help/11-1/network/network-interfaces/layer-3-interface) | yes | 10.2, 11.1 | generic | UI fields | no new record | all | no exact-model acceptance/export |
| [11.1 CLI hierarchy](https://docs.paloaltonetworks.com/ngfw/pan-os-cli-quick-start/cli-command-hierarchy/pan-os-11-1-configure-cli-command-hierarchy), [11.2 change log](https://docs.paloaltonetworks.com/ngfw/pan-os-cli-quick-start/cli-changes/modified-set-commands-11-2) | yes | 11.1, 11.2 | generic | command surface/change | no new record | all applicable | no XML/default or per-model rule |
| `PAN-CONFIG-ETHERNET-LINK-SPEED`, `PAN-CONFIG-ETHERNET-LINK-SPEED-TEST` [pinned SDK](https://github.com/PaloAltoNetworks/pan-os-python/blob/92ed648d89b7541052a15e234eb34e99edba6d2d/panos/network.py) | yes | pinned commit | generic | direct child serialization | existing | all | no model acceptance/default |
| [11.1 XML/XPath](https://docs.paloaltonetworks.com/pan-os/11-1/pan-os-panorama-api/about-the-pan-os-xml-api/structure-of-a-pan-os-xml-api-request/xml-and-xpath), [CLI debug](https://docs.paloaltonetworks.com/pan-os/11-1/pan-os-panorama-api/get-started-with-the-pan-os-xml-api/explore-the-api/use-the-cli-to-find-xml-api-syntax), [API browser](https://docs.paloaltonetworks.com/ngfw/api/getting-started/explore-xmlapi/explore-browser) | yes | 11.1 | generic | discovery method | no new record | all | requires a device; no model export supplied |
| [11.1 REST Ethernet example](https://docs.paloaltonetworks.com/pan-os/11-1/pan-os-panorama-api/get-started-with-the-pan-os-rest-api/configure-ethernet-interface-rest-api) | yes | 11.1 | generic | interface API example | no new record | all | not a link-speed/duplex model acceptance matrix |

## 9. Insufficient sources

Generic CLI `<value>` and web `auto` options show a control exists; they do not prove the specific hardware accepts a value. The SDK test proves direct-child numeric serialization, not default omission. XML API and browser pages explain how an authorized operator could inspect syntax, but publish no PA-1400/3200/5200 answer. The REST example covers interface configuration without settling the two link fields. The historical Chinese PDF narrows the question but cannot alone establish current exact-model semantics. No new registry record was added because none materially closes exact serialization.

## 10. Version applicability

| Series | Modeled trains | Reviewed evidence trains | Version-dependent semantics found? | Conclusion |
| --- | --- | --- | --- | --- |
| PA-3200 | 10.1, 10.2, 11.0, 11.1 | 10.2/11.1 help, 11.1 CLI/API, hardware | none proved | 11.2+ cannot be inherited |
| PA-5200 | 10.1, 10.2, 11.0, 11.1, 11.2 | 10.2/11.1 help, 11.1 CLI/API, 11.2 CLI change, hardware | 11.2 CLI option presentation changed; XML impact unknown | no cross-train flattening |
| PA-1400 | 11.0, 11.1, 11.2, 12.1.2+, 12.2 | 11.1 help/API, 11.2 CLI change, current English/historical Chinese hardware | none established for XML; language/date discrepancy | no current accepted 2.5G/5G rule |

## 11. Gap outcome

| Gap ID | Before | After | Blocking | New IDs | Remaining fact | Next requirement |
| --- | --- | --- | --- | --- | --- | --- |
| `PAN-GAP-PA3200-AUTO-RJ45` | partial | partial | yes | none | speed and duplex omission/auto/manual handling per model/train | vendor confirmation |
| `PAN-GAP-PA5200-AUTO-RJ45` | partial | partial | yes | none | same, including 11.2 boundary | vendor confirmation |
| `PAN-GAP-PA1400-MULTIGIG` | partial | partial | yes | none | auto-only versus manual, 2.5G/5G representation, both defaults | vendor confirmation |

Only these P0 manifest records changed. Priorities, exact model/groups, and all P1 gaps remain frozen.

## 12. Vendor confirmation questions

| Gap | Exact TAC/Engineering question |
| --- | --- |
| PA-3200 | On PA-3220, PA-3250, and PA-3260 PAN-OS 10.1/10.2/11.0/11.1, for RJ45 `ethernet1/1`–`1/12`, must `link-speed` and `link-duplex` each be omitted or explicitly `auto` in exported/accepted configuration? Are manual nodes rejected, ignored, or normalized, and does this vary by model or train? |
| PA-5200 | On PA-5220, PA-5250, PA-5260, and PA-5280 PAN-OS 10.1–11.2, for RJ45 `ethernet1/1`–`1/4`, what are the independent accepted/exported speed and duplex nodes and defaults? What happens to manual values, and did 11.2 alter XML behavior or only CLI presentation? |
| PA-1400 | On PA-1410 ports 9–12 and PA-1420 ports 5–8/9–12, across supported 11.0–12.2 trains, are speed and duplex auto-only as the ©2023 Chinese PDF says, despite the current English page's silence? If manual 2.5G/5G is allowed, what exact values and exported XML are accepted? For each field, what is the omitted/default versus explicit-auto behavior? |

No TAC case or external message was sent.

## 13. Future renderer contract

All three gaps remain partial. A safe remove/set operation, duplex normalization, default handling, and failure boundary cannot yet be specified. All affected candidates remain blocked. No device experiment is formally assigned `DEVICE_VALIDATION_NEEDED`; authoritative vendor clarification is the next step.

## 14. Production state

The catalog remains 11 verified, 2 renderer-supported (PA-3410, PA-5410), and 9 analysis-only. All three P0 gaps remain blocking. The Phase 5 29-row frozen test and Phase 6A 10-row P0 test protect coverage. No model was promoted or physically validated.

## 15. Next milestone

Recommend **Palo Alto Completion Phase 6B — Vendor Confirmation Closure** for the three exact questions above. All P1 PA-1400/3200/5200 gaps, PA-5410 breakout rendering, full Layer 2, virtual wire, dynamic routing transformation, advanced NAT, PBF, VPN, GlobalProtect, Panorama, PAN-OS upgrade, device validation execution, and live deployment remain deferred. Phase 6B was not started.
