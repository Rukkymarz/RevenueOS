# RevenueOS plugin boundary

The initial plugin system is a **trusted adapter registry**, not a marketplace or arbitrary code execution engine.

Source: `apps/api/revenueos/plugins/registry.py`. Each manifest declares `id`, `version`, `category`, `capabilities`, required `scopes`, approval-gated actions, data classes and enabled state. The `PluginAdapter` protocol describes the contract for separately reviewed adapters.

All plugin actions must be mediated by the API's authenticated business context and RBAC. A manifest does not grant a permission; the relevant route enforces it. Plugins must not have direct access to other tenants or model keys. External secrets are stored only server-side. A connector may be replaced without changing frontend routes if it implements the same validated action and response contract.

Current adapters: CRM CRUD, signed quote ingestion, Resend send-once email, website ZIP factory, SVG/FFmpeg creative factory and optional AI text gateway. **OpenSEO, model-driven image/video providers, social publishing, marketplace installation and OAuth vendor connections are future extensions**, not silently enabled. All external sends/publishing/deployments must have durable approval records.

Review checklist for adding an adapter: license, maintenance, scopes, user permission and lawful basis, data transfer countries, SSRF/egress control, auth method, retries/idempotency, spending caps, timeout, rate-limit, health checks, telemetry redaction and replacement/rollback procedure.
