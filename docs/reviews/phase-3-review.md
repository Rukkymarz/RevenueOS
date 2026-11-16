# Phase 3 review — computer-use runtime + agent OS (C02, C03)

Gate protocol Step 3. Phase spec: v4 §3.1–3.6, Acceptance 3.

**Gate status: NOT SEALED. Gate re-run 2026-11-15 on `78d960e`: Steps 1–2 green, Step 3 red.**
Gate runs: CI 43791376552 (Validate RevenueOS) had every job green, with live acceptance 39/39
across Phases 1–3 (raw output: `phase-3-acceptance.log`), Q1/Q2/Q6/Q7 PASS (Q3–Q5 not
applicable yet), the trace secret scan, and contracts ts1/ts2. Security 43791376467 green, with
AutoSecScan scan success; OpenHack and VulnHunter are skipped on push by design. The review
(Step 3) still fails on the owner blocker below, so the phase is not sealed.
Section (a) shows every built row `complete`. The NAVA fork is decided by
[ADR-0001](../adr/ADR-0001-nava-vs-openhands.md). One owner blocker remains (the model-driven C02 components were re-phased to Phase 13 by the owner, [ADR-0002](../adr/ADR-0002-rephase-model-driven-c02-components.md)). It is not a build
gap, but it still fails the gate under the protocol. It is listed first so
nobody reads the rest as a seal.

| Open item | Why it blocks | What closes it |
| --- | --- | --- |
| **OpenHack** security scan records DO_NOT_FILE. | D10: a scan that did not run is never PASS. The owner set the `SECURITY_OPEN_MODEL_*` secrets on 2026-11-15 and the scan now reaches the provider (OpenRouter), but the re-run of PR #3's security run 43692377257 (attempt 2) was refused: `Error code: 402 - Insufficient credits. This account never purchased credits` → `DO_NOT_FILE - scan did not complete (status 'failed')`. | Owner: set `SECURITY_OPEN_MODEL_NAME` to a model the account can use for free (on OpenRouter these end in `:free`), or add credits, or switch the three secrets to another provider. |

**Closed 2026-11-15:** *nava* (named-not-found; documented add-on OpenHands). Decided by
[ADR-0001](../adr/ADR-0001-nava-vs-openhands.md), status Accepted: the in-repo kernel is NAVA's
implementation of record, and OpenHands is demoted to a fallback candidate for the model-driven
agent loop, admissible only as a client of `Gateway.syscall`. The ADR lists three reversal
triggers. Main evidence: the pinned `OpenHands/OpenHands@830c0459` is the Agent Canvas
React/TypeScript frontend, not an agent; the OpenHands agent lives in the unpinned
`software-agent-sdk`, requires an LLM, and its `LocalWorkspace` operates on the host filesystem
directly.

**Closed since the table above was first written:** aegis-os is now built from the pinned
commit (CI: `scripts/build-aegis-os.sh`, `infra/docker/python.Dockerfile`'s `aegis` stage) and
run as an opt-in `engine="aegis"` option on `sandbox.run` (`infra/sandbox-supervisor/
revenueos_sandbox/aegis.py`, `supervisor.py`) — the Bubblewrap path stays the default, aegis-os
is a real, additional, selectable engine, not a doc-only pin (CI run 43783782183, green).
playwright-mcp is built from its pinned commit (`infra/docker/playwright-mcp.Dockerfile`) and
runs as its own compose service, callable through `runtime-os`'s `browser.call` tool
(`services/runtime-os/revenueos_runtime_os/tools.py`) over its own HTTP MCP transport.
ambient-watchers is a real scanner (`services/ambient-watchers/`) wired into compose with its
own `/health` + `/v1/info` surface.

Everything below describes what *is* built and proven.

## (a) Component coverage matrix

| Item | Component | Paths | Status |
| --- | --- | --- | --- |
| 3.1 OmniPilot runtime, real desktop, 41 tools, CLI + web UI + REST | C02 | `services/runtime-omni/` (REST), OmniPilot pinned `2e3a6bd` (its own CLI + local web UI ship in the pinned package), `infra/docker/runtime-omni-entrypoint.sh` (Xvfb/fluxbox/x11vnc/noVNC), `infra/compose.yaml` runtime-omni | complete |
| 3.1 built-in MCP client behind the same permission system | C02 | OmniPilot's MCP client is retained in the pinned package; every RevenueOS-side MCP surface goes through `packages/mcp-common` | complete |
| 3.2 shared risk library, single-sourced | C02/C03 | `packages/risk/` — used by runtime-omni (`runtime.py`), NAVA (`nava.py` step 4), approval flows; critical blocked in every mode incl. YOLO | complete |
| 3.3 NAVA 12-step mutation gateway | C03 | `services/runtime-os/revenueos_runtime_os/nava.py`, `db/migrations/0003_nava.sql` (order + precondition triggers) | complete |
| 3.3 inter-agent message bus | C03 | `a2a_messages` + `a2a_send/receive` (0003), `kernel.py`, `/v1/bus/*` | complete |
| 3.3 four-tier memory hierarchy | C03 | `nava_memory` (working/episodic/semantic/procedural; task-scoped working, provenance on durable tiers), `/v1/memory` | complete |
| 3.3 15 specialized MCP servers | C03 | `mcp/nava-suite/` — files, terminal, python, processes, system, screen, gui, clipboard, apps, notify, web, browser, memory, bus, plans; each a facade over governed syscalls; compose `nava-mcp` | complete |
| 3.3 21 certified invariants, each with a test | C03 | `docs/NAVA.md` N01–N21 (upstream NAVA has no public repo, so the 21 are defined in-repo, enforced in Postgres/gateway), `tests/nava/test_nava_invariants.py` | complete |
| 3.3 static agents ×7 | C03 | `services/runtime-os/revenueos_runtime_os/agents.py` — CodingAgent, TerminalAgent, ReviewerAgent, VerifierAgent, WebScraperAgent, BrowserAgent, ComputerAgent; DB deny fences; deterministic plan compilers | complete |
| 3.3 dynamic JIT subagents | C03 | `Kernel.spawn` + `nava_subagents` (TTL, inherited fences, killed on expiry) | complete |
| 3.3 managed system call: policy, risk, quotas, locks, rollback | C03 | steps 5 (policy), 4 (risk), 7 (quotas `nava_quotas`), 8 (`nava_locks`), 9/N14 (snapshot/rollback) | complete |
| 3.4 Aegis: kernel sandboxes, COW, egress integration, A2A, workspace authz | C03 | The pinned `heurion-org/aegis-os` binary is built from source (CI `scripts/build-aegis-os.sh`; `infra/docker/python.Dockerfile`'s `aegis` stage) and run as an opt-in `engine="aegis"` option on `sandbox.run` (`infra/sandbox-supervisor/revenueos_sandbox/aegis.py`); its own `run`/`diff --json` cycle feeds our existing, approval-hash-bound `commit()` (we do not call its own `commit`/`promote` — N13/N14, INV-06 stay the one host-write path). Bubblewrap stays the default engine. A2A bus and per-agent workspace authz are NAVA's own (`nava_locks`, A2A bus) either way. | complete |
| 3.4 large repo clone inside sandbox, no host exposure | C03 | e2e `test_aegis_large_repo_clone_inside_sandbox` (cpython depth-1 through the pinned MITM proxy) | complete |
| 3.5 OpenMuse persistent browser + takeover console | C03 | `services/runtime-omni/revenueos_runtime_omni/openmuse.py` — per-agent persistent Chromium on the Phase 2 profile; takeover: VNC (x11vnc) + noVNC web console (pinned add-on) + typing channel; agent paused 423 / resumes | complete |
| 3.5 isolated terminal, 30 s, no host mounts | C03 | `sandbox.run` via bwrap (shadow workspace, ro root); the terminal MCP server clamps every command to 30 s | complete |
| 3.5 durable plans pause/resume/retry | C03 | `plans`/`plan_steps` (0003) + `Kernel.plan_*`; survive restarts (test) | complete |
| 3.5 attachment → PDF → filled form → reviewed reply | C03 | `pipeline.py` + nib (pinned `1f23f70`) + deterministic review + Drafts APPEND; e2e unattended | complete |
| 3.6 remote control path, 41 receipts | C02 | orchestrator `/v1/runtime/tools/{name}` → runtime REST → receipt + span; e2e proves all 41 | complete |
| 3.1/3.2 playwright-mcp: real, invokable MCP domain (not a docs-only pin) | C02 | Built from the pinned commit (`infra/docker/playwright-mcp.Dockerfile`), run as its own compose service, called via `browser.call` (`services/runtime-os/revenueos_runtime_os/tools.py`) over its own HTTP MCP transport — a thin passthrough, since playwright-mcp validates its own tools' native argument shapes at its own boundary | complete |
| C02 ambient-watchers: scans NAVA's own durable state, A2A-notifies the owning agent | C02 | `services/ambient-watchers/` — its own package (no OmniPilot dependency), wired into compose with a `/health` + `/v1/info` surface (spec 1.1) | complete |

## (b) Spec-to-build diff

- "15 specialized MCP servers" / "21 certified system invariants": NAVA names no public repo
  (docs/PINS.md: no usable upstream), so both sets are defined in this repo (docs/NAVA.md) and
  enforced in Postgres and the gateway. Nothing in the sentence is narrowed: there are exactly
  15 servers and exactly 21 invariants, each with a test.
- "CLI + local web UI + REST" (3.1): REST is RevenueOS's surface; OmniPilot's own CLI and local
  web UI ship unchanged in the pinned package inside the runtime image. RevenueOS drives tools
  via REST only, because the CLI/web UI paths are not receipted.
- Static agents are deterministic plan compilers, not LLM loops: no model credentials exist in
  this environment, and INV-07 forbids the model being load-bearing for control decisions. The
  agent loop (model-driven planning) arrives with the model router in later phases; the
  execution substrate they will call is what Phase 3 specifies and it is complete.
- Takeover "human types": provided through two real channels — VNC/noVNC into the live desktop,
  and an authenticated, audited typing endpoint used by the unattended acceptance test.

## (c) Substitution log

**None unresolved.** NAVA's in-repo kernel is its implementation of record by
[ADR-0001](../adr/ADR-0001-nava-vs-openhands.md). This follows the precedent of the in-repo D1
components `llm-tracker` and `dataforge`. OpenHands stays pinned as a D1 fallback candidate for
the agent loop, as D1 itself provides ("the add-on becomes the fallback"). aegis-os is no longer a substitution:
it is built from its pinned commit and run as an opt-in engine (see the component matrix above);
Bubblewrap remains the default engine for every existing caller, which is additive, not a
stand-in. Otherwise only the R03/D1 pins already recorded: OmniPilot `2e3a6bd` (named), nib `1f23f70`
(named), playwright + noVNC (documented add-on for unlicensed openmuse), bubblewrap `1fb0aa2`.

## (d) Defect list (found during the phase, all fixed)

1. runtime-os health reported 503 without a database — postgres check now applies only when
   `PGHOST` is set (same convention as runtime-omni).
2. N10 test depended on a random UUID's sort position — lock-order assertion made per-syscall.
3. N13 was shadowed by N16 when both failed — guard order fixed so each names its own violation.
4. Step-order guard reported N01 for post-termination inserts — now reports N02.
5. `walk()` fixture could record execute without classification — N05 trigger caught it; the
   fixture now classifies at step 4 (the trigger stands).
6. Delegated omni calls would have double-consumed approvals (gateway + executor) — gateway now
   verifies bindings and the executor consumes; DB accepts `omni.`-prefixed receipts (N07/N16).
7. `python3 -I` in the CodingAgent check blocked importing the module under test — dropped.
8. mcp-common imported FastMCP and the OTel SDK at package import — both lazy now, so receipt
   writers don't drag the full SDK in.
9. Pipeline logged in to IMAP with the address — Stalwart wants the principal; fixed to the
   allmail convention (`meta.login`, fallback local part).
10. agent_identities filtered on a nonexistent `active` column — `status='active'`.
11. Chromium would have needed `--ignore-certificate-errors` for the MITM CA — instead the
    entrypoint trusts the egress CA in the per-user NSS store.
12. Receipt write refused at step 12 (e.g. INV-06) would have left a syscall `running` — the
    gateway now downgrades to failed/rolled_back and audits the denial.

13. aegis-os install path: the `aos-cli` crate names its binary `aegis-os`
    (`crates/aos-cli/Cargo.toml`), and both the Dockerfile and the CI build script installed
    `target/release/aos-cli` (CI run 43783238847 red). Fixed in `a5a3dc9`; green in 43783782183.
14. ambient-watchers lacked the standard service shape (`app.py`/`__main__.py`, `/health`,
    `/v1/info`), so `tests/unit/test_services.py` failed in CI run 43781226568 too. Fixed in
    `04fe05c`: the scan loop runs in a background thread behind the HTTP surface.
15. Spec 1.3 boundary: `browser_call` imported `fastmcp` directly in runtime-os (CI run
    43784872498, Q1/Q2 FAIL). Fixed in `dbb4b7e` with `RawMcpClient` in mcp-common.

## (e) Invariant audit (INV-01..15)

| INV | Effect | Proof |
| --- | --- | --- |
| 01 completion needs verification | untouched | `test_inv01_*` green |
| 02 every tool call receipted | strengthened — receipts extended to NAVA syscalls (N16 ties commit to its receipt), OpenMuse browser/pipeline actions | `test_inv02_*`, `test_n16_commit_needs_receipt`, e2e 41-receipts |
| 03 verifier ≠ executor | untouched | `test_inv03_*` |
| 04 LLM may only veto | untouched | `test_inv04_*` |
| 05 unknown telemetry does not file | untouched (and honored: a scan that did not run stays DO_NOT_FILE) | `test_inv05_*` |
| 06 hash-bound approvals | strengthened — N07 requires the consumed approval at the execute step inside the DB; plans pause on approvals | `test_inv06_*`, `test_n07_approval_bound_execution` |
| 07 model is not the security boundary | strengthened — all 21 NAVA invariants are DB triggers/constraints; forged step sequences rejected by Postgres | `test_inv07_*`, `tests/nava/*` DB-attack cases |
| 08 budget halts agent | strengthened — budget_halted agents cannot open syscalls (N03) | `test_inv08_*`, `test_n03_only_active_agents` |
| 09 agent owns identity | strengthened — browser/pipeline refuse agents without provisioned identities | `test_inv09_*`, `test_browser_requires_a_provisioned_profile` |
| 10 only approved servers in production | untouched (Phase 4) | `test_inv10_*` |
| 11 egress only through proxy | strengthened — runtime network has no route out; browser and clone traffic proven in egress_log | `test_inv11_*`, e2e egress assertions |
| 12 COW blocks destruction | strengthened — snapshots + N14 exact-hash rollback on top of the Phase 2 shadow workspace | `test_inv12_*`, `test_n14_*` |
| 13 website design gate | untouched (Phase 7) | `test_inv13_*` |
| 14 learning promotion gate | untouched (Phase 12) | `test_inv14_*` |
| 15 insight reads verified bundles | untouched (Phase 11) | `test_inv15_*` |

## (f) Security audit

- No bypasses: the only executors are the bwrap sandbox (shell) and runtime-omni (desktop), both
  behind the gateway; the 15 MCP servers execute nothing locally.
- Secrets stay by reference: NAVA tokens stored as digests; `issue-token` prints the keychain
  ref, never the token; pipeline reads the mailbox password by ref and never logs it; trace
  scan stays in CI.
- The model is not a boundary: every N-invariant is enforced in Postgres; `tests/nava` attacks
  the DB directly.
- Takeover console: bearer-authenticated, single-holder, input-validated, audited; VNC/noVNC
  bound to the container loopback; never exposed off-host.
- Browser: runtime-only network, per-agent pinned proxy, MITM CA trusted via NSS (verification
  on, not off), downloads jailed to the workspace.

## (g) Integration seams (Phase 3 → Phase 4)

- Tool-call envelope and receipts: unchanged contracts (`ToolCallEnvelope`, `Receipt`) — the 15
  NAVA servers speak them through mcp-common; round-trip tests already in CI (ts1/ts2).
- `/v1/syscalls` is the execution seam Forage-installed servers will ride in Phase 4: new tools
  register in the gateway tool table; INV-10 status checks slot into step 3 (authorize).
- `nava_delegation()` is the executor-binding seam for any future delegated runtime.

## (h) Coverage and observability

- Coverage (CI run 43702840418): runtime-os 86.3%, runtime-omni 87.7%, nava-suite 99.2%,
  sandbox-supervisor 86.0%, qc 100%; every unit above its threshold.
- Every syscall opens an OTel span (`nava.syscall <tool>`) carrying task_id/agent_id/tool and
  ends in a receipt or an audited denial; runtime-omni spans carry the same four attributes;
  e2e asserts receipts sit on the orchestrator's trace.

## (i) Improvement log (beyond the literal spec)

1. Crash reaper (`Gateway.reap`) — orphaned syscalls are rolled back and closed; not asked for
   by name, required for "transactional" to be true across process death.
2. Content-hash verification of rollback (N14 `restored_hash = snapshot_hash` as a CHECK) —
   stronger than "restore the workspace".
3. Postconditions (`expect`) as first-class step-11 checks usable per plan step.
4. The delegation binding (`nava_delegation`) so the desktop executor only runs what a live,
   snapshot-passed syscall authorizes.
5. NSS-trusted MITM CA for Chromium instead of disabling certificate verification.
6. Per-agent NAVA tokens with digests-only storage, mirroring the Phase 2 API RBAC pattern.

### Defects found in live runs (added after the first CI passes, all fixed)

13. bwrap failed with EAGAIN on a busy host: `RLIMIT_NPROC` was counted against the host uid all
    containers share. The pid cap now applies inside the sandbox's own user namespace.
14. Networked sandbox syscalls had no route: `sandbox.run` now opens an identity-pinned egress
    session when `network: true`.
15. Commit refused every symlink, so real source trees could not be committed: relative links that
    stay inside the workspace commit; links that leave it are refused (tested both ways).
16. Stalwart refuses LOGIN on the clear-text port: the pipeline negotiates STARTTLS like allmail.
17. nib rejected the JSON record shape: the pipeline writes XFDF, nib's interchange format.
18. `SERVER` was undefined in the runtime-omni app (500 on browser/pipeline routes).
19. nava-suite had no `manifest.json` (MCP boundary test).
