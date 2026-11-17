# Phase 4 review — tool discovery and governance (C04)

Gate evidence: CI run **44035789107** on `25ec047` (all five jobs green: node, python Q-gates incl.
coverage ≥ 80 % per unit, contracts ts2, gitleaks, compose acceptance 45/45 incl. six Phase 4 live
tests). Security run **44035789137**: AutoSecScan, VulnHunter, Strix, open-kritt green; OpenHack
**DO_NOT_FILE** (provider cap; waived as a seal condition by ADR-0004, still blocks merge/deploy).

## (a) Component coverage
| Item | Built | Where | Proof |
| --- | --- | --- | --- |
| 4.1 Forage (search / install / learn) | yes, D1: in-repo on FastMCP (no public Forage repo) | `services/discovery`, `mcp/forage` | e2e `test_gap_to_search_to_install_to_use…` |
| 4.2 agent-discover registry of record | yes, pinned `c8a48bc7` built in the image, daemon on loopback; metrics, probes, activate/deactivate | `agent_discover.py`, `registry.py`, Dockerfile | e2e metrics + failed-probe test |
| 4.3 mcptoon + MCPfinder | yes, pinned; MCPfinder registered approved by bootstrap | `sources.py`, `app.PINNED` | unit + e2e |
| 4.4 curated sources | Official Registry, punkpeye 2026, wong2, best-of-mcp-servers ingested at pinned SHAs | `sources.CURATED` | `test_discovery_sources` |
| 4.5 selection policy | 7 checks; unknown is never a pass | `policy.py` | 25 unit tests |
| 4.6 INV-10 | database function + triggers; re-checked at NAVA step 3, at activation and on every call | `0004_discovery.sql`, `nava.py` | invariant tests + e2e |
| 4.7 sandbox + own secret scope | Bubblewrap + strace wrapper, per-server identity, egress rules, secrets by reference | `sandbox_exec.py`, `forage.py` | e2e hostile server |
| 4.8 api-anything | registered experimental, 14-day observation window enforced by trigger | `app.PINNED` | e2e |

## (b) Acceptance 4 (live stack)
Capability gap → search → install → usable same session → `forage_learn` rule file; INV-10 blocks a
production activation and logs it; hostile server blocked and logged on network, secrets and
sandbox escape, then quarantined; per-tool metrics; failed probe marks unhealthy and removes it;
api-anything experimental with the window. All pass in CI 44035789107.

## (c) Defects found and fixed this phase
- `setdefault` built a keychain store on every call (eager default argument): fixed.
- `DatabaseError.message` is a property, called as a method: 500 instead of a typed 409. Fixed, tested.
- Observation window must be fixed at install for every role. Fixed in the trigger.
- Policy test strings tripped gitleaks; built at runtime now (branch rewritten before merge).

## (d) Substitution log
Forage: D1 (fastmcp add-on is the implementation; re-evaluate each cycle). No other substitutions.

## (e) Open items
- OpenHack DO_NOT_FILE (ADR-0003/0004). The wong2 and best-of lists are index-only (MIT; CC-BY-SA-4.0).
- The pinned `mcpfinder` and `api-anything` run only inside the sandbox wrapper; their live tool
  use is not exercised by acceptance (api-anything is deliberately not enabled until Phase 6).
