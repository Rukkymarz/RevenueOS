# Phase 5 review — C06 mission control, PM, decomposition

Gate: see the seal commit for the CI run id. OpenHack stays DO_NOT_FILE (ADR-0003/0004): blocks merge and deploy.

## (a) Component coverage
| Item | Built | Where | Proof |
| --- | --- | --- | --- |
| Spec/Plan/Rules approval gate | yes, in Postgres: human-only approver, frozen once approved, EXECUTING refused until the latest of each is approved | `0005_pm.sql` | invariant + unit + e2e |
| Milestone (4-10 slices) / slice (1-7 tasks) tree, dependency DAG | yes, validator returns all errors; cycles refused by trigger | `plan.py` | unit |
| FIST-Mbt lifecycle verbs | yes, on the existing state machine | `lifecycle.py` | unit + HTTP |
| Verify with Omega + GitReins | managed tasks need both PASS to reach QC_PASSED | `0005_pm.sql`, `lifecycle.py` | unit |
| Budget halt (INV-08) | automatic BUDGET_HALTED, resume needs headroom | `task_pm_guard` | unit |
| Slice runner (plan/execute/verify/advance/reassess) | yes; **scripted** planner/executor (ADR-0005) | `runner.py`, `scripted.py` | unit + e2e |
| Mission Control | live in compose at pin `c1a846fe`; REST, CLI, MCP, web all see the task | `compose.yaml`, `mirrors.py` | e2e |
| llm-tracker filesystem mode | yes | `FileTracker` | unit |
| Agency roster (20 agents) | generated from components.yaml; Command Center `/roster` | `gen_roster.py`, `app.py` | unit + e2e + CI `--check` |
| Piyaz | adapter only | `mirrors.py` | **not proven** (ADR-0006) |
| APM Planner, GSD Pi Auto Mode | moved to Phase 13 (ADR-0005) | | machinery proven with scripted components |

## (b) Defects found and fixed
- Eager `setdefault` default built the tracker store on every call (same class as Phase 4): fixed lazily.
- Mission Control CLI/MCP subprocesses need a HOME; the service user has none: fixed.
- Phase 2 mail e2e failed once under CI load and passed on re-run (stalwart spam-filter fetch error is in the log). Flake, unconfirmed root cause.

## (c) Open items
- Piyaz live proof (ADR-0006, needs owner ratification and an OAuth consent).
- Phase 13 carries APM Planner, GSD Pi Auto Mode (re-evaluate `open-gsd/gsd-pi`), browser-use, magentic-ui, openclaw-heartbeat.
