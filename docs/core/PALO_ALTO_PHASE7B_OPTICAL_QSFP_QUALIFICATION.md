# Phase 7B: PA-3200 and PA-5200 optical and QSFP scoped rendering

## Purpose

Phase 7B extends operation-scoped non-interference rendering to qualified optical and QSFP mappings. PA-3200 and PA-5200 targets remain `SCOPED`. This phase does not establish canonical model-specific speed or duplex XML.

## Official hardware evidence

The existing official [PA-3200 front-panel reference](https://docs.paloaltonetworks.com/hardware/pa-3200-hardware-reference/pa-3220-series-overview/front-panel-3200-series) (`PAN-HW-PA3200-FRONT`) identifies PA-3220 SFP 13–16 as fixed 1G; PA-3220 SFP/SFP+ 17–20 and PA-3250/3260 SFP/SFP+ 13–20 as 1G or 10G according to the transceiver; and PA-3260 QSFP+ 21–24 as fixed 40G.

The existing official [PA-5200 front-panel reference](https://docs.paloaltonetworks.com/hardware/pa-5200-hardware-reference/pa-5200-series-firewall-overview/pa-5200-front-panel) (`PAN-HW-PA5200-FRONT`) identifies SFP/SFP+ 5–20 as 1G or 10G, PA-5220 QSFP+ 21–24 as 40G, and PA-5250/5260/5280 QSFP 21–24 as 40G or 100G according to the transceiver.

## Evidence limit

Hardware rate capability does not prove how a particular target exports, accepts, or defaults speed and duplex XML. The six Phase 7B optical/QSFP gaps in `palo_alto_evidence_gaps.json` remain `EVIDENCE_PARTIAL` and blocking for exact serialization. No gap or vendor confirmation is closed here. Community material is not used as renderer evidence.

## Operator optic context

`target_settings.optic_rate` is an explicit operator assertion about the installed or intended physical target optic. Allowed values are `1G`, `10G`, `40G`, and `100G`, limited by the selected port's documented capabilities. The value is validation and deployment context. It is never converted into `target_settings.link_speed`, a `SET_INTERFACE_LINK_SPEED` operation, or PAN-OS XML. Even fixed-rate groups require an explicit selection.

## Official transceiver check

Palo Alto's [transceiver monitoring guidance](https://docs.paloaltonetworks.com/ngfw/administration/monitoring/monitor-transceivers) lists PA-3200 and PA-5200 and describes `show transceiver <interface>` and `show transceiver-detail <interface>`. Operators can use these on the target device to inspect the installed transceiver. ConfigHop does not run commands or discover optics.

## Qualified non-interference path

The `OPTIC_CONTEXT_LINK_FIELDS_ABSENT` condition requires absent source `link-speed` and `link-duplex` XML nodes, an explicitly selected target optic rate supported by that port, compatible source and target media and speed capabilities, an explicit mapping for every active interface, modeled Layer3 dependencies, and engineer review of transceiver, cabling, peer, and rate. The candidate changes only the existing qualified identity and dependency references. It introduces no speed or duplex XML. A valid optic context yields `PHYSICAL_OPTIC_VERIFICATION_REQUIRED` and `REVIEW_REQUIRED`; candidate generation needs the existing review confirmation.

## Fixed-rate groups

PA-3220 SFP 13–16 accepts only 1G context. PA-3260 QSFP+ 21–24 and PA-5220 QSFP+ 21–24 accept only 40G context. The UI starts blank for each.

## Mixed-rate groups

PA-3220 SFP/SFP+ 17–20, PA-3250/3260 SFP/SFP+ 13–20, and every PA-5200 SFP/SFP+ 5–20 accept 1G or 10G context. PA-5250/5260/5280 QSFP 21–24 accept 40G or 100G context. Selection does not authorize automatic physical rate transformation.

## Blocked paths

Missing or unsupported optic rate, explicit source `auto` or manual speed/duplex, and requested target `link_speed` are errors. Media incompatibility, Layer2, virtual wire, aggregate members, unknown references, missing active mappings, and PAN-OS train changes remain blocked. `allow_review` cannot override errors.

## PA-5410 distinction

PA-5410 `MANUAL_NATIVE_PORT_SPEED` remains a configuration decision that serializes a qualified 40G or 100G link speed. Phase 7B `optic_rate` is separate physical context and never serializes a link setting.

## Support status and next phase

PA-3410 and PA-5410 remain `SUPPORTED`; PA-3200 and PA-5200 remain `SCOPED`; PA-1410 and PA-1420 remain `ANALYSIS_ONLY`. The PAN-OS matrices, same-train rule, API namespace, and version remain unchanged. The recommended next milestone is Phase 7C: Optical/QSFP Hardening & Deployment Plan, covering deployment requirement presentation, migration-plan quality, aggregate/Layer2 boundaries, and an optional controlled device-validation package. It is outside Phase 7B.
