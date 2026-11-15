# Progress

| Phase | Status | Seal commit | Evidence |
| --- | --- | --- | --- |
| 1 Foundation | sealed | see `git log --grep "phase-1: sealed"` | [review](reviews/phase-1-review.md), [acceptance](reviews/phase-1-acceptance.log) |
| 2 Identity, sandbox, egress, approvals | next | | partial work parked on `wip/phase-2` |
| 3-13 | pending | | |
| 14A Signal Room (UI sprint) | queued, runs before Phase 14 completes | | spec received 2026-11-14 |
| 14-15 | pending | | |

## Phase 1: foundation

- **Tests:** CI run 43653421009, all five jobs green. Acceptance 9/9 (live stack 8/8 + contract
  round trip ts1 39 checks, py, ts2 18 checks). Q1 PASS, Q2 PASS, Q6 PASS, Q7 PASS; Q3-Q5
  NOT_APPLICABLE until Phase 8. Strict expected-failures: 9 (controls scheduled for Phases 2, 4, 8, 13).
- **Coverage:** services 91.4-100% (orchestrator lowest), qc 100%, mcp-common 89.4%, pycommon 81.9%.
- **Gates run:** Q1, Q2, Q6, Q7, secret scan, invariant harness, MCP SDK boundary, star gate, compose health.
- **Gaps found and fixed:** 16 (review section d).
- **Open risks:** none unmitigated. Scheduled controls with tripwire tests: egress identity
  pinning and sandbox (Phase 2), gateway filtering and activation (Phase 4), verdict reducer
  (Phase 8), budget router (Phase 13). Rejection audit inside a transaction that already holds
  the audit lock is raised as a Postgres WARNING and logged by the API state machine (Phase 5).
- **Pins added:** 137 repos in `config/sources.yaml` (81 named, 37 added, plus D1 add-ons),
  37 addendum submodule pointers; OTel collector 0.164.0, Envoy v1.40.2, Postgres 16.
- **Re-audit (2026-11-14):** 9 gaps against v4 fixed and re-sealed (review, re-audit section):
  standing D10 security job, RFC 8785 cross-language hashing, package health, DuckDB mirror,
  4 docs, README purpose column, pinned scanner image, 4 AutoSecScan highs fixed. AutoSecScan PASS.
  OpenHack DO_NOT_FILE until its model secrets are set.

