# Phase 9A: limited Switch migration

## Scope and architecture

The Phase 8B Switch workspace calls the local FastAPI `/api/v1/switch-projects` contract. The IOS XE line parser produces versioned, vendor-neutral statement and interface records. The AOS-CX renderer uses those records, validated slot assignments, and optional exact JL663A port metadata. A dependency pass records graph edges and findings before export. A browser session stores only a backend project ID; the backend session holds redacted parsed data for one hour and is isolated by UUID.

This adapter covers **Cisco IOS XE 17.12.x to Aruba AOS-CX 10.15.x on an explicitly selected JL663A standalone capability context**. Parsing and logical planning do not require hardware selection. An unknown OS version or missing exact target capability blocks export. The existing hardware profile continues to be marked analysis-only for its older general migration path; this phase validates the specific syntax subset here. No device connection, lab execution, or deployment verification was performed.

## Normalized model

`SwitchMigrationIR` schema version `1` contains selected source OS/version, a list of declared interfaces with kind and source line, and a list of `SwitchStatement` records. Each statement has redacted source text, line, scope, semantic feature, normalized values, explicit flag, dependencies, render support, and one of `TRANSLATED`, `PRESERVED`, `REVIEW_REQUIRED`, `UNSUPPORTED`, `BLOCKED`. No missing source command is silently treated as explicit. The `SwitchCandidate` contains deterministic CLI text and SHA-256, findings, dependency edges, status, coverage counts, resolved interfaces, and syntax/hardware context. Its `deployment_verified` value is always false.

The source inventory contains only configured declarations. Physical, LAG, SVI, loopback, and other interfaces are distinct. Operational link and forwarding state cannot be inferred from running configuration. The renderer never pads source interfaces to 48, maps logical interfaces to physical slots, or emits commands for unmapped physical ports.

## Translation matrix

| Source IOS XE 17.12 | Target AOS-CX 10.15 | Handling |
| --- | --- | --- |
| Hostname, VLAN ID/name | `hostname`, `vlan`, `name` | Translated, validated identifiers |
| `spanning-tree mode rapid-pvst`, VLAN priority, PortFast/BPDU guard | `spanning-tree mode rpvst`, `spanning-tree vlan`, priority in 4096 steps, `port-type admin-edge`, `bpdu-guard` | Translated with explicit mode and VLAN scope |
| `lldp run`, simple IPv4 NTP server | `lldp`, `ntp server`, `ntp enable` | Translated |
| `aaa authentication login default local` | Same AOS-CX command | Translated; target local account provisioning requires review |
| IPv4 `ip route` via directly connected next hop | Prefix-form `ip route` | Translated only with a configured, enabled, connected egress context |
| Extended IPv4 ACL `permit/deny ip any any` | AOS-CX IPv4 ACL `permit/deny any any any` | Translated; other ACE forms block |
| Inbound IPv4 ACL on SVI or routed physical port | `routed-in` on SVI; `in` on physical port | Translated with resolved definition |
| Description, explicit shutdown, L2 access/trunk/native/allowed VLANs, routed IPv4 address | AOS-CX interface context | Translated after mapping and dependency checks |
| `channel-group active/passive/on`, Port-channel | `lag`, `lacp mode` where applicable | Translated when member and LAG declarations agree |
| Domain, DNS, logging, management gateway, local user names, management ACL, dynamic routing, SNMP, DHCP snooping, unknown commands | No target commands | Detected/reported; unsupported or secret-bearing input blocks export |

Unsupported authentication, SNMP communities, passwords, hashes, keys, and certificate material are redacted and require explicit re-entry. No replacement secret is fabricated. This is a limited translation subset; the report, not a universal compatibility claim, defines its coverage.

## Dependency and export rules

The graph relates access/trunk ports to VLANs, LAGs to physical members in both directions, SVIs to VLANs, ACL attachments to definitions, STP to VLAN/interface scope, and static routes to configured connected egress contexts. Missing or contradictory references generate `BLOCKED` findings. Slots are integers 1–48, unique, and assigned only to declared physical interfaces. With JL663A selected, slots resolve against that profile’s first 48 fixed copper ports; the grid itself supplies no naming or capacity evidence. Unmapped ports are omitted and reported for review. Candidate declarations are checked for duplicates.

`BLOCKED` forbids export. `REVIEW_REQUIRED` requires explicit acknowledgement of the current preview. Export requires its current revision and SHA-256; any mapping, platform, capability, or source change invalidates the browser candidate immediately. The backend rejects stale revisions and digests. Review acknowledgement does not mean hardware or deployment is verified.

## API v1

| Method | Path | Contract |
| --- | --- | --- |
| POST | `/api/v1/switch-projects` | `{source_os:"IOS_XE",source_version,text}` → project UUID, revision, redacted inventory |
| GET / DELETE | `/api/v1/switch-projects/{id}` | Retrieve session inventory / remove session |
| PUT | `/api/v1/switch-projects/{id}/preview` | `{revision,target_os:"AOS_CX",target_version,capability_id,mappings}` → current candidate, report, dependencies, findings |
| POST | `/api/v1/switch-projects/{id}/export` | `{revision,sha256,acknowledge_review}` → candidate filename, CLI text, digest |

Requests are typed, limited to 3 MiB transport, 2 MiB source text, 20,000 lines, and 256 expanded VLAN IDs per supported list. They use the existing local mutation header. Up to 32 sessions are retained for one hour. Session data is memory only. Errors never echo input. This is a local, single-user API; it has no authentication and should be bound to loopback.

## Synthetic demonstration and evidence

[IOS XE source](../backend/tests/fixtures/switch/phase9a-iosxe.cfg) has three VLANs, five physical ports, access/trunk/LAG interfaces, an SVI, ACL, STP, NTP, AAA, and a static route. The assignments are `Gi1/0/1→24`, `Gi1/0/2→10`, `Gi1/0/3→48`, `Gi1/0/4→7`, `Gi1/0/5→8`. The [golden AOS-CX candidate](../backend/tests/fixtures/switch/phase9a-aos-cx.cfg) is complete for the supported subset. This synthetic run produced 46 translated and 3 preserved statements, 26 resolved dependency edges, and two review findings (`AAA_ACCOUNT_REENTRY`, `DEPLOYMENT_REVIEW`). Removing VLAN 20 creates `DEPENDENCY_UNRESOLVED` and blocks export. Browser screenshots are in `artifacts/phase9a/`.

Syntax and hardware references: [Cisco IOS XE 17.12 VLAN trunk guide](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst9300/software/release/17-12/configuration_guide/vlan/b_1712_vlan_9300_cg/configuring_vlan_trunks.html); [AOS-CX 10.15 native VLAN](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.15/HTML/l2_bridging_6300-6400/Content/Chp_vlans/vlan_cmds/vla-tru-nat.htm), [RPVST configuration](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.15/HTML/l2_bridging_6300-6400/Content/Chp_stp/cnf-rpv.htm), [LACP settings](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.15/HTML/link_aggregation/Content/Chp_LAG/lac-cnf-set-10.htm), [ACL guide](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.15/PDF/acls_6300-6400-8100-8360.pdf), [fundamentals/NTP](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.15/PDF/fundamentals_6300-6400.pdf), [static routing concepts](https://arubanetworking.hpe.com/techdocs/AOS-CX/10.15/HTML/ip_route_6300-6400-8100-83xx-9300-10000/Content/Chp_StatRoute/cnf-con.htm), and [JL663A port inventory](https://arubanetworking.hpe.com/techdocs/hpe-central/content/get-started-with-hpe-aruba-networking-central/aos-cx-6300m-switch-port-types.html).

## Known limits

No OS pair beyond IOS XE 17.12.x to AOS-CX 10.15.x is implemented. Hardware data identifies port names and fixed copper capacity for JL663A; it does not verify installed firmware, link media, cabling, connected topology, feature licenses, TCAM use, or production traffic. Dynamic routing, SNMP, advanced ACLs, DHCP snooping, management ACLs, and credential conversion require a later documented adapter. A successful synthetic golden test is not device validation.
