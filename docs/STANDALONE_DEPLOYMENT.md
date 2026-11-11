# Standalone RevenueOS deployment policy

RevenueOS is a **separate SaaS application**, not a module, deployment, CRM plugin, or hosted path of another business.

## Isolation contract

| Boundary | RevenueOS value | Invariant |
|---|---|---|
| Source | `Rukkymarz/RevenueOS` (new, private repository) | Do not deploy from another business repository |
| Render | Dedicated **RevenueOS** project/services (after connection) | No shared deploy targets, environment groups, or access tokens |
| Application domain | Independent RevenueOS domain/subdomain to be selected | Never attach to an existing business host without explicit authorization |
| Business data | `revenueos` PostgreSQL DB | Separate database credentials, backups and migration roles |
| Authentication | Dedicated `revenueos` Keycloak realm and production identity service | Do not reuse another product's user/session tables |
| Cache | Dedicated Redis instance and keyspace | No shared session/queue cache |
| Storage | Private RevenueOS-only media storage | No shared user uploads/buckets |
| Email | RevenueOS-specific verified sender and opt-out | No inherited marketing lists or sending domain |
| Providers | Unique AI/API secrets configured per RevenueOS service | Do not copy credentials or consume budget from another product |
| CI/CD | Independent GitHub Actions jobs and deployment authorization | Never auto-deploy to third-party services |

No existing business has been connected or imported. The former `/api/v1/integrations/quotes/events` endpoint has been **removed**. New integrations require explicit owner authorization, purpose limitation, and review of tenant mappings and credentials.

The initial application must be usable with manually created leads and independent CRM records. Industry templates (including cleaning) are generic content options and do **not** create an integration with any existing business.

## Deployment sequence

1. Create dedicated private GitHub repository `Rukkymarz/RevenueOS` and publish this **standalone** source.
2. Create a fresh Render project (or dedicated self-hosted VPS) named `revenueos`. Do not select existing business services.
3. Provision dedicated PostgreSQL, Keycloak, Redis, app and storage resources with distinct credentials.
4. Set the production RevenueOS hostname, HTTPS/OIDC issuer, CORS and redirect URLs before building the PWA.
5. Run CI build, PostgreSQL RLS, login/MFA, mobile UX and secret-scope tests; verify backup restore.
6. Record and approve recurring spend before enabling any paid services.

No hosting service or domain has been configured in this release candidate. Render connection, GitHub repository creation, frontend dependency lockfile and live deployment remain outstanding.
