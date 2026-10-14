# Palo Alto Phase 7C: Optical Deployment Plan

## 1. Purpose

Present the physical work required for a scoped PA-3200 or PA-5200 migration alongside the PAN-OS configuration candidate. The plan is operational guidance derived from the current backend preview; it is not a deployment record.

## 2. Architecture

`build_deployment_plan` reads inventory, selected hardware and PAN-OS trains, explicit interface mappings, compatibility findings, preview findings, and an optional candidate result. It returns a typed `DeploymentPlan` without writing source or candidate files. Existing API preview and candidate responses carry the plan as an optional read-only field.

## 3. Configuration vs physical deployment

`TransformationPlan.operations` describes XML changes. `DeploymentPlan.configuration_operations` mirrors those operations only for a validated candidate. `DeploymentPlan.deployment_requirements` describes engineer actions; none is appended to the renderer plan or serialized into candidate XML. An optic-rate choice is physical context, not a PAN-OS speed command.

## 4. DeploymentPlan model

The model records source and target profiles and PAN-OS trains, target render support, backend assessment, optional candidate validation, physical verification status, configuration operations, requirements, blockers, and evidence IDs. Each requirement has a stable ID, phase, category, interface context, target port capability, selected optic rate where supplied, source configured speed where present, action status, finding codes, and evidence references.

## 5. Optical requirements

For a mapped optical port, the plan calls for target transceiver, selected rate, cabling, remote peer, source baseline, and post-change interface verification. Rate and supported capability come from the explicit mapping and hardware catalog. The plan does not infer installed transceiver identity, actual link speed, or peer readiness. Missing optic-rate context remains blocked.

## 6. RJ45 requirements

The qualified auto-only RJ45 path receives cutover link-negotiation and peer checks plus post-change interface checks. It receives no optic-rate selection requirement. Explicit or unsupported link settings remain subject to existing backend guards.

## 7. Engineer verification states

Requirements use `ENGINEER_ACTION_REQUIRED`, `BLOCKED`, or `INFORMATIONAL`; the overall physical state remains `NOT_VERIFIED`. Candidate validation `PASS` proves software checks only. `allow_review=True` permits an eligible reviewed candidate and never marks physical tasks complete.

## 8. Pre-change checks

Confirm selected platform and versions, review mappings and backend findings, prepare rollback, inspect transceiver and rate context, verify cabling and remote peer, and record a source interface baseline. These require engineer action outside ConfigHop.

## 9. Cutover checks

For RJ45 paths, check that the target and peer negotiate an operational link during cutover. Optical requirements are pre-change checks because installed modules, cabling, and peer capabilities must be known before change execution.

## 10. Post-change checks

Observe target link state and errors after cutover. For Layer3 source interfaces, validate intended connectivity. No live telemetry or successful result is inferred from configuration XML.

## 11. Rollback preparation

The plan asks the engineer to retain a source backup and confirm an approved rollback procedure. ConfigHop neither executes nor verifies rollback.

## 12. Evidence traceability

Requirement evidence IDs come from existing hardware profiles and backend findings. The builder reports registered IDs separately from unavailable references. UI evidence links open the existing official-evidence dialog. A documented port capability is not evidence that a particular optic is installed.

## 13. API presentation

`deployment_plan` is optional on `PreviewView` and `CandidateMetadata` in `/api/v1`. The preview plan is available before candidate generation, including blocked preview findings. A blocked candidate can also surface renderer findings. No request schema, endpoint, candidate download, or renderer semantics change.

## 14. Migration Plan UI

The Migration Plan tab shows candidate configuration operations separately from deployment requirements grouped into pre-change, cutover, and post-change. It displays backend blockers, candidate validation, `NOT VERIFIED` physical status, interface and optic context, and linked evidence. Existing mapping changes invalidate the stored preview and candidate shown by the UI.

## 15. Safety boundaries

Backend compatibility and direct Core renderer guards remain authoritative. `TARGET_MEDIA_INCOMPATIBLE`, unsupported dependencies, missing optic context, and unmodeled references are blockers; review acknowledgement does not downgrade them. Phase 7C does not add link-speed or link-duplex serialization and does not claim optical deployment is automatic.

## 16. Controlled validation template

For later exact-model device validation, record the following without assuming an outcome:

| Field | Observed value |
| --- | --- |
| Target hardware model | |
| PAN-OS exact version | |
| Target interface | |
| Installed transceiver identity | |
| Configured speed/duplex XML presence | |
| Candidate commit validation result | |
| Exported XML after commit | |
| Relevant CLI output | |
| Validation timestamp | |
| Engineer reviewer | |
| Evidence provenance | |

This template is for controlled future evidence collection. Do not use production configurations as test fixtures.

## 17. Frozen evidence state

The six Phase 7B optical serialization gaps remain `EVIDENCE_PARTIAL`. This milestone changes neither the evidence-gap catalog, vendor-request manifest, nor evidence registry and makes no `DEVICE_VALIDATED` claim.

## 18. Tests

Synthetic tests cover optical and RJ45 requirements, fixed and mixed rate context, blocked media and dependencies, candidate/physical status separation, evidence IDs, deterministic output, API response presentation, and preview invalidation. Frozen direct-renderer security tests and Phase 5/6A/6B evidence oracles remain required regression gates.

## 19. Next milestone

Gather controlled exact-device evidence for currently unresolved optical serialization behavior, then review the evidence gaps before considering any renderer expansion. No such expansion is part of Phase 7C.

## Deterministic requirement identity

Finding-derived dependency requirements use a SHA-256 ID from the finding's code, source interface, target interface, and message. This is the same semantic identity used to deduplicate repeated findings. Distinct OSPF and BGP unmodeled references therefore remain separate; identical findings produce one requirement. Ordinary one-to-one mapping requirements keep their existing IDs. When a blocked preview contains conflicting decisions for the same interface pair, each distinct mapping receives a deterministic suffix; an exact duplicate decision produces no duplicate physical task. IDs provide stable React row keys. This identity change does not affect migration decisions, candidate XML, or physical verification status.
