# Phase 9B: limited cross-vendor firewall translation

## Baseline and isolation

The implementation branch starts at `9d21e0d287f889f435c2df3b553c6b37608257a5` (Phase 9A). That commit includes the unmerged Phase 8B locked UI. `main` was `a8619a2bf25e4d8ecef64b29039e683bd4f666df` at the start of this work. The existing PAN-OS-to-PAN-OS project API, hardware profile logic, preservation audit, and Switch router are unchanged. The new cross-vendor router and workspace are separate.

The local workspace also contained user-owned `.gitignore`, `.graphifyignore`, `tsconfig*.tsbuildinfo`, `vite.config.d.ts`, and `vite.config.js`. Later, user-owned `AGENTS.md` and `.agents/` appeared. They are excluded from Phase 9B commits.

## Reference audit

| Source, pinned revision | Inspected files and relevant behavior | Decision |
| --- | --- | --- |
| [VahidTa/firewall_migration_tool](https://github.com/VahidTa/firewall_migration_tool) `6d8c27f693f113745a08e906330ed99c0a9c8fe9` | `resources/parser.py`, source Forti/Palo converters and policy converters, destination vendor ABC/data objects and Forti/Palo writers. PyYAML and `xmltodict` based object/service/policy flow. MIT. Limited NAT, interface, route, and dependency coverage for this task. | Architecture reference only; no imported or copied source. |
| [gswsystems/fortigate-palo-migration](https://github.com/gswsystems/fortigate-palo-migration) `c907825d51583756b985dba8b6353c4632bf958c` | Main converter, enhanced addon/main, and migration guide. `requests` API ingestion and Terraform output, not uploaded CLI or PAN-OS XML candidates. `verify_ssl=False` by default and unbounded HTTP calls in the inspected client are unsuitable for ConfigHop. AGPL-3.0. | Feature inventory reference only; no imported or copied source. No device API calls. |
| [gateshift/gateshift](https://github.com/gateshift/gateshift) `4b97a76ea7b7f10202b2f03cad2c72ed678f8d97` | `webui/refmodel.py`, `namemap.py`, `deploy/integrity.py`, Fortinet/PANW drivers, enrichment importers, shadowing. Its pure integrity functions emphasize cross-vendor reference safety, but the deploy drivers depend on the project model and API layer. BSL 1.1 for release 0.9.3, change date 2030-10-07. | Conceptual reference only; no imported or copied source. ConfigHop blocks unresolved references instead of pruning them. |

## Architecture

```mermaid
flowchart LR
  A[Upload or paste] --> B[FortiOS CLI parser or existing secure PAN-OS XML inventory parser]
  B --> C[Typed FirewallIR]
  C --> D[Reference and semantic validation]
  D --> E[Explicit name and interface mappings]
  E --> F[PAN-OS XML or FortiOS CLI renderer]
  F --> G[Syntax reparse and coverage]
  G --> H[Read-only Live IDE]
  H --> I[Revision and digest gated review export]
```

The parser limit is 2 MB and 20,000 FortiOS lines. XML uses `defusedxml`. The API keeps source IR in per-project, in-memory sessions for one hour, with a 32-session limit. It stores no source file for cross-vendor projects. Mutating API requests require the existing `X-ConfigHop-Client: web` header. Preview revisions increase monotonically; export requires the current revision and SHA-256 digest. A blocked candidate has no render text. Review-required export needs acknowledgement for that current candidate.

The IR carries source vendor/version/scope, typed interfaces, zones, addresses/groups, services/groups, schedules, ordered policies, NAT, and routes. Entities have stable scoped identity, source name/location, dependencies, parse status, and findings. Mapping dictionaries rename references in groups, policies, zones, NAT, and routes. Names and collisions are checked before rendering. Group members are emitted before their groups. Source order is preserved for policies and NAT.

## Capability matrix

The supported pair is **FortiOS 7.4 ↔ PAN-OS 11.1**, using synthetic fixtures and offline syntax reparse. Hardware suitability and deployment equivalence are unverified.

| Area | Existing ConfigHop | Phase 9B subset | Classification / limit |
| --- | --- | --- | --- |
| PAN-OS XML and inventory | Secure parser, same-vendor inventory | Adapter for one device and one VSYS | EXISTING_CONFIGHOP, extended independently |
| FortiOS CLI | None | Nested `config/edit/set/unset/next/end`, quoted values, VDOM detection, unknown command/field findings | NEW_IMPLEMENTATION; multi-VDOM blocked |
| IPv4 addresses, FQDN, groups | PAN-OS object inventory | IPv4 CIDR/range/FQDN and nested static groups | NEW_IMPLEMENTATION; dynamic groups blocked |
| TCP/UDP services and groups | PAN-OS service inventory | One destination port or range and nested groups | NEW_IMPLEMENTATION; ICMP/SCTP/source-port forms blocked |
| Interfaces and zones | Same-vendor physical mapping | Explicit physical, simple VLAN/aggregate mappings; zone name mapping | NEW_IMPLEMENTATION; no hardware profile claim |
| Static routes | PAN-OS inventory | IPv4 static route in the sole `default` PAN-OS virtual router, with optional mapped egress and IP next hop | NEW_IMPLEMENTATION; additional or non-default virtual routers, including empty contexts, and dynamic routing blocked |
| Security policies | PAN-OS inventory | Ordered allow/deny, disabled state, address/service/zone refs, log-end and description | NEW_IMPLEMENTATION; App-ID, identity, profiles, negation, category blocked |
| NAT | PAN-OS inventory | Single-address overload SNAT and one-to-one VIP/DNAT with explicit ingress, one resolvable service match, and policy link | NEW_IMPLEMENTATION; PAN-OS DNAT `translated-port`, port forwarding, central NAT, complex pools, combined SNAT/DNAT, and ambiguous packet flow blocked; every emitted NAT rule requires engineer review |
| Schedules | Not translated | Inventory and findings | UNSUPPORTED for restricted/one-time/recurring conversion; no widening to `always` |
| VPN, security profiles | Not translated | Detected when visible in parsed sections/policies | UNSUPPORTED, BLOCKED_PENDING_EVIDENCE |
| Name mapping and reference integrity | Same-vendor interface mapping | Explicit interface mapping; zone/object/service/policy/NAT renames; missing/cyclic/duplicate checks | NEW_IMPLEMENTATION; concrete identities mapped to target wildcard names are blocked |
| Candidate, validation, export | PAN-OS same-vendor renderer and audit | Isolated XML/CLI candidate, local syntax reparse, per-category coverage, revision/digest export | NEW_IMPLEMENTATION; no hardware validation |

`READY_FOR_REVIEW` means local checks found no review findings; it is not deployment certification. Coverage `validated` counts entities passing local checks, not hardware or packet-flow validation. A blocked source produces no candidate bytes. The supported NAT subset is always `REVIEW_REQUIRED`, so the UI requires explicit acknowledgement before exporting an artifact.

## Demonstrations and tests

Synthetic fixtures are in `backend/tests/fixtures/phase9b/`. `fortios.conf` has two physical interfaces/zones, IPv4 objects and groups, TCP service and group, three ordered policies including a disabled deny, single-address overload SNAT, one-to-one VIP/DNAT with explicit ingress, and a static default route. `panos.xml` is the pinned PAN-OS candidate used as the reverse-direction source. `fortios-candidate.cfg` is the pinned reverse candidate. Both directions produce review-required candidates with two `NAT_REVIEW` findings. Tests verify order, disabled state, NAT policy links, parser round trip, deterministic output, rename propagation, blocked unsupported features, and export revision/digest gates. Browser screenshots in `artifacts/phase9b/` are local inspection artifacts and are not hardware evidence.

Unsafe additions, including App-ID matching, missing VIP ingress, group cycles, unresolved services, and restricted schedules, are tested as blockers. Production configurations can contain other constructs; the supported input subset is intentionally narrow and must be reviewed by a network engineer before any device use.

## Phase 10B-A semantic blockers

The backend blocks concrete zone, address/group, service/group or interface identities that would become reserved target wildcard references, and PAN-OS service mappings to `application-default`. Case-insensitive target collisions are also blocked; explicit source wildcard matches remain supported. PAN-OS DNAT with a destination `translated-port` is blocked instead of dropping that port. PAN-OS interfaces with distinct secondary addresses, dynamic/IPv6 addressing, or unmodeled VLAN/loopback and aggregate-subinterface forms are blocked before the single-address adapter can lose data. The reverse static-route subset uses at most one PAN-OS virtual router named `default`; any additional or non-default context blocks the candidate, even if it has no static routes, because interface ownership still carries routing semantics.

These cases produce specific `BLOCKED` findings and no candidate bytes. Current revision and digest acknowledgement cannot override a block; export returns HTTP 409. The FortiOS 7.4 to PAN-OS 11.1 and reverse subsets above remain synthetic software validations only. No device compatibility or packet-flow equivalence has been verified.

For FortiOS output, a VIP target name that collides with an effective address or address-group name is blocked because a policy destination reference would be ambiguous. Engineers must choose distinct target identities; ConfigHop does not rename them automatically, and export acknowledgement cannot override the block.
