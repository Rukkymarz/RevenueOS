# NAVA — the agent operating system kernel (C03)

NAVA treats every tool call an agent makes as a **managed system call**. There is one gate
(`services/runtime-os`, `Gateway.syscall`), it always runs the same twelve steps in the same
order, and the database — not the model, not the service — is the enforcement boundary
(INV-07): the step order, the execution preconditions and the terminal states are all
triggers and constraints in `db/migrations/0003_nava.sql`, so a buggy or hostile caller
cannot skip a step and still record a call.

## The 12-step managed syscall

| # | Step | What happens | Fails closed on |
|---|------|--------------|-----------------|
| 1 | validate | tool exists; arguments match its schema | unknown tool, bad args |
| 2 | authenticate | bearer token → agent (digests in `nava_tokens`); agent is on this task | wrong/expired token, foreign task |
| 3 | authorize | no capability deny matches (subagents inherit the parent's denies) | `nava_denies` hit |
| 4 | classify | shared risk library (spec 3.2), declared risk as a floor | — (recorded) |
| 5 | policy | `decide(risk, mode)`: critical blocks in **every** mode; high always prompts | critical |
| 6 | approval | consume the hash-bound approval (args + task + tool); delegated tools verify here, the executor consumes | missing/foreign approval |
| 7 | quota | concurrency, rate per minute, budget halt | quota exceeded |
| 8 | lock | exclusive locks on the call's resources, in sorted order | lock timeout |
| 9 | snapshot | content-hashed copy of every workspace the call can change | snapshot failure |
| 10 | execute | the tool runs (`sandbox.run` inside bubblewrap with rlimits + wall clock) | tool error, timeout, kill |
| 11 | verify | tool verdict + caller postconditions against the real post-state | postcondition failure |
| 12 | record | receipt in `tool_calls`, audit row, OTel span, locks released | — (always runs) |

A failure at any step jumps to 12. A mutating call that failed after its snapshot is restored
from it and ends `rolled_back`; the database checks the restored content hash equals the
snapshot hash.

## The 21 kernel invariants

Each invariant names its enforcing object and its test in `tests/nava/`.

| ID | Invariant | Enforced by | Test |
|----|-----------|-------------|------|
| N01 | Steps are recorded 1→12, in order, under their canonical names; after a failed step only step 12 may follow | `syscall_step_guard` trigger | `test_n01_step_order` |
| N02 | A syscall ends exactly once; nothing is recorded after it ends | `syscall_status_guard`, step guard | `test_n02_single_terminal_state` |
| N03 | Only an active agent can open a syscall (paused, budget-halted or killed agents cannot) | `syscall_caller_guard` trigger | `test_n03_only_active_agents` |
| N04 | A capability deny blocks the tool, and a subagent inherits every deny of its parent chain | `nava_allowed()` + gateway step 3 | `test_n04_capability_denies` |
| N05 | Nothing executes without a prior risk classification | step-10 guard in `syscall_step_guard` | `test_n05_no_execute_without_classification` |
| N06 | Critical risk never executes — in ask, auto **and** yolo mode | CHECK on `syscalls`, step-10 guard, `decide()` | `test_n06_critical_never_executes` |
| N07 | High risk (and medium in ask mode) executes only with a consumed approval bound to these args, this task and this tool | step-10 guard | `test_n07_approval_bound_execution` |
| N08 | Per-agent quotas hold: concurrent calls, calls per minute, budget halt | `nava_quota_check()` + N03 | `test_n08_quotas` |
| N09 | An approval is consumed at most once; reuse is refused and audited | `consume_approval()` (0002) | `test_n09_single_use_approvals` |
| N10 | A resource has at most one lock holder at a time | `nava_locks` primary key | `test_n10_exclusive_locks` |
| N11 | No lock outlives its syscall: terminal state releases every lock | `syscall_audit` trigger | `test_n11_locks_released` |
| N12 | A syscall acquires its locks in sorted resource order (no deadlocks by ordering) | `nava_lock_order_guard` trigger | `test_n12_lock_ordering` |
| N13 | A mutating call snapshots its workspaces before executing | `syscall_status_guard` | `test_n13_snapshot_before_mutation` |
| N14 | A rollback restores exactly the snapshotted state: `restored_hash = snapshot_hash` | CHECK on `syscalls` | `test_n14_rollback_restores_snapshot` |
| N15 | A commit requires all 12 steps passed (verify included) | `syscall_status_guard` | `test_n15_commit_needs_all_steps` |
| N16 | A commit carries its own receipt: same agent, task and args hash in `tool_calls` | `syscall_status_guard` | `test_n16_commit_needs_receipt` |
| N17 | A call orphaned by a crash is reaped: rolled back, closed, locks freed — never left `running` | `Gateway.reap()` | `test_n17_crash_reap` |
| N18 | Only an active agent can send on the A2A bus, and messages are immutable (append-only) | `a2a_send()` + `forbid_mutation` | `test_n18_bus_sender_and_immutability` |
| N19 | An agent reads only its own inbox | `a2a_receive()` + API | `test_n19_inbox_isolation` |
| N20 | Memory has exactly four tiers; working memory is task-scoped and cleared when the task ends; semantic/procedural entries carry provenance | `nava_memory` CHECKs + task trigger | `test_n20_memory_tiers` |
| N21 | A JIT subagent is scoped and mortal: inherits its parent's denies, cannot spawn subagents, expires and is then killed | `nava_subagents`, `Kernel.spawn`, `nava_expire_subagents()` | `test_n21_jit_subagents` |

## The rest of the kernel

- **A2A bus** — `a2a_messages` in Postgres: ordered per channel (`seq`), capped bodies,
  append-only, sender authenticated by the gateway's token, inbox scoped per recipient.
- **Four-tier memory** — `nava_memory`: `working` (per task, auto-cleared), `episodic`
  (what happened), `semantic` (facts, with provenance), `procedural` (how-to, with
  provenance). A subagent reads its parent's semantic and procedural tiers, nothing else.
- **JIT subagents** — `Kernel.spawn` synthesizes a child agent for one objective with a TTL
  and extra denies; its token expires with it; `nava_expire_subagents()` kills it after.
- **Durable plans (OpenMuse)** — `plans` / `plan_steps`: each step is a syscall; pause /
  resume / retry survive restarts because the next pending step is always in the database.

## Operations

- Crash recovery: run `Gateway.reap()` (idempotent) at service start and on a timer; it closes
  syscalls stuck `running`, restores their snapshots and frees their locks.
- Subagent hygiene: `SELECT nava_expire_subagents();` on the same timer.
- Approvals: `SELECT approval_expire_sweep();` (Phase 2) covers NAVA approvals too.
