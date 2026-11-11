# RevenueOS release acceptance

This record supersedes historical build/connection notes in the archive.
Status: release candidate. Production approval remains blocked by unverified live services.

**Current hosting selection (2026-11-07): Netlify + Supabase.** See
`NETLIFY_SUPABASE.md` for the implemented serverless migration and its outstanding
live gates. Keycloak/Redis/Vercel requirements below describe the preserved Python
and Docker topology, not mandatory services for the selected serverless deployment.

**Budget constraint:** the owner selected $0, with no paid services. See
`ZERO_COST_HOSTING.md`. Do not proceed with the paid Vercel/Render production
topology, enable metered overages, or start card-backed trials.

## Function inventory reviewed

| Requested function | Implementation and remaining acceptance |
|---|---|
| Executive dashboard and AI Core | Real workspace API totals, persistent dock, command composer, themes, responsive navigation; browser tested locally with signed test identity |
| Leads and scoring | Create, edit, stage, suppression, contact-basis evidence, measured scoring, pagination and bounded JSON import with source-ID deduplication |
| Clients and opportunities | Create/edit, active client status, open/won/lost deals; recorded revenue updates reports; no payment reconciliation |
| Tasks and follow-ups | Create, due date, completion; unattended scheduled follow-ups and notifications are not implemented |
| Campaigns and content | Create/edit plans and email drafts; configured external publishing adapters are still required |
| Proposals | Editable scopes/prices; actual PDF and DOCX exports; pricing comes from user input |
| Website factory | Actual editable Next.js ZIP exports; no automatic custom site deployment or agency-grade visual editor |
| Media studio | SVG graphics and FFmpeg template MP4 exports; not generative photography or model-driven video |
| Human approvals | Exact-content preview/hash, manager gate and manual send-once Resend adapter; live sender/compliance config not connected |
| AI | Six role profiles, configurable provider routing, persistent per-user/workspace quotas; real provider keys/models and spending limits need owner setup |
| Lead discovery and auditing | Research-request preparation; autonomous discovery, enrichment and public audits are not implemented |
| Team/workspaces | Administrator membership management and additional workspaces; server RBAC and tenant selection |
| Settings/operations | Connection inventory, AI quota visibility, audit history, bounded workspace JSON export |
| Billing | No subscriptions, invoice reconciliation or verified bank/processor MRR |
| Security | OIDC/PKCE, JWT signature/issuer/audience tests, DB RLS, exact approvals, wired Redis limiter, bounded request bodies, strict inputs, readiness validation |
| Privacy/retention | Workspace export and outreach suppression; identity-verified deletion and timed retention remain unfinished |
| Web hosting | Next.js/Vercel frontend plus separate API, PostgreSQL, Redis and Keycloak; no purchased domain required |

## Reproduced evidence

- API regression suite: 26 passing tests (including real signed-token verification).
- Next.js 16.4.5 production build, TypeScript and ESLint checked locally.
- npm full dependency audit: no known vulnerabilities after upgrading Next.js and overriding the lint parser's vulnerable minimatch dependency.
- Python pinned dependency audit: no known vulnerabilities after upgrading Pillow to 13.0.0.
- Source release preflight passes. It is not a substitute for live acceptance.
- PostgreSQL migration, FORCE RLS, runtime-role and real API transaction checks passed in GitHub Actions on commit b459bc9: https://github.com/Rukkymarz/RevenueOS/actions/runs/42342741269.
- Frontend build/typecheck/lint, API tests, source preflight and security audits passed on the same commit: https://github.com/Rukkymarz/RevenueOS/actions/runs/42342741253. Later commits must pass the same checks.
- Local browser fixture exercises real UI/API/OIDC-code/PKCE with an ephemeral signing key and disposable SQLite database. It does not verify Keycloak, PostgreSQL, SMTP or cloud hosting.
- Browser checks include first-run setup, lead create/edit, exact-content approval, composer, sign-out, theme persistence, 390px layout without horizontal overflow, mobile navigation, browser Back, keyboard AI dock, settings and switching between two isolated workspaces.
- Source is published on `codex/revenueos-cyber-executive-v6`; draft PR: https://github.com/Rukkymarz/RevenueOS/pull/1.

## Domain-free deployment

Vercel provides a generated HTTPS `*.vercel.app` hostname for the frontend.
Container hosts such as Render provide service hostnames for the API and identity service.
Use the actual assigned HTTPS origins for CORS, OIDC redirects and issuer configuration.
Do not guess or advertise a hostname before a deployment returns it.

Vercel team access must be authorized for `rukkymarzs-projects`. The account was
observed on Hobby; commercial hosting requires an appropriate approved plan.
Render is available but not connected. No paid infrastructure has been provisioned.

## Production release gates

1. Approve hosting budget and connect the backend host. Deploy isolated services and enter secrets privately.
2. Run migrations using the schema owner, then run the API as `revenueos_app` with FORCE RLS; verify readiness.
3. Configure persistent Keycloak with exact HTTPS redirects, verified owner account and enforced MFA. Test login, renewal, logout and role changes.
4. Connect each required AI/email/data/creative/publishing/payment provider and implement remaining functions above. Verify limits, approval policy, failure paths and delivery reconciliation.
5. Exercise the hosted app on desktop/mobile against actual PostgreSQL/Redis/Keycloak.
6. Verify monitoring, database/artifact backups, a real restore drill, incident handling, retention/deletion and external security review before customer launch.

## Disposable browser QA

Use only a local test environment:

```powershell
$env:REVENUEOS_E2E_TEST='true'
.\.venv\Scripts\python.exe scripts/e2e_fixture.py
# In another terminal, inside apps/web:
$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8765'
$env:NEXT_PUBLIC_OIDC_ISSUER='http://127.0.0.1:8765/identity'
node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3000
```

The fixture binds to loopback, creates a temporary database, disables email/AI,
and signs only disposable test-user tokens. Never deploy it, reuse its identity,
or substitute it for production OIDC/MFA tests.
