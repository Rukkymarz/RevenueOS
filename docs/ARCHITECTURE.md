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
