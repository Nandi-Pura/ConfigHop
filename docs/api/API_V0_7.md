# API v0.7 registry output

The `/api/v1` route namespace is unchanged. `/hardware-profiles` lists 12 exact profiles in stable order. Detail responses add `domain`, `software_family`, `target_render_support`, and structured `software_support_rules`; legacy `supported_panos_trains` remains derived from the rules. `/capabilities` derives verified, synthetic, render-supported, and analysis-only profile IDs from the registry. Evidence routes include the new official hardware records.

An analysis-only target can be selected and inspected. Compatibility returns `TARGET_PROFILE_RENDERING_NOT_VERIFIED` as a blocking finding; candidate generation cannot bypass it with `allow_review=true`. PA-3410 and PA-5410 target rendering, including PA-5410 native QSFP handling, remains available.
