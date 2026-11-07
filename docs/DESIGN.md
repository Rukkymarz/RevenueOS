# RevenueOS original design system

**Intent:** Linear's information hierarchy, Stripe's executive numeric dashboard, Arc's spatial clarity, Claude's calm assistant, and Vercel's restrained developer aesthetic. These are visual inspirations, *not* assets or copied code.

## Tokens

- Background: `#0b0e14`; sidebar: `#10151d`; elevated: `#151b25`
- Border: `#252e3b`; primary copy: `#ecf1f8`; supporting: `#93a2b7`
- Actions: `#397fff`; success: `#5ee0ae`; warning: `#f9c27a`
- Radius: `9–14px`; cards: restrained 1px border, no neon glow
- Type: system UI stack (no external fonts, no tracking/cookies)

## Mobile UX

The mobile shell retains bottom navigation (Home, Leads, Tasks, Approvals, AI) and a separate complete menu. The same PWA supports touch and desktop. Responsive breakpoints: 1220px, 900px, 620px. Compact cards replace spreadsheet tables. Statuses and human approvals must always be readable in text, not color alone. Focus-visible outlines, keyboard interactions, semantic buttons/forms, and reduced-motion CSS are included.

## Assistant / generative UI

**One conversational assistant** with six role profiles; no background agents are exposed. The first release shows contextual action buttons and normal business views rather than arbitrary AI-rendered HTML. A future CopilotKit-compatible adapter can stream typed UI events (lead selection, proposal preview, approval request), but the API and durable approval record—not the chat widget—remain the source of truth. All AI output is untrusted text and must not be treated as a tool action without separate authorization.

## References reviewed, not redistributed

- LibreChat (MIT): https://github.com/LibreChat-AI/LibreChat
- CopilotKit (MIT): https://github.com/CopilotKit/CopilotKit
- Vercel AI Chatbot (check license and attribution at adoption): https://github.com/vercel/chatbot
- Open WebUI modern releases have branding restrictions; **do not incorporate its source** in this MIT application: https://docs.openwebui.com/license/
- Reference patterns require independent implementation and assets unless an explicit compatible license applies.
