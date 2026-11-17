# Lead pipeline (Addendum C)

A Clay-equivalent waterfall built in Phase 10. Each row is a Phase 5 task, not a spreadsheet
cell: the task record is the truth and the spreadsheet (NocoDB/Teable grid, Google Sheets view)
is a view of it. Every stage transition writes a `task_event` and an audit entry.

| Stage | Name | What happens | Exit condition |
| --- | --- | --- | --- |
| L0 | Ingest | Row arrives from scraper, inbound, social or CSV with name, company, domain, role, source, timestamp, raw payload. Deduplicated by domain + normalized name | Unique row |
| L1 | Identity | Domain resolved to a company: scraper, then api-anything, then OpenGTM | Canonical `company_id`, `domain_verified` |
| L2 | Contact waterfall | Stop on the first valid result: scraper team page, api-anything, OpenGTM, dataforge (D1: no public repo, skipped), Hunter-compatible fallback. Every attempt logged with cost and result hash | Email found, or `email_status=NOT_FOUND` |
| L3 | Verification | Syntax, MX, safe SMTP check, catch-all detection. Deterministic oracle, never an LLM (INV-04) | INVALID stops; RISKY advances flagged |
| L4 | Enrichment | Employees, industry, funding, tech stack, HQ, revenue band; every field carries a source URI and a verified, inferred or missing label | Labeled record |
| L5 | ICP scoring | Deterministic weights from the premise bundle, 0-100 with per-factor breakdown; no LLM scoring | Below threshold: DISQUALIFIED (kept) |
| L6 | Personalize | Recent posts, funding, hiring, launches, mutuals; lead-intelligence skill writes a 2-3 line hook, stored, not sent | Hook stored |
| L7 | Routing | 80+ to SEQUENCE_A, 50-79 to SEQUENCE_B, under 50 to NURTURE; contact written to Twenty with full enrichment; sheet status and `crm_record_id` updated | CRM record |
| L8 | Outreach | Phase 6 outreach server sends from the agent's own identity (INV-09); a rendered-message hash above threshold needs approval (INV-06) | Sent and receipted |
| L9 | Feedback | Opens, replies, bounces, meetings write back. Bounce: INVALID + suppress. Reply: ENGAGED + new Phase 5 task. All outcomes feed Myelinate | Outcome recorded |

The waterfall order and ICP weights are configurable per project and re-ordered by Myelinate
from observed hit rate per source (Phase 12 acceptance). Per-provider hit-rate logging is a
Phase 10 acceptance criterion.
