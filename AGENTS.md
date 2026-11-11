# AGENTS.md — RevenueOS

You are working in `Rukkymarz/RevenueOS`, a standalone, MIT-licensed Revenue Operating System. Do not touch any Express Cleaning Consult repository, service, database, or credentials.

## Source of truth
The repository's existing `apps/web` (Next.js 15/React 19/TypeScript) and `apps/api` (FastAPI) implementations, docs, migrations, and tests are the source of truth. Do not replace them with a scaffold or a different app. Keep the Cyber Executive design: electric-blue #00E5FF, purple #7C3AED, green #10B981, background #080B12. Preserve the persistent AI Core panel, animated orb, simplified dashboard, grouped navigation, geographic lead filters, and dark/light/system themes.

## Architecture
- `apps/web` is Next.js for Vercel (root directory `apps/web`).
- `apps/api` is a separately hosted Python 3.12+ FastAPI service.
- PostgreSQL/pgvector, Redis, and Keycloak remain external to Vercel; no secrets in `NEXT_PUBLIC_*` variables.
- Require server-enforced tenant isolation, RBAC, human approval before external actions, secure config, audit logging, and tests.
- Keep development fixtures unmistakably labeled and out of production customer views.

## Workflow
1. Inspect current files and `STATUS.md` before editing; run `git status` and review dependency manifests.
2. Make a feature branch, not a direct push to `main`.
3. Install dependencies, generate a genuine npm lockfile, and execute frontend lint/typecheck/build.
4. Execute backend `pytest -q`, production preflight, and PostgreSQL RLS integration tests. If infrastructure unavailable, state that explicitly.
5. Fix actual issues, not tests by weakening checks. Keep feature claims grounded in runtime behavior.
6. Validate WCAG keyboard/focus behavior, responsive layouts, loading/empty/error states, and reduced-motion behavior.
7. Create or repair CI; push branch and open a draft PR if GitHub credentials permit.
8. Do not merge, deploy to production, connect paid plans, purchase services, or send external outreach without explicit approval.

## Safety and quality
No secrets, customer data, `.env` values, fake credentials, hard-coded cities, or fabricated production metrics in git. Do not imply that AI model calls, prospect enrichment, or video/image APIs work without functional provider integrations. Treat any deployment as preview-only until auth, data isolation, payments/costs, and backup/restore checks pass.
