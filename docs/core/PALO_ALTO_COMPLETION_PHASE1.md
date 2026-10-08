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

PA-5220, PA-5250, PA-5260 and PA-5280 retain `ANALYSIS_ONLY`. Their official hardware profiles are documentation verified, but this phase has not established model-specific target rendering and preservation qualification for each model. No PA-5410 QSFP rule is inherited by these models. Renderer-supported targets remain PA-3410 and PA-5410; nine real targets remain analysis only.

## Explicit limitations

Layer 2 bridge/VLAN closure, virtual-wire closure, dynamic routing semantics (BGP, OSPF and OSPFv3), PBF, QoS, DHCP, VPN, GlobalProtect, tunnels, advanced NAT, Panorama templates/device groups and multi-device ownership are not transformed. Exact changed interface identities in such XML block candidate generation unless they occur in known nonsemantic text. This guard cannot prove semantics for indirect references that do not contain the changed interface identity. Physical optics, peer settings and actual device behavior require engineer validation.
