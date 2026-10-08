# Palo Alto completion Phase 2: PA-5200 link serialization

## Decision

No PA-5200 target is promoted. Phase 1's Q30 failure remains: a test-only override of `TargetRenderSupport` demonstrates that the generic renderer preserves source `link-speed` and `link-duplex` unchanged, including a manual `1000` / `full` pair on target RJ45 `ethernet1/1`. The production registry stays `ANALYSIS_ONLY`, and the API blocks candidate generation even with `allow_review=true`. The override is a qualification probe only; it is never saved to the registry.

The hardware restriction is clear, but the exact PA-5200 target XML representation is not. No official source examined here distinguishes omission from explicit `auto` for the auto-only RJ45 ports. No source establishes how an SFP/QSFP target should serialize manual speed or duplex when its physical rate depends on the installed optic. Generic PAN-OS XML support is not proof of model-specific acceptance. No removal, insertion, or normalization operation is introduced without that proof.

## Official evidence and its limits

| Evidence | Proves | Does not prove |
| --- | --- | --- |
| [PAN-HW-PA5200-OVERVIEW](https://docs.paloaltonetworks.com/hardware/pa-5200-hardware-reference/pa-5200-series-firewall-overview) | Model identities and first PAN-OS releases | Link-setting XML representation |
| [PAN-HW-PA5200-FRONT](https://docs.paloaltonetworks.com/hardware/pa-5200-hardware-reference/pa-5200-series-firewall-overview/pa-5200-front-panel) | RJ45 1–4 are 100M/1G/10G and auto speed/duplex only; SFP 5–20 follow the transceiver; PA-5220 QSFP 21–24 are 40G; other PA-5200 QSFP 21–24 are 40/100G based on the transceiver | Whether `auto`, omission, or a numeric value is accepted or canonical in a PA-5200 configuration export |
| [PAN-COMPAT-PANOS-BY-MODEL](https://docs.paloaltonetworks.com/compatibility-matrix/reference/supported-os-releases-by-model/palo-alto-networks-next-gen-firewalls) | Modeled PAN-OS train support | Interface XML serialization |
| [PAN-CONFIG-ETHERNET-LINK-SPEED](https://github.com/PaloAltoNetworks/pan-os-python/blob/92ed648d89b7541052a15e234eb34e99edba6d2d/panos/network.py) | Pinned official SDK maps generic `link_speed`, `link_duplex`, and `link_state` to direct Ethernet child nodes | PA-5200 port restrictions, default/omission behavior, or device acceptance |
| [PAN-CONFIG-ETHERNET-LINK-SPEED-TEST](https://github.com/PaloAltoNetworks/pan-os-python/blob/92ed648d89b7541052a15e234eb34e99edba6d2d/tests/test_integration.py) | Generic direct numeric `link-speed` serialization | PA-5200 `auto` versus omitted-node choice |
| [PAN-CONFIG-ETHERNET-LINK-SPEED-VALUES](https://docs.paloaltonetworks.com/ngfw/networking/configure-interfaces/configure-an-aggregate-interface-group/configure-an-aggregate-ethernet-interface) | Generic PAN-OS numeric/auto speed and duplex choices | Model-specific PA-5200 port acceptance |
| [PAN-OS 11.1 Layer 3 interface help](https://docs.paloaltonetworks.com/ngfw/help/11-1/network/network-interfaces/layer-3-interface) | Generic speed, duplex, and link-state controls are separate; link state permits `auto`, `up`, or `down` | PA-5200-specific link-setting exports or optic-dependent choices |

## Per-model target matrix

Each row was researched and tested independently. “Unverified XML” means no target candidate is enabled. Link state is audited separately: generic PAN-OS documents the field, and the qualification probe confirms it remains unchanged, but model-specific acceptance is not inferred from that fact.

| Model | Ports | Media and physical rate | Speed / duplex target rule | Link state | Serialization conclusion | Result |
| --- | --- | --- | --- | --- | --- | --- |
| PA-5220 | 1–4 | RJ45, 100M/1G/10G | Both auto-only | Separate generic field | Explicit `auto` versus omission unverified | `ANALYSIS_ONLY` |
| PA-5220 | 5–20 | SFP/SFP+, 1G/10G by optic | Manual setting acceptance unverified | Separate generic field | Optic-dependent XML unverified | `ANALYSIS_ONLY` |
| PA-5220 | 21–24 | QSFP+, 40G | Manual speed/duplex rule unverified | Separate generic field | `40000`, `auto`, or omission unverified | `ANALYSIS_ONLY` |
| PA-5250 | 1–4 | RJ45, 100M/1G/10G | Both auto-only | Separate generic field | Explicit `auto` versus omission unverified | `ANALYSIS_ONLY` |
| PA-5250 | 5–20 | SFP/SFP+, 1G/10G by optic | Manual setting acceptance unverified | Separate generic field | Optic-dependent XML unverified | `ANALYSIS_ONLY` |
| PA-5250 | 21–24 | QSFP+/QSFP28, 40/100G by optic | Manual speed/duplex rule unverified | Separate generic field | `40000`, `100000`, `auto`, or omission unverified | `ANALYSIS_ONLY` |
| PA-5260 | 1–4 | RJ45, 100M/1G/10G | Both auto-only | Separate generic field | Explicit `auto` versus omission unverified | `ANALYSIS_ONLY` |
| PA-5260 | 5–20 | SFP/SFP+, 1G/10G by optic | Manual setting acceptance unverified | Separate generic field | Optic-dependent XML unverified | `ANALYSIS_ONLY` |
| PA-5260 | 21–24 | QSFP+/QSFP28, 40/100G by optic | Manual speed/duplex rule unverified | Separate generic field | `40000`, `100000`, `auto`, or omission unverified | `ANALYSIS_ONLY` |
| PA-5280 | 1–4 | RJ45, 100M/1G/10G | Both auto-only | Separate generic field | Explicit `auto` versus omission unverified | `ANALYSIS_ONLY` |
| PA-5280 | 5–20 | SFP/SFP+, 1G/10G by optic | Manual setting acceptance unverified | Separate generic field | Optic-dependent XML unverified | `ANALYSIS_ONLY` |
| PA-5280 | 21–24 | QSFP+/QSFP28, 40/100G by optic | Manual speed/duplex rule unverified | Separate generic field | `40000`, `100000`, `auto`, or omission unverified | `ANALYSIS_ONLY` |

## Qualification boundary and next evidence

The new synthetic tests exercise absent, explicit `auto`, manual, and unknown source speed/duplex values, with `up` and `down` link states, for every model and port group. The probe confirms that current generic preservation does not normalize any of them; the real profiles block all candidates. No target-link policy field, compatibility finding, transformation operation, semantic diff, or preservation inverse was added because there is no proven target mutation to represent. PA-3410 and PA-5410 renderer behavior remains unchanged. The supported catalog remains 11 verified real models, 2 renderer-supported targets, and 9 analysis-only targets.

To qualify a target later, obtain an official PA-5200 model-specific PAN-OS 11.1 configuration example or vendor documentation that distinguishes omitted and explicit `auto` nodes for RJ45 speed and duplex, plus supported SFP/QSFP XML behavior with installed optic context. A device-backed import/export check would strengthen that evidence but has not occurred here. Only then can explicit, reviewable operations and preservation inverses be implemented and tested. No device validation or deployment certification is claimed.
