# ADR-0001: NAVA is implemented natively; OpenHands becomes a fallback candidate for the agent loop

- **Status:** Accepted (2026-11-15)
- **Decided by:** Claude (build agent), under the owner's written instruction of 2026-11-15 to
  decide this fork and record it as an ADR. The owner can supersede it with a later ADR.
- **Component:** C03 `nava` (`config/components.yaml`, `config/sources.yaml`)
- **Supersedes:** the open item "NAVA is named-not-found with documented add-on OpenHands" in
  `docs/reviews/phase-3-review.md` (top table, first row).

## Context

The spec names NAVA as the C03 agent operating system. NAVA has no public repository, so under
D1 ("where a named tool has no usable public repo or license, the documented functional
equivalent is the official implementation") the Phase 1 pins recorded OpenHands
(`OpenHands/OpenHands` @ `830c0459e2f6056ab81e020c22970e782ae1be75`) as NAVA's official
implementation. Phase 3 then built NAVA's spec sentences natively: the 12-step managed syscall,
the A2A bus, four-tier memory, 15 MCP servers, 21 invariants, 7 static agents and JIT
subagents (`services/runtime-os`, `db/migrations/0003_nava.sql`, `mcp/nava-suite`,
`docs/NAVA.md`, `tests/nava`). That left a fork: accept native NAVA as the implementation, or
integrate OpenHands. It has blocked the Phase 3 seal, and under R07 Phase 4 cannot start until
Phase 3 is sealed.

### The evidence

**1. The pinned add-on is no longer an agent.** At the pinned commit, `OpenHands/OpenHands` is
"Agent Canvas". Its own `AGENTS.md` says: "This repository is the OpenHands Agent Canvas
React/TypeScript frontend" (`@openhands/agent-canvas` 1.40.0, 56 runtime and 50 dev npm
dependencies). Its ownership table places "Python SDK, Agent Server, agents/tools" in a
different repository, `OpenHands/software-agent-sdk`, which RevenueOS has never pinned
(MIT; HEAD `1d4c0249668c86d4327af51af1659330f8f0dbfc` seen on 2026-11-15). So D1's premise, that
the pinned add-on is NAVA's functional equivalent, no longer holds for the pin as recorded. D1
also says the choice is "re-evaluated each build cycle". This ADR is that re-evaluation.

**2. Even the real OpenHands agent does not provide what NAVA specifies.** In
`software-agent-sdk`, the agent is an LLM loop (`openhands-sdk/openhands/sdk/agent/base.py`:
`llm: LLM = Field(..., description="LLM configuration for the agent.")`, required). Its
`LocalWorkspace` "operates on the host filesystem" (`openhands-sdk/openhands/sdk/workspace/local.py`),
and its `DockerWorkspace` runs a container agent server (`ghcr.io/openhands/agent-server`, pinned
by Canvas at 1.62.0 in `config/defaults.json`). Neither has a 12-step gate, database-enforced
step order, hash-bound approvals at the execute step, snapshots with exact-hash rollback, or
any of the 21 invariants. OpenHands could be a client of a NAVA gateway. It cannot be the
gateway.

**3. Cost of each option:**

| | NAVA-native | OpenHands |
| --- | --- | --- |
| New dependency surface | None. Built and green: CI run `43786346724` (Validate RevenueOS, `31d9000`) | Re-pin to `software-agent-sdk` (not the current pin), plus the agent-server image, plus Agent Canvas (a second control UI next to the Command Center), plus a custom Workspace so its actions go through `Gateway.syscall` |
| Model key | None. Static agents are deterministic plan compilers; the database is the enforcement boundary, not the model (INV-07, `docs/NAVA.md`) | Required. The `llm` field above is mandatory, so the option cannot run or be accepted until a model provider exists. The component map puts that provider in Phase 13 (`model-router`, defaults `ollama`/`vllm`) |
| Phase 4 integration work | As already designed: Forage-installed MCP servers register in the gateway tool table and run through `/v1/syscalls`, with INV-10 checked at step 3 (phase-3 review, section g) | Phase 4 would need a second activation target (OpenHands' own MCP/tool configuration), which would be a tool path outside the gateway. INV-10 and the receipts would have to be rebuilt there or bypassed |

**4. What the existing build already assumes.** Every C02/C03 piece finished this phase
assumes the native gateway is the kernel:
- aegis-os: its `run`/`diff --json` output feeds NAVA's own `commit()`, and its own
  commit/promote is never called (`infra/sandbox-supervisor/revenueos_sandbox/aegis.py`; N13/N14,
  INV-06). This was proven in CI run `43783782183`.
- playwright-mcp: reached only as the `browser.call` ToolSpec in the gateway's tool table
  (`services/runtime-os/revenueos_runtime_os/tools.py`).
- ambient-watchers: reads NAVA's own tables (`nava_subagents`, `approvals`, `syscalls`) and
  alerts over NAVA's A2A bus (`services/ambient-watchers/revenueos_ambient_watchers/watchers.py`).
- The original pin already said so. `config/sources.yaml` → `nava.reason` reads: "OpenHands
  provides coding, terminal and browser agents; the 12-step mutation gateway is built in-repo."

Making OpenHands the kernel would orphan all four. Adding OpenHands later as an agent-loop
client changes none of them.

**5. A model key is a deferral, not a third option.** A key would make the OpenHands
option runnable. It would not choose between the options. The same fork would come back in
Phase 4 as "which tool path does Forage activate into?", and by then more code would depend on
the answer. A key alone does not settle anything.

## Decision

**NAVA-native is the implementation of record for C03 `nava`.** The in-repo kernel
(`services/runtime-os` + `0003_nava.sql` + `mcp/nava-suite`) is NAVA's official implementation.
This follows the existing precedent for D1 components built in-repo: `llm-tracker` and
`dataforge` keep status `named-not-found`, their D1 label and `license: in-repo`.

**OpenHands is demoted, not removed,** following D1's own rule that "the add-on becomes the
fallback". It stays pinned in `config/sources.yaml` as a fallback candidate for one layer only:
the model-driven agent loop that sits on top of the gateway. It is never the gateway.

### Reversal triggers

This decision is reversible, and an owner ADR can supersede it at any time. Any one of these
reopens it:

1. **A public NAVA repository appears.** D1 re-evaluation runs each build cycle. If it finds a
   usable NAVA repo, that repo becomes the primary, and this ADR is superseded for whatever the
   repo covers.
2. **The model router lands (Phase 13), or a model provider is approved earlier.** At that point,
   evaluate `OpenHands/software-agent-sdk` (pinned at that time, star gate re-checked) as the
   agent loop. It is admissible only as a client of the gateway, meaning every host effect goes
   through `Gateway.syscall` through a RevenueOS Workspace adapter. If it cannot run that way, it
   is rejected and the native static/JIT agents stay.
3. **Native NAVA fails an invariant in production that a pinned upstream would have prevented.**
   Record the incident and re-run this comparison.

Until one of these fires, nobody needs to revisit this decision.

## Consequences

- **The NAVA fork is closed as a Phase 3 seal blocker.** This was the first row of the phase-3
  review's top table.
- **This ADR alone does not let Phase 4 start.** R07 requires Phase 3 to be sealed. Two owner
  blockers are still open, and neither is a build gap:
  1. **A model provider for browser-use, magentic-ui and openclaw-heartbeat.** All three need
     an LLM to do anything, and each needs a provider choice that decides its client code:
     browser-use's `Agent(llm=...)` resolves a provider model and raises before any browser
     starts if the key is missing, and with `llm=None` it "runs (and bills) bu-fast"
     (`browser_use/agent/service.py` @ `e717df18`); magentic-ui needs two OpenAI-compatible model
     clients (`config.yaml.example` @ `d3c9d13c`); openclaw-heartbeat's automations are
     gateway-only (`src/cli/cron-cli/register.ts`: `"Manage automations (via Gateway)"` @
     `c787d0fa`).
  2. **Model access for the OpenHack scan.** PR #3's security run `43692377257` recorded
     `openhack: DO_NOT_FILE - scan made no model calls (0 tokens)`. D10 says that is never a
     PASS.
- **Phase 4 has its design target now, whenever it starts.** Discovered and installed MCP
  servers activate behind `Gateway.syscall` (authorize at step 3 with INV-10, classify, policy,
  receipt). There will be no second tool path.
- **Pins:** `nava` keeps `named-not-found` and its D1 label. `components.yaml` `nava.license`
  becomes `in-repo`. The OpenHands extension stays pinned, with its role restated as a
  fallback candidate for the agent loop. The note records that the pinned commit is Agent
  Canvas and that the agent itself lives in `software-agent-sdk`, to be pinned only if trigger
  2 fires.

## Evidence

| What | Where |
| --- | --- |
| Native NAVA built and green at the decision commit's parent | CI run `43786346724` (Validate RevenueOS, `31d9000`, success) |
| aegis-os engine feeding NAVA `commit()` | CI run `43783782183` |
| MCP SDK boundary (only mcp-common imports the SDK) enforced and passing | caught in CI run `43784872498` (Q1/Q2 FAIL), fixed in `dbb4b7e`, green in `43786346724` |
| OpenHack DO_NOT_FILE | security run `43692377257` on PR #3 (`606d00a`) |
| OpenHands pin is the Agent Canvas frontend | `OpenHands/OpenHands` @ `830c0459`: `AGENTS.md`, `package.json`, `config/defaults.json` |
| OpenHands agent requires an LLM, and its local workspace writes the host directly | `OpenHands/software-agent-sdk` @ `1d4c0249`: `openhands-sdk/openhands/sdk/agent/base.py`, `.../workspace/local.py` |
| Gateway design and invariants | `docs/NAVA.md`, `db/migrations/0003_nava.sql`, `tests/nava/` |
| Phase 4 seam | `docs/reviews/phase-3-review.md` section (g) |
