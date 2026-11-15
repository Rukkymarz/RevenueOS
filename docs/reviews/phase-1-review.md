# Phase 1 gate review: foundation

Evidence: CI run [43653421009](https://github.com/Rukkymarz/RevenueOS/actions/runs/43653421009)
(all five jobs green) and `docs/reviews/phase-1-acceptance.log`.

## (a) Component coverage matrix

| Spec item | Built at | Status |
| --- | --- | --- |
| 1.1 Monorepo scaffold | `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `tsconfig.base.json`, `eslint.config.mjs`, `.prettierrc.json`, `pyproject.toml` (uv workspace), `.pre-commit-config.yaml`, `.github/workflows/ci.yml`; 16 `services/*` + 3 `apps/*` + infra processes, each with an entrypoint and `/health` | complete |
| 1.2 Contracts | `packages/contracts/src/schemas.ts` (15 contracts) -> `scripts/generate.ts` (JSON Schema) -> `scripts/gen-python-contracts.sh` (pydantic); round trip `test/roundtrip.ts` ts1/ts2 + `python/tests/test_roundtrip.py`; 15 fixture sets with valid and invalid cases | complete |
| 1.3 mcp-common | `packages/mcp-common/revenueos_mcp_common/` (server, client, telemetry, receipts, ratelimit, validation); SDK boundary test `tests/connectivity/test_mcp_boundary.py` | complete |
| 1.4 design-system | `packages/design-system/src/` (OKLCH tokens + WCAG contrast, concentric radius, five states, sentence case, slop scanner, DESIGN.md merge) | complete (slop catalog extended in Phase 9 per spec) |
| 1.5 Compose | `infra/compose.yaml`: Postgres, migrate+seed, DuckDB volume, OTel collector, orchestrator, echo-probe, egress-authz, Envoy, sandbox supervisor, api, command-center | complete |
| 1.6 Migrations | `db/migrations/0001_core.sql`, `db/seed/0001_probe.sql`, `db/migrate.sh` | complete |
| 1.7 Audit ledger + CLI | `audit_chain()`, `audit_verify()`, `audit_reject()`; `revenueos audit verify|export` (`packages/pycommon/revenueos_common/cli.py`) | complete |
| 1.8 Observability | `apps/api/src/tracing.ts`, `revenueos_mcp_common.telemetry`, `infra/otel/collector.yaml`; e2e span chain test | complete |
| 1.9 Invariant harness + Q-gates | `tests/invariants/test_inv01..15_*.py`, `tests/invariants/test_harness.py`, `scripts/qgate.py`, `scripts/coverage_gate.py` | complete |
| 1.10 Docs + pins | `README.md`, `docs/PINS.md`, `docs/PROGRESS.md`, `docs/ARCHITECTURE.md`, `docs/POLICY.md`, `docs/PARITY.md`, `docs/LEAD_PIPELINE.md`, `config/sources.yaml`, `vendor/` (37 submodule pointers); secret scanner fixed | complete |

## (b) Spec-to-build diff

- 1.1 "Every service/package dir ... real entrypoint and health endpoint": done for every runtime
  directory. `packages/contracts`, `design-system`, `sdk` and `mcp-common` are libraries; they ship
  tests and builds rather than a health endpoint, which is the meaningful equivalent for a library.
- 1.1 commit hooks use the pre-commit framework (pinned upstream) rather than husky; same checks run in CI.
- 1.2 "every MCP payload and REST endpoint": every payload that exists in Phase 1 has a contract
  (15). Payloads for later phases are added with those phases, in the same file and pipeline.
- 1.5 "sandbox supervisor": Phase 1 ships the supervisor process with a kernel-capability health
  check; sandboxing itself is spec item 2.2.
- 1.5 egress identity: Phase 1 identifies the agent by the `x-revenueos-agent` header; identity
  pinning is spec item 2.3 and is guarded by a strict expected-failure test (INV-11).
- 1.8 implemented as specified, with explicit `traceparent` propagation (api -> orchestrator via
  HTTP header, orchestrator -> MCP via the tool-call envelope).
- 1.10 PINS includes every upstream from the spec and Addenda B/C/D/E/F/H with URL, commit SHA,
  license, stars and date.

## (c) Substitution log

Only D1 exceptions and R03 pins, as permitted:

- D1: 18 named tools without a usable repo or license (table in `docs/PINS.md`), including
  NocoDB (moved to the non-OSI Sustainable Use License; Teable is the official implementation).
- R03 canonical-location pins: `googleads/google-ads-mcp` for the spec's
  `google-marketing-solutions/google_ads_mcp` (not public); `ibelick/ui-skills` as the home of
  baseline-ui.
- Envoy chosen from the spec's "Envoy or Squid".

## (d) Defect list (all fixed)

| # | Defect | Fix |
| --- | --- | --- |
| 1 | Secret-scan CI step failed without a GitHub token | `GITHUB_TOKEN` + full history |
| 2 | Envoy Lua filter errored ("object used outside of proper scope"): header handle stale after the authz callout, so no secret was injected | re-acquire headers after `httpCall` |
| 3 | A Lua runtime error let the request through (fail open) | whole filter under `pcall`; any error returns 403 |
| 4 | Acceptance step piped pytest through `tee`, masking a failing test as success | `shell: bash` + `set -o pipefail` |
| 5 | Contract rejections in mcp-common were not audited (silent failure) | every boundary rejection writes `tool.denied` |
| 6 | Keychain `chmod` on a read-only mount crashed egress-authz, echo-probe and orchestrator at start | verify permissions, never modify an existing directory |
| 7 | A `return` inside `finally` would have swallowed the denial exception | if/else, exception propagates |
| 8 | Rejected transitions left no audit trace (transaction rollback) | `audit_reject()` via dblink, autonomous commit |
| 9 | `dblink_exec` on a SELECT relied on an error path | `DO` block |
| 10 | Rejection audit could deadlock when the transaction already holds the audit lock | detect the held lock; emit WARNING; API-level logging (Phase 5) records it |
| 11 | OTel collector tag did not exist; Envoy on a floating tag | pinned `0.164.0` and `v1.40.2` |
| 12 | Envoy healthcheck used HTTP/1.0, which Envoy rejects | HTTP/1.1 with Host |
| 13 | `revenueos audit verify --db` rejected after the subcommand | option on each subcommand |
| 14 | `node --test dir/` resolved as a module | glob |
| 15 | MCP tool names with dots | protocol charset enforced at registration |
| 16 | Six add-ons failed the 90-day commit window; NocoDB license change | removed / D1, recorded in PINS |

## (e) Invariant audit

| INV | Phase 1 effect | Proof (tests/invariants unless noted) | Result |
| --- | --- | --- | --- |
| 01 | strengthened: DB trigger + FK, rejections audited | `test_inv01_*` (16 tests) | pass |
| 02 | strengthened: append-only receipts; mcp-common writes every receipt | `test_inv02_*`, `tests/unit/test_mcp_common.py` | pass |
| 03 | strengthened: CHECK + insert trigger | `test_inv03_*` | pass |
| 04 | strengthened: CHECK + trigger + contract union | `test_inv04_*`, contracts fixture `llm-pass` | pass |
| 05 | storage half: DO_NOT_FILE cannot complete a task | `test_inv05_*` (reducer: strict xfail until Phase 8) | pass / xfail |
| 06 | strengthened: hash-bound single-use approvals at DB and mcp-common | `test_inv06_*`, mcp-common approval tests | pass |
| 07 | tool-name charset at execution layer | `test_inv07_*` (gateway filter: strict xfail until Phase 4) | pass / xfail |
| 08 | budget CHECK; halted task cannot jump | `test_inv08_*` (router: strict xfail until Phase 13) | pass / xfail |
| 09 | unique profiles, secret refs only | `test_inv09_*` (human-profile guard: strict xfail until Phase 2) | pass / xfail |
| 10 | approved status needs an approver | `test_inv10_*` (activation: strict xfail until Phase 4) | pass / xfail |
| 11 | Envoy deny + inject proven live; decision service fails closed | `test_inv11_*`, `tests/e2e` (sandbox route: strict xfail until Phase 2) | pass / xfail |
| 12 | untouched (sandbox is Phase 2) | `test_inv12_*` strict xfail | xfail |
| 13 | website gate enforced in state machine | `test_inv13_*` | pass |
| 14 | promotion needs positive lift; versions retained | `test_inv14_*` | pass |
| 15 | insight roles read verified views only | `test_inv15_*` | pass |

Strict expected-failures fail CI the moment their control exists and the marker is not removed.

## (f) Security audit

- mcp-common is the only MCP SDK importer (`test_mcp_boundary.py`). Every call goes through
  auth, contract validation, rate limit, span, approval and receipt.
- Egress: denied hosts never get a connection; the decision service fails closed on policy or
  secret errors; the Lua filter fails closed on script errors; injected values are never logged;
  the upstream test proves the agent never sees the secret.
- Approvals: requester cannot approve, hash-bound, expiring, single-use, consumed atomically.
- Secrets: references only (DB checks), keychain refuses world-readable files and directories,
  gitleaks + `tests/threats` on every push; audit payloads redact secret-looking keys.
- Verifier separation and LLM-veto-only enforced in the database.
- No path lets a model act as a boundary in Phase 1: no agent runs yet.

## (g) Integration seams for Phase 2

| Seam | Contract | Validates | Round trip |
| --- | --- | --- | --- |
| Tool calls | `ToolCallEnvelope`, `Receipt` | yes | TS -> Py -> TS |
| Approvals | `ApprovalRequest` | yes | TS -> Py -> TS |
| Egress decisions | `EgressDecision` | yes (egress-authz validates every decision) | TS -> Py -> TS |
| Health | `HealthResponse` | yes (api, sdk) | TS -> Py -> TS |
| Audit verify | `AuditVerifyResult` | yes | TS -> Py -> TS |

## (h) Coverage and observability

Per-unit line coverage (CI, `scripts/coverage_gate.py`): every `services/*` 100% except
orchestrator 91.4%; `services/qc` 100% (90% required); `packages/mcp-common` 89.4%;
`packages/pycommon` 81.9%; `infra/egress` 96.8%; `infra/sandbox-supervisor` 100%;
`mcp/echo-probe` 100%. Every tool call through mcp-common emits a span with `task_id`,
`agent_id`, `tool`, `risk_class` and a receipt (unit-tested and proven end to end).

## (i) Improvement log

- Rejections are audited autonomously (dblink), beyond "trigger rejects".
- Conditional contract rules expressed as unions so they survive into pydantic unchanged.
- Strict expected-failure markers turn future controls into tripwires.
- Q-gate runner never reports PASS without evidence; NOT_APPLICABLE names the phase.
- Envoy filter fails closed on script errors.
- Keychain verifies, never modifies, mounted secret directories.
- Per-unit coverage gate rather than one total.
- Addendum repos pinned as submodule pointers at their exact commits.

## Re-audit against spec v4 (all four spec files) — 2026-11-14

The full v1, v3, v4 and Phase 14A files were re-read against the sealed build. Phase 1 scope gaps
found, fixed and re-run through the gate (Step 5 loop):

| # | Gap | Spec reference | Fix |
| --- | --- | --- | --- |
| R1 | Addendum H scanners were not a standing CI job | D10, Addendum H, 15.2 | `.github/workflows/security.yml`: AutoSecScan every commit, OpenHack every PR, open-kritt on `release/*`, VulnHunter pre-deploy, Strix on generated sites; unrun scan = DO_NOT_FILE and fails |
| R2 | Approval hashes could differ between TS and Python | INV-06 | RFC 8785 canonical JSON in both languages, 8 shared vectors |
| R3 | `packages/*` had no health self-check | layout: mcp-common "health" | `health()` in contracts, design-system, sdk, pycommon, mcp-common |
| R4 | No DuckDB schema | layout: "DuckDB schemas"; 15.5 | `db/duckdb/0001_mirror.sql` with verified-only views |
| R5 | THREATMODEL, RUNBOOK, TASK_CLASSES, LEARNING missing | layout section 6 | created; accurate to the Phase 1 build, extended per phase |
| R6 | README components table had no purpose column | Addendum I | purpose column added; doc index lists all docs |
| R7 | AutoSecScan action pulls a floating `:latest` image | R03 pins | image built from pinned SHA 881d960 |
| R8 | 2 high: containers ran as root | AutoSecScan (trivy DS-0002) | non-root images; compose runs as host owner of secrets |
| R9 | 2 high: expressions interpolated into workflow shell | AutoSecScan (semgrep) | event context and secrets only via env vars |

Result: CI green (node, python Q-gates, contracts ts2, compose acceptance, secret scan) at the
re-seal commit; AutoSecScan PASS (0 high/critical). OpenHack records DO_NOT_FILE on pull requests
until `SECURITY_OPEN_MODEL_BASE_URL` / `_API_KEY` / `_NAME` secrets exist; VulnHunter, Strix and
open-kritt need their secrets before they first apply (pre-deploy, Phase 9 sites, release
branches). This is the D10 rule, not a defect.

