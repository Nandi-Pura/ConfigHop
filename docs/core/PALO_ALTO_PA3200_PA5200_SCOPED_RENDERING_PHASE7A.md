# Palo Alto Phase 7A: PA-3200 and PA-5200 scoped rendering

## Purpose and evidence boundary

The former global `ANALYSIS_ONLY` gate was too broad for PA-3200 and PA-5200. Phase 7A permits candidate generation for a narrow Layer3 RJ45 migration path. It does not qualify every target operation.

Official front-panel evidence `PAN-HW-PA3200-FRONT` and `PAN-HW-PA5200-FRONT` establishes that the listed RJ45 ports are auto-negotiation-only. It does not establish the exact target XML representation of the default, explicit `auto`, or manual values. The evidence gaps remain partial and blocking. ConfigHop therefore permits the path only when source `link-speed` and `link-duplex` nodes are physically absent and no target link setting is requested. The renderer leaves both absent; this is non-interference, not a claim that omission is the canonical target export format.

## Target status

| Model | Target render support |
| --- | --- |
| PA-3410, PA-5410 | SUPPORTED |
| PA-3220, PA-3250, PA-3260 | SCOPED |
| PA-5220, PA-5250, PA-5260, PA-5280 | SCOPED |
| PA-1410, PA-1420 | ANALYSIS_ONLY |

## Phase 7A safe path

Every active source physical interface needs an explicit mapping to a qualified RJ45 target port. Layer3 interfaces and their modeled subinterfaces, zones, virtual-router membership, and static-route references may be rewritten. Inactive, unmapped entries may retain their identities when those identities exist on the target. The candidate must introduce no link-speed or link-duplex operation or node. Unmodeled references still block rendering.

Explicit `auto` is blocked just like explicit manual speed or duplex: the node itself requires unverified target serialization. Target speed settings also block. Optical and QSFP destinations, Layer2, virtual wire, aggregate members, and incomplete active-interface mappings block even when review is allowed.

## PA-3200

PA-3220, PA-3250, and PA-3260 support PAN-OS trains 10.1, 10.2, 11.0, and 11.1 under the existing compatibility matrix. RJ45 ports 1–12 are eligible for the absence-only safe path. PA-3220 SFP ports 13–16 and SFP+ ports 17–20, PA-3250 SFP+ ports 13–20, and PA-3260 SFP+ ports 13–20 and QSFP+ ports 21–24 remain blocked for candidate generation.

## PA-5200

PA-5220, PA-5250, PA-5260, and PA-5280 support PAN-OS trains 10.1, 10.2, 11.0, 11.1, and 11.2 under the existing compatibility matrix. RJ45 ports 1–4 are eligible for the absence-only safe path. SFP+ ports 5–20 and QSFP ports 21–24 remain blocked. PAN-OS 11.2 compatibility does not resolve the outstanding CLI/XML serialization question. The existing same-train migration rule remains in force.

## Full support bar and next phase

`SCOPED` is not `SUPPORTED`. Full support requires evidence and tests for every render-impacting target behavior in the supported product contract. The recommended next milestone is Phase 7B: PA-3200/PA-5200 optical and QSFP qualification.
