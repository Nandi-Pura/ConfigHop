# Phase 7A.1: Scoped rendering in the firewall workbench

Phase 7A.1 exposes the Phase 7A backend safety decision before candidate generation. It preserves the existing workbench and migration behavior.

## Status language

`SUPPORTED` identifies qualified profile-level rendering, `SCOPED` identifies operation-scoped rendering, and `ANALYSIS_ONLY` cannot generate a candidate. A verified SCOPED target displays “Hardware Verified · Scoped Rendering” and explains that candidate generation is limited to qualified interface paths.

## Mapping and render safety

The mapping `Status` and `Render Scope` columns answer different questions. A mapped interface may still be blocked for rendering. The Render Scope cell displays `PENDING` until a current backend preview arrives. Its `SAFE PATH`, `REVIEW`, and `BLOCKED` states follow backend findings; the frontend does not approve migration safety independently.

The detail panel shows the source and target interfaces, target capability, source link values and node presence, backend decision and finding codes, and official evidence IDs. The row evidence action reuses the existing evidence dialog.

## Qualified RJ45 path

For PA-3200 RJ45 ports 1–12 and PA-5200 RJ45 ports 1–4, a backend-qualified Layer3 mapping shows `SAFE PATH` and explains that ConfigHop will not write speed or duplex. Absent source nodes display “Default / absent”. The UI does not infer that absence means an explicit `auto` node.

Explicit `auto` and manual speed or duplex show backend blockers. Unqualified optical/QSFP targets remain selectable for mapping analysis and show `BLOCKED` after preview. Missing active mappings and partial dependency modes also show blockers. Backend preview and compatibility remain authoritative, including the Generate Migration control.

The 40G/100G selector appears only for `MANUAL_NATIVE_PORT_SPEED` on PA-5410 native QSFP ports. Scoped auto-only RJ45 ports never receive that selector.

## API view

The existing `/api/v1` inventory response now exposes `link_state`, `link_speed`, `link_duplex`, `link_speed_explicit`, and `link_duplex_explicit` from the parser. This is an additive, read-only view change; no parser, renderer, or migration-core decision changed.

## Next

Phase 7B: PA-3200 and PA-5200 optical and QSFP qualification.
