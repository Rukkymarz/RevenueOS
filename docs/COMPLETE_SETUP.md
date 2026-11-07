# RevenueOS deployment setup — 2026-11-06

## Current state — no public deployment exists

| Item | State | Evidence / next action |
|---|---|---|
| Render integration | BLOCKED — not connected | Owner must approve/connect Render in ChatGPT Plugins. Do not infer consent from this file. |
| GitHub identity | Connected as `Rukkymarz` | `Rukkymarz/RevenueOS` does not exist or is not accessible. Create a new, private repository specifically for RevenueOS. |
| Source code | Prepared | See project root, `README.md`, and original Command Center source. |
| Local API tests | PASS | `PYTHONPATH=. pytest -q` under `apps/api`: 17 passed (Python 3.13 in this session). |
| PostgreSQL RLS | TEST ADDED, NOT EXECUTED | `.github/workflows/postgres-rls.yml` runs disposable Postgres pgvector; must pass via GitHub Actions. |
| Next.js build | BLOCKED | `apps/web/package-lock.json` must be generated from the registry. This environment cannot resolve registry.npmjs.org (EAI_AGAIN). |
| Docker integration | NOT EXECUTED | Docker engine unavailable here. |
| Keycloak/MFA | NOT EXECUTED | Requires connected host, HTTPS issuer and a realm administrator. |
| Paid infrastructure | NOT PROVISIONED | Review provider quotes and explicitly authorize recurring charges before provisioning. |

## Required user authorization

1. Connect **Render** in ChatGPT (`Settings > Plugins`, or the Render install/connection option already surfaced). This requires the owner's sign-in; an assistant cannot install or authorize the connector on their behalf.
2. Create a **private**, empty GitHub repository named `RevenueOS` under the already connected GitHub account `Rukkymarz`, then make it accessible to the GitHub connector. Use https://github.com/new, select owner and name, and keep it private. Do not place the application in any other business repository.
3. Do not approve paid services until an actual itemized Render pricing quote can be checked for the account. A free deployment is evaluation-only: free web instances sleep and free Postgres expires after 30 days.

## Once repository access exists

1. Upload these monorepo files to the *new* repository (not the ZIP binary itself), keeping `.env.*`, generated realm secrets, and customer data out of Git. Inspect `.gitignore` first.
2. On a networked runner, execute:

```sh
cd apps/web
npm install --package-lock-only --ignore-scripts --no-audit --no-fund
npm ci
npm run typecheck && npm run lint && npm run build
```

3. Commit `apps/web/package-lock.json`. The production Dockerfile requires **npm ci** and must not silently fall back to nondeterministic install.
4. Run all GitHub Actions jobs, especially the **PostgreSQL tenant isolation** workflow. That test uses an ephemeral PG+pgvector database and never a business production database.
5. Only after CI passes, connect the repository to Render and inspect service sizes/quotes.

## Production architecture on Render

- **Web:** One Next.js 16/Node 22 Docker web service. Set build-time `NEXT_PUBLIC_OIDC_ISSUER`, `NEXT_PUBLIC_API_URL` after DNS is known.
- **API:** One FastAPI Python 3.12 Docker web service, health path `/ready`; exposes `/api/v1` only via its approved domain and secure CORS. Do not use a privileged DB role at runtime.
- **Authentication:** One persistent **production-mode** Keycloak service + its own dedicated PostgreSQL database; HTTPS issuer, realm and redirect URIs aligned, real MFA enforced, and privileged admin controls private.
- **Business database:** A separate PostgreSQL database with `pgvector`, Alembic migrations, a privileged migration role and unprivileged `revenueos_app` runtime role. Verify RLS cross-tenant isolation. Do not use credentials, connections or databases belonging to any other business.
- **Rate limiting:** One private Redis-compatible Key Value service. Production must reject missing/invalid `REDIS_URL`.
- **File storage:** Persistent disk or private object-storage adapter for `/data/media`; ephemeral web filesystems are not suitable for customer artifacts.
- **Routing:** TLS for web, auth, API. The root `compose.prod.yaml` is an **alternative single-node VPS** recipe, NOT an importable Render deployment blueprint.

Render service and database sizing, costs, internal URLs, region, environment variables and domain records cannot be finalized until account access and approved budget are available. Never mark a successful provisioning action as a passed application security or release test.

## Secret configuration (enter privately, never in chat/repo)

`APP_ENV`, `DATABASE_URL`, `OIDC_ISSUER`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, `BOOTSTRAP_ADMIN_EMAIL`, `CORS_ORIGINS`, `PUBLIC_BASE_URL`, `REDIS_URL`, `METRICS_TOKEN`, `UNSUBSCRIBE_SECRET`.

Configure email, unapproved external data connector, AI model API keys and outbound publishing **separately**, after verifying domain ownership, opt-outs, cost limits and explicit human approvals.

## Release acceptance gates

- All CI unit/build tests green, including real Postgres RLS test.
- Keycloak OIDC Authorization Code + PKCE login/logout, verified MFA, correct roles and tenancy.
- HTTPS, CORS and proxy trust tested from a phone/browser; PWA installation works.
- Cross-tenant, email draft-fingerprint tampering and double-send attempts rejected.
- Backup schedules and actual restore test completed, with alerting for API latency, exceptions and database failure.
- Browser source assets and private data served under appropriate CSP, cache, and authentication restrictions.
- No sample business data or fictitious MRR portrayed as real; sample dashboard is clearly a demo.
- All AI, email, media and external automation costs are bounded and approved; never ship unlocked paid API calls.
- Confirm all secrets are private, cost commitments approved and live endpoints tested before calling this production-ready.

## What to do now

**Connect Render and create the separate private RevenueOS repository.** Until then, no deployment can be performed through Render, and the current artifact remains an offline release candidate. Once connected, resume from the completed checks rather than rebuilding the application.
