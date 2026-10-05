# ConfigHop Core v0.3: PAN-OS candidate renderer

Core v0.3 patches a copy of the full source PAN-OS XML using approved v0.2 interface mappings. It never regenerates configuration from `PaloAltoInventory`, because v0.1 models only part of the source. The renderer changes exact known nodes and preserves unknown XML sections.

## Plan and safety gates

`TransformationPlan` records SHA-256 digests for source bytes and normalized inventory, target profile identity and status, preview status, deterministic operations, findings, and plan status. The renderer recomputes the v0.2 preview, reparses the source and compares inventory, validates the final physical and subinterface namespaces, and refuses `BLOCKED` previews. `REVIEW_REQUIRED` needs explicit `--allow-review`; this never bypasses structural or validation errors.

Operations cover physical and child entry renames, zone/virtual router/static-route/NAT reference updates, and structural assertions for subinterface parent and aggregate membership. Same-name mappings produce no rename. Rename swaps and cycles work because all original XML element handles are resolved before any mutation. Occupied targets that would duplicate a final name are blocked.

The renderer validates source bytes with `defusedxml` before a second standard-library parse that retains comments and processing instructions. It uses explicit structural paths and compares names as data, with exact occurrence preconditions. It never constructs XPath from user input or applies string replacement to arbitrary configuration text. The original source file is read-only. Candidate output is written only after all checks pass, using a temporary file and atomic publication. Existing output is refused unless `--force` is passed; the output path can never equal the source.

## Candidate validation

The candidate is parsed again through Core v0.1. A deep copy of source inventory receives only expected modeled identity and reference changes for a strict model comparison. The preservation audit inverts the actual XML mutations on a candidate clone and compares canonical XML with the source tree, including comments. This checks semantic XML content outside the approved plan; it does not promise byte-identical formatting. ElementTree may normalize declarations, attribute formatting, self-closing tags, and namespace prefixes. Postconditions check each mutated node, including atomic rename cases.

`CandidateValidationReport` contains parse, expected-inventory, postcondition, and preservation results. `SemanticMigrationDiff` lists only planned interface-oriented changes, not a raw source diff. A successful candidate means XML is well formed, v0.1 can parse it, modeled state matches the plan, and the preservation audit passed. It does not mean PAN-OS import or commit validation, hardware compatibility, OS compatibility, or production deployment safety.

The included hardware profile is synthetic. No PA-3410 or PA-5410 port facts are inferred. Layer2, virtual-wire, dynamic-routing, and other dependencies remain limited by v0.2 coverage. v0.3 does not translate policies, NAT semantics, routing protocols, VPNs, or other platforms.

## Local commands

From `backend`:

```powershell
python -m pytest -q
python -m compileall src
python -m confighop_core.render "..\local-samples\paloalto\backup7sept2026.xml" --target-profile "tests\fixtures\hardware\paloalto_target_synthetic.json" --map "ethernet1/12=ethernet1/50" --output "..\local-output\candidate.xml"
```

Use repeated `--map` for multiple mappings. `--allow-review` is required for warning status; `--force` permits replacing an existing candidate but never the source. Default output contains counts, status, and digests only. Private source and candidate files belong under ignored `local-samples/` and `local-output/`, never in Git.

Core v0.4 may add a service layer and frontend integration for upload, inventory, mapping, preview, candidate download, and semantic diff display. Those interfaces are not part of v0.3.
