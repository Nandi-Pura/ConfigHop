# Phase 11B: bounded AOS-CX to IOS XE translation

The tested reverse direction is AOS-CX **10.13.x** to Cisco IOS XE **17.18.x**. The existing Cisco-to-Aruba Phase 11A paths remain separate. The [bidirectional support matrix](phase11a-switch-support-matrix.json) records train status and the [Phase 11A notes](phase11a-os-based-switch-translation.md) retain vendor lifecycle evidence. Synthetic tests do not prove device acceptance. `DEVICE_VALIDATION = NOT_PERFORMED`.

## Pipeline and feature disposition

`parse_aruba_migration` bounds input at 2 MB and 20,000 lines. It produces line-numbered, redacted statements and typed interface identities. Every nonblank, noncomment command receives a statement; unknown syntax is `UNSUPPORTED`, secrets and security controls are `MANUAL_REQUIRED`, malformed or duplicate declarations are `BLOCKED`. The native IOS XE renderer only consumes supported statements. The same backend revision, digest, acknowledgement, and blocked export checks protect both directions.

| Feature | Reverse path | Limit |
| --- | --- | --- |
| Hostname, VLAN IDs/names, access ports, descriptions, shutdown state | AUTO | VLAN names are normalized to the safe IOS XE identifier subset; port names require explicit mapping. |
| Trunks, LAG/LACP, static IPv4 SVI, static routes, NTP, DNS, syslog | AUTO | Dependencies, explicit mode, and next-hop reachability are checked. A static route conditionally emits `ip routing` because [Cisco documents it as disabled by default](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst9300/software/release/17-18/configuration_guide/rtng/b_1718_rtng_9300_cg/configuring_ip_unicast_routing.pdf); target forwarding role and license require review. |
| RPVST mode | AUTO + REVIEW | Explicit VLAN scope is preserved in the report; target STP behavior requires verification. |
| DHCP-addressed SVI, banner, timezone | MANUAL | No executable substitute is guessed. |
| AAA, TACACS/RADIUS, local users and ciphertext, SSH/HTTPS management intent | MANUAL + BLOCKED | No credentials, authentication defaults, or plain HTTP are generated. Engineer must design and validate recovery and bindings. |
| VSF/VSX/stack links | MANUAL + BLOCKED | No StackWise or provisioning CLI is generated. |
| Unknown syntax, DHCP snooping, client tracking, advanced policy | UNSUPPORTED + BLOCKED | No source command is copied into target CLI. |

The review draft is a JSON artifact with findings, redacted source dispositions, coverage, and partial CLI. It is not a deployable candidate. Validated export remains disabled while any blocking finding exists; a review-required candidate needs current-digest acknowledgement. Hardware is optional, and Cisco port existence is always `NOT_VERIFIED` without independent platform evidence.

## Sanitized acceptance evidence

`backend/tests/test_switch_reverse.py` generates an entirely synthetic 52-port 10.13 fixture with documentation IP addresses. It covers 48 access ports, two LAG members, two VLAN 1 ports, VLANs 1/99/101, RPVST, SVI, static route, NTP/DNS/syslog, and synthetic credential markers. The markers are checked absent from IR and candidate serialization. The full fixture is deliberately blocked by DHCP client and management security actions. A safe smaller subset exercises revision-bound export.

## Engineer device/lab checklist

1. Confirm exact target hardware, IOS XE image, interface inventory, license, and port media.
2. Verify every physical mapping and LAG member against cabling and transceiver plan.
3. Rebuild credentials and AAA/VTY/console policy with a tested recovery path; do not reuse Aruba ciphertext.
4. Configure DHCP client SVI, timezone, banner, and management exposure manually where required.
5. Build a separate VSF-to-StackWise/standalone topology plan if stacking appears.
6. Compare VLAN membership, STP roots and scope, SVI reachability, route next hops, and management access in an isolated lab.
7. Capture device CLI acceptance and operational evidence before any deployment claim.

Official command references: [Aruba AOS-CX 10.13 RPVST](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.13/HTML/l2_bridging_8400/Content/Chp_stp/rpvst_cmds/spa-tre-mod.htm), [AOS-CX LACP modes](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.13/HTML/link_aggregation/Content/Chp_LAG/lac-ope-mod.htm), and the [Cisco Catalyst 9300 IOS XE 17.18 configuration guide](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst9300/software/release/17-18/configuration_guide/lyr2/b_1718_lyr2_9300_cg.pdf). Feature behavior still depends on platform and release patch.
