# RevenueOS — Codex import handoff

## Destination

- GitHub: https://github.com/Rukkymarz/RevenueOS
- Existing repository is separate from Express Cleaning Consult.
- The archive is packaged with the application at ZIP root, so do not
  add a second `revenueos/` parent directory.

## Before import

- Treat the archive as untrusted source until audited.
- Do not commit `.env`, provider secrets, personal/customer data, or cache files.
- The GitHub repository was observed as public: review contents before pushing.
- The README/STATUS documents may contain historical connection information.
  Use real GitHub state at execution time.

## First commands (inside the extracted project)

```bash
cd apps/web
npm install --package-lock-only --ignore-scripts --no-audit --no-fund
npm ci
npm run typecheck
npm run lint
npm run build
```

For the Python API follow `apps/api/pyproject.toml` and `README.md`,
then run `pytest -q`, and execute `scripts/check_release.py` at repo root.
Use the GitHub Actions ephemeral PostgreSQL test for real tenant/RLS coverage.

## Known release limitations

- Missing `apps/web/package-lock.json` in supplied source: generate it using npm.
- Full Next.js build, real PostgreSQL/pgvector RLS tests, Docker E2E,
  Keycloak/MFA live login, and backup/restore have not been confirmed.
- All financial and approval operations need production verification.
- No automatic lead research, AI image/video inference, provider publishing,
  or paid infrastructure is included as a verified live feature.
- No production secrets are bundled.

## Safety

Create a new branch and draft PR. Do not merge, provision paid hosting,
change public settings, or launch outreach without explicit user approval.
