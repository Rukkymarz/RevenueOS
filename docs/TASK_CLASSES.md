# Task classes

A task class fixes three things: the risk class of its tool calls, the deterministic oracle that
can confirm it (INV-04), and what evidence its bundle must carry (INV-15). A task with no oracle
cannot reach `COMPLETED`; an LLM verifier may only veto (INV-04).

## Risk classes (Phase 1, enforced in mcp-common and the database)

| Risk class | Examples | Approval | Rate limit |
| --- | --- | --- | --- |
| low | read, search, fetch public page, draft | none | token bucket per tool |
| medium | write to own workspace, create draft record | none; receipt required | token bucket per tool |
| high | send email, publish, write to external system, install MCP server | hash-bound single-use human approval (INV-06) | token bucket + approval |
| critical | payment, DNS, deploy, delete external data, change `main` | hash-bound approval; never auto-approved | token bucket + approval |

Every call, at any risk class, writes a receipt (INV-02). A denied call writes an audit event
(`tool.denied`).

## Task classes

| Class | Lands | Oracle that can confirm | Evidence bundle |
| --- | --- | --- | --- |
| probe | P1 | echo round trip, receipt present, trace present | receipt, span |
| identity.provision | P2 | inbox receives test message; profile isolated; OTP signup completes | account record, message id, profile id |
| runtime.action | P3 | post-condition check in sandbox (file hash, page state) | action log, screenshot, diff |
| tool.install | P4 | contract test against the server; status `approved` | manifest, test result, approval |
| project.decompose | P5 | every subtask has owner, oracle and budget | task tree |
| research | P6 | sources fetched and cited; claims traceable to evidence | fetched pages, citations |
| outreach.send | P6/P10 | message id from provider; approval matched | approval, provider receipt |
| eval | P8 | EvalForge / veripipe oracle | eval run record |
| site.build | P9 | D1–D8 design gate + Strix scan | build artifact, gate report, scan verdict |
| social.publish / marketing.send | P10 | publish id and analytics pull recorded | receipt, analytics evidence |
| lead.enrich | P10 | Addendum C L0–L9 per-step validators; INVALID does not advance | provider hit log, row snapshot |
| insight.query | P11 | query reads only `v_verified_*` views | query, result, bundle ids |
| skill.promote | P12 | canary + holdout causal lift, non-regression | experiment record, rollback pointer |

Classes land in the phase shown; each adds its oracle to `services/qc` and its row here.
