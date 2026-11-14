# evals

Behavior evaluation assets, filled in Phase 8 (spec 8.1-8.3):

| Path | Contents | Runner |
| --- | --- | --- |
| `evals/evalforge/*.yaml` | EvalForge suites: trajectories, tool-call sequences, deterministic graders, baselines | EvalForge (Q3) |
| `evals/veripipe/` | veripipe oracles for web/HTTP deliverables, graded L1-L4 | veripipe (Q5) |
| `evals/gitreins/` | GitReins task definitions and resolution-gate seed files | GitReins (Q4) |

Until Phase 8 the Q-gate runner (`scripts/qgate.py`) reports Q3-Q5 as `NOT_APPLICABLE`,
never `PASS`.
