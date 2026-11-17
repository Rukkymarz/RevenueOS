# ADR-0005: APM Planner and GSD Pi Auto Mode move to Phase 13 (need a model key)

- **Status:** Accepted, 2026-11-17. **Owner decision:** the owner chose option "A" on 2026-11-17.
- **Expiry / trigger:** Phase 13 cannot seal without both running, and an earlier model key
  from the owner moves them forward. Same shape as ADR-0002.

## Context

Two Phase 5 behaviours are model-driven: the agentic-pm **Planner** (discovery conversation that
writes Spec/Plan/Rules) and **GSD Pi Auto Mode** (a model plans, executes and reassesses a slice).
Neither can run, or be proven, without a model key, and we do not fabricate one. The pinned
`gsd-build/gsd-2` is also archived; its successor is `open-gsd/gsd-pi` (D1 re-evaluation, taken
in Phase 13 with the key).

## Decision

- **Built now, with no model:** the whole machinery both rely on: Spec/Plan/Rules artifacts and
  the DB approval gate, the milestone (4-10 slices) / slice (1-7 tasks) / task shape validator,
  the dependency DAG, the FIST-Mbt lifecycle verbs on the state machine, budget halt, the
  slice runner loop (plan, execute, verify, advance, reassess) driven by a pluggable planner
  and executor, Mission Control and Piyaz sync, the llm-tracker filesystem mode, the Agency roster.
- **Phase 13:** the model-backed Planner and Auto Mode planner/executor plug into those
  interfaces; agentic-pm and gsd-pi stay pinned and in the component map.
- Acceptance 5 lines "agentic-pm decomposition runs" and "GSD Pi Auto Mode runs a slice end to
  end" are proven here with a deterministic scripted planner/executor, and labelled as such.
  They are **not** proof of the model-backed behaviour.
