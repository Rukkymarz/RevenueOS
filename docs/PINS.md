# Pins

Every upstream project behind RevenueOS, checked 2026-11-14. Machine-readable
source: `config/sources.yaml` (full 40-character commit SHAs). CI fails if any
component lacks a pinned, approved-license repo.

**Vetting standard:** an approved open-source license (MIT, Apache-2.0, BSD-3-Clause,
MPL-2.0, LGPL-2.1, GPL-3.0, AGPL-3.0, PostgreSQL), not archived, pushed within the
last six months, and broadly adopted. A spec-named tool that failed was replaced
by the strongest open-source project covering the same job, or built in-repo
when none exists.

**Result:** 28 named tools kept, 35 replaced, 6 built in-repo, 2 removed as duplicates.

| Spec | Component | Selection | Repo | License | Stars | Commit | Why |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C01 | astromesh | replacement | [BerriAI/litellm](https://github.com/BerriAI/litellm) | MIT * | 63,242 | `d81c55f4cc86` | monaccode/astromesh has 39 stars; LiteLLM is the standard open-source multi-provider router with budgets and cost tracking |
| C01 | autogen-ag2 | named | [ag2ai/ag2](https://github.com/ag2ai/ag2) | Apache-2.0 | 5,063 | `4356a5ee64a7` | AG2 is the actively developed AutoGen line; microsoft/autogen code is MIT but docs CC-BY-4.0 |
| C01 | biro | replacement | [paperclipai/paperclip](https://github.com/paperclipai/paperclip) | MIT | 113,796 | `c1451814c155` | no public Biro repo found; Paperclip provides org charts, budgets, heartbeats and tickets for agents |
| C01 | composio | named | [ComposioHQ/composio](https://github.com/ComposioHQ/composio) | MIT | 31,064 | `fdee7595166f` |  |
| C01 | crewai | named | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | MIT | 60,878 | `d7dfa0ef5ade` |  |
| C01 | erebots | replacement | [a2aproject/A2A](https://github.com/a2aproject/A2A) | Apache-2.0 | 26,538 | `4d7cda4b1754` | aislab-hevs/erebots4.0 has 0 stars; the MCP+A2A split is implemented directly on the official A2A protocol |
| C01 | harness-agent | replacement | [letta-ai/letta](https://github.com/letta-ai/letta) | Apache-2.0 | 25,434 | `8816d3a85168` | no public repo found for Harness Agent; Letta provides hierarchical agents with persistent memory |
| C01 | harnis | replacement | [humanlayer/humanlayer](https://github.com/humanlayer/humanlayer)<br>[open-policy-agent/opa](https://github.com/open-policy-agent/opa) | Apache-2.0<br>Apache-2.0 | 12,878<br>12,470 | `b7ad8e1d383f`<br>`8d10da6e34b8` | karawash-projects/harnis has 6 stars; HumanLayer gives human approvals, OPA gives tenant and budget policy |
| C01 | hubzoid | replacement | [openclaw/openclaw](https://github.com/openclaw/openclaw) | MIT | 394,427 | `18892937f802` | hubzoid/hubzoid has 18 stars; OpenClaw provides markdown-defined agents with Slack, WhatsApp, Telegram and webhook routing |
| C01 | incagent | replacement | [getlago/lago](https://github.com/getlago/lago)<br>[documenso/documenso](https://github.com/documenso/documenso) | AGPL-3.0<br>AGPL-3.0 | 10,842<br>15,761 | `63d2ddfcf3c6`<br>`1e2333d534e1` | incagent/incagent has no license; Lago handles invoicing and settlement, Documenso offers and contracts |
| C01 | langgraph | named | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | MIT | 44,948 | `08a201695378` |  |
| C01 | official-mcp-servers | named | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | MIT * | 91,982 | `e1dc4b18dbb9` |  |
| C01 | ollama | named | [ollama/ollama](https://github.com/ollama/ollama) | MIT | 186,934 | `a5864fcb3396` |  |
| C01 | omnigent | named | [omnigent-ai/omnigent](https://github.com/omnigent-ai/omnigent) | Apache-2.0 | 11,377 | `38a65dbdde2d` |  |
| C01 | vllm | named | [vllm-project/vllm](https://github.com/vllm-project/vllm) | Apache-2.0 | 96,915 | `2ab8e2f74669` |  |
| C02 | browser-use | named | [browser-use/browser-use](https://github.com/browser-use/browser-use) | MIT | 120,984 | `e717df1839a2` |  |
| C02 | magenticlite | named | [microsoft/magentic-ui](https://github.com/microsoft/magentic-ui) | MIT | 10,117 | `d3c9d13c3928` |  |
| C02 | omnipilot | replacement | [trycua/cua](https://github.com/trycua/cua) | MIT | 32,334 | `fb2b0df98ef4` | xrchris7/OmniPilot has 2 stars; Cua provides sandboxed desktop VMs and containers for computer-use agents |
| C02 | openclaw-heartbeat | named | [openclaw/openclaw](https://github.com/openclaw/openclaw) | MIT | 394,427 | `18892937f802` |  |
| C02 | playwright-mcp | named | [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | Apache-2.0 | 39,621 | `78eca85361ef` |  |
| C03 | aegis-os | replacement | [containers/bubblewrap](https://github.com/containers/bubblewrap)<br>[google/gvisor](https://github.com/google/gvisor) | LGPL-2.1<br>Apache-2.0 | 9,486<br>20,000 | `1fb0aa26d3eb`<br>`ab5f509c9c6e` | no reputable Aegis OS repo (largest has 2 stars); Bubblewrap and gVisor are the kernel sandboxes the spec calls for |
| C03 | nava | replacement | [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | MIT | 93,455 | `830c0459e2f6` | no public NAVA repo found; OpenHands provides coding, terminal and browser agents; the 12-step mutation gateway is built in-repo |
| C03 | openmuse | replacement | [steel-dev/steel-browser](https://github.com/steel-dev/steel-browser)<br>[novnc/noVNC](https://github.com/novnc/noVNC) | Apache-2.0<br>MPL-2.0 | 7,963<br>14,204 | `552550af7974`<br>`e8b5024d4603` | diggerhq/openmuse has no license; Steel gives persistent agent browsers, noVNC the human takeover console |
| C04 | agent-discover | replacement | [IBM/mcp-context-forge](https://github.com/IBM/mcp-context-forge) | Apache-2.0 | 4,817 | `26809f391bd9` | keshrath/agent-discover has 7 stars; ContextForge includes registry, activation, health and per-tool metrics |
| C04 | forage | replacement | [IBM/mcp-context-forge](https://github.com/IBM/mcp-context-forge) | Apache-2.0 | 4,817 | `26809f391bd9` | no public Forage repo found; ContextForge is a maintained MCP gateway, registry and proxy |
| C04 | mcpfinder | replacement | [modelcontextprotocol/registry](https://github.com/modelcontextprotocol/registry) | MIT * | 7,465 | `115f85225c9f` | mcpfinder has 14 stars; the official MCP Registry is the canonical source |
| C04 | mcptoon | replacement | [docker/mcp-gateway](https://github.com/docker/mcp-gateway) | MIT | 1,633 | `7e0f34277c91` | mcptoon has 430 stars and one maintainer; Docker's MCP gateway provides a vetted server catalog and one-command install |
| C05 | agenticmail | named | [agenticmail/agenticmail](https://github.com/agenticmail/agenticmail) | MIT | 254 | `af1e0ef546b5` | kept as specialist for SMS and phone; moderate adoption (about 250 stars), so Stalwart is the primary mailbox |
| C05 | allmail-mcp | replacement | [Wh1isper/mcp-email-server](https://github.com/Wh1isper/mcp-email-server) | BSD-3-Clause | 394 | `cb1191e4fc6d` | no public allmail-mcp repo found; mcp-email-server is a maintained multi-account IMAP/SMTP MCP server |
| C05 | stalwart-mail | named | [stalwartlabs/stalwart](https://github.com/stalwartlabs/stalwart) | AGPL-3.0 | 15,923 | `e7cde9b3fac3` |  |
| C06 | agentic-pm | replacement | [github/spec-kit](https://github.com/github/spec-kit) | MIT | 149,752 | `2ee2b1e80059` | no reputable agentic-pm repo; GitHub Spec Kit produces Spec, Plan and Tasks |
| C06 | fist-mbt | replacement | [temporalio/temporal](https://github.com/temporalio/temporal) | MIT | 24,396 | `170fb83dca48` | vicTop-cw/FIST-Mbt has 1 star; Temporal provides claim, retry and watchdog semantics |
| C06 | gsd-pi | replacement | [temporalio/temporal](https://github.com/temporalio/temporal) | MIT | 24,396 | `170fb83dca48` | gsd-build/get-shit-done and gsd-2 are archived; Temporal runs the durable plan-implement-verify loops |
| C06 | llm-tracker | native | built in-repo | in-repo |  |  | no reputable llm-tracker repo (largest has 2 stars); filesystem-as-database mode built in-repo |
| C06 | mission-control | named | [builderz-labs/mission-control](https://github.com/builderz-labs/mission-control) | MIT | 6,491 | `c1a846fe0205` |  |
| C06 | piyaz | replacement | [makeplane/plane](https://github.com/makeplane/plane) | AGPL-3.0 | 62,433 | `290383d7f92f` | FrkAk/piyaz has 200 stars; Plane is the established open-source project workspace |
| C07 | firecrawl | named | [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl) | AGPL-3.0 | 201,670 | `71f430a2dabf` |  |
| C07 | openbusiness | replacement | [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | Apache-2.0 | 30,679 | `ddd4db36208d` | wanikua/OpenBusiness has 12 stars; GPT Researcher is the established open-source research agent |
| C07 | searxng | named | [searxng/searxng](https://github.com/searxng/searxng) | AGPL-3.0 | 39,540 | `a7128d5d1d5a` |  |
| C08 | chrome-devtools-mcp | named | [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) | Apache-2.0 | 55,878 | `8ba2ac945eba` |  |
| C08 | deepagents-open-lovable | replacement | [firecrawl/open-lovable](https://github.com/firecrawl/open-lovable)<br>[langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) | MIT<br>MIT | 28,909<br>31,279 | `806b8072f28a`<br>`a93aed4bca3a` | emanueleielo/deepagents-open-lovable has no license; its two upstreams are used directly |
| C08 | design-linter | native | [dequelabs/axe-core](https://github.com/dequelabs/axe-core) | MPL-2.0 | 7,818 | `d991e05ac6eb` | agent-design-skills has no public repo; linter built in-repo, axe-core for WCAG checks |
| C08 | frontend-design-skill | named | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 * | 194,339 | `2c5958ecac7c` |  |
| C08 | nexity | replacement | [sanity-io/sanity](https://github.com/sanity-io/sanity) | MIT | 6,394 | `08b506252df9` | Pagepro/nexity has 26 stars; Next.js 16 plus Sanity is built directly |
| C08 | open-pages | replacement | [dyad-sh/dyad](https://github.com/dyad-sh/dyad) | Apache-2.0 * | 22,296 | `a15e23340ff3` | no public open-pages repo found; Dyad is a local open-source app builder with live preview |
| C08 | syntheon | replacement | [dyad-sh/dyad](https://github.com/dyad-sh/dyad) | Apache-2.0 * | 22,296 | `a15e23340ff3` | cognis-digital/syntheon has 0 stars and no license; Dyad runs fully local models |
| C08 | tastemaker | native | built in-repo | in-repo |  |  | the named 56-pattern scanner has no reputable repo (Harrypatria/tastemaker has 5 stars); slop catalog built in-repo |
| C08 | ui-ux-pro-max | named | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | MIT | 149,276 | `6ae86f61f520` |  |
| C09 | postiz | named | [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | AGPL-3.0 | 41,574 | `132859f32d85` |  |
| C09 | postmill-ai | named | [postmill-ai/postmill-app](https://github.com/postmill-ai/postmill-app) | AGPL-3.0 | 315 | `e06b4796fe53` | secondary; moderate adoption (about 300 stars) |
| C10 | helio | replacement | [PostHog/posthog](https://github.com/PostHog/posthog) | MIT * | 40,777 | `e060b5d34918` | achref-soua/helio has 24 stars; PostHog provides self-hosted CDP, segmentation and journeys |
| C10 | mautic | named | [mautic/mautic](https://github.com/mautic/mautic) | GPL-3.0 | 10,985 | `6711577a1df4` |  |
| C10 | netsendo | replacement | [knadh/listmonk](https://github.com/knadh/listmonk) | AGPL-3.0 | 24,292 | `e735e0b23421` | NetSendo has 19 stars and an unclear license; listmonk is the established self-hosted mailer |
| C11 | evalforge | replacement | [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | MIT | 27,159 | `45f68f0d77db` | EvalForge repos have under 10 stars; promptfoo provides YAML suites, agent evals and CI regression gates |
| C11 | gitreins | replacement | [pre-commit/pre-commit](https://github.com/pre-commit/pre-commit) | MIT | 15,695 | `ba5c4209a6d5` | totalwindupflightsystems/gitreins has 1 star; git hooks via pre-commit, evaluator and resolution gate built in-repo |
| C11 | veripipe | native | built in-repo | in-repo |  |  | no reputable repo (largest has 1 star); fail-closed verifier built in-repo and already enforced in the database |
| C12 | duckdb | named | [duckdb/duckdb](https://github.com/duckdb/duckdb) | MIT | 43,055 | `b678afa97b52` |  |
| C12 | postgres | named | [postgres/postgres](https://github.com/postgres/postgres) | PostgreSQL | n/a | `70c4a57b64d3` |  |
| C12 | tares | native | [duckdb/duckdb](https://github.com/duckdb/duckdb) | MIT | 43,055 | `b678afa97b52` | no public Tares repo found; timeline writer built in-repo on DuckDB |
| C13 | agentjet | replacement | [verl-project/verl](https://github.com/verl-project/verl) | Apache-2.0 | 24,229 | `4191e7f910d8` | modelscope/AgentJet has 243 stars; verl is the most widely used agentic RL trainer |
| C13 | curio | native | [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | Apache-2.0 | 30,679 | `ddd4db36208d` | no public Curio repo found; gap detection built in-repo, filled by GPT Researcher |
| C13 | myelinate | replacement | [mem0ai/mem0](https://github.com/mem0ai/mem0) | Apache-2.0 | 68,950 | `f1791daa86d4` | myelinate repos have 7 stars; Mem0 is the established agent memory layer; canary and holdout built in-repo |
| C13 | openforgerl | replacement | [OpenRLHF/OpenRLHF](https://github.com/OpenRLHF/OpenRLHF) | Apache-2.0 | 10,152 | `26494490bc23` | the OpenForgeRL repo has 2 stars and no license |
| C13 | openspace | replacement | [letta-ai/letta](https://github.com/letta-ai/letta) | Apache-2.0 | 25,434 | `8816d3a85168` | HKUDS/OpenSpace was not reachable; only an archived port exists; Letta provides self-editing agent memory over its API |
| C13 | orchard | replacement | [huggingface/trl](https://github.com/huggingface/trl) | Apache-2.0 | 19,734 | `8ad18ec1b649` | no public Orchard repo found; TRL provides SFT and preference training on partial trajectories |
| C15 | nib | replacement | [Stirling-Tools/Stirling-PDF](https://github.com/Stirling-Tools/Stirling-PDF)<br>[ocrmypdf/OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) | MIT *<br>MPL-2.0 | 96,552<br>35,314 | `ad38e38ce9bb`<br>`3343116ba204` | daniel-alexander4/nib has 10 stars; Stirling-PDF covers forms, redaction and signing, OCRmyPDF covers OCR |
| C15 | pdfcraft | named | [storytold/pdfcraft](https://github.com/storytold/pdfcraft) | Apache-2.0 | 20,674 | `dd6c625274e0` |  |
| C17 | openbao | named | [openbao/openbao](https://github.com/openbao/openbao) | MPL-2.0 | 9,008 | `92de51f7a058` |  |
| C18 | otel-collector | named | [open-telemetry/opentelemetry-collector-contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib) | Apache-2.0 | 5,050 | `e0e1cb6463e1` |  |

**Removed:**
- social0: Abhishek-B-R/social0-oss has 4 stars; Postiz already covers the same 9 networks
- pdf-viewer-editor: SuperiorAg/PDF_Viewer_Editor has 0 stars; Stirling-PDF and PDFCraft cover it

**\* License scope limits (enforced at vendoring):**
- BerriAI/litellm: MIT outside litellm/enterprise/; do not use enterprise/
- PostHog/posthog: MIT outside ee/; do not use ee/
- Stirling-Tools/Stirling-PDF: MIT core; proprietary portions excluded
- anthropics/skills: skills/frontend-design/LICENSE.txt is Apache-2.0; other skills in the repo differ
- dyad-sh/dyad: Apache-2.0 outside src/pro/
- dyad-sh/dyad: Apache-2.0 outside src/pro/; do not use src/pro/
- modelcontextprotocol/registry: transitioning MIT to Apache-2.0
- modelcontextprotocol/servers: transitioning MIT to Apache-2.0; both permissive

**Copyleft obligations:** AGPL-3.0 services (Postiz, Postmill, Firecrawl, SearXNG,
Stalwart, Plane, Lago, Documenso, listmonk) run as separate network services and
are not linked into RevenueOS code. If you modify one and offer it to users over
a network, publish your modifications. GPL-3.0 (Mautic) and LGPL-2.1 (Bubblewrap)
are likewise used as separate programs.

**Method:** GitHub search API for license, stars and last push; `git ls-remote`
for the commit; license files read directly where GitHub reported NOASSERTION.
Star counts are a snapshot.
