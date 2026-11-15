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

## Sandbox (Phase 2)

Agent commands run under Bubblewrap via the sandbox supervisor (`POST /v1/run` on
`sandbox-supervisor:8300`, inside the compose network only). Each run gets a copy-on-write
shadow of the workspace, read-only system directories, a read-only root, its own namespaces
(no network), uid 1000, and quotas (CPU, memory, processes, file size, wall clock). The
destructive-command blocklist applies in every mode, YOLO included. Every run is a
`sandbox_sessions` row; a commit back to the real workspace needs an approval bound to the
changeset hash.

Host requirement: Bubblewrap creates unprivileged user namespaces. Ubuntu 24.04+ restricts
those through AppArmor; on such hosts run
`sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0` (CI does). The supervisor
container runs without Docker's seccomp/AppArmor profiles for the same reason; it stays
non-root with no added capabilities, and `/health` is green only if a sandbox actually starts.

## Egress (Phase 2)

Rules are rows, not files: `egress_rules` (agent-wide, or per task) and `secret_bindings`
(secret reference, host, header). Add a host for an agent:

```sql
INSERT INTO egress_rules(agent_id, task_id, host, created_by) VALUES ('<agent>', NULL, 'api.example.com:443', 'owner');
```

Every decision is in `egress_log` (append-only) and the audit ledger. Unsigned, stale,
closed-session or foreign-session requests are denied. The identity HMAC key is
`keychain://egress-identity-hmac`; rotating it ends every open session.

## Identity (Phase 2)

Provision an agent in one command (email via AgenticMail on Stalwart, calendar via CalDAV,
private browser profile, phone):

```bash
docker compose -f infra/compose.yaml exec identity revenueos-identity provision --name leads-agent --role leads \
  --allow signup.example.com:80
docker compose -f infra/compose.yaml exec identity revenueos-identity rotate-profile --agent-id <id>
docker compose -f infra/compose.yaml exec identity revenueos-identity leads-signup --agent-id <id> --task-id <id> \
  --service http://signup.example.com --mode otp
```

The mailbox API key and password go to the keychain only; the proxy injects the key when the
agent calls its own inbox. A phone identity stays `pending` until carrier credentials exist
and a number purchase is approved (it is a paid external resource).

## Approvals API (Phase 2)

Bearer tokens are in the keychain (`api-token-owner`, `api-token-probe-agent`); the API holds
only their sha256 digests (`api-principals`). Roles: `requester` (agents), `approver`
(humans), `auditor`.

```bash
curl -H "authorization: Bearer $(cat infra/secrets/keychain/api-token-owner)" localhost:3000/v1/approvals?status=pending
curl -X POST -H "authorization: Bearer $(cat infra/secrets/keychain/api-token-owner)" -H 'content-type: application/json' \
  -d '{"approve": true}' localhost:3000/v1/approvals/<id>/decision
```

## Kill switch, budgets, rollback

Per-agent and global kill switches (Phase 14), budget halts (Phase 5) and skill rollback
(Phase 12) are added here when those phases land.
