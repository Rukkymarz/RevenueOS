# RevenueOS

Self-hosted, self-improving multi-agent business operating system.

## What it is

- AI agents with their own identities (email, phone, calendar, browser profile) that research a
  line of business, propose income projects grounded in labeled evidence, and run them.
- Projects decomposed into Spec, Plan and Rules, then milestones, slices and tasks, with a task
  state machine enforced in the database.
- Every tool call receipted; high-risk calls need a human approval bound to a hash of the exact
  arguments; nothing completes without verification by someone other than the agent that did it.
- A website factory behind a design-governance gate, outreach, social and marketing from each
  agent's own identity, and a Clay-style lead pipeline.
- A hash-chained audit ledger, OpenTelemetry tracing end to end, and learning only from verified
  outcomes.

## Quick start

```sh
sh infra/bootstrap.sh                                   # local secrets into infra/secrets (git-ignored)
docker compose -f infra/compose.yaml up --wait          # Postgres, API, Command Center, Envoy, OTel ...
open http://127.0.0.1:3001                              # Command Center
revenueos audit verify                                  # walk the audit hash chain
```

Development: `pnpm install && pnpm build && pnpm test` for TypeScript; `pytest` for Python
(needs Postgres 16; see `.github/workflows/ci.yml`).

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the loop, the component graph and data
flow, and [docs/PROGRESS.md](docs/PROGRESS.md) for the fifteen phases and their seals.

## Components

Generated from `config/components.yaml` and `config/sources.yaml`; every repository is pinned
to a commit in [docs/PINS.md](docs/PINS.md). Status: `named` = named in the spec and primary;
`added` = add-on beyond the spec (>= 10k stars); `named-unlicensed` / `named-not-found` = D1
exception, add-on is the official implementation; `native` = built in RevenueOS.

| Service | Purpose | Component | Phase | Named tool / add-on | License | Stars | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C01 orchestrator | Plans, routes models and coordinates agents | agency-agents (framework, primary) | 13 | [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents) | MIT | 168,251 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | agent-skills (tool, specialist) | 13 | [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | MIT | 117,387 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | anthropic-skills-all (tool, specialist) | 13 | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | 194,339 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | astromesh (service, specialist) | 13 | [monaccode/astromesh](https://github.com/monaccode/astromesh); add-on: [BerriAI/litellm](https://github.com/BerriAI/litellm) | Apache-2.0 + MIT | 39, 63,242 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | autogen-ag2 (framework, specialist) | 13 | [microsoft/autogen](https://github.com/microsoft/autogen), [ag2ai/ag2](https://github.com/ag2ai/ag2) | MIT + Apache-2.0 | 61,814, 5,063 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | biro (service, specialist) | 13 | —; add-on: [paperclipai/paperclip](https://github.com/paperclipai/paperclip) | MIT | 113,796 | named-not-found |
| C01 orchestrator | Plans, routes models and coordinates agents | composio (tool, fallback) | 13 | [ComposioHQ/composio](https://github.com/ComposioHQ/composio) | MIT | 31,064 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | crewai (framework, specialist) | 13 | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | MIT | 60,878 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | erebots (service, specialist) | 13 | [aislab-hevs/erebots4.0](https://github.com/aislab-hevs/erebots4.0); add-on: [a2aproject/A2A](https://github.com/a2aproject/A2A) | MIT + Apache-2.0 | n/a, 26,538 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | everything-claude-code (tool, primary) | 13 | [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code) | MIT | n/a | named |
| C01 orchestrator | Plans, routes models and coordinates agents | harness-agent (framework, specialist) | 13 | —; add-on: [letta-ai/letta](https://github.com/letta-ai/letta) | Apache-2.0 | 25,434 | named-not-found |
| C01 orchestrator | Plans, routes models and coordinates agents | harnis (service, specialist) | 13 | [karawash-projects/harnis](https://github.com/karawash-projects/harnis); add-on: [humanlayer/humanlayer](https://github.com/humanlayer/humanlayer), [open-policy-agent/opa](https://github.com/open-policy-agent/opa) | Apache-2.0 | 6, 12,878, 12,470 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | hosted-byok (service, fallback) | 13 | built in RevenueOS | proprietary | — | owner |
| C01 orchestrator | Plans, routes models and coordinates agents | hubzoid (service, specialist) | 13 | [hubzoid/hubzoid](https://github.com/hubzoid/hubzoid); add-on: [openclaw/openclaw](https://github.com/openclaw/openclaw) | Apache-2.0 + MIT | 18, 394,427 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | incagent (service, specialist) | 13 | —; add-on: [getlago/lago](https://github.com/getlago/lago), [documenso/documenso](https://github.com/documenso/documenso) | AGPL-3.0 | 10,842, 15,761 | named-unlicensed |
| C01 orchestrator | Plans, routes models and coordinates agents | langgraph (framework, primary) | 13 | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | MIT | 44,948 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | mattpocock-skills (tool, specialist) | 13 | [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | 324,196 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | model-router (service, primary) | 13 | built in RevenueOS | in-repo | — | native |
| C01 orchestrator | Plans, routes models and coordinates agents | nextcloud (service, primary) | 13 | [nextcloud/server](https://github.com/nextcloud/server) | AGPL-3.0 | 37,511 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | official-mcp-servers (tool, primary) | 13 | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | MIT | 91,982 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | ollama (service, primary) | 13 | [ollama/ollama](https://github.com/ollama/ollama) | MIT | 186,934 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | omnigent (framework, primary) | 13 | [omnigent-ai/omnigent](https://github.com/omnigent-ai/omnigent) | Apache-2.0 | 11,377 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | richdocuments (service, specialist) | 13 | [nextcloud/richdocuments](https://github.com/nextcloud/richdocuments) | AGPL-3.0 | 459 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | superpowers (tool, specialist) | 13 | [obra/superpowers](https://github.com/obra/superpowers) | MIT | 317,455 | named |
| C01 orchestrator | Plans, routes models and coordinates agents | vllm (service, primary) | 13 | [vllm-project/vllm](https://github.com/vllm-project/vllm) | Apache-2.0 | 96,915 | named |
| C02 runtime-omni | Computer and browser use for agents | ambient-watchers (agent, specialist) | 3 | built in RevenueOS | in-repo | — | native |
| C02 runtime-omni | Computer and browser use for agents | browser-use (agent, primary) | 13 (ADR-0002) | [browser-use/browser-use](https://github.com/browser-use/browser-use) | MIT | 120,984 | named |
| C02 runtime-omni | Computer and browser use for agents | magenticlite (agent, specialist) | 13 (ADR-0002) | [microsoft/magentic-ui](https://github.com/microsoft/magentic-ui) | MIT | 10,117 | named |
| C02 runtime-omni | Computer and browser use for agents | omnipilot (agent, primary) | 3 | [xrchris7/OmniPilot](https://github.com/xrchris7/OmniPilot); add-on: [trycua/cua](https://github.com/trycua/cua) | MIT | 2, 32,334 | named |
| C02 runtime-omni | Computer and browser use for agents | openclaw-heartbeat (agent, specialist) | 13 (ADR-0002) | [openclaw/openclaw](https://github.com/openclaw/openclaw) | MIT | 394,427 | named |
| C02 runtime-omni | Computer and browser use for agents | playwright (tool, primary) | 3 | —; add-on: [microsoft/playwright](https://github.com/microsoft/playwright) | Apache-2.0 | 100,148 | added |
| C02 runtime-omni | Computer and browser use for agents | playwright-mcp (tool, primary) | 3 | [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | Apache-2.0 | 39,621 | named |
| C03 runtime-os | Sandboxed OS runtime (COW workspace, quotas) | aegis-os (service, primary) | 3 | [heurion-org/aegis-os](https://github.com/heurion-org/aegis-os), [containers/bubblewrap](https://github.com/containers/bubblewrap); add-on: [google/gvisor](https://github.com/google/gvisor), [firecracker-microvm/firecracker](https://github.com/firecracker-microvm/firecracker) | Apache-2.0 + LGPL-2.1 | 1, 9,486, 20,000, 38,015 | named |
| C03 runtime-os | Sandboxed OS runtime (COW workspace, quotas) | nava (framework, primary) | 3 | built in RevenueOS ([ADR-0001](docs/adr/ADR-0001-nava-vs-openhands.md)); fallback candidate (agent loop only): [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | in-repo | 93,455 | named-not-found |
| C03 runtime-os | Sandboxed OS runtime (COW workspace, quotas) | openmuse (service, primary) | 3 | —; add-on: [microsoft/playwright](https://github.com/microsoft/playwright), [novnc/noVNC](https://github.com/novnc/noVNC) | Apache-2.0 + MPL-2.0 | 100,148, 14,204 | named-unlicensed |
| C04 discovery | Finds, vets and registers MCP tools | agent-discover (service, primary) | 4 | [keshrath/agent-discover](https://github.com/keshrath/agent-discover); add-on: [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) | MIT + Apache-2.0 | 7, 28,417 | named |
| C04 discovery | Finds, vets and registers MCP tools | forage (service, primary) | 4 | —; add-on: [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) | Apache-2.0 | 28,417 | named-not-found |
| C04 discovery | Finds, vets and registers MCP tools | mcpfinder (tool, specialist) | 4 | [mcpfinder/mcpfinder](https://github.com/mcpfinder/mcpfinder); add-on: [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers), [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | AGPL-3.0 + MIT | 14, 97,691, 91,982 | named |
| C04 discovery | Finds, vets and registers MCP tools | mcptoon (tool, specialist) | 4 | [activeing123/mcptoon](https://github.com/activeing123/mcptoon); add-on: [activepieces/activepieces](https://github.com/activepieces/activepieces) | Apache-2.0 + MIT | 430, 25,523 | named |
| C05 identity | Per-agent email, phone, calendar and browser identity | agenticmail (service, primary) | 2 | [agenticmail/agenticmail](https://github.com/agenticmail/agenticmail) | MIT | 254 | named |
| C05 identity | Per-agent email, phone, calendar and browser identity | agentmail (service, fallback) | 2 | built in RevenueOS | proprietary | — | owner |
| C05 identity | Per-agent email, phone, calendar and browser identity | allmail-mcp (tool, primary) | 2 | —; add-on: [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) | Apache-2.0 | 28,417 | named-not-found |
| C05 identity | Per-agent email, phone, calendar and browser identity | browser-profiles (service, primary) | 2 | built in RevenueOS | in-repo | — | native |
| C05 identity | Per-agent email, phone, calendar and browser identity | browser-use-cloud (service, fallback) | 2 | built in RevenueOS | proprietary | — | owner |
| C05 identity | Per-agent email, phone, calendar and browser identity | imapi (tool, fallback) | 2 | built in RevenueOS | proprietary | — | owner |
| C05 identity | Per-agent email, phone, calendar and browser identity | leads-agent (agent, primary) | 2 | built in RevenueOS | in-repo | — | native |
| C05 identity | Per-agent email, phone, calendar and browser identity | livekit (service, primary) | 2 | —; add-on: [livekit/livekit](https://github.com/livekit/livekit) | Apache-2.0 | 22,206 | added |
| C05 identity | Per-agent email, phone, calendar and browser identity | livekit-agents (agent, primary) | 2 | —; add-on: [livekit/agents](https://github.com/livekit/agents) | Apache-2.0 | 15,220 | added |
| C05 identity | Per-agent email, phone, calendar and browser identity | stalwart-mail (service, primary) | 2 | [stalwartlabs/stalwart](https://github.com/stalwartlabs/stalwart) | AGPL-3.0 | 15,923 | named |
| C06 pm | Breaks projects into tracked tasks | agentic-pm (agent, primary) | 5 | [sdi2200262/agentic-project-management](https://github.com/sdi2200262/agentic-project-management); add-on: [github/spec-kit](https://github.com/github/spec-kit) | MPL-2.0 + MIT | 2,453, 149,752 | named |
| C06 pm | Breaks projects into tracked tasks | fist-mbt (agent, specialist) | 5 | [vicTop-cw/FIST-Mbt](https://github.com/vicTop-cw/FIST-Mbt); add-on: [temporalio/temporal](https://github.com/temporalio/temporal) | Apache-2.0 + MIT | 1, 24,396 | named |
| C06 pm | Breaks projects into tracked tasks | gsd-pi (agent, specialist) | 5 | [gsd-build/gsd-2](https://github.com/gsd-build/gsd-2); add-on: [temporalio/temporal](https://github.com/temporalio/temporal) | MIT | 7,740, 24,396 | named |
| C06 pm | Breaks projects into tracked tasks | llm-tracker (service, specialist) | 5 | built in RevenueOS | in-repo | — | native |
| C06 pm | Breaks projects into tracked tasks | mission-control (service, primary) | 5 | [builderz-labs/mission-control](https://github.com/builderz-labs/mission-control); add-on: [paperclipai/paperclip](https://github.com/paperclipai/paperclip) | MIT | 6,491, 113,796 | named |
| C06 pm | Breaks projects into tracked tasks | piyaz (service, specialist) | 5 | [FrkAk/piyaz](https://github.com/FrkAk/piyaz); add-on: [makeplane/plane](https://github.com/makeplane/plane) | AGPL-3.0 | 200, 62,433 | named |
| C06 pm | Breaks projects into tracked tasks | planning-with-files (tool, specialist) | 5 | [OthmanAdi/planning-with-files](https://github.com/OthmanAdi/planning-with-files) | MIT | 28,052 | named |
| C07 research / scrape | Web research and data extraction | agent-reach (tool, primary) | 7 | [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) | MIT | 111,707 | named |
| C07 research / scrape | Web research and data extraction | api-anything (tool, fallback-extractor) | 7 | [goodnight000/api-anything](https://github.com/goodnight000/api-anything) | MIT | 3,177 | named |
| C07 research / scrape | Web research and data extraction | crawl4ai (tool, primary) | 7 | —; add-on: [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) | Apache-2.0 | 87,341 | added |
| C07 research / scrape | Web research and data extraction | crawlee (tool, specialist) | 7 | —; add-on: [apify/crawlee](https://github.com/apify/crawlee) | Apache-2.0 | 26,443 | added |
| C07 research / scrape | Web research and data extraction | dataforge (tool, specialist) | 7 | built in RevenueOS | in-repo | — | native |
| C07 research / scrape | Web research and data extraction | easyspider (tool, specialist) | 7 | [NaiboWang/EasySpider](https://github.com/NaiboWang/EasySpider) | AGPL-3.0 | 44,791 | named |
| C07 research / scrape | Web research and data extraction | firecrawl (tool, primary) | 7 | [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl) | AGPL-3.0 | 201,670 | named |
| C07 research / scrape | Web research and data extraction | keelead (tool, experimental) | 7 | [Atum246/keelead](https://github.com/Atum246/keelead) | MIT | 54 | experimental |
| C07 research / scrape | Web research and data extraction | maxun (tool, specialist) | 7 | —; add-on: [getmaxun/maxun](https://github.com/getmaxun/maxun) | AGPL-3.0 | 18,382 | added |
| C07 research / scrape | Web research and data extraction | openbusiness (agent, primary) | 7 | [wanikua/OpenBusiness](https://github.com/wanikua/OpenBusiness); add-on: [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | MIT + Apache-2.0 | 12, 30,679 | named |
| C07 research / scrape | Web research and data extraction | opengtm (tool, specialist) | 7 | [debpalash/OpenGTM](https://github.com/debpalash/OpenGTM) | AGPL-3.0 | 110 | named |
| C07 research / scrape | Web research and data extraction | scrapegraph-ai (agent, specialist) | 7 | —; add-on: [ScrapeGraphAI/Scrapegraph-ai](https://github.com/ScrapeGraphAI/Scrapegraph-ai) | MIT | 32,773 | added |
| C07 research / scrape | Web research and data extraction | scrapling (tool, primary) | 7 | —; add-on: [D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) | BSD-3-Clause | 102,678 | added |
| C07 research / scrape | Web research and data extraction | scrapy (tool, specialist) | 7 | —; add-on: [scrapy/scrapy](https://github.com/scrapy/scrapy) | BSD-3-Clause | 65,383 | added |
| C07 research / scrape | Web research and data extraction | searxng (tool, primary) | 7 | [searxng/searxng](https://github.com/searxng/searxng) | AGPL-3.0 | 39,540 | named |
| C07 research / scrape | Web research and data extraction | sec-edgar (tool, primary) | 7 | built in RevenueOS | public-data | — | owner |
| C07 research / scrape | Web research and data extraction | tavily (tool, fallback) | 7 | built in RevenueOS | proprietary | — | owner |
| C08 web | Builds and design-gates websites | astryx (tool, primary) | 9 | [meta/astryx](https://github.com/meta/astryx) | MIT | 27,736 | named |
| C08 web | Builds and design-gates websites | baseline-ui (tool, specialist) | 9 | [ibelick/ui-skills](https://github.com/ibelick/ui-skills) | MIT | 11,054 | named |
| C08 web | Builds and design-gates websites | chrome-devtools-mcp (tool, primary) | 9 | [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) | Apache-2.0 | 55,878 | named |
| C08 web | Builds and design-gates websites | deepagents-open-lovable (agent, specialist) | 9 | —; add-on: [firecrawl/open-lovable](https://github.com/firecrawl/open-lovable), [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) | MIT | 28,909, 31,279 | named-unlicensed |
| C08 web | Builds and design-gates websites | design-linter (tool, primary) | 9 | —; add-on: [GoogleChrome/lighthouse](https://github.com/GoogleChrome/lighthouse) | Apache-2.0 | 31,079 | named-not-found |
| C08 web | Builds and design-gates websites | frontend-design-skill (tool, primary) | 9 | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | 194,339 | named |
| C08 web | Builds and design-gates websites | nexity (agent, specialist) | 9 | [Pagepro/nexity](https://github.com/Pagepro/nexity), [sanity-io/sanity](https://github.com/sanity-io/sanity); add-on: [payloadcms/payload](https://github.com/payloadcms/payload) | MIT | 26, 6,394, 45,811 | named |
| C08 web | Builds and design-gates websites | open-design (service, primary) | 9 | [nexu-io/open-design](https://github.com/nexu-io/open-design) | Apache-2.0 | 107,601 | named |
| C08 web | Builds and design-gates websites | open-pages (agent, primary) | 9 | —; add-on: [dyad-sh/dyad](https://github.com/dyad-sh/dyad) | Apache-2.0 | 22,296 | named-not-found |
| C08 web | Builds and design-gates websites | syntheon (agent, specialist) | 9 | —; add-on: [dyad-sh/dyad](https://github.com/dyad-sh/dyad) | Apache-2.0 | 22,296 | named-unlicensed |
| C08 web | Builds and design-gates websites | tastemaker (tool, primary) | 9 | [Harrypatria/tastemaker](https://github.com/Harrypatria/tastemaker) | MIT | 5 | named |
| C08 web | Builds and design-gates websites | ui-ux-pro-max (tool, primary) | 9 | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | MIT | 149,276 | named |
| C09 social | Social publishing and inbox | chatwoot (service, primary) | 10 | —; add-on: [chatwoot/chatwoot](https://github.com/chatwoot/chatwoot) | MIT | 39,858 | added |
| C09 social | Social publishing and inbox | openwa (service, secondary) | 10 | [rmyndharis/OpenWA](https://github.com/rmyndharis/OpenWA) | MIT | 16,840 | named |
| C09 social | Social publishing and inbox | postiz (tool, secondary) | 10 | [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | AGPL-3.0 | 41,574 | named |
| C09 social | Social publishing and inbox | postmill-ai (tool, specialist) | 10 | [postmill-ai/postmill-app](https://github.com/postmill-ai/postmill-app) | AGPL-3.0 | 315 | named |
| C09 social | Social publishing and inbox | social0 (tool, primary) | 10 | [Abhishek-B-R/social0-oss](https://github.com/Abhishek-B-R/social0-oss) | AGPL-3.0 | 4 | named |
| C10 marketing | Email marketing, ads and lead pipeline | claude-ads (tool, primary) | 10 | [AgriciDaniel/claude-ads](https://github.com/AgriciDaniel/claude-ads) | MIT | 11,019 | named |
| C10 marketing | Email marketing, ads and lead pipeline | google-ads-mcp (tool, primary) | 10 | [googleads/google-ads-mcp](https://github.com/googleads/google-ads-mcp) | Apache-2.0 | 1,176 | named |
| C10 marketing | Email marketing, ads and lead pipeline | helio (service, specialist) | 10 | [achref-soua/helio](https://github.com/achref-soua/helio); add-on: [PostHog/posthog](https://github.com/PostHog/posthog) | AGPL-3.0 + MIT | 24, 40,777 | named |
| C10 marketing | Email marketing, ads and lead pipeline | listmonk (service, primary) | 10 | —; add-on: [knadh/listmonk](https://github.com/knadh/listmonk) | AGPL-3.0 | 24,292 | added |
| C10 marketing | Email marketing, ads and lead pipeline | mautic (service, primary) | 10 | [mautic/mautic](https://github.com/mautic/mautic) | GPL-3.0 | 10,985 | named |
| C10 marketing | Email marketing, ads and lead pipeline | mjml (tool, primary) | 10 | —; add-on: [mjmlio/mjml](https://github.com/mjmlio/mjml) | MIT | 18,295 | added |
| C10 marketing | Email marketing, ads and lead pipeline | netsendo (service, specialist) | 10 | —; add-on: [knadh/listmonk](https://github.com/knadh/listmonk) | AGPL-3.0 | 24,292 | named-unlicensed |
| C10 marketing | Email marketing, ads and lead pipeline | nocodb (service, primary) | 10 | —; add-on: [teableio/teable](https://github.com/teableio/teable) | AGPL-3.0 | 21,982 | named-unlicensed |
| C10 marketing | Email marketing, ads and lead pipeline | postal (service, primary) | 10 | —; add-on: [postalserver/postal](https://github.com/postalserver/postal) | MIT | 16,956 | added |
| C10 marketing | Email marketing, ads and lead pipeline | react-email (tool, specialist) | 10 | —; add-on: [resend/react-email](https://github.com/resend/react-email) | MIT | 19,936 | added |
| C10 marketing | Email marketing, ads and lead pipeline | twenty (service, primary) | 10 | [twentyhq/twenty](https://github.com/twentyhq/twenty) | AGPL-3.0 | 60,918 | named |
| C10 marketing | Email marketing, ads and lead pipeline | univer (service, specialist) | 10 | [dream-num/univer](https://github.com/dream-num/univer) | Apache-2.0 | 24,243 | named |
| C11 qc | Verification oracles and QC records | evalforge (service, primary) | 8 | [heManKuMAR6/evalforge](https://github.com/heManKuMAR6/evalforge); add-on: [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | MIT | 9, 27,159 | named |
| C11 qc | Verification oracles and QC records | gitreins (service, primary) | 8 | [totalwindupflightsystems/gitreins](https://github.com/totalwindupflightsystems/gitreins); add-on: [pre-commit/pre-commit](https://github.com/pre-commit/pre-commit) | MIT | 1, 15,695 | named |
| C11 qc | Verification oracles and QC records | verifier-agent (agent, primary) | 8 | built in RevenueOS | in-repo | — | native |
| C11 qc | Verification oracles and QC records | veripipe (service, primary) | 8 | [zhangyy0423/veripipe](https://github.com/zhangyy0423/veripipe) | MIT | 1 | named |
| C12 insight | Analytics over verified evidence | duckdb (service, primary) | 11 | [duckdb/duckdb](https://github.com/duckdb/duckdb) | MIT | 43,055 | named |
| C12 insight | Analytics over verified evidence | plausible (service, primary) | 11 | [plausible/analytics](https://github.com/plausible/analytics) | AGPL-3.0 | 29,844 | named |
| C12 insight | Analytics over verified evidence | postgres (service, primary) | 11 | [postgres/postgres](https://github.com/postgres/postgres) | PostgreSQL | 22,820 | named |
| C12 insight | Analytics over verified evidence | tares (service, primary) | 11 | [glassflow/tares](https://github.com/glassflow/tares); add-on: [duckdb/duckdb](https://github.com/duckdb/duckdb) | MIT | 47, 43,055 | named |
| C12 insight | Analytics over verified evidence | umami (service, primary) | 11 | —; add-on: [umami-software/umami](https://github.com/umami-software/umami) | MIT | 40,139 | added |
| C13 learning | Skill learning with canary and holdout | agentjet (service, specialist) | 12 | [modelscope/AgentJet](https://github.com/modelscope/AgentJet); add-on: [verl-project/verl](https://github.com/verl-project/verl) | Apache-2.0 | 243, 24,229 | named |
| C13 learning | Skill learning with canary and holdout | curio (agent, specialist) | 12 | —; add-on: [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | Apache-2.0 | 30,679 | named-not-found |
| C13 learning | Skill learning with canary and holdout | myelinate (service, primary) | 12 | [notaaaronfr/myelinate](https://github.com/notaaaronfr/myelinate); add-on: [mem0ai/mem0](https://github.com/mem0ai/mem0) | MIT + Apache-2.0 | 7, 68,950 | named |
| C13 learning | Skill learning with canary and holdout | openforgerl (service, specialist) | 12 | —; add-on: [OpenRLHF/OpenRLHF](https://github.com/OpenRLHF/OpenRLHF) | Apache-2.0 | 10,152 | named-unlicensed |
| C13 learning | Skill learning with canary and holdout | openspace (service, specialist) | 12 | [HKUDS/OpenSpace](https://github.com/HKUDS/OpenSpace); add-on: [letta-ai/letta](https://github.com/letta-ai/letta) | MIT + Apache-2.0 | n/a, 25,434 | named |
| C13 learning | Skill learning with canary and holdout | orchard (service, specialist) | 12 | —; add-on: [huggingface/trl](https://github.com/huggingface/trl) | Apache-2.0 | 19,734 | named-not-found |
| C13 learning | Skill learning with canary and holdout | pgvector (service, specialist) | 12 | —; add-on: [pgvector/pgvector](https://github.com/pgvector/pgvector) | PostgreSQL | 23,678 | added |
| C13 learning | Skill learning with canary and holdout | qdrant (service, primary) | 12 | —; add-on: [qdrant/qdrant](https://github.com/qdrant/qdrant) | Apache-2.0 | 35,550 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | chatterbox (tool, primary) | 6 | —; add-on: [resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox) | MIT | 27,809 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | comfyui (service, primary) | 6 | —; add-on: [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI) | GPL-3.0 | 146,764 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | diffusers (tool, specialist) | 6 | —; add-on: [huggingface/diffusers](https://github.com/huggingface/diffusers) | Apache-2.0 | 34,919 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | ffmpeg (tool, primary) | 6 | —; add-on: [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) | LGPL-2.1 | 67,240 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | invokeai (service, primary) | 6 | —; add-on: [invoke-ai/InvokeAI](https://github.com/invoke-ai/InvokeAI) | Apache-2.0 | 29,089 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | losslesscut (tool, specialist) | 6 | —; add-on: [mifi/lossless-cut](https://github.com/mifi/lossless-cut) | GPL-2.0 | 46,025 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | ltx-video (tool, specialist) | 6 | —; add-on: [Lightricks/LTX-Video](https://github.com/Lightricks/LTX-Video) | Apache-2.0 | 11,383 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | moneyprinterturbo (agent, specialist) | 6 | —; add-on: [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | MIT | 143,459 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | moviepy (tool, primary) | 6 | —; add-on: [Zulko/moviepy](https://github.com/Zulko/moviepy) | MIT | 15,150 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | obs-studio (tool, specialist) | 6 | —; add-on: [obsproject/obs-studio](https://github.com/obsproject/obs-studio) | GPL-2.0 | 79,539 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | outreach (tool, primary) | 6 | built in RevenueOS | owner | — | owner |
| C14 media / scrape / outreach | Media generation, scraping and outreach | penpot (service, primary) | 6 | —; add-on: [penpot/penpot](https://github.com/penpot/penpot) | MPL-2.0 | 62,345 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | photo-generator (tool, primary) | 6 | built in RevenueOS | owner | — | owner |
| C14 media / scrape / outreach | Media generation, scraping and outreach | rembg (tool, primary) | 6 | —; add-on: [danielgatis/rembg](https://github.com/danielgatis/rembg) | MIT | 25,459 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | scraper (tool, primary) | 6 | built in RevenueOS | owner | — | owner |
| C14 media / scrape / outreach | Media generation, scraping and outreach | shotcut (tool, specialist) | 6 | —; add-on: [mltframework/shotcut](https://github.com/mltframework/shotcut) | GPL-3.0 | 15,678 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | upscayl (tool, primary) | 6 | —; add-on: [upscayl/upscayl](https://github.com/upscayl/upscayl) | AGPL-3.0 | 52,545 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | video-use (agent, primary) | 6 | —; add-on: [browser-use/video-use](https://github.com/browser-use/video-use) | MIT | 31,038 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | wan-video (tool, primary) | 6 | —; add-on: [Wan-Video/Wan2.2](https://github.com/Wan-Video/Wan2.2) | Apache-2.0 | 18,643 | added |
| C14 media / scrape / outreach | Media generation, scraping and outreach | whisperx (tool, primary) | 6 | —; add-on: [m-bain/whisperX](https://github.com/m-bain/whisperX) | BSD-2-Clause | 25,256 | added |
| C15 research (parity) | Open-source parity tools (PDF, docs) | docling (tool, primary) | 7 | —; add-on: [docling-project/docling](https://github.com/docling-project/docling) | MIT | 70,567 | added |
| C15 research (parity) | Open-source parity tools (PDF, docs) | nib (tool, primary) | 7 | [daniel-alexander4/nib](https://github.com/daniel-alexander4/nib); add-on: [Stirling-Tools/Stirling-PDF](https://github.com/Stirling-Tools/Stirling-PDF), [ocrmypdf/OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) | AGPL-3.0 + MIT + MPL-2.0 | 10, 96,552, 35,314 | named |
| C15 research (parity) | Open-source parity tools (PDF, docs) | paddleocr (tool, specialist) | 7 | —; add-on: [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Apache-2.0 | 92,693 | added |
| C15 research (parity) | Open-source parity tools (PDF, docs) | pdfcraft (tool, secondary) | 7 | [storytold/pdfcraft](https://github.com/storytold/pdfcraft) | Apache-2.0 | 20,674 | named |
| C16 command-center | Operator UI and live task view | command-center (service, primary) | 14 | built in RevenueOS | in-repo | — | native |
| C17 infra (sandbox, egress, secrets) | Sandbox, egress proxy and secrets | autosecscan (service, primary) | 2 | [jhammant/AutoSecScan](https://github.com/jhammant/AutoSecScan) | MIT | 1 | named |
| C17 infra (sandbox, egress, secrets) | Sandbox, egress proxy and secrets | egress-proxy (service, primary) | 2 | [envoyproxy/envoy](https://github.com/envoyproxy/envoy) | Apache-2.0 | n/a | named |
| C17 infra (sandbox, egress, secrets) | Sandbox, egress proxy and secrets | open-kritt (service, primary) | 2 | [Kritt-ai/open-kritt](https://github.com/Kritt-ai/open-kritt) | AGPL-3.0 | 2,430 | named |
| C17 infra (sandbox, egress, secrets) | Sandbox, egress proxy and secrets | openhack (service, primary) | 2 | [openhackai/OpenHack](https://github.com/openhackai/OpenHack) | MIT | 442 | named |
| C17 infra (sandbox, egress, secrets) | Sandbox, egress proxy and secrets | secrets-vault (service, primary) | 2 | —; add-on: [Infisical/infisical](https://github.com/Infisical/infisical) | MIT | 30,509 | added |
| C17 infra (sandbox, egress, secrets) | Sandbox, egress proxy and secrets | strix (service, primary) | 2 | [usestrix/strix](https://github.com/usestrix/strix) | Apache-2.0 | 75,506 | named |
| C17 infra (sandbox, egress, secrets) | Sandbox, egress proxy and secrets | vulnhunter (service, primary) | 2 | [capitalone/VulnHunter](https://github.com/capitalone/VulnHunter) | Apache-2.0 | 1,171 | named |
| C18 infra (observability) | Traces, metrics and logs | observability (service, primary) | 1 | [open-telemetry/opentelemetry-collector-contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib); add-on: [SigNoz/signoz](https://github.com/SigNoz/signoz), [prometheus/prometheus](https://github.com/prometheus/prometheus), [jaegertracing/jaeger](https://github.com/jaegertracing/jaeger) | Apache-2.0 + MIT | 5,050, 32,638, 67,599, 23,409 | named |

## The lead pipeline

Ten stages, L0 ingest to L9 feedback: identity resolution, a contact waterfall, deterministic
email verification, labeled enrichment, deterministic ICP scoring, personalization, routing to
Twenty CRM, approved outreach from the agent's own identity, and feedback into learning. Each row
is a task, not a cell. Details: [docs/LEAD_PIPELINE.md](docs/LEAD_PIPELINE.md).

## Security

- **Sandbox:** every agent command runs under Bubblewrap with a copy-on-write workspace, no
  host mounts, a read-only root, no network of its own, and CPU/memory/process/time quotas;
  destructive commands are refused in every mode, YOLO included.
- **Egress:** the sandbox's only way out is a per-session socket whose forwarder signs the
  agent, task and session; Envoy and egress-authz allow only that agent's or task's hosts
  (Postgres rules), inject secrets by reference (even the agent's own inbox key), and log
  every decision.
- **Identity:** each agent has its own mailbox (AgenticMail on Stalwart), calendar and private
  browser profile; human browser profiles are refused.
- **Approvals:** bound to the exact arguments, the task and the tool; expiring, single-use,
  requester cannot approve; role-based API; every refusal logged with its reason.
- **Scanners:** standing `security` workflow (D10): AutoSecScan on every commit, OpenHack on
  every PR, open-kritt on release branches, VulnHunter before deploys, Strix on generated
  sites. A scan that did not run records DO_NOT_FILE and fails the check; it never passes.
- **Threat model:** [docs/THREATMODEL.md](docs/THREATMODEL.md); completed in Phase 15.

## Documentation

| Document | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Loop, component graph, data flow |
| [docs/PROGRESS.md](docs/PROGRESS.md) | Phase seals, tests, coverage, gaps fixed |
| [docs/PINS.md](docs/PINS.md) | Every upstream: URL, commit, license, stars, date |
| [docs/POLICY.md](docs/POLICY.md) | Selection, install, egress, approval and secret policy; D1/D3 |
| [docs/PARITY.md](docs/PARITY.md) | Open-source parity library and correction record |
| [docs/LEAD_PIPELINE.md](docs/LEAD_PIPELINE.md) | Addendum C waterfall |
| [docs/THREATMODEL.md](docs/THREATMODEL.md) | Threats, named controls, test that proves each |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Operating, recovering and verifying the stack |
| [docs/TASK_CLASSES.md](docs/TASK_CLASSES.md) | Task classes, risk classes and their oracles |
| [docs/LEARNING.md](docs/LEARNING.md) | Learning loop: canary, holdout, promotion, rollback |
| [docs/reviews/](docs/reviews/) | Phase gate reviews, acceptance logs, Q-gate results |
| [evals/README.md](evals/README.md) | Evaluation assets (Phase 8) |

## Correction record

`chrislgarry/Apollo-11` is the NASA Apollo Guidance Computer source code, not a lead generator,
and is not integrated. Apollo.io has no open-source repository. Lead generation is the Addendum C
waterfall.

## License and pins

Third-party projects keep their own licenses; see [docs/PINS.md](docs/PINS.md) for every
repository, commit, license, star count and check date, and the license-scope notes for
open-core projects.
