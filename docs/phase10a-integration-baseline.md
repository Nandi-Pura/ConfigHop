# Phase 10A integration baseline

Verified on 2026-10-20. [PR #19](https://github.com/Nandi-Pura/ConfigHop/pull/19) merged the accepted Phase 8B, 9A, and 9B branch into `main` with a regular merge commit. This document records software integration evidence; it does not certify hardware deployment.

| Ref | SHA |
| --- | --- |
| Pre-merge `main` | `a8619a2bf25e4d8ecef64b29039e683bd4f666df` |
| Authorized and merged PR head | `1504b4e9ec555cabeaf5acbce5c2d1a3d54be14b` |
| Verified integrated `main` | `030ef8ab4baf7050566ea0d0ba0460ed39319066` |

GitHub recorded the merge at `2026-10-20T04:15:11Z`. The merge commit has the pre-merge `main` and authorized PR head as its two parents. [Main-branch CI](https://github.com/Nandi-Pura/ConfigHop/actions/runs/39368590230) succeeded at the merge SHA.

## Post-merge verification

Verification ran in an isolated worktree at the merge commit, with the merged backend on `PYTHONPATH`. The original working tree and user-owned files were preserved.

| Gate | Result |
| --- | --- |
| Complete backend regression | 617 passed |
| Frontend unit tests | 31 passed, 0 failed |
| Browser integration | 26 passed, 0 failed |
| TypeScript no-emit check | Passed |
| Python compilation | Passed |
| Production build | Passed |
| Focused Switch and Firewall smoke tests | 5 passed |

The smoke tests covered the Switch golden candidate and determinism, FortiOS-to-PAN-OS and PAN-OS-to-FortiOS candidates, explicit VIP protocol rejection, and Firewall API revision/export/session behavior. Browser tests covered Switch dependency blocking, both real Firewall translation directions, App-ID broadening rejection, stale preview and export invalidation, failed source replacement, and current-candidate export.

On this Windows host, the default temporary checkout converted two browser fixtures to CRLF. Two tests replace exact LF strings and initially timed out because their fixture edits did not occur. Restoring only those fixtures from the committed blobs with `core.autocrlf=false` in the isolated worktree made all 26 browser tests pass. No repository code or fixture content was committed as part of this normalization. A follow-up should make those tests independent of checkout line endings.

## Accepted limits and next gate

Phase 8B, 9A, and 9B retain the `PASS_WITH_LIMITATIONS` verdicts in [final acceptance](final-acceptance-phase8b-9a-9b.md). Exact visual parity and a complete keyboard/screen-reader audit remain unverified. Switch translation remains scoped to the documented IOS XE 17.12.x to AOS-CX 10.15.x JL663A path; Firewall translation remains a limited FortiOS 7.4 / PAN-OS 11.1 subset. Generated candidates require engineer review. Neither device syntax acceptance, packet behavior, nor production deployment was verified. The local unauthenticated API must remain bound to loopback absent a separate access-control design.

Phase 10B MVP stabilization may start from the verified merge SHA. Priorities are the locked UI visual review, keyboard and accessibility audit, clear compatibility and unsupported-feature guidance, export acknowledgement UX, error messages, and the Windows fixture line-ending issue. New vendor capabilities, live hardware deployment, and a production release require separate review and authorization.
