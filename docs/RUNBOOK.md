# Runbook

Operating procedures for the stack as built. Each section says which phase it applies from;
later phases extend this file.

## Start and stop (Phase 1)

```bash
infra/bootstrap.sh                      # one-time: env file, keychain dir, pinned images
docker compose -f infra/compose.yaml up -d
docker compose -f infra/compose.yaml ps # every service healthy
docker compose -f infra/compose.yaml down
```

Health: every service exposes `GET /health` (503 when a dependency check fails); the API exposes
`/health` and the apps `/api/health`.

## Database (Phase 1)

```bash
db/migrate.sh                           # applies migrations in order, then seed data
revenueos audit verify --db "$DATABASE_URL"   # exit 0 intact; exit 2 names first broken seq/id
revenueos audit export --db "$DATABASE_URL" > audit.jsonl
```

If `audit verify` exits 2: stop writers, preserve the database volume, export the chain, and
treat it as a security incident (THREATMODEL T17). Do not "repair" rows; the ledger is
append-only by design.

## Secrets (Phase 1)

- Never put a secret value in a file, prompt, log, trace or commit. Reference it:
  `keychain://<name>` (local) or `vault://<name>` (Infisical).
- Rotate: write the new value in the vault, restart the egress-authz service, verify a probe call,
  then revoke the old value.
- A gitleaks or secret-hygiene failure blocks merge. Rotate the exposed value first, then remove
  it from history.

## Approvals (Phase 1 DB, Phase 2 UI)

High and critical tool calls wait for an approval bound to the canonical hash of their arguments.
Approvals expire and are single-use; the requester cannot approve. A call whose arguments change
after approval no longer matches the hash and is refused.

## Security job (Phase 1)

`.github/workflows/security.yml` records one verdict per scanner in `.security/*.verdict.json`.

| Verdict | Meaning | Action |
| --- | --- | --- |
| PASS | Scanner ran, nothing at or above high | none |
| FAIL | Finding at or above high | fix before merge |
| DO_NOT_FILE | Scanner did not run or produced no report | fix the cause (often a missing secret); never treat as pass |
| NOT_APPLICABLE | Scanner does not apply to this event (e.g. Strix before sites exist) | none |

Secrets the LLM-backed scanners need (set in GitHub → Settings → Secrets):
`SECURITY_OPEN_MODEL_BASE_URL`, `SECURITY_OPEN_MODEL_API_KEY`, `SECURITY_OPEN_MODEL_NAME`
(OpenHack), `VULNHUNTER_ANTHROPIC_API_KEY`, `STRIX_LLM`, `STRIX_LLM_API_KEY`,
`KRITT_HOST_REPORT_URL` (open-kritt report host).

## Phase gate (every phase)

Per spec section 5: run acceptance into `docs/reviews/phase-N-acceptance.log`, write
`docs/reviews/phase-N-review.md` (sections a–i), append `docs/PROGRESS.md`, commit
`phase-N: sealed — <IDs>`, report in the Step 7 shape. Phase N+1 starts only after Phase N is
sealed. `main` changes only at a seal.

## Kill switch, budgets, rollback

Per-agent and global kill switches (Phase 14), budget halts (Phase 5) and skill rollback
(Phase 12) are added here when those phases land.
