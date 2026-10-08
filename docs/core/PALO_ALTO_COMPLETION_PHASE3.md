# Palo Alto completion Phase 3: PA-3200 target qualification

## Result

PA-3220, PA-3250, and PA-3260 remain `ANALYSIS_ONLY`. This is an evidence and qualification review, not a renderer implementation. The generic renderer's ability to preserve and reparse link settings does not prove that those settings are valid on a PA-3200 target. No target-link policy, XML mutation, profile promotion, or device validation was added.

The shared failure is precise: [official front-panel documentation](https://docs.paloaltonetworks.com/hardware/pa-3200-hardware-reference/pa-3220-series-overview/front-panel-3200-series) says RJ45 dataplane ports 1–12 negotiate speed and duplex automatically, while the existing renderer would retain a source manual `link-speed` and `link-duplex`. Official material examined does not distinguish an omitted XML node from explicit `auto` or another valid PA-3200 export representation. It also does not establish the target XML rule for optic-dependent SFP/SFP+ ports or PA-3260 QSFP+. ConfigHop must keep candidate generation blocked rather than infer serialization from physical speed.

## Official evidence and scope

| Evidence | Establishes | Does not establish |
| --- | --- | --- |
| [PAN-HW-PA3200-OVERVIEW](https://docs.paloaltonetworks.com/hardware/pa-3200-hardware-reference/pa-3220-series-overview) | Exact three models; first supported PAN-OS release 8.1 | Current target link XML |
| [PAN-HW-PA3200-FRONT](https://docs.paloaltonetworks.com/hardware/pa-3200-hardware-reference/pa-3220-series-overview/front-panel-3200-series) | Model-specific port groups, physical rates, RJ45 auto-only speed/duplex, transceiver-dependent SFP rate, PA-3260 40G QSFP+ | Whether `auto`, omission, or a numeric value is accepted or canonical in target XML |
| [PAN-COMPAT-PANOS-BY-MODEL](https://docs.paloaltonetworks.com/compatibility-matrix/reference/supported-os-releases-by-model/palo-alto-networks-next-gen-firewalls) | Modeled PAN-OS support boundary | Interface serialization |
| [PAN-CONFIG-ETHERNET-LINK-SPEED](https://github.com/PaloAltoNetworks/pan-os-python/blob/92ed648d89b7541052a15e234eb34e99edba6d2d/panos/network.py) and [PAN-CONFIG-ETHERNET-LINK-SPEED-TEST](https://github.com/PaloAltoNetworks/pan-os-python/blob/92ed648d89b7541052a15e234eb34e99edba6d2d/tests/test_integration.py) | Pinned official SDK source and test expose generic direct-child link fields | PA-3200 model-specific acceptance or default/omission behavior |
| [PAN-CONFIG-ETHERNET-LINK-SPEED-VALUES](https://docs.paloaltonetworks.com/ngfw/networking/configure-interfaces/configure-an-aggregate-interface-group/configure-an-aggregate-ethernet-interface) and [PAN-OS 11.1 Layer 3 interface help](https://docs.paloaltonetworks.com/ngfw/help/11-1/network/network-interfaces/layer-3-interface) | Generic speed, duplex, and state configuration controls | PA-3200 target XML and optic-dependent choices |

The hardware overview's 8.1 release is historical. ConfigHop's current modeled train set remains 10.1, 10.2, 11.0, and 11.1 supported; 11.2, 12.1, and 12.2 unsupported. Unknown trains remain unverified and malformed versions remain unknown.

## Exact target-port matrix

`link-state` is a separate generic field. Tests show that the current renderer preserves absent, `up`, and `down` states, but no PA-3200-specific acceptance claim is inferred. Every row has unverified target XML and remains blocked through its analysis-only profile.

| Model | Ports | Hardware / physical rate | Speed and duplex configuration evidence | Optic dependency | Target XML / renderer result |
| --- | --- | --- | --- | --- | --- |
| PA-3220 | 1–12 | RJ45, 10M/100M/1G | Both auto-negotiate only | No | Omission versus explicit `auto` unverified; blocked |
| PA-3220 | 13–16 | SFP, 1G | Model-specific manual speed/duplex rule unverified | SFP installed | Numeric, `auto`, or omission unverified; blocked |
| PA-3220 | 17–20 | SFP/SFP+, 1G/10G | Model-specific manual speed/duplex rule unverified | Rate follows transceiver | Numeric, `auto`, or omission unverified; blocked |
| PA-3250 | 1–12 | RJ45, 10M/100M/1G | Both auto-negotiate only | No | Omission versus explicit `auto` unverified; blocked |
| PA-3250 | 13–20 | SFP/SFP+, 1G/10G | Model-specific manual speed/duplex rule unverified | Rate follows transceiver | Numeric, `auto`, or omission unverified; blocked |
| PA-3260 | 1–12 | RJ45, 10M/100M/1G | Both auto-negotiate only | No | Omission versus explicit `auto` unverified; blocked |
| PA-3260 | 13–20 | SFP/SFP+, 1G/10G | Model-specific manual speed/duplex rule unverified | Rate follows transceiver | Numeric, `auto`, or omission unverified; blocked |
| PA-3260 | 21–24 | QSFP+, 40G | Model-specific manual speed/duplex rule unverified | QSFP+ installed | `40000`, `auto`, or omission unverified; blocked |

PA-3260 QSFP+ does not inherit PA-5410 native QSFP speed-selection or breakout rules. Hardware rates alone cannot establish link-speed or link-duplex XML.

## Qualification and production boundary

| Model | Hardware | PAN-OS | Target serialization | Generic renderer probe | Negative checks | Result |
| --- | --- | --- | --- | --- | --- | --- |
| PA-3220 | Three exact groups verified | Modeled trains explicit | RJ45 and both optical groups unresolved | Preserves source settings; candidate reparses | Real profile and API block | `ANALYSIS_ONLY` |
| PA-3250 | Two exact groups verified | Modeled trains explicit | RJ45 and optical group unresolved | Preserves source settings; candidate reparses | Real profile and API block | `ANALYSIS_ONLY` |
| PA-3260 | Three exact groups verified | Modeled trains explicit | RJ45, optical, and QSFP groups unresolved | Preserves source settings; candidate reparses | Real profile and API block | `ANALYSIS_ONLY` |

The synthetic qualification probe uses a test-only copied profile marked `SUPPORTED`. For each exact group it exercises absent, explicit `auto`, manual, one-sided manual, unknown speed/duplex, and independent `up`/`down` link state. Generic rendering mechanically succeeds and preserves these values. Real registry profiles remain analysis-only; candidate generation returns `TARGET_PROFILE_RENDERING_NOT_VERIFIED`, including with `allow_review=true`. No candidate file or API download is available, and source bytes and SHA remain unchanged. Existing Phase 1 and Phase 2 tests cover rename, derived references, inventory, postconditions, preservation, and unmodeled-reference safety; none supplies the missing target semantics.

The Palo Alto catalog remains 11 verified models, with PA-3410 and PA-5410 renderer-supported and nine analysis-only targets. To reconsider a PA-3200 promotion, obtain official exact-model PAN-OS XML evidence for RJ45 auto speed and duplex, SFP/SFP+ behavior with installed optic context, and PA-3260 QSFP+ behavior. No physical-device import, commit, or validation was performed.
