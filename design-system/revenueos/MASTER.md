# RevenueOS interface design

Source: UI UX Pro Max, nextlevelbuilder/ui-ux-pro-max-skill.
Queries run: `fintech dashboard --design-system -p RevenueOS`,
`analytics dashboard --domain product`, and Next.js stack guidance.

The fintech result's Enterprise Gateway marketing layout is unsuitable for this
authenticated workspace. The targeted Analytics Dashboard result recommends
data-focused layouts, minimalism, and optional dark mode. Apply those principles
with the repository's existing AI Core layout and theme support.

## Product decisions

- Preserve background #080B12, cyan #00E5FF, purple #7C3AED and mint #10B981.
- Retain system/Inter typography; use tabular figures for comparable metrics.
- Keep one primary composer, four metrics, priority actions, and contextual tools.
- Use restrained glow, clear surface boundaries and readable secondary text.
- Give command inputs 16px text, visible keyboard focus, and 44px action targets.
- Stack composer actions on small screens; allow long labels and values to wrap.
- Respect reduced motion and mobile safe areas.
- Preserve API integration, approvals and honest setup/empty/error states.

Implementation: `apps/web/app/ux-pro.css`, loaded after the existing theme.
No marketing sections, invented metrics, external fonts or animation dependencies.
