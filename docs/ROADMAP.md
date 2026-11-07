# RevenueOS delivery roadmap

## V0.1 — built starter, pending environment-based verification

- Mobile PWA shell, original executive dark design, settings, single assistant, tenant-aware CRUD for leads, clients, opportunities, campaigns, tasks, proposals, websites and media jobs.
- Explainable lead digital-health scoring, pipeline KPIs and due-task/approval views.
- Generated PDF/DOCX proposals, Next.js website ZIP, original SVG graphics, FFmpeg-based template MP4.
- Independent lead management, persisted approvals, Resend send-once gate, role checks, audit events, optional configurable AI text provider gateway.
- PostgreSQL with tenant RLS policy migration, OIDC, local Docker Compose, CI definitions and API tests.

## V0.2 — validate first real revenue workflow

- Validate lead imports from independently collected, properly licensed data, with provenance and explicit user authorization. No other business integration is configured.
- Verify provider response handling in an isolated PostgreSQL stack, then smoke-test approved send and delivery webhook.
- Add search/pagination, saved filters, deal attribution, reports from real activity, approval previews, data export/deletion and suppression UI.
- Add bounded public website audit plugin and explicit score source provenance.

## V0.3 — creative and sales productization

- Mobile approval previews and typed CopilotKit/AG-UI adapter behind backend authorization.
- Specialized website templates, editable proposals and media, streaming download, queued renders and output retention.
- Secure image/video model provider plugins with signed job callbacks, per-tenant budgets and privacy scopes.
- Multichannel social calendar and approved publishing connectors.

## V1 — customer-grade service

- Subscription/payments reconciliation, verified MRR and retention; automated client reports.
- Self-serve tenant onboarding, enforced MFA, email verification, rate limiting, retention/deletion/portability workflows, audit exports, invoices and billing.
- Durable workflow queue with retries, timed follow-ups, suppression, message/webhook reconciliation, monitoring and disaster recovery exercises.
- Penetration test, mobile accessibility audit, load test, threat-model review, production deployment with rollback.
