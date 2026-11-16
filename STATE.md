# STATE

Updated: 2026-11-15 (America/New_York). Read this file first; it is kept accurate at every stop.

**Target:** RevenueOS Phase 3 seal (C02 computer use, C03 agent OS), branch `build/phase-3`.

**Verdict:** Built, CI-green, NOT SEALED. The build is complete. It is blocked on 2 owner
decisions (governance, not build gaps), and no code work remains. Decision of record: ADR-0001.

**Proof of build:** CI run 43786346724 (Validate RevenueOS @ `31d9000`): every job green,
including live acceptance across Phases 1–3, unit/invariant tests, the coverage gate, the trace
secret scan and the MCP SDK boundary. Run 43784872498 is the Q1/Q2 gate that caught the MCP SDK
boundary violation, fixed in `dbb4b7e`. The security workflow on push (43786346804) is green, but
OpenHack is skipped on push events, so it is **not** an OpenHack pass.

**Stack (as built):** Postgres 16 · NAVA kernel in `services/runtime-os` (in-repo implementation
of record, ADR-0001) · OmniPilot `2e3a6bd` in `services/runtime-omni` · aegis-os `d9bdfa97`
(opt-in `engine="aegis"` on `sandbox.run`, Bubblewrap `1fb0aa2` is the default) ·
playwright-mcp `78eca853` via `browser.call` · ambient-watchers (in-repo) · nib `1f23f70` ·
noVNC `e8b5024`.

**Last gate run (2026-11-15, `78d960e`):** CI 43791376552 every job green (acceptance 39/39,
Q1/Q2/Q6/Q7 PASS); security 43791376467 green (OpenHack skipped on push). The review step fails
on the two owner blockers, so the phase is **not sealed**. No seal commit exists.

**Capital deployed:** $0.

## Owner blockers (the only things between Phase 3 and its seal)

| # | Blocker | What clears it | Evidence |
| --- | --- | --- | --- |
| 1 | No model provider for browser-use, magentic-ui and openclaw-heartbeat (C02, scheduled for Phase 3; the model router is scheduled for Phase 13) | Choose and provide a provider (self-hosted open weights is policy-first; hosted BYOK is a fallback and needs approval under INV-06), **or** re-phase the three components to Phase 13 | `docs/reviews/phase-3-review.md` top table; pinned-source citations in ADR-0001 Consequences |
| 2 | OpenHack scan is DO_NOT_FILE (0 model tokens) | Enable GitHub Models for the repo, or set the `SECURITY_OPEN_MODEL_*` secrets | security run 43692377257 on PR #3 |

Closed: the NAVA-native vs OpenHands fork, by
[ADR-0001](docs/adr/ADR-0001-nava-vs-openhands.md), Accepted 2026-11-15, with reversal triggers.

## Next 3 actions

1. **Owner:** resolve blocker 1. Pick a model provider, or re-phase the three components. The
   build agent cannot defer them (R04) and cannot invent a key.
2. **Owner:** resolve blocker 2. Enable GitHub Models, or set `SECURITY_OPEN_MODEL_*`. Then
   re-run PR #3's security workflow.
3. **Build agent, as soon as both are cleared:** integrate the three components behind the
   gateway, re-run the Section 5 gate, seal with
   `phase-3: sealed — <gate-run-id>, ADR-0001, <blocker refs>`, and start Phase 4 (C04
   discovery: Forage/agent-discover activate MCP servers behind `Gateway.syscall`) without
   re-asking.

## Open risks

- **Schedule risk only.** No unmitigated technical risk is known in built code.
- **ADR-0001 reversal.** If trigger 2 (model router or an approved provider) leads to adopting
  OpenHands' agent loop, it must run as a gateway client. That means a Workspace adapter, which
  is new work at that time.
