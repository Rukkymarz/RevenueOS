# Threat model

Every threat names the control that stops it, the invariant it rests on, and the test that
proves it. A control marked with a later phase is designed but not yet built; its invariant test
is a strict `xfail` until that phase lands, so it cannot pass by accident. Phase 15.2 adds the
full attack suite (`tests/threats/`). This file is completed and re-checked at Phase 15.

## Trust boundaries

| Boundary | Inside | Outside | Enforced by |
| --- | --- | --- | --- |
| Model → tools | Agent reasoning | Every tool, MCP server, host | mcp-common boundary + per-agent toolset grants (INV-07) |
| Agent → network | Sandbox | Internet, SaaS APIs | Envoy L7 egress + egress-authz (INV-11) |
| Agent → host | COW shadow workspace | Host filesystem, devices | Sandbox supervisor, Bubblewrap (INV-12, Phase 2) |
| Agent → secrets | Secret references only | Secret values | Resolver in egress path; agents never see values |
| Agent → completion | Executor's claim | `COMPLETED` state | DB constraint + independent verifier (INV-01, INV-03, INV-04) |
| Agent → spend | Budget | Model and paid-API cost | Budget ledger halts agent (INV-08) |
| Repo → main | Branches, PRs | `main` | Phase seal + CI + standing security job |

## Threats and controls

| # | Threat | Control | Invariant | Proof | Status |
| --- | --- | --- | --- | --- | --- |
| T01 | Agent claims work it did not do | `COMPLETED` needs a `QC_PASSED` verification record; DB rejects otherwise | INV-01 | `test_inv01_*` | built (P1) |
| T02 | Tool call leaves no trace | Every call writes an immutable receipt; append-only triggers; hash-chained audit log, `revenueos audit verify` | INV-02 | `test_inv02_*`, `tests/db` | built (P1) |
| T03 | Agent grades its own work | Verifier ≠ executor, enforced at insert | INV-03 | `test_inv03_*` | built (P1) |
| T04 | LLM judge rubber-stamps | LLM verifier may veto, never confirm; deterministic oracle required | INV-04 | `test_inv04_*` | built (P1) |
| T05 | Missing telemetry read as success | Unknown resolves to `DO_NOT_FILE`; same rule for scanners that did not run | INV-05, D10 | `test_inv05_*`, `security.yml` | built (P1) |
| T06 | High-risk action without a human | Approval bound to canonical (RFC 8785) args hash, expiring, single-use, requester ≠ approver | INV-06 | `test_inv06_*`, canonical vectors in TS and Python | built (P1); approval UI P2 |
| T07 | Prompt injection makes the model call a tool it should not | Unauthorized tools are hidden and refused at the execution layer, not by the prompt | INV-07 | `test_inv07_*`; injection attack suite P15 | partial (P1 boundary); P4 grants |
| T08 | Runaway loop or budget exhaustion | Per-agent monthly budget; exceeding it sets `BUDGET_HALTED` | INV-08 | `test_inv08_*` | P5 |
| T09 | Agent acts as a human (shared session) | Own email identity and own browser profile per agent; attaching to a human profile is rejected | INV-09 | `test_inv09_*` | P2 |
| T10 | Tool poisoning via malicious MCP server | Servers are `experimental` / `approved` / `production`; only approved or production run in production; install needs approval | INV-10 | `test_inv10_*`; poisoning attack P15 | P4 |
| T11 | Credential exfiltration | Secrets by reference (`keychain://`, `vault://`) injected by the egress proxy; agents never hold values; gitleaks + secret-hygiene test on every push; trace secret-scan | INV-11 | `test_inv11_*`, `tests/threats/test_secret_hygiene.py`, `test_egress_authz` | built (P1 proxy); P2 identity-pinned forwarder |
| T12 | Direct egress bypassing the proxy | Sandbox has no route except the per-session forwarder; Lua filter fails closed (403) on any error | INV-11 | `test_inv11_*`, e2e | built (P1); P2 sandbox |
| T13 | Destructive host operation | COW shadow workspace, no host mounts, destructive-pattern blocklist in every mode | INV-12 | `test_inv12_*` | P2 |
| T14 | Unsafe or sloppy website shipped | D1–D8 design gate before QC; Strix scan on generated sites | INV-13 | `test_inv13_*` | P9 |
| T15 | Learning update regresses behaviour | Canary + holdout causal lift before promotion; every promotion reversible | INV-14 | `test_inv14_*` | P12 |
| T16 | Insight built on unverified data | Insight queries read only `v_verified_*` views over verified evidence bundles | INV-15 | `test_inv15_*`, `test_duckdb_mirror` | built (P1 views) |
| T17 | Audit log tampering | Hash chain under advisory lock; `audit_verify()` names the first broken row; CLI exits 2 | INV-02 | `tests/db`, `test_pycommon` | built (P1) |
| T18 | Vulnerable dependency or code | AutoSecScan every commit, OpenHack every PR, open-kritt on release, VulnHunter pre-deploy; high/critical blocks merge | D10 | `.github/workflows/security.yml` | built (P1) |
| T19 | Data exfiltration through social or marketing content | Outbound content filter; every publish is a receipt and needs approval where high-risk | INV-02, INV-06 | attack suite P15 | P10 |

## Named external risks

- **OpenWA (WhatsApp, Addendum E, Phase 10).** Uses reverse-engineered clients
  (whatsapp-web.js / baileys), not the official Cloud API. Terms-of-service violation and
  permanent number ban are real risks. Controls: secondary channel only, never primary (email is
  primary); `allowedChats` restricted to opted-in leads; every send needs INV-06 approval for the
  first 30 days of a new number; never cold-message from a business-critical number.
- **api-anything (Addendum F, Phases 4 and 6).** Self-healing extractors can silently change the
  shape of their output. Controls: experimental for 14 days before approval; every response is
  validated against a contract before use, and a shape change is a contract violation, not data;
  reads auto-run, any write needs INV-06; all traffic through the Phase 2 proxy.
- **Hosted fallbacks (AgentMail, Browser Use Cloud, imAPI, hosted BYOK models).** Data leaves the
  stack. Used only after the self-hosted path, per the free-tier order in POLICY.md, with
  approval for paid use.
- **Phone numbers (Phase 2).** Need an external carrier account (46elks, Twilio or Google Voice);
  carrier credentials are referenced from the vault, never stored in the repo.
- **LLM-backed scanners.** OpenHack, VulnHunter and Strix need model credentials held as GitHub
  secrets. Until they are set the jobs record `DO_NOT_FILE` and fail; this is intended.
