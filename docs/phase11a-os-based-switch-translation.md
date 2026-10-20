# Phase 11A: OS-based Switch translation

Phase 11A translates a **limited** Cisco IOS XE configuration subset to native HPE Aruba Networking AOS-CX CLI. The migration identity is source OS/version to target OS/version. Hardware context is optional. This is synthetic software validation, not a lab or device qualification. The [machine-readable matrix](phase11a-switch-support-matrix.json) records each release and its evidence.

## Release evidence and support levels

Retrieved 2026-10-20. Cisco calls IOS XE 17.12, 17.15, and 17.18 [Extended-Support releases](https://www.cisco.com/c/en/us/support/docs/switches/catalyst-9300-series-switches/214814-recommended-releases-for-catalyst-9200-9.html). Cisco lists the [17.12 last support date](https://www.cisco.com/c/en/us/products/collateral/ios-nx-os-software/ios-xe-17/ios-xe-17-12-x-eol.html) as 2028-03-31 and the [17.15 last support date](https://www.cisco.com/c/en/us/products/collateral/ios-nx-os-software/ios-xe-17/ios-xe-17-15-x-eol.html) as 2029-03-31. An exact last support date for 17.18 was not established.

HPE identifies [10.10](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.10/RN/rn_6000-6100_10-10-0002.pdf), [10.13](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.13/RN/rn_6200_10-13-1000.pdf), and [10.16](https://support.hpe.com/hpesc/public/docDisplay?docId=sd00007242en_us&docLocale=en_US&page=GUID-32C2FA9F-EB66-4BB3-AA0F-7E9651524219.html) as Long Supported Releases. The cited notes describe a five-year support period from initial release. Exact end-of-support dates were not independently established. AOS-CX [10.15 is a Short Supported Release](https://arubanetworking.hpe.com/techdocs/AOS-CX/Consolidated_RNs/6000%20Release%20Notes/GUID-2885B166-95FF-4C90-BA75-D1BD512FC810_4.html); it remains selectable solely to preserve the tested Phase 9A path.

| Source | Target | Software status |
| --- | --- | --- |
| IOS XE 17.12/17.15/17.18 | AOS-CX 10.10/10.13/10.16 | `TRANSLATION_SUPPORTED` for the bounded feature subset below; synthetic tests only |
| IOS XE 17.12 | AOS-CX 10.15 | Legacy SSR subset retained; synthetic tests only |
| AOS-CX to IOS XE, or any other pair | Any | `NOT_IMPLEMENTED`; candidate blocked or unavailable |

The shared AOS-CX renderer emits only command forms covered by the existing 10.15 adapter and the documented common subset in [10.10 Layer-2](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.10/PDF/l2_bridging_8400.pdf), [10.13 Layer-2](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.13/PDF/l2_bridging_8400.pdf), and [10.16 CLI](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.16/PDF/cli_8100-8360.pdf) references. These references do **not** prove that every command or feature is present on every device. Selected source and target trains gate preview; unrecognized trains produce `BLOCKED`. Any future syntax divergence requires a small version-specific adapter and new evidence before support is extended.

## Architecture and hardware boundary

The Phase 9A parser already produced typed statements, source lines, interface identities, and dependencies. The semantic renderer already checked unresolved VLAN, ACL, route, STP, LAG, and administrative-state conditions before deterministic output. Its hard coupling was the mandatory JL663A capability and integer slots 1-48. The UI always displayed that 48-slot plan. Phase 11A accepts explicit AOS-CX physical interface names (`member/module/port` positive integers) without a profile and keeps old numeric slots only when JL663A is selected. Without hardware, a `PORT_EXISTENCE_NOT_VERIFIED` review finding accompanies a candidate. Syntax-valid names never assert that a physical port exists.

The unchanged phase-8A Palo Alto hardware mapping and firewall translator are separate. The old JL663A path retains its exact slot range and profile inventory checks. Its software evidence covers 10.15 only, so choosing JL663A with another AOS-CX train keeps hardware compatibility `NOT_VERIFIED` and adds a review finding. Switching the optional profile clears incompatible mapping values. Changing versions, source, target, mappings, or capability invalidates the current UI candidate; the backend still checks revision, digest, blocked status, and review acknowledgement at export.

## Coverage and safety

Implemented semantic subset: VLANs and names, explicit access/trunk VLAN sets and native VLAN, explicit shutdown state, LAG/LACP, rapid PVST subset, IPv4 SVI/routed interfaces, static IPv4 routes, limited `permit/deny ip any any` ACLs, LLDP, NTP, and local AAA method with separate account reentry. Source statements carry redacted provenance and a disposition. Unknown, malformed, secret-bearing, and unsupported statements produce findings and block export. The renderer does not copy unrecognized source text to target CLI. Native VLANs excluded from an explicit allowed list now block pending engineering review.

Unsupported: advanced ACL matches, OSPF/BGP, SNMP configuration, syslog translation, DHCP snooping, management ACLs, VRFs, loopbacks, credentials/local users, and platform-specific services. The parser may recognize some of these to classify them; recognition is not translation support. No Aruba-to-Cisco renderer exists.

Each preview includes a machine-readable `translation_summary` with OS/version, construct disposition counts, unsupported families, unresolved dependencies, mapping completeness, hardware verification status, and scoped output-validation status. `CHECKED_SUBSET` means parser/renderer and structural checks passed for this bounded grammar, not that the CLI was executed on a switch. A `BLOCKED` candidate cannot be exported. Every permitted candidate remains `REVIEW_REQUIRED` and requires acknowledgement for its current SHA-256 digest.

## Verification and remaining limits

The backend matrix tests all nine LSR train pairs using the same synthetic fixture, manual nonsequential mappings, and deterministic candidate equality. Separate tests cover malformed/duplicate target names, optional JL663A checks, stale digest/version exports, legacy golden output, unsupported source syntax, dependency failures, and redaction. Browser tests exercise manual mapping without hardware and the retained JL663A slot flow. The two fixture-based browser tests normalize CRLF to LF before exact source edits and assert that those edits occurred.

No device accepted this output during Phase 11A. Physical port existence, optics, capacity, firmware patch level, operational state, and packet behavior remain `NOT_VERIFIED`. The local API remains unauthenticated and intended for loopback use only. Do not treat the release matrix as a platform compatibility guarantee.
