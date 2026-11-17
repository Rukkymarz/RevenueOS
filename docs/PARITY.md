# Open-source parity library

Proprietary categories mapped to vetted open-source replacements. Agents check this list
first on a capability gap, before any hosted API (free-tier order in POLICY.md). Commits and
stars for every repo are in PINS.md.

| Proprietary category | Open-source replacement | License | Notes |
| --- | --- | --- | --- |
| Adobe Acrobat | Nib (named), Stirling-PDF + OCRmyPDF (add-ons) | AGPL-3.0; MIT core; MPL-2.0 | Nib: form filling, 41-language on-device OCR, true redaction, reflow in the document's font, PDF/UA tagging, co-signing up to 32 parties, scriptable CLI |
| Acrobat desktop | PDFCraft (`storytold/pdfcraft`) | Apache-2.0 | Rust, 53+ tools, native macOS/Windows/Linux/FreeBSD, in-place text editing, offline Ollama copilot, node-based DAG workflows |
| Microsoft 365 | Nextcloud server + richdocuments (D7) | AGPL-3.0 | Files, calendar, contacts, mail, chat, video; real-time DOCX/XLSX/PPTX. ONLYOFFICE and CryptPad were excluded for failing the star gate |
| Airtable / Google Sheets backend | Teable (D1 for NocoDB), Univer | AGPL-3.0 core; Apache-2.0 | NocoDB is named but moved to the Sustainable Use License (not OSI) in Jan 2026 |
| Salesforce / HubSpot CRM | Twenty | AGPL-3.0 (enterprise files excluded) | System of record for leads (Addendum C, L7) |
| Apollo.io / Clay / ZoomInfo | Twenty + `everything-claude-code` lead-intelligence skill + Phase 6 outreach server | AGPL-3.0; MIT | No 10k+ open-source Apollo equivalent exists (D5). OpenGTM is a named waterfall source; KeeLead is experimental only |
| Mailchimp / Customer.io | listmonk, Postal, Mautic | AGPL-3.0; MIT; GPL-3.0 | Sending always from the agent's own identity (INV-09) |
| Google Analytics | Umami, Plausible | MIT; AGPL-3.0 | Wired into every generated site in Phase 11 |
| Twilio WhatsApp | OpenWA (secondary channel only) | MIT | Reverse-engineered client: ToS and permanent-ban risk (THREATMODEL) |
| Canva / Figma | Penpot, Open Design | MPL-2.0; Apache-2.0 | Design studio (Phase 9/14) |
| Google Ads tooling | claude-ads (skill pack) + google-ads-mcp (named vendor exception) | MIT; Apache-2.0 | Different jobs: audit/automation vs. official API access. Writes need INV-06 approval |

## Correction record

**Apollo-11 is not a lead scraper.** `chrislgarry/Apollo-11` is the NASA Apollo Guidance
Computer source code. It is not integrated. Apollo.io has no open-source repository. Lead
generation is the Addendum C waterfall (docs/LEAD_PIPELINE.md).
