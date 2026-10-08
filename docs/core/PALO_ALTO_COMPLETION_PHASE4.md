# Palo Alto completion Phase 4: PA-1400 qualification

## Decision

PA-1410 and PA-1420 remain `ANALYSIS_ONLY`. This is an evidence and renderer-qualification review, not a production renderer change. Physical capabilities are documented, but exact target XML for Multi-Gig link settings, PoE, and optical HA1 remapping is not sufficiently established. The generic renderer can preserve source link fields mechanically; that does not qualify a PA-1400 target candidate. No device import or commit validation occurred.

## Evidence and limits

| Evidence | Establishes | Does not establish |
| --- | --- | --- |
| [PAN-HW-PA1400-OVERVIEW](https://docs.paloaltonetworks.com/hardware/pa-1400-hardware-reference/pa-1400-series-overview) | PA-1410/PA-1420 identity and first PAN-OS 11.0 release | Target interface XML |
| [PAN-HW-PA1400-FRONT](https://docs.paloaltonetworks.com/hardware/pa-1400-hardware-reference/pa-1400-series-overview/front-panel-1400-series) | Current model-specific port rates, port 1 ZTP, ports 9–12 PoE, transceiver-dependent optical rates, and optical HA1 remap capability | Exact XML for speed, duplex, PoE, or remap state |
| [PAN-COMPAT-PANOS-BY-MODEL](https://docs.paloaltonetworks.com/compatibility-matrix/reference/supported-os-releases-by-model/palo-alto-networks-next-gen-firewalls) | Current modeled train support and 12.1 floor | Interface serialization |
| [PAN-CONFIG-ETHERNET-LINK-SPEED](https://github.com/PaloAltoNetworks/pan-os-python/blob/92ed648d89b7541052a15e234eb34e99edba6d2d/panos/network.py), [PAN-CONFIG-ETHERNET-LINK-SPEED-TEST](https://github.com/PaloAltoNetworks/pan-os-python/blob/92ed648d89b7541052a15e234eb34e99edba6d2d/tests/test_integration.py), and [PAN-CONFIG-ETHERNET-LINK-SPEED-VALUES](https://docs.paloaltonetworks.com/ngfw/networking/configure-interfaces/configure-an-aggregate-interface-group/configure-an-aggregate-ethernet-interface) | Generic PAN-OS link field existence and direct-node serialization | PA-1400-specific acceptance, 2.5G/5G choice, or canonical `auto`/omission |
| [Configure PoE](https://docs.paloaltonetworks.com/ngfw/networking/poe/configure-poe) and [PoE model table](https://docs.paloaltonetworks.com/ngfw/networking/poe) | Ports 9–12 support PoE; PoE is enabled by default and has per-port enable and reserved-power CLI controls and a shared power budget | Exact exported XML, safe rename behavior, or complete PoE preservation semantics |
| [HA ports guide](https://docs.paloaltonetworks.com/ngfw/administration/high-availability/ha-ports-on-palo-alto-networks-firewalls) | Generic data-port HA use and dedicated PA-1400 HA ports | PA-1400 optical remap XML and reference-rewrite rules |

The current English web front-panel page lists physical rates but does not state a PA-1400-specific auto-negotiation restriction for RJ45 speed or duplex. No historical or alternate-language document is used to fill that gap. Generic PAN-OS defaults and SDK fields cannot be promoted into model-specific XML evidence. Link state is reviewed separately; its `auto`, `up`, and `down` probe values are preserved, with no target-specific normalization inferred.

## Exact target-port matrix

All XML results below are unverified. The actual installed optic determines the physical rate where a group supports both SFP and SFP+. HA1 remapping is a capability of the optical ports, but ConfigHop does not model its exported configuration. Port 1 ZTP is registry metadata for onboarding, not a candidate XML transformation.

| Model | Ports | Media | Physical rates | PoE | ZTP | Optic dependency | HA1 remap | XML result / qualification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PA-1410 | 1–8 | RJ45 | 10M/100M/1G | No | Port 1 | No | No | Link speed/duplex unknown; blocked |
| PA-1410 | 9–12 | RJ45 Multi-Gig | 10M/100M/1G/2.5G/5G | Yes | No | No | No | Multi-Gig and PoE XML unknown; blocked |
| PA-1410 | 13–18 | SFP | 1G | No | No | SFP installed | Capable | Optical and remap XML unknown; blocked |
| PA-1410 | 19–22 | SFP/SFP+ | 1G/10G | No | No | Rate follows optic | Capable | Optical and remap XML unknown; blocked |
| PA-1420 | 1–4 | RJ45 | 10M/100M/1G | No | Port 1 | No | No | Link speed/duplex unknown; blocked |
| PA-1420 | 5–8 | RJ45 Multi-Gig | 10M/100M/1G/2.5G/5G | No | No | No | No | Multi-Gig XML unknown; blocked |
| PA-1420 | 9–12 | RJ45 Multi-Gig | 10M/100M/1G/2.5G/5G | Yes | No | No | No | Multi-Gig and PoE XML unknown; blocked |
| PA-1420 | 13–14 | SFP | 1G | No | No | SFP installed | Capable | Optical and remap XML unknown; blocked |
| PA-1420 | 15–22 | SFP/SFP+ | 1G/10G | No | No | Rate follows optic | Capable | Optical and remap XML unknown; blocked |

## Safety boundary and qualification

Official PoE instructions expose interface-specific CLI controls and a total power budget, so blindly moving an interface subtree could change power behavior. No exact exported XML example was found to support a synthetic PoE fixture or a safe rewrite. Official hardware documentation says optical ports can become HA1 ports, but the current parser and renderer have no explicit PoE or HA1-remap model. The XML-aware unmodeled-reference guard protects references it recognizes; it is not proof that every HA remap or PoE structure is covered. The real analysis-only profile blocks candidates before either ambiguity can be silently accepted. ZTP on port 1 stays informational.

| Model | Hardware | PAN-OS | Multi-Gig | PoE | HA remap | Serialization | Renderer probe / negatives | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PA-1410 | Four exact groups verified | Modeled trains explicit | 2.5G/5G target rule unknown | 9–12 capable; XML unknown | Optical remap XML unknown | Unverified | Generic preservation passes; real API blocks | `ANALYSIS_ONLY` |
| PA-1420 | Five exact groups verified | Modeled trains explicit | 5–8 and 9–12 rules unknown | 9–12 capable; XML unknown | Optical remap XML unknown | Unverified | Generic preservation passes; real API blocks | `ANALYSIS_ONLY` |

Synthetic tests cover all nine groups and absent, auto, numeric 10M through 10G, half/full duplex, `auto`/`up`/`down` link state, and unknown values. A test-only copied profile shows generic link-field preservation and a reparsable candidate. Real profiles and `/api/v1` block candidate creation with `TARGET_PROFILE_RENDERING_NOT_VERIFIED` even with `allow_review=true`; download is unavailable. Source bytes and SHA remain unchanged. The modeled software boundary remains 11.0, 11.1, 11.2, 12.1.2+, and 12.2 supported; 10.1 and 10.2 unsupported. Unknown and malformed versions fail closed.

The catalog remains 11 verified models: PA-3410 and PA-5410 renderer-supported, nine others analysis-only. Further qualification needs official exact-model target XML examples for 2.5G/5G, PoE configuration and budget effects, optical link fields, and HA1 remap state and references. No physical-device validation or deployment certification is claimed.
