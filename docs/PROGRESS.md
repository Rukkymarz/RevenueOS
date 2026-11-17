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
- **Why it is not sealed** (`docs/reviews/phase-3-review.md`, top table; updated 2026-11-15):
  the NAVA fork is decided — native NAVA is the implementation of record
  ([ADR-0001](adr/ADR-0001-nava-vs-openhands.md)). Two owner blockers remain, both governance,
  not build gaps: (1) a model provider for browser-use, magentic-ui and openclaw-heartbeat;
  (2) model access for the OpenHack scan (DO_NOT_FILE on PR #3, security run 43692377257).
- **Pins used this phase:** nib `1f23f70`, noVNC `e8b5024`, playwright (pip `>=1.49`), Chromium
  (Debian package in the runtime image, not SHA-pinned).

### 2026-11-15 — aegis-os engine, playwright-mcp, ambient-watchers health surface (CI green: 43783782183)
- aegis-os (`heurion-org/aegis-os`) built from its pinned commit and wired as an opt-in
  `engine="aegis"` option on `sandbox.run` (Bubblewrap stays the default); its `run`/`diff --json`
  cycle feeds our own approval-hash-bound `commit()` rather than its own commit/promote path.
  Closes the R04 blocker in the phase-3 review's top table.
- playwright-mcp (`microsoft/playwright-mcp`) built from its pinned commit, running as its own
  compose service, called through the new `browser.call` tool (a thin generic MCP passthrough,
  not 20+ hand-wired tool specs).
- ambient-watchers (previously code-complete but missing from `tests/unit/test_services.py`'s
  service layout and lacking the `/health` + `/v1/info` surface every other service has) now
  has both, via a background scan-loop thread behind a minimal HTTP app.
- openclaw-heartbeat investigated against the pinned commit (`c787d0fac8`): confirmed a real,
  genuine heartbeat feature exists (migrated from a standalone `HEARTBEAT.md` file into a
  per-agent auto-provisioned "proactive job" on openclaw's generic cron/automation system), but
  its only interface (`automations`/`cron` CLI) is explicitly gateway-bound
  (`"Manage automations (via Gateway)"` — no standalone CLI/library path exists), and the
  gateway itself needs a configured agent with model access before the feature does anything.
  Not integrated this phase for the same reason as browser-use/magentic-ui — missing model
  key — now confirmed by direct evidence rather than assumed. See phase-3-review.md's top table.

### 2026-11-15 — NAVA fork decided (ADR-0001); gate re-run
- [ADR-0001](adr/ADR-0001-nava-vs-openhands.md), Accepted: the in-repo kernel is NAVA's
  implementation of record. OpenHands is demoted to a fallback candidate for the model-driven
  agent loop, admissible only as a client of `Gateway.syscall`. The ADR records three reversal
  triggers. Key evidence: the pinned `OpenHands/OpenHands@830c0459` is the Agent Canvas frontend,
  not an agent, and the OpenHands agent (`software-agent-sdk`) requires an LLM and writes the host
  directly from its local workspace.
- Pins updated to match: `components.yaml` `nava.license: in-repo`, `sources.yaml` `nava.reason`,
  the PINS.md D1 row and nava row, and the README components row. aegis-os and playwright-mcp
  source builds added to PINS.md "Runtime images and source builds".
- Spec-1.3 MCP SDK boundary violation (direct `fastmcp` import in runtime-os) caught by CI run
  43784872498 and fixed in `dbb4b7e` (`RawMcpClient` in mcp-common). Green in CI run 43786346724.
- Root cause of the remaining model blocker: the component map schedules three model-driven C02
  components in Phase 3, while the model router (C01, open-weights default `ollama`/`vllm`) is
  scheduled for Phase 13. Only the owner can resolve that: provide a provider now (hosted BYOK
  is a fallback and needs approval under INV-06; self-hosted open weights is policy-first), or
  re-phase the three components. R04 forbids the build agent from deferring a named component.
- **Gate re-run on `78d960e`: not sealed.** Steps 1–2 green: CI 43791376552 (every job green;
  acceptance 39/39; Q1/Q2/Q6/Q7 PASS) and security 43791376467 (green; OpenHack skipped on
  push). Step 3 (review) red on the two owner blockers. The acceptance log was refreshed from
  43791376552.

### 2026-11-15 (late) — owner decisions: re-phase (ADR-0002); OpenHack secrets set but scan refused
- Owner chose to move browser-use, magentic-ui and openclaw-heartbeat to Phase 13
  ([ADR-0002](adr/ADR-0002-rephase-model-driven-c02-components.md)). They stay pinned and in the
  component map; README phase column updated. That seal blocker is closed.
- Owner set the `SECURITY_OPEN_MODEL_*` secrets. Re-run of security run 43692377257 (attempt 2,
  PR #3): the key reaches OpenRouter, which answered `402 - Insufficient credits. This account
  never purchased credits`. Verdict stays DO_NOT_FILE. One owner blocker remains; not sealed.

### 2026-11-17 — Phase 3 sealed with an owner waiver (ADR-0003)
- OpenHack reached the model but was stopped by the provider's free daily cap (security run
  43800695820 attempt 2; again in 44022282817). Verdict stays DO_NOT_FILE. The owner waived it
  as a seal condition ([ADR-0003](adr/ADR-0003-openhack-waiver-phase-3.md)); it still blocks any
  merge to `main` or deploy.
- Gate on `90b4333`: CI 44022282389 every job green; security 44022282817 green except OpenHack.
- Phase 4 (C04 discovery) starts on `build/phase-4`.

