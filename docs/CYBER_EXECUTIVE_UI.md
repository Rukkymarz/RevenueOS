# Cyber Executive UI v6

## Minimal dashboard

AI Core orb → prompt composer → four metric cards → two priority columns → four create actions. Other workspaces are behind **All tools**. AI Core is available as a floating dock from every non-dashboard workspace, with `Ctrl/⌘ K`.

## Tokens

Background `#080B12`; electric cyan `#00E5FF`; neon violet `#7C3AED`; success mint `#10B981`; Inter/system typography; restrained glass panels and subtle orb glow.

## Component boundaries

- `apps/web/components/command-center.tsx`: authenticated executive overview and backend-sourced figures.
- `apps/web/components/ai-core-orb.tsx`: Framer Motion + CSS orb, with reduced-motion support; state comes from real request/approval status.
- `apps/web/components/ai-core-dock.tsx`: persistent command palette from other workspaces.
- `apps/web/app/neo.css`: scoped design skin and Uiverse-based animation patterns. Original user-provided snippets are adapted, not used as global `.loader` classes.
- `apps/web/app/page.tsx`: existing RBAC-aware API/CRUD and approval workspaces (no backend endpoint changes).

## Guardrails

No fabricated revenue, progress or research results; missing provider connections show explicit status. All emails, deployments and external publishing require backend approvals. Themes: system, light, dark saved only in browser preference storage. Geography is configurable per lead; lead discovery provider is not live yet. Neon animations are decorative and disabled for `prefers-reduced-motion`.
