# Deployment and operations

## Local development

`cp .env.example .env` then set unique strong credentials, then `docker compose up --build -d`. Docker Compose ports are bound to `127.0.0.1` so they are accessible **only on the Docker host**; a phone elsewhere cannot connect to this configuration. Keycloak start-dev uses transient DB storage and HTTP; it is not production-ready.

## Production architecture

1. A stable Linux host or managed container runtime with enough RAM for PostgreSQL, Keycloak, FastAPI and Next.js, or separately managed PostgreSQL and identity. Always-on containers require an actual host and usually cost money.
2. Put web, API and IdP behind HTTPS with a reverse proxy (Caddy, Traefik, or equivalent), configure public OIDC issuer and callback URLs, private service networks, security headers, request limits and egress policies.
3. Run Keycloak in production mode backed by persistent PostgreSQL (separate database/schema) and enforce MFA for privileged roles. Rotate bootstrap admin and restrict its console.
4. Use independent database owner/migration and API runtime accounts. Run migrations only during a controlled release and test rollback with a pre-migration backup; never run migration as the API role.
5. Set long random non-interpolated secrets through an orchestrator/secret manager; never put production credentials in Git. Vault is an optional later enterprise secret store, not a day-one prerequisite.
6. Back up PostgreSQL with PITR where supported, export artifacts, and test restoration. Install alerting for API error rate and task/send failures. Protect optional Prometheus/Grafana behind admin authentication.
7. Enforce minimum TLS 1.2 and strict CORS origins. Protect anti-CSRF semantics for any cookie-auth endpoints; this starter's API requires bearer tokens, not cookies.
8. Integrations: verify signatures for incoming events, review Resend sender ownership, use least-privilege service credentials, and test sending with explicit contact permission.
9. Audit retention, access logs, incident response, billing limits, tenant data isolation, and DPAs before onboarding outside organizations.
10. Set a domain, DNS, and TLS; perform realistic staging smoke tests for login/logout, tenant creation, CRUD, approvals, signed webhooks, exports, backup/restore and mobile PWA install.

**No live deployment was performed as part of this repository export.** The supplied compose is a local baseline requiring deployment-specific edits and manual identity/bootstrap steps. The source itself is MIT; third-party service licenses and model/API costs remain separate.
