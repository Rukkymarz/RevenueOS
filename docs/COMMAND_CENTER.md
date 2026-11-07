# RevenueOS Command Center — interface specification

## Experience

The Command Center is an original UI composed of:

1. **Mission strip** — next overdue priority task from the authenticated dashboard API, with a clear action to create another task. It never implies unsaved goals were achieved.
2. **Business signals** — recorded MRR, open opportunity value, active clients and actionable work queue. Revenue amounts are user-entered and are explicitly not settlement-verified.
3. **AI command cockpit** — one assistant surface, with optional provider routing and explicit human control. Sample prompt chips populate the composer but do not execute a command without a separate user submit action.
4. **Priority leads** — current workspace's API records, sorted by existing evidence-based score, with confidence metadata.
5. **Next actions** — due follow-ups, pending human approvals and deal pipeline.
6. **Revenue pathway** — recorded stage counts without invented completion percentage or AI-generated performance claims.
7. **Workspaces** — a small persistent navigation group and additional grouped pages; all original application routes remain available.

## Accessibility & responsive rules

- At narrow phone widths the order is mission → assistant → business metrics → leads → next actions → pipeline → workspace shortcuts.
- Real mobile navigation, minimum-size action targets, visible labels and keyboard-focus outlines are retained.
- Dark and light themes, reduced-motion preference and empty/error states are supported.
- The AI orbit is decorative and `aria-hidden`; never rely on its visual circles for navigation or status.
- The command form and shortcuts use native controls and semantic labels.

## What the interface does not do

- Does not discover prospects autonomously from the public internet.
- Does not make payments, publish campaigns, or send outreach from chat just because text asks it to.
- Does not calculate verified ARR/MRR from a connected payment processor.
- Does not represent the illustrative static preview as real CRM data.

## Files

- `apps/web/components/command-center.tsx` — authenticated, data-backed Command Center React component.
- `apps/web/app/page.tsx` — integration, business API calls, navigation and existing approval flow.
- `apps/web/app/globals.css` — adaptive visual system.
- `docs/preview/index.html` — stand-alone interactive visual demonstration using visibly marked sample data.

## Remaining verification

The command center is browser-tested as a standalone representation; the React source passed TypeScript syntax parsing. Full Next.js dependency installation, type checking, production build, Keycloak identity, and Docker stack integration are not validated in this runtime. Follow `docs/DEPLOYMENT.md` before exposing an installation publicly.
