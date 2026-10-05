# ConfigHop Core v0.2: interface mapping preview

Core v0.2 previews the effect of engineer supplied physical Ethernet mappings on normalized Palo Alto source inventory. It consumes `PaloAltoInventory` from the v0.1 parser, builds one exact identity dependency index, validates mappings against a local target `HardwareProfile`, derives child names from `Subinterface.parent_interface`, and returns a structured `MigrationPreview`. It does not edit the inventory or XML.

## Contracts

`InterfaceMapping(source_interface, target_interface)` is manual and exact. Source must be a parsed physical Ethernet interface. Target must be an interface in the supplied profile with kind `physical_ethernet`. Duplicate source or target mappings are blocked. A source and target may share the same name because they belong to separate hardware contexts. Mapping order is preserved.

`HardwareProfile` contains vendor, model, `profile_status` (`synthetic`, `user_supplied`, or `verified`), and uniquely named `HardwareInterface` entries. The JSON loader rejects malformed files and invalid profiles. The included `synthetic-target-fw` profile tests the engine only; it is not an authoritative PA-3410 or PA-5410 port catalog. Speed, media, and mode capability checks are outside this release.

For a child named `ethernet1/12.100` whose explicit parent is `ethernet1/12`, mapping the parent to `ethernet1/5` derives `ethernet1/5.100`. Its VLAN tag is preserved separately, even if the tag is `200`. References are looked up by complete interface identity; `ethernet1/1` never matches `ethernet1/10`.

The dependency index covers subinterface parent relationships, zone interface members with VSYS scope, virtual router interface members, static route egress interfaces, NAT interface references, and aggregate membership. A `ReferenceChange` is a proposed reference operation, never a configuration write. Security rules and address or service objects are not rewritten.

## Status and coverage

`BLOCKED` means an error finding invalidated at least one mapping, including absent source or target, unsupported direct mapping object, duplicate source or target, or ambiguous multi-device inventory. `REVIEW_REQUIRED` means mappings are structurally valid but a warning needs human review, such as an aggregate member, Layer2, or virtual-wire interface. `READY` means: **No blocking or review condition was detected within Core v0.2's currently modeled preview scope.** It does not mean safe to deploy to a production firewall.

Findings use stable codes and severities. Parser warnings remain separate from mapping findings. `DependencyCoverage` records supported reference types and known gaps. Layer2 bridge/VLAN relationships, full virtual-wire membership, dynamic routing, and target hardware compatibility are not fully modeled. The preview does not claim complete PAN-OS dependency coverage.

## Local use

From `backend`:

```powershell
python -m pytest -q
python -m compileall src
python -m confighop_core.preview "..\local-samples\paloalto\backup7sept2026.xml" --target-profile "tests\fixtures\hardware\paloalto_target_synthetic.json" --map "ethernet1/12=ethernet1/5"
```

Repeat `--map` for multiple mappings. The CLI prints counts and status only. Private XML under `local-samples/` remains ignored and must never be committed or copied into fixtures or documentation.

Core v0.3 may add a PAN-OS to PAN-OS candidate renderer from inventory, mapping, and preview, producing target XML or set commands. Core v0.2 generates neither.
