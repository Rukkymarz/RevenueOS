# ADR-0002: browser-use, magentic-ui and openclaw-heartbeat move from Phase 3 to Phase 13

- **Status:** Accepted (2026-11-15)
- **Decided by:** the owner (Christine), 2026-11-15, choosing option A ("Move them to Phase 13")
  from the two options put to her. Recorded by the build agent.
- **Components:** C02 `browser-use`, `magenticlite` (microsoft/magentic-ui), `openclaw-heartbeat`

## Context

All three are model-driven and cannot do anything without a model provider (pinned-source
evidence in ADR-0001, Consequences, and `docs/reviews/phase-3-review.md`). The component map
scheduled them for Phase 3, but the model router (C01 `model-router`, open-weights default
`ollama`/`vllm`) is scheduled for Phase 13. No model provider exists before then. R04 forbids
the build agent from deferring a named component, so this needed an owner decision.

## Decision

The three components are re-phased to **Phase 13**, where the model router lands. They are not
removed, renamed or substituted: each stays in `config/components.yaml`, stays pinned at its
commit in `config/sources.yaml` and `docs/PINS.md`, and stays a member of its toolset. Only the
phase in which they are integrated changes. This is an owner-granted exception to R04's
"no deferral" for these three components only.

## Consequences

- Phase 3 component coverage no longer includes these three; that seal blocker is closed.
- Phase 13's acceptance must include all three, integrated behind `Gateway.syscall` (ADR-0001)
  and driven through the model router. Phase 13 cannot seal without them.
- Until Phase 13, browser work runs on OmniPilot, OpenMuse and playwright-mcp (`browser.call`),
  and periodic checks run on ambient-watchers. No native stand-in is built for the three.
- If a model provider is approved before Phase 13, the owner may pull them forward with a new ADR.
