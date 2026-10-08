# Palo Alto completion Phase 1

## Scope and reference path

The reference migration is PA-5220 on PAN-OS 11.1.x to PA-5410 on the same 11.1 train. The source and target profiles must be verified; cross-train migration remains blocked. This is a documentation-verified candidate workflow, not device validation or deployment certification.

## Coverage and safety boundary

| Construct | Current treatment |
| --- | --- |
| Config/detail version, devices, VSYS | Parsed; multi-device mapping blocked |
| Physical Ethernet, Layer 2/3 modes, virtual wire, aggregate membership | Parsed; physical identity can be mapped |
| Layer 2/3 Ethernet units, VLAN and loopback units, IP, management profile, comment, link settings, TCP MSS | Parsed and preserved; child names derive from their physical parent |
| Zone, virtual-router, static-route egress, NAT interface-address | Parsed and rewritten at exact XML locators |
| Aggregate member and subinterface parent | Asserted; aggregate compatibility needs engineer review |
| Address/service objects, security/NAT policies, static routes | Parsed and preserved except modeled interface references |
| Unknown subtree without changed interface identity | Preserved by the XML audit |
| Unknown semantic occurrence of an exact changed physical or child identity | Candidate blocked with `UNMODELED_INTERFACE_REFERENCE` and XML path |

The reference guard uses the renderer's resolved operation nodes as its known declaration/reference set. It checks exact attribute and element text values for each changed physical or derived child identity. Description, comment and XML comment content is nonsemantic. It does not rewrite unmodeled XML. The candidate reparses, must equal expected inventory, passes operation postconditions and a canonical XML preservation audit, and is written separately only after validation. Source bytes are checked again before output.

Effective explicit and implicit assignments are checked against source and target hardware profiles. Collision, absent port, unsupported speed and breakout findings block; narrowed speeds, media changes and aggregate relationships require review where modeled. PA-5410 breakout children 25-40 remain blocked. Native QSFP ports 41-44 require explicit 40G or 100G and engineer review. No breakout configuration is generated.

## PA-5200 qualification

Each model was checked independently against Q1–Q31 in the Phase 1B gate. Q1–Q7 (exact profile, port/media/speed evidence and PAN-OS rules), Q8–Q10 (no unmodeled activation or PA-5410 breakout/native-mode inheritance), Q11–Q23 (generic renderer mechanics on a test-only copy of each profile) and Q24–Q29 (negative hardware/version behavior) passed the bounded synthetic checks. Q30 **fails**: the current renderer has no PA-5200-specific treatment for source manual `link-speed` on target RJ45 ports 1–4. The [official PA-5200 front-panel reference](https://docs.paloaltonetworks.com/hardware/pa-5200-hardware-reference/pa-5200-series-firewall-overview/pa-5200-front-panel) says those ports use auto-negotiated speed and duplex only. The qualification test proves the generic renderer would preserve `<link-speed>1000</link-speed>` on target `ethernet1/1`. Q31 confirms the official hardware evidence supports this restriction; it does not support treating the current output as qualified. The test-only profile copy does not alter the catalog or enable API candidates.

| Model | Hardware and PAN-OS | Generic renderer and preservation | Negative tests | Result | Specific reason |
| --- | --- | --- | --- | --- | --- |
| PA-5220 | Verified 40G QSFP+ and 11.1 support | Bounded rewrite passes with test-only render flag | Invalid port, collision, speed, media, source mismatch, version and stale reference checked | `ANALYSIS_ONLY` | Q30: auto-only RJ45 target can inherit a manual source speed |
| PA-5250 | Verified 40/100G QSFP and 11.1 support | Same mechanics checked independently | Same model-specific negative set checked | `ANALYSIS_ONLY` | Q30: auto-only RJ45 target can inherit a manual source speed |
| PA-5260 | Verified 40/100G QSFP and 11.1 support | Same mechanics checked independently | Same model-specific negative set checked | `ANALYSIS_ONLY` | Q30: auto-only RJ45 target can inherit a manual source speed |
| PA-5280 | Verified 40/100G QSFP and 11.1 support | Same mechanics checked independently | Same model-specific negative set checked | `ANALYSIS_ONLY` | Q30: auto-only RJ45 target can inherit a manual source speed |

No PA-5410 QSFP rule is inherited by these models. Renderer-supported targets remain PA-3410 and PA-5410; nine real targets remain analysis only. Hardware documentation and synthetic tests do not constitute device validation.

## Reference scenario matrix

| Scenario | Expected | Actual | Result |
| --- | --- | --- | --- |
| A Copper identity | READY, candidate | READY; no rename operation | PASS |
| B SFP rename and children | Valid candidate, aggregate review | Compatibility READY; preview REVIEW_REQUIRED for aggregate; candidate valid after review | PASS |
| C Native 40G | REVIEW_REQUIRED; `40000` | Review required; `40000`; semantic diff `40G` | PASS |
| D Native 100G | REVIEW_REQUIRED; `100000` | Review required; speed-change finding; semantic diff `100G` | PASS |
| E Breakout child | BLOCKED | `BREAKOUT_MODE_REQUIRED`; no download | PASS |
| F Unknown semantic reference | BLOCKED | `UNMODELED_INTERFACE_REFERENCE` with path; no output | PASS |
| G Implicit missing target | BLOCKED | `TARGET_INTERFACE_NOT_FOUND`; no download | PASS |
| H1 Two explicit sources, one target | BLOCKED | Hardware collision; no candidate | PASS |
| H2 Explicit versus implicit collision | BLOCKED | Hardware and final-name collision; no candidate | PASS |
| I Source profile mismatch | BLOCKED | `SOURCE_HARDWARE_PROFILE_MISMATCH`; no download | PASS |
| J Derived child collision | BLOCKED | `TARGET_SUBINTERFACE_NAME_COLLISION`; no output | PASS |
| K Safe unknown subtree | Preserved | Candidate valid; subtree unchanged | PASS |
| L Description/comment identity | Preserved | Candidate valid; text unchanged | PASS |

The API reference test creates a project, selects both profiles, uploads synthetic XML, assesses compatibility, previews and generates with explicit review, downloads and reparses the candidate, and verifies source bytes. Separate API tests prove `allow_review=true` cannot bypass breakout, stale unknown references, source mismatch, missing target or collision blocks. Multiple unknown-reference findings follow XML document order.

## Explicit limitations

Layer 2 bridge/VLAN closure, virtual-wire closure, dynamic routing semantics (BGP, OSPF and OSPFv3), PBF, QoS, DHCP, VPN, GlobalProtect, tunnels, advanced NAT, Panorama templates/device groups and multi-device ownership are not transformed. Exact changed interface identities in such XML block candidate generation unless they occur in known nonsemantic text. This guard cannot prove semantics for indirect references that do not contain the changed interface identity. Physical optics, peer settings and actual device behavior require engineer validation.
