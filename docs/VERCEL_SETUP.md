# RevenueOS — Vercel frontend deployment

RevenueOS is a standalone application and does **not** use Express Cleaning infrastructure.

## Architecture

- **Vercel:** Next.js UI (`apps/web`) only, with managed TLS and branch previews.
- **Separate Docker host:** FastAPI (`apps/api`), long-running worker, Redis and Keycloak.
- **Separate PostgreSQL:** Dedicated database with RLS and backups. Do not reuse Express databases.
- **DNS:** `app.<dedicated-domain>` for Vercel, `api.<dedicated-domain>` for FastAPI, `auth.<dedicated-domain>` for Keycloak.

**Vercel does not run the existing production Compose stack or replace Keycloak/Redis.** Do not publish the application as production until the API and identity provider are ready.

## Dashboard configuration

1. Import **Rukkymarz/RevenueOS** into the *connected Vercel account* after the source has actually been pushed to GitHub.
2. Set **Root Directory** to `apps/web` and Framework Preset **Next.js**.
3. Use `npm ci` to install, `npm run build` to build. Commit a generated real `apps/web/package-lock.json` before attempting deployment. Do not fabricate the lockfile.
4. Set `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_OIDC_ISSUER` separately for Production/Preview; both MUST use HTTPS for published sites.
5. In Keycloak: create/configure client `revenueos-web`, use authorization-code + PKCE, and allow only explicit Vercel deployment domains as redirect URIs and web origins. Enable MFA per role policy.
6. Configure the FastAPI CORS allowlist to include the exact Vercel origin(s); do not use `*` with authenticated endpoints.
7. Test one real sign-in, token refresh/expiry, business switching, tenant isolation, approvals, API requests and logout in Preview before approving Production.
8. **Commercial usage requires Vercel Pro or Enterprise**. Vercel's published Hobby terms restrict Hobby to personal, non-commercial projects. As of November 2026, Pro begins at $20/month with separately metered usage. Confirm pricing with the account owner before selecting any paid plan or enabling paid features. Do not treat this production revenue product as a Hobby project.
9. Confirm the budget **before** provisioning paid tiers. Do not select production until CI and integration checks are green.

## Security conditions

Never put API tokens, model secrets, Postgres passwords or OAuth client secrets into `NEXT_PUBLIC_*`. For a browser OAuth client, use a public client with PKCE. Retain server-side approval checks and audit logs. Configure the provider gateway, webhooks and SMTP/Resend credentials on the API/worker host only.

## Current blockers

- GitHub repo is still observed with just README; complete monorepo source must be uploaded.
- `apps/web/package-lock.json` is missing; generate using npm with registry access, then `npm ci && npm run typecheck && npm run lint && npm run build`.
- No verified public API, Keycloak, Redis, PostgreSQL RLS, or backups.
- Vercel plugin is connected in ChatGPT, but deployment actions were not exposed in this session; do not claim a Vercel deployment until Vercel returns an actual deployment URL and successful checks.
