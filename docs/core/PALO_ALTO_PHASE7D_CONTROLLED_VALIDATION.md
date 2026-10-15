# Phase 7D controlled exact-model validation protocol

## Purpose and current execution state

This package defines future experiments for PA-3200 and PA-5200 speed/duplex serialization. Phase 7D performs no device testing, command execution, configuration load, commit, or evidence intake. All 1,668 expanded protocol cases are `NOT_RUN`, their device outcomes are `UNDETERMINED`, and no real observations are included. PA-1400 remains parked.

## Evidence categories

Keep these categories explicit in every record:

| Category | Meaning and limit |
| --- | --- |
| Documented hardware fact | Existing catalog port/media/rate capabilities; does not prove XML acceptance. |
| Protocol hypothesis | A planned action or candidate value; no predicted device outcome. |
| Synthetic test | Tests the offline framework with invented metadata, never device behavior. |
| Unobserved device behavior | Unknown until evidence is supplied. |
| Official vendor evidence | Exact-model documentation or engineering statements with verified provenance and version scope. |
| Controlled device evidence | Observations from authorized isolated equipment with retained sanitized artifacts. |
| Review decision | A separately recorded human evaluation of a precisely bounded scope. |

## Authorized laboratory prerequisites

Load/commit experiments can disrupt connectivity. Future execution requires authorized non-production equipment, change-control approval, confirmed equipment ownership/access, management-plane recovery access, a tested operator recovery procedure, and no production traffic dependency. Never test rejected configurations on production firewalls.

Before each experiment, record exact model, exact PAN-OS patch/hotfix build, train, exact interface, canonical port-group ID, physical media, installed transceiver identity/rate context, initial configuration, one controlled mutation, and backup/recovery arrangements. Use a serial-free laboratory equipment identifier. Baseline and artifact handling must exclude customer exports.

## Scope selection

Use `palo_alto_phase7d_qualification_protocol.json`. Its 20 group/model scopes are generated from the frozen gap catalog and current hardware/software registry. PA-3220/3250/3260 protocol trains are 10.1, 10.2, 11.0, 11.1; PA-5220/5250/5260/5280 also include 11.2. Exact patch/build must be chosen and recorded when an observation is made. A train does not identify an exact tested release.

PA-3220 SFP 13–16 requires 1G context; mixed PA-3200 SFP/SFP+ groups require separate 1G and 10G contexts; PA-3260 QSFP+ requires 40G context. PA-5200 optical 5–20 requires separate 1G and 10G contexts; PA-5220 QSFP+ requires 40G; PA-5250/5260/5280 QSFP requires separate 40G and 100G contexts. These are physical capabilities, not canonical XML values. Never inherit PA-5410 XML behavior.

A group case chooses one exact interface for the evidence packet. Passing review readiness for that interface does not automatically qualify sibling ports, models, patches, trains, or optic contexts.

## Independent speed and duplex experiments

Expand six case types independently for `link-speed` and `link-duplex`, for each exact model/group/train and applicable optic-rate context:

1. `DEFAULT_ABSENT`: capture untouched defaults and test omission of the node.
2. `EXPLICIT_AUTO`: test an explicit `auto` node independently of omission.
3. `EXPLICIT_MANUAL`: test a recorded lab-approved candidate token (numeric for speed). A physical rate does not establish its XML representation or acceptance.
4. `ACCEPTANCE_REJECTION`: test a lab-approved unsupported-value hypothesis and record rejection, retention, ignoring, or normalization. Do not assume rejection beforehand.
5. `EXPORT_NORMALIZATION`: compare attempted and exported presence/value and explicitly record normalization.
6. `REIMPORT_STABILITY`: re-import the sanitized exported representation, record acceptance/rejection, and compare the resulting export.

Reset to the known baseline between independent actions. Record any relevant interaction cases separately with their controlled conditions; one field's result does not settle the other field. Additional manual-value boundaries and interactions require explicit future reviewed protocol additions. For PA-5200 on 11.2, retain the unresolved question of CLI presentation versus XML behavior; do not infer an answer.

## Observation sequence

For future authorized execution, prepare synthetic interface configuration, capture baseline, apply one approved test action, and record load and commit results separately. Capture the attempted and exported node presence/value, normalization or ignored-value explanation, and re-import result. Accepted load is not accepted commit; accepted commit is not stable exported XML; stable export is not re-import acceptance.

Record negative outcomes as evidence. After a rejected load/commit, a later stage may be `NOT_APPLICABLE` only with the explicit predecessor rejection and a technical reason. Unknown stages remain `NOT_OBSERVED` and leave review readiness incomplete. Capture stage-specific output and baseline-versus-candidate distinction in the retained artifact. Do not invent actual link state, optical power, or peer readiness.

A justified skipped stage preserves the rejection evidence but cannot cover a case whose purpose is to observe that stage. `EXPORT_NORMALIZATION` requires an actual export observation; `REIMPORT_STABILITY` requires an actual export and an attempted re-import with an explicit result. Otherwise those cases remain incomplete, even when non-applicability is explained.

Re-import acceptance requires a recorded re-exported node presence/value and an explicit stability observation. Acceptance alone does not establish a stable round trip; the assessment detects a stability claim that contradicts the recorded representations.

## Record and artifact hygiene

`ObservationRecord` holds metadata, not raw XML or secrets. Record IDs and `artifact://` references must be safe technical identifiers; retain hashes, provenance, observation time with timezone, author, and designated independent reviewer. A SHA-256 hash provides integrity metadata, not technical sufficiency or proof of device behavior.

Sanitize artifacts before future review. Exclude credentials, keys, cookies, serial numbers, customer names, management addresses, production IP plans, private case URLs, and raw customer configuration. Retain minimal synthetic node excerpts and relevant diagnostic evidence in an approved separate evidence store. The offline component does not read referenced artifacts or connect to a device. No real artifacts are committed in Phase 7D.

## Offline validation tooling

From `backend`, run:

```text
python -m confighop_core.evidence.qualification_protocol
python -m pytest -q tests/test_palo_alto_phase7d_qualification.py
```

The module prints the canonical inventory and current planning report. Its pure functions generate deterministic case IDs, validate manifest snapshots, and assess structured metadata via `assess_serialization_evidence(scope, records, manifest, catalog)`. The CLI performs no device or artifact intake.

`INCOMPLETE` identifies absent cases or missing evidence fields. `REJECTED` identifies invalid scope, contradictions, unsupported source classes, or invalid metadata. `READY_FOR_REVIEW` means structural coverage for the supplied exact scope only. It does not qualify XML, validate a device, close a gap, or promote rendering support. Synthetic readiness remains explicitly synthetic.

## Human review and future qualification

Identify the observation author and designated independent reviewer separately. A designated reviewer field is not a claim that review occurred. Future completed human review must record reviewer identity, review time, technical decision, reasoning, artifact provenance, exact qualified model/version/interface/group/optic scope, rejected generalizations, and remaining uncertainties. Wider port/model/version applicability requires authoritative evidence and a separate reviewed scope decision.

Keep protocol specification, observed/extracted evidence, and review decision as separate artifacts. Any production evidence-state change or renderer operation requires a later qualification approval; this framework provides no automatic path to either.

## Optional authoritative vendor route

Current exact-model official documentation or vendor engineering responses may supply equivalent deterministic semantics, provided they explicitly address both fields, omission/default, accepted values, failure/normalization boundaries, export/re-import where relevant, and exact version scope. Future transcribed reference records must retain their evidence class and provenance; they are not device observations. Existing generic hardware guides and SDK examples do not establish these exact-model semantics.

Community reports support hypotheses or corroboration only. The three existing vendor requests remain `REQUEST_READY`, responses `NOT_RECEIVED`, and submission remains optional when authorized access exists. Phase 7D submits no request and requires no TAC access.
