# Progress

| Phase | Status | Seal commit | Evidence |
| --- | --- | --- | --- |
| 1 Foundation | sealed | see `git log --grep "phase-1: sealed"` | [review](reviews/phase-1-review.md), [acceptance](reviews/phase-1-acceptance.log) |
| 2 Identity, sandbox, egress, approvals | sealed (phone descoped by owner) | branch `build/phase-2` | [review](reviews/phase-2-review.md), [acceptance](reviews/phase-2-acceptance.log) |
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

## Phase 2: identity, sandbox, egress, approvals

- **Tests:** CI run 43670554824, all five jobs green. Live acceptance 23/23 (Phase 1 + Phase 2
  suites) plus trace secret scan PASS. Q1, Q2, Q6, Q7 PASS. Strict expected failures: 5 left
  (INV-09, INV-11 and INV-12 controls landed; their xfails removed).
- **Coverage:** identity 92.1%, allmail 96.5%, egress 98.0%, sandbox supervisor 81.5%,
  mcp-common 89.6%, pycommon 85.8%, qc 100%.
- **Acceptance 2:** all items PASS. Phone removed from scope by the owner (2026-11-15);
  the approval-gated purchase path stays built for later.
- **Gaps found and fixed:** 15 (review section d), including a secret AgenticMail printed to its
  log, caught by the new trace scan.
- **Pins added:** Stalwart `v0.15.5` image, AgenticMail build `af1e0ef`, Bubblewrap build
  `1fb0aa2` (compose + CI), AutoSecScan build `881d960`.

## Phase 3: computer-use runtime + agent OS (in progress, branch `build/phase-3`)

- **Done, proven live (CI run 43694352166, 30/30 e2e, trace scan PASS):**
  - 3.2 shared risk library (`packages/risk`): one classification for every runtime. Critical
    is blocked in every mode including YOLO; high always needs a hash-bound approval; the
    sandbox blocklist now lives here.
  - 3.1 / 3.6 `runtime-omni`: OmniPilot's 41 tools (pinned `2e3a6bd`) on a real X11 desktop,
    driven one call at a time by remote control (orchestrator -> runtime REST -> tool ->
    receipt -> span). All 41 leave a receipt on the orchestrator's trace; `rm -rf /` blocked
    and audited in ask, auto and YOLO; the runtime has no route out except the pinned proxy.
- **Next:** 3.4 Aegis OS (large repo clone inside the sandbox), 3.5 OpenMuse (persistent
  browser, human takeover console, durable plans, attachment -> PDF -> form -> reply with
  Nib), runaway-process kill report and transactional rollback, 3.3 NAVA layer and its 21
  invariants, then Acceptance 3 and the gate.

### NAVA kernel (C03, runtime-os) — 2026-11-15
- `db/migrations/0003_nava.sql`: syscalls + 12 step records with order/precondition triggers,
  resource locks, A2A bus, four-tier memory, JIT subagents, durable plans, agent tokens.
- `services/runtime-os`: `Gateway.syscall` (the 12-step managed syscall: validate → … → record),
  snapshot/rollback on content hashes, crash reaper, `Kernel` (bus, memory, subagents, plans),
  HTTP surface with per-agent bearer tokens; OmniPilot desktop tools delegated to runtime-omni
  under the same gateway (`nava_delegation` binds the executor call to the live syscall).
- The 21 NAVA invariants are defined in `docs/NAVA.md`, each enforced in Postgres or the gateway
  and proven in `tests/nava/` (21 invariant tests + plans/units/API; 51 local tests green).
- e2e additions: NAVA syscall loop, runaway-process kill (Acceptance 3.3), transactional
  rollback (Acceptance 3.4), rm -rf critical in every mode, bus + memory.

### Phase 3 status — 2026-11-15, head of `build/phase-3`: built and green, NOT SEALED
- **Live proof:** CI run 43702840418, all five jobs green. 39/39 e2e (Phases 1–3), 1,100+ unit and
  invariant tests, coverage gate passed (runtime-os 86.3%, runtime-omni 87.7%, nava-suite 99.2%),
  trace secret scan PASS. Raw output: `docs/reviews/phase-3-acceptance.log`.
- **Acceptance 3, all seven green:** unattended browser signup → OTP → PDF → nib fill → reviewed
  draft; rm -rf blocked in ask/auto/YOLO; runaway process killed and reported; transactional
  rollback; human takeover attach/type/resume; 21 NAVA invariants; 41 receipts by remote control.
- **Why it is not sealed** (`docs/reviews/phase-3-review.md`, top table): aegis-os binary not
  integrated (Bubblewrap supervisor stands in); NAVA is native rather than its documented add-on
  (OpenHands); five C02 components not integrated (browser-use, playwright-mcp, magentic-ui,
  openclaw-heartbeat, ambient-watchers); OpenHack scan still DO_NOT_FILE.
- **Pins used this phase:** nib `1f23f70`, noVNC `e8b5024`, playwright (pip `>=1.49`), Chromium
  (Debian package in the runtime image, not SHA-pinned).
