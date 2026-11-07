# RevenueOS — Render connector deployment handoff (2026-11-06)

## Decision

Use **Render** as the deployment connector for the original Next.js / FastAPI / Keycloak architecture. Do not move the Python API into a different JavaScript SDK solely to fit a hosting service. Keep RevenueOS in its own source repository and database; deploy independently with its own hosting resources and credentials.

**State:** Render connection offered but not yet confirmed, so no hosting resources have been created. This repository is a release *candidate* and cannot honestly be marked production-ready yet.

## Deployment architecture

| Component | Render resource | Notes |
|---|---|---|
| Next.js PWA | Web service, Node or Docker | Needs build-time public OIDC/API URLs and a committed dependency lockfile |
| FastAPI | Docker web service | Health check `/ready`; non-root user; persistent media goes to object storage or attached disk |
| Keycloak | Separate service (production mode) | HTTPS issuer and a second persistent database; enforce MFA and disable unsafe bootstrap workflows |
| App PostgreSQL | Managed PostgreSQL | Must install `vector` extension, run Alembic migrations, create least-privileged app role and verify RLS |
| Keycloak PostgreSQL | Separate persistent PostgreSQL DB | No shared application-role credentials |
| Redis | Managed Key Value/Redis | Required for production API rate limiting; allow private network access only |
| Reverse proxy / TLS | Render routing + application-domain routing | Render does not duplicate the supplied single-host Caddy network topology; explicitly design reverse proxy routes and trusted IP headers |

Render's free web services sleep after inactivity and free Postgres expires after 30 days; neither constitutes safe ongoing production service. Confirm the exact monthly charges before activating paid resources. Payment or domain changes require the owner's authorization.

## Exact gating checklist for the connected deployment agent

1. Confirm access to a **new RevenueOS GitHub repository**. The GitHub connection currently returned no accessible repositories; never push to another business repository.
2. Generate `apps/web/package-lock.json` with a trusted registry, commit it, then replace `npm install` in CI with `npm ci`; run build/lint/typecheck on Node 22. The ZIP intentionally does not invent a lockfile. The present Dockerfile uses `npm ci`, so it cannot build without one.
3. Verify the Python 3.12 API test suite and run PostgreSQL integration tests against an isolated migrated DB. SQLite-only regression tests are insufficient for row-level-security verification.
4. Provision and restrict production app and Keycloak databases. Create separate DB migration and runtime credentials. Recheck RLS under the runtime role from a non-superuser connection. Enable backups and run a restore drill.
5. Select and verify the app URL, API routing, OIDC HTTPS issuer and redirect URI **before** building the PWA. Generate a production Keycloak realm using the approved public URL, enable MFA, and restrict administrative access.
6. Set `APP_ENV=production`, proper `DATABASE_URL` (with `postgresql+psycopg` driver), `OIDC_ISSUER`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, `BOOTSTRAP_ADMIN_EMAIL`, `CORS_ORIGINS`, `PUBLIC_BASE_URL`, `REDIS_URL`, `METRICS_TOKEN`, `UNSUBSCRIBE_SECRET`. Enter secrets only through Render's secret UI, never in commits or chat.
7. Disable AI, outbound email, external lead discovery and publishing until tested with explicit cost/consent controls. Enable individual integrations one at a time after validating provider credentials, budgets, opt-outs and approved integration boundaries.
8. Configure persistent media storage (do not leave `MEDIA_DIR` on an ephemeral web service), structured logs/alerting, HTTPS and accurate client IP treatment. The supplied single-host Caddyfile is **not** an equivalent deployment recipe for three public Render services.
9. Verify login/logout, mobile PWA install, tenant creation, CRUD, cross-tenant access rejection, signed webhook replay rejection, email preview fingerprint, approval and send-once semantics, unsubscribe, exported proposal and website ZIP, rate limiting, production backups and alerting.
10. Restrict public traffic until the production release review passes. Report actual live URL, deployment IDs, build status, costs and unresolved capabilities; never declare success from infrastructure provisioning alone.

## Work already verified locally

- API regression tests: **17 passed** on 2026-11-06 after a production config test was updated to include Redis.
- Production Compose now explicitly includes a non-public Redis instance and `REDIS_URL` wired to API; Caddy now overwrites `X-Real-IP` on proxied API calls.
- Production Compose YAML syntax parses.

## Current blockers

- Render connector must be connected by the user, then project/repository access checked.
- No accessible RevenueOS GitHub repository was returned at this point.
- Frontend dependency lockfile missing and npm registry request timed out in the present runtime, so **Next.js build is unverified**.
- Docker runtime not available here; no production Compose integration or Keycloak OIDC test has been run.
- PostgreSQL RLS and backups not validated against a live production-grade datastore.
- Render service topology and domain-specific Keycloak configuration still must be implemented after actual environment/domain selection.
- Vendor integrations (image/video inference, lead discovery, live email/publishing) remain feature-gated.

## Cost / ownership

Do not create paid instances without presenting a current cost breakdown and approval. Retain the MIT repository in the owner's GitHub account, use deploy credentials limited to RevenueOS, and keep a migration/backup export path independent of Render.
