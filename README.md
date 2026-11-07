# RevenueOS

**Mobile-first revenue operating system** · Next.js 16 / TypeScript · FastAPI · PostgreSQL · Optional LangGraph · MIT

**Current release candidate:** the full source is on `codex/revenueos-cyber-executive-v6`, with [draft PR #1](https://github.com/Rukkymarz/RevenueOS/pull/1). Frontend/API validation and real PostgreSQL/RLS checks have passed in CI. Read [release acceptance](docs/RELEASE_ACCEPTANCE.md) for the current function inventory and remaining production gates; dated setup notes below are historical snapshots. A custom domain is optional: hosting providers assign HTTPS service URLs.

RevenueOS is a **working starter product**, not a deployed SaaS. It includes authenticated, tenant-scoped lead management, business/lead scoring, clients, opportunities, tasks, campaigns, PDF/DOCX proposal exports, editable Next.js website generation, SVG ad cards, template-based MP4 video rendering, human approvals, and a send-once Resend outreach adapter. A single assistant can perform deterministic task routing or use an explicitly configured text-model API for draft creation.

**Honest capability boundaries:** automatic discovery of public leads, internet-scale SEO audits, model-generated photography, AI video inference, provider-driven social publishing, subscriptions and payment reconciliation, and unattended full website deployments **are not implemented**. Media Studio makes original template graphics and video clips today; GPU-backed generators are future plugins. Revenue reports reflect user-entered amounts, not payment processor settlements. Do not treat example output as verified business facts.

## Quick start: Docker, on a machine/server that supports it

1. Install Docker Engine and Compose V2 (the phone is a *client*, not the Docker host).
2. `cp .env.example .env` and replace **every** password, secret and bootstrap email. Use **URL-safe** passwords because URLs are used in database connection strings; URL-encode reserved characters if needed.
3. `docker compose build && docker compose up -d`.
4. Visit `http://localhost:8080/admin` on the Docker host. Create a RevenueOS realm user matching `BOOTSTRAP_ADMIN_EMAIL`, set a strong password, mark their email verified, and enroll TOTP MFA in the account console. For production configure required MFA authentication flows at the IdP.
5. Visit `http://localhost:3000`, sign in, and create the first business workspace. The verified bootstrap email is allowed to initialize **exactly one** workspace.
6. Once signed in, create a lead, an opportunity or task; then create a proposal and export the file. Email sending remains blocked until a verified Resend sender and a human approval are configured.

API health: `http://localhost:8000/health`; OpenAPI: `http://localhost:8000/api/docs`.

**Production warning:** `compose.yaml` is local developer infrastructure using Keycloak's `start-dev` mode and HTTP loopback ports; it is **not safe to expose directly on the internet**. Do not forward its ports or treat this as production deployment. See [deployment requirements](docs/DEPLOYMENT.md).

## Separate deployment

RevenueOS operates completely independently of any other business website or CRM. There is no inbound quote import or shared database/hosting configuration. See [Standalone deployment policy](docs/STANDALONE_DEPLOYMENT.md).

## Architecture

```text
Next.js mobile PWA (one assistant + executive dashboard)
     │ Authorization Code + PKCE (Keycloak OIDC)
     ▼
FastAPI /api/v1  ── business-level RBAC ── human approvals
     │                                      │
     ├── PostgreSQL with RLS (separate app database role)
     ├── optional configurable model provider gateway
     ├── independent CRM records / verified Resend sender
     └── PDF, DOCX, website ZIP, SVG & FFmpeg template MP4 generators
```

The platform does not fork LibreChat or Open WebUI; the visual system is independently implemented to preserve MIT distribution rights and a lighter operational surface. CopilotKit/AG-UI support can be evaluated later without making the approval policy depend on any UI library.

## Developer workflows

Frontend: `cd apps/web && npm install && npm run dev` (Node.js 22+). API: `cd apps/api && python -m venv .venv && . .venv/bin/activate && pip install -e '.[test]' && uvicorn revenueos.main:app --reload` (Python 3.12+), provided `DATABASE_URL` and identity service are configured.

Tests: `cd apps/api && pytest -q`; `cd apps/web && npm run typecheck && npm run lint && npm run build`. A Docker-only smoke test requires the full stack. The `.github/workflows/ci.yml` workflow runs those checks in separate jobs.

See [API and data model](docs/API.md), [security and controls](docs/SECURITY.md), [deployment](docs/DEPLOYMENT.md), [design system](docs/DESIGN.md), [plugins](docs/PLUGINS.md), and [roadmap](docs/ROADMAP.md).

## Cost and license

Core source code is MIT-licensed (see `LICENSE`). Its dependencies and optional services retain **their own** licenses; MIT does not relicense Keycloak, PostgreSQL, FFmpeg, LangGraph, AI model weights, cloud APIs, or hosted creative services. Expect potential hosting, database, email and model charges depending on usage. An always-on multi-container deployment is **not guaranteed to be free**.

## Command Center redesign (2026-11-06)

The default dashboard is now an AI-centered **RevenueOS Command Center**: mission, current business signals, priority leads, a single AI composer, actionable approvals, CRM pipeline stages and concise workspaces. Desktop uses a three-panel cockpit; narrow mobile layouts put the assistant directly beneath the mission. The visual direction draws inspiration from Arc/Linear spatial navigation and restrained futuristic interfaces, without copying third-party product assets.

Try the independent, sample-data-only interactive demonstration in [`docs/preview/index.html`](docs/preview/index.html). Source/UI integration and remaining verification notes are in [`docs/COMMAND_CENTER.md`](docs/COMMAND_CENTER.md). No production deployment is implied.

## Deployment setup status (2026-11-06)

The `Rukkymarz/RevenueOS` repository exists but has not received the full source; the Vercel connection is authorized in ChatGPT, but this runtime has not exposed deployment actions. The offline regression suite passes (17 tests), but a genuine frontend `package-lock.json` could not be generated in this runtime because the npm registry is unreachable. The production CI now includes a PostgreSQL/pgvector RLS smoke test (not yet run). **Do not expose this starter publicly until the build, identity, database, backup and service checks pass.**

See [the setup handoff](docs/COMPLETE_SETUP.md); run `python scripts/check_release.py` to inspect offline release gates.


## Cyber Executive v6 redesign — 2026-11-06

The home screen is intentionally **smaller**: an animated, human-controlled AI Core (the provided Uiverse design motifs adapted with scoped CSS and Framer Motion), one command composer, four real business metrics, next actions, three top leads and four creation shortcuts. All remaining workspaces are under **All tools**. AI Core can be opened with `Ctrl/⌘ K` on other pages. Theme modes: system, light and dark. Mobile bottom navigation is preserved.

To preview the appearance without authentication or connected services, open [`docs/preview/cyber-executive.html`](docs/preview/cyber-executive.html). This file uses **explicit demo data only**; the actual authenticated UI is implemented in `apps/web`.

Deployment is split by design: **Vercel** serves only the Next.js frontend and other dedicated infrastructure must host FastAPI, Keycloak, Redis and PostgreSQL. Import the GitHub monorepo into Vercel with **Root Directory `apps/web`**. Full instructions and required public environment variables are in [`docs/VERCEL_SETUP.md`](docs/VERCEL_SETUP.md). This source change is **not** a claim of a completed Vercel deployment.
