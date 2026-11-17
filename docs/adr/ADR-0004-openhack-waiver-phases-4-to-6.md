# ADR-0004: OpenHack waiver carried through Phases 4 to 6 (assumption from the owner's standing instruction)

- **Status:** Accepted, 2026-11-17, with an expiry (below). **This extends ADR-0003 on the build
  agent's reading of the owner's instructions; the owner can reverse it.**
- **Basis:** the owner said "just move on" about the OpenHack scan (ADR-0003) and then "complete
  more phases before stopping". The same provider cap that stopped the Phase 3 scan stops every
  later scan, so sealing Phases 4–6 needs the same waiver.

## Decision

OpenHack is waived as a **seal condition** for Phases 4, 5 and 6, nothing else. Its verdict is
unchanged: **DO_NOT_FILE** (the scan did not complete: provider free-tier daily cap, `429`).
Nothing in the repo may describe OpenHack as passed.

## Expiry and consequences

- Expires at the first of: model access that lets a scan complete (the scan is then re-run on all
  waived code and findings are fixed before the next seal), or any merge to `main` or deploy.
- PRs #3, #4, #5 and any later phase PR stay unmerged. No deploy.
- Other scanners still gate: AutoSecScan, VulnHunter, Strix, open-kritt, gitleaks (green on
  Phase 4: CI 44035789107, security 44035789137).
