# ADR-0006: Piyaz live proof is carried to Phase 13 (needs an owner OAuth grant)

- **Status:** PROVISIONAL, 2026-11-17. **Needs the owner's ratification.** R04 allows deferring a named
  component only with an owner exception; this ADR records the gap and asks for it. It follows the
  precedent of ADR-0003/0004 (a blocker that only the owner can clear is carried, never marked passed).
- **Expiry / trigger:** Phase 13 cannot seal without it; an earlier owner OAuth grant moves it forward.

## Context
Piyaz (pinned `e1ed033e`, AGPL-3.0) is a Next.js app with its own Postgres 18 (RLS), bun, and an
OAuth 2.1 MCP endpoint. A client gets a bearer only through an interactive consent by a signed-in
person. No unattended flow exists, so CI cannot obtain a token, and its nine tool names are
unverified (`create_task` / `update_task` in `mirrors.py` are placeholders).

## What is built and proven
- `Piyaz` adapter (OAuth bearer MCP client, token by reference), wired into `sync` and into the
  `task_mirrors` table. A down or unauthorised mirror reports an error and never blocks a task.
- Mission Control is live in compose and proven: one task visible through REST, CLI, MCP and the
  web session (e2e `test_approval_gate_then_tree_then_run_and_mirror`).

## What is NOT proven
Acceptance 5 "tasks appear in BOTH Piyaz and Mission Control": the Piyaz half is **unproven**.

## Needed from the owner
Ratify this deferral, and later run the Piyaz consent once so Phase 13 can verify tool names and
prove the second mirror.
