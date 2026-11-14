# Pins

Every upstream behind RevenueOS, checked 2026-11-14. Governing rule: RevenueOS v3 (R03/R04: named components are primary; extensions allowed).
Machine-readable source with full commit SHAs: `config/sources.yaml`. CI fails on any
unpinned repo, unapproved license, extension under 10,000 stars, or
named component without a pinned primary.

**Totals:** 54 named (primary), 43 added extensions, 0 built in-repo,
6 named but not open-source licensed, 10 named but with no public repo.

## Blocked named components (owner action needed)

These are named in the spec, so they cannot be silently replaced (R04). Each one's
capability is provided meanwhile by the extensions listed, and is flagged in the build.

| Component | Status | Why | Capability provided meanwhile by |
| --- | --- | --- | --- |
| biro | named-not-found | no public repository for Biro | paperclipai/paperclip |
| harness-agent | named-not-found | OrcaKit harness-agent is not public (OrcaKit org exists; repo not accessible) | letta-ai/letta |
| incagent | named-unlicensed | incagent/incagent has no license file; using it would be copyright infringement | getlago/lago, documenso/documenso |
| nava | named-not-found | no public repository for NAVA | OpenHands/OpenHands |
| openmuse | named-unlicensed | diggerhq/openmuse has no license file | microsoft/playwright, novnc/noVNC |
| forage | named-not-found | no public repository for Forage | PrefectHQ/fastmcp |
| allmail-mcp | named-not-found | no public repository for allmail-mcp | PrefectHQ/fastmcp |
| llm-tracker | named-not-found | no public repository matching the spec's llm-tracker | built in-repo |
| deepagents-open-lovable | named-unlicensed | emanueleielo/deepagents-open-lovable has no license file | firecrawl/open-lovable, langchain-ai/deepagents |
| design-linter | named-not-found | agent-design-skills has no public repository | GoogleChrome/lighthouse |
| open-pages | named-not-found | no public repository for open-pages | dyad-sh/dyad |
| syntheon | named-unlicensed | cognis-digital/syntheon uses the Cognis Open Collaboration License, not an OSI license | dyad-sh/dyad |
| netsendo | named-unlicensed | NetSendo/NetSendo ships under a proprietary end-user license agreement | knadh/listmonk |
| curio | named-not-found | no public repository for Curio | assafelovic/gpt-researcher |
| openforgerl | named-unlicensed | the only public OpenForgeRL repo has no license file | OpenRLHF/OpenRLHF |
| orchard | named-not-found | no public repository for Orchard | huggingface/trl |

To unblock: for `named-unlicensed`, the owner of that repo must add an open-source
license (or you obtain written permission); for `named-not-found`, send the repo link.

## All components

| Spec | Component | Status | Named (primary) | Extensions |
| --- | --- | --- | --- | --- |
| C01 | astromesh | named | [monaccode/astromesh](https://github.com/monaccode/astromesh) Apache-2.0 · 39★ · `e80ed42583` | [BerriAI/litellm](https://github.com/BerriAI/litellm) MIT * · 63,242★ · `27c796c412` |
| C01 | autogen-ag2 | named | [microsoft/autogen](https://github.com/microsoft/autogen) MIT * · 61,814★ · `8390985108`<br>[ag2ai/ag2](https://github.com/ag2ai/ag2) Apache-2.0 · 5,063★ · `fb3061e061` | — |
| C01 | biro | named-not-found | — | [paperclipai/paperclip](https://github.com/paperclipai/paperclip) MIT · 113,796★ · `c1451814c1` |
| C01 | composio | named | [ComposioHQ/composio](https://github.com/ComposioHQ/composio) MIT · 31,064★ · `fdee759516` | — |
| C01 | crewai | named | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) MIT · 60,878★ · `d7dfa0ef5a` | — |
| C01 | erebots | named | [aislab-hevs/erebots4.0](https://github.com/aislab-hevs/erebots4.0) MIT · ★ n/a · `162c9be94a` | [a2aproject/A2A](https://github.com/a2aproject/A2A) Apache-2.0 · 26,538★ · `4d7cda4b17` |
| C01 | harness-agent | named-not-found | — | [letta-ai/letta](https://github.com/letta-ai/letta) Apache-2.0 · 25,434★ · `8816d3a851` |
| C01 | harnis | named | [karawash-projects/harnis](https://github.com/karawash-projects/harnis) Apache-2.0 · 6★ · `b4077e370b` | [humanlayer/humanlayer](https://github.com/humanlayer/humanlayer) Apache-2.0 · 12,878★ · `b7ad8e1d38`<br>[open-policy-agent/opa](https://github.com/open-policy-agent/opa) Apache-2.0 · 12,470★ · `8d10da6e34` |
| C01 | hubzoid | named | [hubzoid/hubzoid](https://github.com/hubzoid/hubzoid) Apache-2.0 · 18★ · `fc8b6363c3` | [openclaw/openclaw](https://github.com/openclaw/openclaw) MIT · 394,427★ · `c787d0fac8` |
| C01 | incagent | named-unlicensed | — | [getlago/lago](https://github.com/getlago/lago) AGPL-3.0 · 10,842★ · `63d2ddfcf3`<br>[documenso/documenso](https://github.com/documenso/documenso) AGPL-3.0 · 15,761★ · `1e2333d534` |
| C01 | langgraph | named | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) MIT · 44,948★ · `08a2016953` | — |
| C01 | official-mcp-servers | named | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) MIT * · 91,982★ · `e1dc4b18db` | — |
| C01 | ollama | named | [ollama/ollama](https://github.com/ollama/ollama) MIT · 186,934★ · `a5864fcb33` | — |
| C01 | omnigent | named | [omnigent-ai/omnigent](https://github.com/omnigent-ai/omnigent) Apache-2.0 · 11,377★ · `38a65dbdde` | — |
| C01 | vllm | named | [vllm-project/vllm](https://github.com/vllm-project/vllm) Apache-2.0 · 96,915★ · `6f1ec6a4c6` | — |
| C02 | browser-use | named | [browser-use/browser-use](https://github.com/browser-use/browser-use) MIT · 120,984★ · `e717df1839` | — |
| C02 | magenticlite | named | [microsoft/magentic-ui](https://github.com/microsoft/magentic-ui) MIT · 10,117★ · `d3c9d13c39` | — |
| C02 | omnipilot | named | [xrchris7/OmniPilot](https://github.com/xrchris7/OmniPilot) MIT · 2★ · `2e3a6bd02f` | [trycua/cua](https://github.com/trycua/cua) MIT · 32,334★ · `b3dafe7f47` |
| C02 | openclaw-heartbeat | named | [openclaw/openclaw](https://github.com/openclaw/openclaw) MIT · 394,427★ · `c787d0fac8` | — |
| C02 | playwright | added | — | [microsoft/playwright](https://github.com/microsoft/playwright) Apache-2.0 · 100,148★ · `b4d016aadc` |
| C02 | playwright-mcp | named | [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) Apache-2.0 · 39,621★ · `78eca85361` | — |
| C03 | aegis-os | named | [heurion-org/aegis-os](https://github.com/heurion-org/aegis-os) Apache-2.0 * · 1★ · `d9bdfa978d`<br>[containers/bubblewrap](https://github.com/containers/bubblewrap) LGPL-2.1 · 9,486★ · `1fb0aa26d3` | [google/gvisor](https://github.com/google/gvisor) Apache-2.0 · 20,000★ · `e45d53c763`<br>[firecracker-microvm/firecracker](https://github.com/firecracker-microvm/firecracker) Apache-2.0 · 38,015★ · `cc88013ead` |
| C03 | nava | named-not-found | — | [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) MIT · 93,455★ · `830c0459e2` |
| C03 | openmuse | named-unlicensed | — | [microsoft/playwright](https://github.com/microsoft/playwright) Apache-2.0 · 100,148★ · `b4d016aadc`<br>[novnc/noVNC](https://github.com/novnc/noVNC) MPL-2.0 · 14,204★ · `e8b5024d46` |
| C04 | agent-discover | named | [keshrath/agent-discover](https://github.com/keshrath/agent-discover) MIT · 7★ · `c8a48bc739` | [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) Apache-2.0 · 28,417★ · `a8745d61e6` |
| C04 | forage | named-not-found | — | [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) Apache-2.0 · 28,417★ · `a8745d61e6` |
| C04 | mcpfinder | named | [mcpfinder/mcpfinder](https://github.com/mcpfinder/mcpfinder) AGPL-3.0 · 14★ · `4c9e2f421a` | [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) MIT · 97,691★ · `f431a5cd95`<br>[modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) MIT * · 91,982★ · `e1dc4b18db` |
| C04 | mcptoon | named | [activeing123/mcptoon](https://github.com/activeing123/mcptoon) Apache-2.0 · 430★ · `3af4967dd2` | [activepieces/activepieces](https://github.com/activepieces/activepieces) MIT * · 25,523★ · `182b7f2bdc` |
| C05 | agenticmail | named | [agenticmail/agenticmail](https://github.com/agenticmail/agenticmail) MIT · 254★ · `af1e0ef546` | — |
| C05 | allmail-mcp | named-not-found | — | [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) Apache-2.0 · 28,417★ · `a8745d61e6` |
| C05 | livekit | added | — | [livekit/livekit](https://github.com/livekit/livekit) Apache-2.0 · 22,206★ · `fb2044e3c9` |
| C05 | livekit-agents | added | — | [livekit/agents](https://github.com/livekit/agents) Apache-2.0 · 15,220★ · `cbb5770c71` |
| C05 | stalwart-mail | named | [stalwartlabs/stalwart](https://github.com/stalwartlabs/stalwart) AGPL-3.0 · 15,923★ · `e7cde9b3fa` | — |
| C06 | agentic-pm | named | [sdi2200262/agentic-project-management](https://github.com/sdi2200262/agentic-project-management) MPL-2.0 * · 2,453★ · `b88434f081` | [github/spec-kit](https://github.com/github/spec-kit) MIT · 149,752★ · `2ee2b1e800` |
| C06 | fist-mbt | named | [vicTop-cw/FIST-Mbt](https://github.com/vicTop-cw/FIST-Mbt) Apache-2.0 · 1★ · `5ba7123d82` | [temporalio/temporal](https://github.com/temporalio/temporal) MIT · 24,396★ · `170fb83dca` |
| C06 | gsd-pi | named | [gsd-build/gsd-2](https://github.com/gsd-build/gsd-2) MIT * · 7,740★ · `33c00aaffa` | [temporalio/temporal](https://github.com/temporalio/temporal) MIT · 24,396★ · `170fb83dca` |
| C06 | llm-tracker | named-not-found | — | — |
| C06 | mission-control | named | [builderz-labs/mission-control](https://github.com/builderz-labs/mission-control) MIT · 6,491★ · `c1a846fe02` | [paperclipai/paperclip](https://github.com/paperclipai/paperclip) MIT · 113,796★ · `c1451814c1` |
| C06 | piyaz | named | [FrkAk/piyaz](https://github.com/FrkAk/piyaz) AGPL-3.0 · 200★ · `e1ed033e9a` | [makeplane/plane](https://github.com/makeplane/plane) AGPL-3.0 · 62,433★ · `290383d7f9` |
| C07 | crawl4ai | added | — | [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) Apache-2.0 · 87,341★ · `cae74b203a` |
| C07 | crawlee | added | — | [apify/crawlee](https://github.com/apify/crawlee) Apache-2.0 · 26,443★ · `a972548a5f` |
| C07 | firecrawl | named | [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl) AGPL-3.0 · 201,670★ · `71f430a2da` | — |
| C07 | jina-reader | added | — | [jina-ai/reader](https://github.com/jina-ai/reader) Apache-2.0 · 12,256★ · `1574bfd380` |
| C07 | maxun | added | — | [getmaxun/maxun](https://github.com/getmaxun/maxun) AGPL-3.0 · 18,382★ · `99c6bd0d42` |
| C07 | openbusiness | named | [wanikua/OpenBusiness](https://github.com/wanikua/OpenBusiness) MIT · 12★ · `3f9a1bbeda` | [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) Apache-2.0 · 30,679★ · `ddd4db3620` |
| C07 | scrapegraph-ai | added | — | [ScrapeGraphAI/Scrapegraph-ai](https://github.com/ScrapeGraphAI/Scrapegraph-ai) MIT · 32,773★ · `194055e203` |
| C07 | scrapling | added | — | [D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) BSD-3-Clause · 102,678★ · `bb223f2f5f` |
| C07 | scrapy | added | — | [scrapy/scrapy](https://github.com/scrapy/scrapy) BSD-3-Clause · 65,383★ · `e63a574c76` |
| C07 | searxng | named | [searxng/searxng](https://github.com/searxng/searxng) AGPL-3.0 · 39,540★ · `a7128d5d1d` | — |
| C08 | chrome-devtools-mcp | named | [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) Apache-2.0 · 55,878★ · `8ba2ac945e` | — |
| C08 | deepagents-open-lovable | named-unlicensed | — | [firecrawl/open-lovable](https://github.com/firecrawl/open-lovable) MIT · 28,909★ · `806b8072f2`<br>[langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) MIT · 31,279★ · `a93aed4bca` |
| C08 | design-linter | named-not-found | — | [GoogleChrome/lighthouse](https://github.com/GoogleChrome/lighthouse) Apache-2.0 · 31,079★ · `4875928438` |
| C08 | frontend-design-skill | named | [anthropics/skills](https://github.com/anthropics/skills) Apache-2.0 * · 194,339★ · `2c5958ecac` | — |
| C08 | nexity | named | [Pagepro/nexity](https://github.com/Pagepro/nexity) MIT · 26★ · `2097cfb684`<br>[sanity-io/sanity](https://github.com/sanity-io/sanity) MIT · 6,394★ · `08b506252d` | [payloadcms/payload](https://github.com/payloadcms/payload) MIT · 45,811★ · `56033d9561` |
| C08 | open-pages | named-not-found | — | [dyad-sh/dyad](https://github.com/dyad-sh/dyad) Apache-2.0 * · 22,296★ · `a15e23340f` |
| C08 | syntheon | named-unlicensed | — | [dyad-sh/dyad](https://github.com/dyad-sh/dyad) Apache-2.0 * · 22,296★ · `a15e23340f` |
| C08 | tastemaker | named | [Harrypatria/tastemaker](https://github.com/Harrypatria/tastemaker) MIT · 5★ · `921637b69c` | — |
| C08 | ui-ux-pro-max | named | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) MIT · 149,276★ · `6ae86f61f5` | — |
| C09 | chatwoot | added | — | [chatwoot/chatwoot](https://github.com/chatwoot/chatwoot) MIT * · 39,858★ · `1ef1d2b45a` |
| C09 | postiz | named | [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) AGPL-3.0 · 41,574★ · `132859f32d` | — |
| C09 | postmill-ai | named | [postmill-ai/postmill-app](https://github.com/postmill-ai/postmill-app) AGPL-3.0 · 315★ · `e06b4796fe` | — |
| C09 | social0 | named | [Abhishek-B-R/social0-oss](https://github.com/Abhishek-B-R/social0-oss) AGPL-3.0 · 4★ · `217744b511` | — |
| C10 | helio | named | [achref-soua/helio](https://github.com/achref-soua/helio) AGPL-3.0 · 24★ · `63d0cedb21` | [PostHog/posthog](https://github.com/PostHog/posthog) MIT * · 40,777★ · `e060b5d349` |
| C10 | listmonk | added | — | [knadh/listmonk](https://github.com/knadh/listmonk) AGPL-3.0 · 24,292★ · `e735e0b234` |
| C10 | mautic | named | [mautic/mautic](https://github.com/mautic/mautic) GPL-3.0 · 10,985★ · `6711577a1d` | — |
| C10 | mjml | added | — | [mjmlio/mjml](https://github.com/mjmlio/mjml) MIT · 18,295★ · `40ddfbb4c0` |
| C10 | netsendo | named-unlicensed | — | [knadh/listmonk](https://github.com/knadh/listmonk) AGPL-3.0 · 24,292★ · `e735e0b234` |
| C10 | postal | added | — | [postalserver/postal](https://github.com/postalserver/postal) MIT · 16,956★ · `d96eddbade` |
| C10 | react-email | added | — | [resend/react-email](https://github.com/resend/react-email) MIT · 19,936★ · `f27d9e2082` |
| C11 | evalforge | named | [heManKuMAR6/evalforge](https://github.com/heManKuMAR6/evalforge) MIT · 9★ · `7931647894` | [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) MIT · 27,159★ · `45f68f0d77` |
| C11 | gitreins | named | [totalwindupflightsystems/gitreins](https://github.com/totalwindupflightsystems/gitreins) MIT · 1★ · `9e0bf429f2` | [pre-commit/pre-commit](https://github.com/pre-commit/pre-commit) MIT · 15,695★ · `ba5c4209a6` |
| C11 | veripipe | named | [zhangyy0423/veripipe](https://github.com/zhangyy0423/veripipe) MIT · 1★ · `bd557a3b17` | — |
| C12 | duckdb | named | [duckdb/duckdb](https://github.com/duckdb/duckdb) MIT · 43,055★ · `b678afa97b` | — |
| C12 | postgres | named | [postgres/postgres](https://github.com/postgres/postgres) PostgreSQL · 22,820★ · `70c4a57b64` | — |
| C12 | tares | named | [glassflow/tares](https://github.com/glassflow/tares) MIT * · 47★ · `f1b3b23fab` | [duckdb/duckdb](https://github.com/duckdb/duckdb) MIT · 43,055★ · `b678afa97b` |
| C12 | umami | added | — | [umami-software/umami](https://github.com/umami-software/umami) MIT · 40,139★ · `b18d5144df` |
| C13 | agentjet | named | [modelscope/AgentJet](https://github.com/modelscope/AgentJet) Apache-2.0 · 243★ · `25118bbcb3` | [verl-project/verl](https://github.com/verl-project/verl) Apache-2.0 · 24,229★ · `4191e7f910` |
| C13 | curio | named-not-found | — | [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) Apache-2.0 · 30,679★ · `ddd4db3620` |
| C13 | myelinate | named | [notaaaronfr/myelinate](https://github.com/notaaaronfr/myelinate) MIT · 7★ · `f8d20d4f5b` | [mem0ai/mem0](https://github.com/mem0ai/mem0) Apache-2.0 · 68,950★ · `f1791daa86` |
| C13 | openforgerl | named-unlicensed | — | [OpenRLHF/OpenRLHF](https://github.com/OpenRLHF/OpenRLHF) Apache-2.0 · 10,152★ · `26494490bc` |
| C13 | openspace | named | [HKUDS/OpenSpace](https://github.com/HKUDS/OpenSpace) MIT · ★ n/a · `e5a81e7635` | [letta-ai/letta](https://github.com/letta-ai/letta) Apache-2.0 · 25,434★ · `8816d3a851` |
| C13 | orchard | named-not-found | — | [huggingface/trl](https://github.com/huggingface/trl) Apache-2.0 · 19,734★ · `8ad18ec1b6` |
| C13 | pgvector | added | — | [pgvector/pgvector](https://github.com/pgvector/pgvector) PostgreSQL · 23,678★ · `10a73eceef` |
| C13 | qdrant | added | — | [qdrant/qdrant](https://github.com/qdrant/qdrant) Apache-2.0 · 35,550★ · `95d89e5142` |
| C14 | chatterbox | added | — | [resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox) MIT · 27,809★ · `ab55923c27` |
| C14 | comfyui | added | — | [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI) GPL-3.0 · 146,764★ · `eee59185ff` |
| C14 | diffusers | added | — | [huggingface/diffusers](https://github.com/huggingface/diffusers) Apache-2.0 · 34,919★ · `43e30028af` |
| C14 | ffmpeg | added | — | [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) LGPL-2.1 * · 67,240★ · `604ef3784d` |
| C14 | flux | added | — | [black-forest-labs/flux](https://github.com/black-forest-labs/flux) Apache-2.0 * · 26,059★ · `802fb47139` |
| C14 | framepack | added | — | [lllyasviel/FramePack](https://github.com/lllyasviel/FramePack) Apache-2.0 · 17,354★ · `97fe5dbe06` |
| C14 | invokeai | added | — | [invoke-ai/InvokeAI](https://github.com/invoke-ai/InvokeAI) Apache-2.0 · 29,089★ · `48b83d98da` |
| C14 | liveportrait | added | — | [KlingAIResearch/LivePortrait](https://github.com/KlingAIResearch/LivePortrait) MIT * · 19,476★ · `9b294b3d05` |
| C14 | losslesscut | added | — | [mifi/lossless-cut](https://github.com/mifi/lossless-cut) GPL-2.0 · 46,025★ · `4c7ab1cb0c` |
| C14 | ltx-video | added | — | [Lightricks/LTX-Video](https://github.com/Lightricks/LTX-Video) Apache-2.0 * · 11,383★ · `50f0aef129` |
| C14 | moneyprinterturbo | added | — | [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) MIT · 143,459★ · `ce289ffb61` |
| C14 | motion-canvas | added | — | [motion-canvas/motion-canvas](https://github.com/motion-canvas/motion-canvas) MIT · 19,813★ · `7b91435c30` |
| C14 | moviepy | added | — | [Zulko/moviepy](https://github.com/Zulko/moviepy) MIT · 15,150★ · `211e4b15f6` |
| C14 | obs-studio | added | — | [obsproject/obs-studio](https://github.com/obsproject/obs-studio) GPL-2.0 · 79,539★ · `fe1ed7955f` |
| C14 | open-sora | added | — | [hpcaitech/Open-Sora](https://github.com/hpcaitech/Open-Sora) Apache-2.0 · 29,934★ · `7ad6a96a13` |
| C14 | penpot | added | — | [penpot/penpot](https://github.com/penpot/penpot) MPL-2.0 · 62,345★ · `9c5260314a` |
| C14 | rembg | added | — | [danielgatis/rembg](https://github.com/danielgatis/rembg) MIT · 25,459★ · `991927b776` |
| C14 | shotcut | added | — | [mltframework/shotcut](https://github.com/mltframework/shotcut) GPL-3.0 · 15,678★ · `f291f3f253` |
| C14 | upscayl | added | — | [upscayl/upscayl](https://github.com/upscayl/upscayl) AGPL-3.0 · 52,545★ · `a00d55fee9` |
| C14 | video-use | added | — | [browser-use/video-use](https://github.com/browser-use/video-use) MIT · 31,038★ · `43cfc56683` |
| C14 | wan-video | added | — | [Wan-Video/Wan2.2](https://github.com/Wan-Video/Wan2.2) Apache-2.0 · 18,643★ · `1ea34ff48f` |
| C14 | whisperx | added | — | [m-bain/whisperX](https://github.com/m-bain/whisperX) BSD-2-Clause · 25,256★ · `b904f02b7e` |
| C15 | docling | added | — | [docling-project/docling](https://github.com/docling-project/docling) MIT · 70,567★ · `5e600e8d37` |
| C15 | nib | named | [daniel-alexander4/nib](https://github.com/daniel-alexander4/nib) AGPL-3.0 · 10★ · `1f23f70bb2` | [Stirling-Tools/Stirling-PDF](https://github.com/Stirling-Tools/Stirling-PDF) MIT * · 96,552★ · `ad38e38ce9`<br>[ocrmypdf/OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) MPL-2.0 · 35,314★ · `3343116ba2` |
| C15 | paddleocr | added | — | [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) Apache-2.0 · 92,693★ · `dab3fe3537` |
| C15 | pdfcraft | named | [storytold/pdfcraft](https://github.com/storytold/pdfcraft) Apache-2.0 · 20,674★ · `358e33a307` | — |
| C17 | egress-proxy | named | [envoyproxy/envoy](https://github.com/envoyproxy/envoy) Apache-2.0 · ★ n/a · `e989d8c732` | — |
| C17 | secrets-vault | added | — | [Infisical/infisical](https://github.com/Infisical/infisical) MIT * · 30,509★ · `8218dcf23c` |
| C18 | observability | named | [open-telemetry/opentelemetry-collector-contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib) Apache-2.0 · 5,050★ · `e0e1cb6463` | [SigNoz/signoz](https://github.com/SigNoz/signoz) MIT * · 32,638★ · `e010c4fa03`<br>[prometheus/prometheus](https://github.com/prometheus/prometheus) Apache-2.0 · 67,599★ · `8e974df217`<br>[jaegertracing/jaeger](https://github.com/jaegertracing/jaeger) Apache-2.0 · 23,409★ · `3b69761c0b` |

**\* License scope limits (enforced at vendoring):**
- BerriAI/litellm: MIT outside litellm/enterprise/; do not use enterprise/
- FFmpeg/FFmpeg: build without --enable-gpl / --enable-nonfree to stay LGPL
- Infisical/infisical: MIT outside ee/; do not use ee/
- KlingAIResearch/LivePortrait: code MIT; default InsightFace models are non-commercial, use the MediaPipe face detector
- Lightricks/LTX-Video: code Apache-2.0; check the model weights license per checkpoint before commercial use
- PostHog/posthog: MIT outside ee/; do not use ee/
- SigNoz/signoz: MIT outside ee/ and cmd/enterprise/
- Stirling-Tools/Stirling-PDF: MIT core; proprietary portions excluded
- activepieces/activepieces: MIT outside packages/ee/ and packages/server/api/src/app/ee; do not use those
- anthropics/skills: skills/frontend-design/LICENSE.txt is Apache-2.0; other skills in the repo differ
- black-forest-labs/flux: code Apache-2.0; FLUX.1 [schnell] weights Apache-2.0; FLUX.1 [dev] weights are non-commercial, do not use
- chatwoot/chatwoot: MIT outside enterprise/; do not use enterprise/
- dyad-sh/dyad: Apache-2.0 outside src/pro/
- dyad-sh/dyad: Apache-2.0 outside src/pro/; do not use src/pro/
- glassflow/tares: MIT outside ee/ and the tares_ee package
- gsd-build/gsd-2: archived upstream; pinned as-is
- heurion-org/aegis-os: closest public match to the spec's Aegis OS; confirm with the owner
- microsoft/autogen: code MIT, docs CC-BY-4.0
- modelcontextprotocol/servers: transitioning MIT to Apache-2.0
- modelcontextprotocol/servers: transitioning MIT to Apache-2.0; both permissive
- sdi2200262/agentic-project-management: v0.4.0+ MPL-2.0; v0.3.x and earlier MIT

**Copyleft:** AGPL and GPL projects run as separate services or programs, not linked into
RevenueOS code. Modifying one and offering it over a network requires publishing the changes.

**Method:** GitHub search API for license, stars and last push; `git ls-remote` for the
commit; license files read directly where GitHub reported NOASSERTION.
