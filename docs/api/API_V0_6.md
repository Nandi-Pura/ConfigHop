# API v0.6 target speed

Existing compatibility, preview, and candidate endpoints accept optional settings on a manual mapping:

```json
{"mappings":[{"source_interface":"ethernet1/12","target_interface":"ethernet1/41","target_settings":{"link_speed":"100G"}}]}
```

For PA-5410 ethernet1/41–44, `40G` and `100G` select native speed. Missing speed yields `TARGET_NATIVE_PORT_MODE_REQUIRED`; `auto`, `10G`, `25G`, and unknown speed strings yield `TARGET_LINK_SPEED_UNSUPPORTED`. Settings on unrelated ports yield `TARGET_INTERFACE_SETTING_NOT_APPLICABLE`. Breakout targets still yield `BREAKOUT_MODE_REQUIRED`. These are normal `BLOCKED` domain results.

A valid native choice clears the native blocker and produces `PHYSICAL_LINK_CHANGE_REQUIRED` as a review warning. An explicitly configured source speed that differs also produces `TARGET_LINK_SPEED_CHANGED`. Candidate generation requires the existing `allow_review=true` acknowledgement for warnings. It cannot bypass errors. The candidate response includes `SET_INTERFACE_LINK_SPEED` in the plan, semantic diff, and validation results. No new endpoint or live firewall connection is added.
