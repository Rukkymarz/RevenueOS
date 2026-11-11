# API contract (v1)

Prefix: `/api/v1`. OpenAPI schema: `/api/openapi.json`. Authentication: Keycloak access token with `aud=revenueos-api`, `iss` pinned. Tenant selection: `X-Business-Id` on every business endpoint. Server cross-checks memberships. All data is JSON except generated artifact downloads.

| Resource | Routes | Minimum role |
|---|---|---|
| Identity | `GET /me` | authenticated |
| Setup | `POST /setup` | verified bootstrap email, first run only |
| Businesses | `POST /businesses`, `GET /members`, `POST /members` | admin |
| Leads | `GET/POST /leads`, `GET/PATCH /leads/{id}` | viewer read, operator write |
| Clients | `GET/POST /clients` | viewer read, operator write |
| Opportunities | `GET/POST /opportunities` | viewer read, operator write |
| Tasks | `GET/POST /tasks`, `PATCH /tasks/{id}` | viewer read, operator write |
| Campaigns | `GET/POST /campaigns` | viewer read, operator write |
| Proposals | `GET/POST /proposals`, `GET /proposals/{id}/export?format=pdf|docx` | viewer read; operator create/export |
| Website Factory | `GET/POST /websites`, `GET /websites/{id}/download` | viewer read; operator create/export |
| Media Studio | `GET/POST /media`, `GET /media/{id}/download` | viewer read; operator create/export |
| Draft outreach | `GET/POST /outreach/drafts`, `POST /outreach/{id}/send` | operator draft, manager send |
| Approvals | `GET /approvals`, `GET /approvals/{id}/preview`, `POST /approvals/{id}/decision` | operator read; manager decision |
| AI | `POST /assistant/chat`, `POST /ai/drafts` | operator |
| Plugins | `GET /plugins` | operator |
| Reports | `GET /dashboard`, `GET /reports/pipeline` | authenticated workspace member |
| External CRM intake | Not installed | Requires separately approved plugin, own credentials and data-sharing policy |

`GET /health` does not reveal dependencies. `/ready` checks database readiness. `/metrics` returns 404 without a configured `METRICS_TOKEN` and matching `X-Metrics-Token` request header; do not expose it through the public ingress.

Create and patch use strict Pydantic validation. Per-tenant record IDs are opaque UUIDs. Lead score `0–100` reflects user-provided observed *digital health*, not true purchase intent. Unknown dimensions stay unknown with a measured coverage confidence. Exports and other privileged activity are audited.
