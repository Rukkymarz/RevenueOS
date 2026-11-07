# RevenueOS: Netlify + Supabase deployment

Selected by the owner on 2026-11-07. Supersedes Oracle/Vercel hosting plans for
this deployment. Keep the original Python implementation and Docker topology as
the reference and alternate self-hosted distribution; do not remove them.

## Accounts and current state

- Netlify Free team: `rukkymarz`. New project: `revenueos-hh24`, ID
  `8e641284-8c1c-4d49-96d3-e3673ea790fe`. The short name `revenueos` was taken.
- Authenticated Netlify CLI is linked. `.netlify/` is git-ignored.
- Owner selected a DIFFERENT Supabase organization from the one containing the
  unrelated cleaning project. That existing project must not be inspected,
  reused or modified. New Free organization creation is pending owner action.
- No Supabase RevenueOS project or public deployment exists yet. Do not infer
  a functioning site from Netlify's allocated project hostname.
- Administrator email was supplied privately in chat; configure it only in the
  new project's private configuration table, not source control.

## Runtime

Next.js Route Handlers implement `/api/v1/*` in Netlify's OpenNext runtime. They
preserve the existing frontend contracts. All Supabase operations carry the
user's verified JWT and the publishable key. No service-role key is needed or
permitted in browser configuration or these routes.

Configuration in Netlify (Builds AND Functions scopes, then redeploy):

```
NEXT_PUBLIC_AUTH_PROVIDER=supabase
NEXT_PUBLIC_SUPABASE_URL=<actual new project HTTPS URL>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<actual publishable key>
NEXT_PUBLIC_API_URL=
```

Supabase Auth uses verified email, password sign-in, PKCE/sessionStorage and
TOTP MFA. Every database operation checks `aal2`, confirmed email and a matching
live session. The app additionally records revoked session IDs at logout, so
already-issued JWTs cannot continue reading business data through the Data API.
Revoking a session does not depend on waiting for JWT expiry. Provider sign-out
is still attempted if the database revoke step fails; the UI reports when
immediate revocation could not be confirmed.

Configure exact site/recovery redirect origins, secure email delivery, a minimum
12-character password policy and a short JWT lifetime in the new project's Auth
settings. Do not turn off email confirmation or MFA to get through testing.
User registration alone does not grant workspace membership. Only the designated
verified owner may initialize the first workspace. Administrators can add other
verified existing identities by subject ID and matching email.

## Schema and access controls

`supabase/migrations/` retains the existing model tables. The new deployment's
RLS uses authenticated memberships instead of FastAPI's transaction-local
business context. Every table denies anonymous access and unknown tables remain
ungranted. Immutable identity/tenant/timestamp/calculated columns cannot be
updated through the Data API. Scoring, audit events, cross-tenant lead references,
approval hash checks and atomic imports are enforced inside PostgreSQL.

Private SECURITY DEFINER helpers have an empty search path, explicit actor/role
checks, no PUBLIC/anonymous execution grants and are called by narrow invoker
wrappers. They exist to avoid recursive membership RLS and perform authorized
multi-table transactions; they are not generic SQL execution endpoints.

After inspecting the new project's empty schema, apply migrations in order and
insert the owner-designated bootstrap email into `private.configuration` through
an owner-authorized private SQL operation. Run security/performance advisors and
actual hosted isolation checks. The isolated CI fixture simulates Supabase Auth
tables; it does not verify hosted GoTrue or Storage service behavior.

## Implemented migration scope

- Verified login and required TOTP; recovery UI and global sign-out.
- Initial/additional workspaces and verified membership management.
- Lead creation/editing, scoring, suppression and atomic deduplicated import.
- Clients, opportunities, tasks, campaigns, proposals, real reports/dashboard.
- Exact-content email draft approvals. Email transmission remains unconfigured.
- Actual Unicode-font PDF, DOCX and editable Next.js source ZIP exports.
- SVG artwork and real four-second template MP4 rendering. The video path
  converts font outlines to PNG, then encodes MP4; it does not require Linux
  FFmpeg's optional `drawtext` filter or host fonts.
- Private Supabase artifact bucket. Upload names must match a reserved job and
  actor/workspace; completed files cannot be overwritten through the app.
- Enforced media quotas: 20 requests/day/workspace, at most five videos/day and
  100 stored jobs/workspace. Failed jobs also consume reservations. No paid AI
  generation is enabled. Failed rendering does not report a completed artifact.
- Role-limited audit history, bounded data export, honest integration inventory.

Heavy export packages load only after authentication and when that route is used.
The openly licensed Noto Sans font and license are bundled under `assets/fonts`;
Next file tracing includes it and the platform's FFmpeg binary for Netlify.

## Outstanding launch gates

1. New Free organization, separate $0 project and its actual configuration.
2. Apply/test schema on that project; check advisors, RLS and Storage policies.
3. Hosted Auth settings, real email confirmation, owner registration and TOTP.
4. Netlify preview build on Linux; verify all traced assets and native packages.
5. Real browser/API tests against hosted Supabase on desktop and mobile,
   including access failures, logout revocation, imports and all exports.
6. Configure independent encrypted backup/restore for Supabase data/artifacts.
   `backup_production.py` is for the Docker topology and does NOT back up hosted
   Supabase. Test a recovery drill before customer data is onboarded.
7. Monitoring, privacy/deletion/retention procedures and required external
   provider integrations. The broader unfinished product features remain listed
   in `RELEASE_ACCEPTANCE.md`; migrating hosting does not implement them.

Free plans have resource caps and inactivity behavior; this architecture does not
establish an uptime guarantee. Do not enable paid upgrades, automatic recharge,
metered overages or paid provider calls under the owner's $0 constraint.
