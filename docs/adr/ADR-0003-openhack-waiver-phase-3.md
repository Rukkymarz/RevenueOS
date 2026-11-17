# ADR-0003: Phase 3 is sealed with the OpenHack scan outstanding (owner waiver)

- **Status:** Accepted (2026-11-17)
- **Decided by:** the owner (Christine), 2026-11-17, with the instruction "just move on" after
  the scan was stopped by the provider's free daily cap. Recorded by the build agent.

## Context

OpenHack runs on pull requests against an open model. On PR #4 (Phase 3 code) it has never
completed. The last attempt (security run 43800695820, attempt 2) reached the model
(`openhack client reply: ok tokens: 31`) and then failed with `429 - Rate limit exceeded:
free-models-per-day`. Its verdict is `DO_NOT_FILE - scan did not complete`. D10 says a scan that
did not run is DO_NOT_FILE, never PASS. Every other gate is green.

## Decision

The owner waives the OpenHack scan as a **Phase 3 seal** condition. The verdict is **not**
changed: it stays DO_NOT_FILE and is carried forward as an open item. Nothing in the repo may
describe OpenHack as passed for Phase 3.

## Consequences

- Phase 3 can seal and Phase 4 can start (R07).
- The waiver expires at the first of: (a) model access that lets a full scan complete (credits
  or another provider), at which point the scan is re-run on Phase 3 and later code and any
  findings are fixed before the next seal; (b) any merge into `main` or any deploy, neither of
  which may happen while the verdict is DO_NOT_FILE.
- PR #3 and PR #4 stay unmerged until then.
- The other scanners ran and passed on PR #4: AutoSecScan, VulnHunter, Strix, open-kritt
  (security run 43800695820) and gitleaks (CI 44022282389).
