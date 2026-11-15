# Phase 2 gate review: identity, sandbox, egress, approvals

Evidence: CI on branch `build/phase-2` (all five jobs) and `docs/reviews/phase-2-acceptance.log`
(live compose stack, 24 tests across Phase 1 and Phase 2). Gate verdict: **6 of 7 acceptance
items PASS; 1 DO_NOT_FILE (phone number: needs a carrier account; see (h)). Not sealed.**

## (a) Component coverage matrix

| Spec item | Built at | Status |
| --- | --- | --- |
| 2.1 AgenticMail self-hosted, per-agent email/phone/calendar/browser | `infra/mail/` (AgenticMail built from pinned `af1e0ef`, Stalwart `v0.15.5`), `services/identity/revenueos_identity/{provision,providers,profiles}.py`, `revenueos-identity provision` | email, calendar, browser complete; phone pending a carrier account |
| 2.1 AgentMail / Browser Use Cloud / imAPI | `providers.py`: AgentMail `POST /v0/inboxes`, Browser Use Cloud v2 `/profiles` + `/sessions`, imAPI MCP bridge by URL; `NotConfigured` without vault credentials | complete (hosted; not exercised live without your accounts) |
| 2.1 allmail-mcp | `mcp/allmail` on mcp-common (D1 native): Gmail/iCloud/Zoho/Fastmail presets + any IMAP/SMTP + each agent's own mailbox; send/trash high-risk (human approval) | complete |
| 2.1 isolated browser profiles, provisioning, rotation, INV-09 | `profiles.py` (private 0700 dir, own user-data, fingerprint seed); `rotate-profile`; `identity_guard` + `executor_identity_guard` (migration 0002) | complete |
| 2.2 Sandbox supervisor | `infra/sandbox-supervisor/revenueos_sandbox/` (Bubblewrap from pinned `1fb0aa2`; COW shadow; read-only root and system dirs; no host mounts; uid 1000; CPU/mem/pids/fsize/wall quotas; blocklist in every mode; Seatbelt profile for macOS dev) + `POST /v1/run` | complete |
| 2.3 Identity-pinned egress | per-session Unix socket + relay (`egress.py`, `relay.py`), HMAC session stamp, `egress-authz` verification against `egress_sessions`, per-agent/per-task `egress_rules`, `egress_log` (append-only, audited); Envoy strips the stamp | complete |
| 2.4 Secrets | single resolver (keychain / Infisical), secrets only by reference; `scripts/scan_traces.py` scans every live keychain value + leak patterns across traces and logs in CI | complete |
| 2.5 Approval service | `apps/api/src/{approvals,auth}.ts`: RFC 8785 hash, redacted preview, RBAC (requester/approver/auditor, token digests only); `approval_decide` / `consume_approval` bind hash + task + tool, single use, expiry, separation of duties, logged reasons | complete |
| 2.6 Leads agent | `leads_agent.py` (stdlib, runs in the sandbox), `leads.py` (timeline + audit per step), `infra/test-signup` | complete (OTP and magic link) |

## (b) Spec-to-build diff

- 2.1 "AgenticMail Enterprise ... M365 + Google Workspace": AgenticMail's own relay/domain
  gateway modes support Gmail and Outlook relays; RevenueOS runs it self-hosted on Stalwart and
  reaches Google Workspace / M365 mailboxes through allmail-mcp accounts. No M365/Workspace
  tenant was provisioned (needs your tenant).
- 2.1 "AgentMail-per-browser-session via Browser Use Cloud": adapters create an AgentMail inbox
  and a Browser Use profile + session on their documented endpoints; they run only with your
  API keys in the vault, since both are paid hosted services.
- 2.2 "Seatbelt on mac dev": the profile is generated and unit-tested; it is not executed in CI
  (no macOS runner).
- 2.3 HTTPS: the forwarder ends the agent's TLS with a per-deployment egress CA (the only CA the
  sandbox trusts), so every HTTPS request is read, identity-stamped, allowlisted and logged;
  Envoy originates TLS to the upstream with SNI and validates it against the system CA store.
  Without the egress CA, tunnels are refused. Proven live against example.com.
- 2.5 approvals are bound to task and tool in addition to the args hash (stronger than spec).

## (c) Substitution log

None beyond D1/R03. allmail-mcp has no public repository (named-not-found), so it is a D1
native implementation on mcp-common, as recorded in `config/sources.yaml`.

## (d) Defect list (all fixed)

| # | Defect | Fix |
| --- | --- | --- |
| 1 | `db.rows` read only the last line of `json_agg` output, which spans lines for multi-row results | `jsonb_agg` (one line) |
| 2 | Identity guard fired before the state machine, masking illegal-transition errors | trigger renamed to order after `trg_task_state_guard` |
| 3 | Blocklist dropped the inner command's flags after `sudo`/`timeout` (missed `timeout 5 rm -rf /usr`) | strip only the wrapper's own options |
| 4 | Ubuntu AppArmor stopped Bubblewrap from configuring loopback (`RTM_NEWADDR`) in CI | pinned bwrap build + documented userns sysctl |
| 5 | Supervisor and egress-authz opened the keychain at import | lazy resolver |
| 6 | Sandbox root (bwrap tmpfs) was writable: `/etc/evil` could be created inside the sandbox | `--remount-ro /` |
| 7 | Approval bound only to the args hash: could be spent on another tool with identical args | `consume_approval` binds task and tool |
| 8 | One `secret_bindings` row per host+header blocked per-agent inbox keys | unique on (host, header, secret_ref); ambiguity fails closed |
| 9 | CalDAV/IMAP login used the email; Stalwart expects the principal name | AgenticMail's `stalwartPrincipal` stored as the login |
| 10 | AgenticMail printed a generated inbound secret to its log (found by the trace scan) | secret generated into the keychain and set at start |
| 11 | Trace scanner imported pycommon without its path in CI | path added |
| 12 | Agents had no HTTPS route (tunnels refused) | egress CA + Envoy TLS origination with upstream validation |
| 13 | Phone purchase had no approved path | `request-phone` / `complete-phone` bound to a critical approval |

## (e) Invariant audit

| Invariant | Phase 2 change | Proof |
| --- | --- | --- |
| INV-06 | API + DB enforce hash/task/tool binding, expiry, single use, separation of duties; reasons logged | `test_phase2_guards.py`, `approvals.test.ts`, e2e approval flow |
| INV-09 | human-profile, root and normalization guards; executor must own email + profile | `test_inv09_*` (strict xfail removed), e2e provisioning |
| INV-11 | sandbox has no network; pinned identity; DB rules; deny log | `test_inv11_*` (strict xfail removed), `test_sandbox.py`, `test_egress_authz.py`, e2e |
| INV-12 | COW shadow, read-only root, blocklist in YOLO, approved commit only | `test_inv12_*` (strict xfails removed), e2e |

Strict expected failures left: 5 (Phase 4 x2, Phase 8 x2, Phase 13 x1).

## (f) Security audit

Standing `security` workflow: AutoSecScan PASS (0 high/critical) on every Phase 2 push.
Trace secret scan: every keychain value and leak pattern across OTel traces, all container
logs and the acceptance log; it found and drove fix (d)10. OpenHack DO_NOT_FILE until its
model secrets exist (D10).

## (g) Integration seams for Phase 3

- Runtimes (OmniPilot, NAVA) launch agent processes through `POST /v1/run` or the
  `run_in_sandbox` API; browser runtimes take `profile.json` (user-data dir + fingerprint).
- Risk classification (3.2) will replace the per-tool `risk_class` literals with the shared lib;
  the approval service already accepts `high` and `critical`.
- Phone transport plugs into AgenticMail's phone routes once a carrier is configured.

## (h) Open items

- **Phone number (Acceptance 2, item 1): DO_NOT_FILE.** Needs a carrier account in your name:
  46elks or Twilio (paid number), or a number you control such as Google Voice on the agent's
  own Google account. The purchase path is built and tested: `request-phone` opens a critical
  approval bound to that exact purchase, a human approves it, `complete-phone` buys and records
  it (RUNBOOK). Until then the phone identity is `pending` with its reason.
- LLM-backed scanners (OpenHack, VulnHunter, Strix) need their model secrets (Phase 1 note).

## (i) Improvement log

- Approvals bound to task and tool, not just arguments.
- The agent's own mail API key is injected by the proxy; the agent never holds it.
- Trace scanner reports the service and key of a finding with the value masked.
- Calendar discovery uses standard CalDAV discovery (RFC 6764/4791), not a guessed path.
