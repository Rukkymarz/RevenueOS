# Architecture

RevenueOS is a self-hosted platform where AI agents research, plan, build, sell and verify,
with every external action receipted, approved where risky, and verified by someone other
than the agent that did it. Postgres is the system of record; every rule that matters is
enforced in the database as well as in code.

## The synchronized loop

```
ingress -> research (premise bundle) -> strategy -> decomposition (Spec/Plan/Rules)
  -> approval -> execution (sandboxed, receipted) -> website production (D1-D8)
  -> outreach / social / marketing (own identity) -> verification (GitReins, veripipe, EvalForge)
  -> completion with receipt -> learning (Myelinate, Tares, RL corpus) -> insight
```

The same loop is written as explicit, typed hops in `config/components.yaml` (`flows`), and CI
proves the path is unbroken.

## Component graph

Six buses connect every component; `config/components.yaml` lists each component, its status
and the buses it is on.

| Bus | Implementation | Carries (contract) |
| --- | --- | --- |
| MCP gateway | FastMCP via `packages/mcp-common` (Forage/agent-discover in Phase 4) | `ToolCallEnvelope`, `Receipt` |
| A2A bus | EREBOTS split on the official A2A protocol (Phase 13) | `A2AMessage` |
| Task API | `apps/api` (NestJS) | `TaskCommand`, `ProbeRequest/Response`, `HealthResponse` |
| Event store | Postgres (`db/migrations`) | receipts, verifications, audit |
| Timeline | Tares on DuckDB (Phase 11) | `TimelineEvent` |
| Telemetry | OpenTelemetry collector | spans with `task_id`, `agent_id`, `tool`, `risk_class` |

## Built in Phase 1

```
 apps/api (NestJS) --traceparent--> services/orchestrator --MCP + traceparent--> mcp/echo-probe
      |                                    |                                        |
      +------------ OTLP spans ------------+--------------> otel-collector <--------+
                                                                                    |
 agents --(x-revenueos-agent)--> Envoy egress --Lua check--> egress-authz --audit-->+--> Postgres
                                   | allowed + secret injected                       (hash-chained
                                   v                                                  audit ledger)
                              upstream host
```

| Path | What it is |
| --- | --- |
| `db/migrations/0001_core.sql` | Every table in the data model; state machine, INV-01/02/03/04 triggers, approvals, hash-chained audit, rejection audit via dblink |
| `packages/contracts` | zod schemas -> JSON Schema -> pydantic; round trip TS -> Py -> TS in CI |
| `packages/mcp-common` | The only MCP SDK importer: bearer auth, envelope validation, rate limit, span, approval consumption, receipt |
| `packages/design-system` | OKLCH tokens with WCAG contrast checks, concentric radius, five UI states, sentence case, slop scanner, DESIGN.md merge |
| `packages/pycommon` | Canonical hashing, Postgres access, secret resolver, service skeleton, `revenueos` CLI |
| `packages/sdk` | Typed, contract-validated client for the API |
| `apps/api`, `apps/command-center`, `apps/admin` | NestJS API; Next.js 16 shells |
| `services/*` (16) | Entrypoints with `/health` and `/v1/info`; capabilities land in their phases |
| `infra/compose.yaml` | Postgres, migrations + seeds, OTel collector, orchestrator, echo-probe, Envoy + egress-authz, sandbox supervisor, api, command-center |

Phases and their seals are recorded in `docs/PROGRESS.md`.

## Built in Phase 2

```
 agent process (bwrap: COW shadow ws, ro /, rlimits, blocklist)
   └── only route out: per-session UDS ─> supervisor forwarder (HMAC identity stamp, MITM CA)
         └─> Envoy ─> egress-authz (rules + secret bindings in Postgres) ─> upstream TLS
 identities: AgenticMail on Stalwart (email+calendar), browser profiles, phone deferred
 approvals: hash-bound, single-use, separation of duties (apps/api RBAC)
```

## Built in Phase 3 (C02 runtime-omni, C03 runtime-os)

```
                 ┌────────────── 15 NAVA MCP servers (mcp/nava-suite, one per domain) ──────────────┐
 agent ──bearer──> services/runtime-os  (NAVA kernel: 12-step managed syscall, docs/NAVA.md)
                     1 validate .. 5 policy (shared risk lib) .. 6 approval .. 8 locks
                     9 snapshot ──> 10 execute ──────────────┬─> sandbox.run (bwrap, quotas)
                     11 verify ──> 12 receipt + span + audit └─> omni.* ──> services/runtime-omni
                                                                              (41 OmniPilot tools on
 plans (durable: pause/resume/retry) ── static agents (7, DB-fenced)           Xvfb desktop, x11vnc)
 A2A bus + 4-tier memory in Postgres ── JIT subagents (TTL, inherited fences)
 OpenMuse: persistent Chromium per agent profile ── human takeover console ── 30 s terminal
           signup -> OTP -> PDF -> nib fill -> deterministic review -> reply draft
```

| Path | What it is |
| --- | --- |
| `db/migrations/0003_nava.sql` | syscalls + ordered step records, N01..N21 triggers, locks, A2A bus, 4-tier memory, JIT subagents, durable plans, agent tokens |
| `services/runtime-os` | the NAVA gateway, kernel (bus/memory/subagents/plans), 7 static agents, HTTP surface, crash reaper |
| `services/runtime-omni` | OmniPilot's 41 tools by remote control; OpenMuse browser, takeover console, acceptance pipeline |
| `packages/risk` | shared risk classification (3.2): single-sourced for OmniPilot, NAVA and approvals |
| `mcp/nava-suite` | the 15 specialized MCP servers, each a facade over governed syscalls |
| `docs/NAVA.md` | the 12 steps and the 21 invariants, each with its enforcing object and test |
