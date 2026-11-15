# Pins

Every upstream behind RevenueOS, checked 2026-11-14. Governing rule: RevenueOS v4 (R04 amended: named components primary; D1/D3 exceptions; Addendum B star gate >=10k + commit within 90 days).
Machine-readable source: `config/sources.yaml`. CI (`tests/connectivity`) fails on any
unpinned repo, unapproved license, add-on outside the star gate (>= 10,000 stars,
commit within 90 days), or named component without a pinned primary.

**Totals:** 81 named, 37 added, 0 built in-repo,
7 named without a usable license, 11 named with no public repo,
1 experimental-only, 1 reference-only.

Addendum repos are also recorded as git submodule pointers under `vendor/` at the pinned
commit (D8), so the exact upstream revision travels with this repository.

## D1 exceptions: the add-on is the official implementation

Policy (docs/POLICY.md): where a named tool has no usable public repo or license, the documented
functional equivalent is the official implementation. The named tool is re-evaluated each build
cycle and, if usable, replaces the add-on and the add-on becomes the fallback.

| Named component | D1 label | Why | Official implementation |
| --- | --- | --- | --- |
| allmail-mcp | No Public Repo — Add-On Replaces | no public repository for allmail-mcp | PrefectHQ/fastmcp |
| biro | No Public Repo — Add-On Replaces | no public repository for Biro | paperclipai/paperclip |
| curio | No Public Repo — Add-On Replaces | no public repository for Curio | assafelovic/gpt-researcher |
| dataforge | No Public Repo — Add-On Replaces | no public repository for 'dataforge' email finder; L2 waterfall skips to the Hunter-compatible fallback | RevenueOS adapter (D3) |
| deepagents-open-lovable | No Usable License — Add-On Replaces | emanueleielo/deepagents-open-lovable has no license file | firecrawl/open-lovable, langchain-ai/deepagents |
| design-linter | No Public Repo — Add-On Replaces | agent-design-skills has no public repository | GoogleChrome/lighthouse |
| forage | No Public Repo — Add-On Replaces | no public repository for Forage | PrefectHQ/fastmcp |
| harness-agent | No Public Repo — Add-On Replaces | OrcaKit harness-agent is not public (OrcaKit org exists; repo not accessible) | letta-ai/letta |
| incagent | No Usable License — Add-On Replaces | incagent/incagent has no license file; using it would be copyright infringement | getlago/lago, documenso/documenso |
| llm-tracker | No Public Repo — Add-On Replaces | no public repository matching the spec's llm-tracker | RevenueOS adapter (D3) |
| nava | No Public Repo — Add-On Replaces | no public repository for NAVA | OpenHands/OpenHands |
| netsendo | No Usable License — Add-On Replaces | NetSendo/NetSendo ships under a proprietary end-user license agreement | knadh/listmonk |
| nocodb | No Usable License — Add-On Replaces | nocodb/nocodb moved to the Sustainable Use License (not OSI, Jan 2026) | teableio/teable |
| open-pages | No Public Repo — Add-On Replaces | no public repository for open-pages | dyad-sh/dyad |
| openforgerl | No Usable License — Add-On Replaces | the only public OpenForgeRL repo has no license file | OpenRLHF/OpenRLHF |
| openmuse | No Usable License — Add-On Replaces | diggerhq/openmuse has no license file | microsoft/playwright, novnc/noVNC |
| orchard | No Public Repo — Add-On Replaces | no public repository for Orchard | huggingface/trl |
| syntheon | No Usable License — Add-On Replaces | cognis-digital/syntheon uses the Cognis Open Collaboration License, not an OSI license | dyad-sh/dyad |

The ten no-repo tools were searched again under alternative names on 2026-11-14 (D2); nothing
surfaced. `everything-claude-code`, `meta/astryx`, Capital One's VulnHunter and Google's official
Ads MCP server were found by direct lookup and pinned.

## Every pinned repository

| Spec | Component | Status | Role | Repository | Commit | License | Stars | Last commit | Checked |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C01 | agency-agents | named | named | [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents) | `8ae6164602c95ca78828b148b9052460ee426885` | MIT | 168,251 | 2026-11-09 | 2026-11-14 |
| C01 | agent-skills | named | named | [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | `39b723ceebf81474d0557c1fecd01eddab585563` | MIT | 117,387 | 2026-11-14 | 2026-11-14 |
| C01 | anthropic-skills-all | named | named | [anthropics/skills](https://github.com/anthropics/skills) | `2c5958ecac7cee2b583967a2c4981d0f4a75c579` | Apache-2.0 — per-skill licenses; document skills (docx/pdf/pptx/xlsx) are source-available, use frontend-design and other Apache skills only | 194,339 | 2026-11-14 | 2026-11-14 |
| C01 | astromesh | named | named | [monaccode/astromesh](https://github.com/monaccode/astromesh) | `e80ed42583776ad48288229b000e9e0ddba0e6da` | Apache-2.0 | 39 | 2026-11-13 | 2026-11-14 |
| C01 | astromesh | named | add-on | [BerriAI/litellm](https://github.com/BerriAI/litellm) | `27c796c412eed2f7336dccb46a58247463b7c498` | MIT — MIT outside litellm/enterprise/; do not use enterprise/ | 63,242 | 2026-11-14 | 2026-11-14 |
| C01 | autogen-ag2 | named | named | [microsoft/autogen](https://github.com/microsoft/autogen) | `8390985108cb1e3881f5f7297765758d8ad2540c` | MIT — code MIT, docs CC-BY-4.0 | 61,814 | 2026-11-12 | 2026-11-14 |
| C01 | autogen-ag2 | named | named | [ag2ai/ag2](https://github.com/ag2ai/ag2) | `fb3061e061990ef2c81ea5a86984519b227cabee` | Apache-2.0 | 5,063 | 2026-11-14 | 2026-11-14 |
| C01 | biro | named-not-found | add-on | [paperclipai/paperclip](https://github.com/paperclipai/paperclip) | `c1451814c155adab79fd0181674a23b0dc2669e4` | MIT | 113,796 | 2026-11-14 | 2026-11-14 |
| C01 | composio | named | named | [ComposioHQ/composio](https://github.com/ComposioHQ/composio) | `fdee7595166f8b5dcff026dc609760d1ce82b2e2` | MIT | 31,064 | 2026-11-14 | 2026-11-14 |
| C01 | crewai | named | named | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | `d7dfa0ef5ade793bd48ff7357c6eb45a45294371` | MIT | 60,878 | 2026-11-13 | 2026-11-14 |
| C01 | erebots | named | named | [aislab-hevs/erebots4.0](https://github.com/aislab-hevs/erebots4.0) | `162c9be94ab32927f5b2fbf594730117e67e3a40` | MIT | n/a (hidden from search) | 2026-11-03 | 2026-11-14 |
| C01 | erebots | named | add-on | [a2aproject/A2A](https://github.com/a2aproject/A2A) | `4d7cda4b1754ed410e41bf3be7ad9ebc62afe3d3` | Apache-2.0 | 26,538 | 2026-11-13 | 2026-11-14 |
| C01 | everything-claude-code | named | named | [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code) | `d2ef2680594f9a17526a6e1a2e18b3d242c5d17b` | MIT — repo hidden from GitHub search; stars not retrievable via API, verified to exist by commit | n/a (hidden from search) | — | 2026-11-14 |
| C01 | harness-agent | named-not-found | add-on | [letta-ai/letta](https://github.com/letta-ai/letta) | `8816d3a8516893bfdc0fa14bfb1235226012e295` | Apache-2.0 | 25,434 | 2026-10-18 | 2026-11-14 |
| C01 | harnis | named | named | [karawash-projects/harnis](https://github.com/karawash-projects/harnis) | `b4077e370bdf18e46b7bed0e1daf053e9b8e8002` | Apache-2.0 | 6 | 2026-11-06 | 2026-11-14 |
| C01 | harnis | named | add-on | [humanlayer/humanlayer](https://github.com/humanlayer/humanlayer) | `b7ad8e1d383ff0f5fbec7bdc30425e4a59d5f789` | Apache-2.0 | 12,878 | 2026-11-14 | 2026-11-14 |
| C01 | harnis | named | add-on | [open-policy-agent/opa](https://github.com/open-policy-agent/opa) | `8d10da6e34b846269f990daa43f39003e79b9dc4` | Apache-2.0 | 12,470 | 2026-11-14 | 2026-11-14 |
| C01 | hubzoid | named | named | [hubzoid/hubzoid](https://github.com/hubzoid/hubzoid) | `fc8b6363c3ffbfec27eeabfab152cea1ba84582d` | Apache-2.0 | 18 | 2026-11-06 | 2026-11-14 |
| C01 | hubzoid | named | add-on | [openclaw/openclaw](https://github.com/openclaw/openclaw) | `c787d0fac8265bfb54f9d1dd05a3eb55298c487b` | MIT | 394,427 | 2026-11-14 | 2026-11-14 |
| C01 | incagent | named-unlicensed | add-on | [getlago/lago](https://github.com/getlago/lago) | `63d2ddfcf3c6085e1286b4aa7101339ae6ddcac6` | AGPL-3.0 | 10,842 | 2026-11-14 | 2026-11-14 |
| C01 | incagent | named-unlicensed | add-on | [documenso/documenso](https://github.com/documenso/documenso) | `1e2333d534e151578ffb05394428e2a7efea5f50` | AGPL-3.0 | 15,761 | 2026-11-14 | 2026-11-14 |
| C01 | langgraph | named | named | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | `08a2016953789a4f579b4d36bd1967941ec62012` | MIT | 44,948 | 2026-11-14 | 2026-11-14 |
| C01 | mattpocock-skills | named | named | [mattpocock/skills](https://github.com/mattpocock/skills) | `5863806dd4e15c63174bee4e7515a4256792ecfa` | MIT | 324,196 | 2026-11-13 | 2026-11-14 |
| C01 | nextcloud | named | named | [nextcloud/server](https://github.com/nextcloud/server) | `61424d946776ada4554117ebfd33174fb3718377` | AGPL-3.0 | 37,511 | 2026-11-14 | 2026-11-14 |
| C01 | official-mcp-servers | named | named | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | `e1dc4b18dbb948921da37f3d4224a628730b43b0` | MIT — transitioning MIT to Apache-2.0; both permissive | 91,982 | 2026-11-12 | 2026-11-14 |
| C01 | ollama | named | named | [ollama/ollama](https://github.com/ollama/ollama) | `a5864fcb33969705de3c0ebfedf4b2a16c970bcc` | MIT | 186,934 | 2026-11-14 | 2026-11-14 |
| C01 | omnigent | named | named | [omnigent-ai/omnigent](https://github.com/omnigent-ai/omnigent) | `38a65dbdde2d79cc2eb02c223b21a02f69c8e7f5` | Apache-2.0 | 11,377 | 2026-11-14 | 2026-11-14 |
| C01 | richdocuments | named | named | [nextcloud/richdocuments](https://github.com/nextcloud/richdocuments) | `9c9291493224cd570f3777bbf4cafea00c077356` | AGPL-3.0 — Nextcloud companion app; below star gate, kept as named | 459 | 2026-11-14 | 2026-11-14 |
| C01 | superpowers | named | named | [obra/superpowers](https://github.com/obra/superpowers) | `22f0b463e7a5e579904dd6211a520321035526f7` | MIT | 317,455 | 2026-11-03 | 2026-11-14 |
| C01 | vllm | named | named | [vllm-project/vllm](https://github.com/vllm-project/vllm) | `6f1ec6a4c62d6a7a756edd53fd00a57782542cbd` | Apache-2.0 | 96,915 | 2026-11-14 | 2026-11-14 |
| C02 | browser-use | named | named | [browser-use/browser-use](https://github.com/browser-use/browser-use) | `e717df1839a2d7368b108de6694f01e9c659b0de` | MIT | 120,984 | 2026-11-14 | 2026-11-14 |
| C02 | magenticlite | named | named | [microsoft/magentic-ui](https://github.com/microsoft/magentic-ui) | `d3c9d13c39288257286a66daabf7c5b5fb72ee69` | MIT | 10,117 | 2026-09-23 | 2026-11-14 |
| C02 | omnipilot | named | named | [xrchris7/OmniPilot](https://github.com/xrchris7/OmniPilot) | `2e3a6bd02f1e508275f7242accad065805993a22` | MIT | 2 | 2026-09-13 | 2026-11-14 |
| C02 | omnipilot | named | add-on | [trycua/cua](https://github.com/trycua/cua) | `b3dafe7f47ab40a5d00c5023855317a2e901c062` | MIT | 32,334 | 2026-11-14 | 2026-11-14 |
| C02 | openclaw-heartbeat | named | named | [openclaw/openclaw](https://github.com/openclaw/openclaw) | `c787d0fac8265bfb54f9d1dd05a3eb55298c487b` | MIT | 394,427 | 2026-11-14 | 2026-11-14 |
| C02 | playwright | added | added | [microsoft/playwright](https://github.com/microsoft/playwright) | `b4d016aadc5cbd2b898a284307975fe73e05483d` | Apache-2.0 | 100,148 | 2026-11-14 | 2026-11-14 |
| C02 | playwright-mcp | named | named | [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | `78eca85361efb545a4c0f59b6140aef0721c5412` | Apache-2.0 | 39,621 | 2026-11-13 | 2026-11-14 |
| C03 | aegis-os | named | named | [heurion-org/aegis-os](https://github.com/heurion-org/aegis-os) | `d9bdfa978d721cae0dc2bfa277ed371c9db60c5a` | Apache-2.0 — closest public match to the spec's Aegis OS; confirm with the owner | 1 | 2026-11-14 | 2026-11-14 |
| C03 | aegis-os | named | named | [containers/bubblewrap](https://github.com/containers/bubblewrap) | `1fb0aa26d3eb66254f7742e704add7f82f41a582` | LGPL-2.1 | 9,486 | 2026-10-14 | 2026-11-14 |
| C03 | aegis-os | named | add-on | [google/gvisor](https://github.com/google/gvisor) | `e45d53c763ac5f2278fbee07bcf7e0a5ab6dce5c` | Apache-2.0 | 20,000 | 2026-11-14 | 2026-11-14 |
| C03 | aegis-os | named | add-on | [firecracker-microvm/firecracker](https://github.com/firecracker-microvm/firecracker) | `cc88013eadcf432da1b37d47d445b7e8bcc3046e` | Apache-2.0 | 38,015 | 2026-11-13 | 2026-11-14 |
| C03 | nava | named-not-found | add-on | [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | `830c0459e2f6056ab81e020c22970e782ae1be75` | MIT | 93,455 | 2026-11-14 | 2026-11-14 |
| C03 | openmuse | named-unlicensed | add-on | [microsoft/playwright](https://github.com/microsoft/playwright) | `b4d016aadc5cbd2b898a284307975fe73e05483d` | Apache-2.0 | 100,148 | 2026-11-14 | 2026-11-14 |
| C03 | openmuse | named-unlicensed | add-on | [novnc/noVNC](https://github.com/novnc/noVNC) | `e8b5024d4603587b29ffede4fbd28b1fa2939829` | MPL-2.0 | 14,204 | 2026-10-23 | 2026-11-14 |
| C04 | agent-discover | named | named | [keshrath/agent-discover](https://github.com/keshrath/agent-discover) | `c8a48bc73993d1cf75c00bb67352f0d20356ab3b` | MIT | 7 | 2026-11-14 | 2026-11-14 |
| C04 | agent-discover | named | add-on | [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) | `a8745d61e650467756bb28b4157822dbfbdfa34f` | Apache-2.0 | 28,417 | 2026-11-14 | 2026-11-14 |
| C04 | forage | named-not-found | add-on | [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) | `a8745d61e650467756bb28b4157822dbfbdfa34f` | Apache-2.0 | 28,417 | 2026-11-14 | 2026-11-14 |
| C04 | mcpfinder | named | named | [mcpfinder/mcpfinder](https://github.com/mcpfinder/mcpfinder) | `4c9e2f421a4bfda47e01052ce21931d9b6026b27` | AGPL-3.0 | 14 | 2026-11-13 | 2026-11-14 |
| C04 | mcpfinder | named | add-on | [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) | `f431a5cd95cebf038e587715635b9d1a0a4d0c02` | MIT | 97,691 | 2026-11-06 | 2026-11-14 |
| C04 | mcpfinder | named | add-on | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | `e1dc4b18dbb948921da37f3d4224a628730b43b0` | MIT — transitioning MIT to Apache-2.0 | 91,982 | 2026-11-12 | 2026-11-14 |
| C04 | mcptoon | named | named | [activeing123/mcptoon](https://github.com/activeing123/mcptoon) | `3af4967dd24433948faf3dbe0259ca64751b8818` | Apache-2.0 | 430 | 2026-11-13 | 2026-11-14 |
| C04 | mcptoon | named | add-on | [activepieces/activepieces](https://github.com/activepieces/activepieces) | `182b7f2bdc5bd9d9a7de02286af2dc2406e72706` | MIT — MIT outside packages/ee/ and packages/server/api/src/app/ee; do not use those | 25,523 | 2026-11-14 | 2026-11-14 |
| C05 | agenticmail | named | named | [agenticmail/agenticmail](https://github.com/agenticmail/agenticmail) | `af1e0ef546b5862c1f7134649e761f56356c688a` | MIT | 254 | 2026-11-13 | 2026-11-14 |
| C05 | allmail-mcp | named-not-found | add-on | [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) | `a8745d61e650467756bb28b4157822dbfbdfa34f` | Apache-2.0 | 28,417 | 2026-11-14 | 2026-11-14 |
| C05 | livekit | added | added | [livekit/livekit](https://github.com/livekit/livekit) | `fb2044e3c9fdc10e60ff889815d696a54ff9fdbe` | Apache-2.0 | 22,206 | 2026-11-13 | 2026-11-14 |
| C05 | livekit-agents | added | added | [livekit/agents](https://github.com/livekit/agents) | `cbb5770c716c70009969cd7fa88e3c3662222ce9` | Apache-2.0 | 15,220 | 2026-11-14 | 2026-11-14 |
| C05 | stalwart-mail | named | named | [stalwartlabs/stalwart](https://github.com/stalwartlabs/stalwart) | `e7cde9b3fac32d2a254ef782efec56f2373ec5d4` | AGPL-3.0 | 15,923 | 2026-11-10 | 2026-11-14 |
| C06 | agentic-pm | named | named | [sdi2200262/agentic-project-management](https://github.com/sdi2200262/agentic-project-management) | `b88434f08130b19faed23288ea46a75543d166c3` | MPL-2.0 — v0.4.0+ MPL-2.0; v0.3.x and earlier MIT | 2,453 | 2026-11-13 | 2026-11-14 |
| C06 | agentic-pm | named | add-on | [github/spec-kit](https://github.com/github/spec-kit) | `2ee2b1e8005905db05f5717300a469b3068b908f` | MIT | 149,752 | 2026-11-12 | 2026-11-14 |
| C06 | fist-mbt | named | named | [vicTop-cw/FIST-Mbt](https://github.com/vicTop-cw/FIST-Mbt) | `5ba7123d821676a9a2325dfe864cbe2a3fc78ce4` | Apache-2.0 | 1 | 2026-11-13 | 2026-11-14 |
| C06 | fist-mbt | named | add-on | [temporalio/temporal](https://github.com/temporalio/temporal) | `170fb83dca48fe82d69aa3ec3b6fe25acfc1791b` | MIT | 24,396 | 2026-11-14 | 2026-11-14 |
| C06 | gsd-pi | named | named | [gsd-build/gsd-2](https://github.com/gsd-build/gsd-2) | `33c00aaffa56e5d394bccce1c8df59fb842e84c5` | MIT — archived upstream; pinned as-is | 7,740 | 2026-05-22 | 2026-11-14 |
| C06 | gsd-pi | named | add-on | [temporalio/temporal](https://github.com/temporalio/temporal) | `170fb83dca48fe82d69aa3ec3b6fe25acfc1791b` | MIT | 24,396 | 2026-11-14 | 2026-11-14 |
| C06 | mission-control | named | named | [builderz-labs/mission-control](https://github.com/builderz-labs/mission-control) | `c1a846fe020567bb3ceb3b65db9f00db875618cd` | MIT | 6,491 | 2026-11-09 | 2026-11-14 |
| C06 | mission-control | named | add-on | [paperclipai/paperclip](https://github.com/paperclipai/paperclip) | `c1451814c155adab79fd0181674a23b0dc2669e4` | MIT | 113,796 | 2026-11-14 | 2026-11-14 |
| C06 | piyaz | named | named | [FrkAk/piyaz](https://github.com/FrkAk/piyaz) | `e1ed033e9a4d0e7af81da5833b47dcd2c0e6fdfb` | AGPL-3.0 | 200 | 2026-10-23 | 2026-11-14 |
| C06 | piyaz | named | add-on | [makeplane/plane](https://github.com/makeplane/plane) | `290383d7f92fa8995ea2adbd12442220b3b9b525` | AGPL-3.0 | 62,433 | 2026-11-13 | 2026-11-14 |
| C06 | planning-with-files | named | named | [OthmanAdi/planning-with-files](https://github.com/OthmanAdi/planning-with-files) | `51bf62def62d1cb317d37936929b4ef97cf862c3` | MIT | 28,052 | 2026-11-11 | 2026-11-14 |
| C07 | agent-reach | named | named | [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) | `c70ae6da5d39bc90e09ad2ae0575ccc89f31e284` | MIT | 111,707 | 2026-11-08 | 2026-11-14 |
| C07 | api-anything | named | named | [goodnight000/api-anything](https://github.com/goodnight000/api-anything) | `d40abd44f171c5cc444f1ac6b947afefa8605b78` | MIT | 3,177 | 2026-11-13 | 2026-11-14 |
| C07 | crawl4ai | added | added | [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) | `cae74b203a33994f7e13b9052c3b0d5c93daa0e6` | Apache-2.0 | 87,341 | 2026-11-13 | 2026-11-14 |
| C07 | crawlee | added | added | [apify/crawlee](https://github.com/apify/crawlee) | `a972548a5f39b4ddd94d758519b15138f3239c2b` | Apache-2.0 | 26,443 | 2026-11-14 | 2026-11-14 |
| C07 | easyspider | named | named | [NaiboWang/EasySpider](https://github.com/NaiboWang/EasySpider) | `899d775513994ca30225fd33e5b99db7fa1fcd20` | AGPL-3.0 | 44,791 | 2026-11-07 | 2026-11-14 |
| C07 | firecrawl | named | named | [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl) | `71f430a2dabffaf718cef7091c340b7384b91178` | AGPL-3.0 | 201,670 | 2026-11-13 | 2026-11-14 |
| C07 | keelead | experimental | named | [Atum246/keelead](https://github.com/Atum246/keelead) | `a846e2b6c19f781d44073f2e651c1ac8de52cf4a` | MIT — experimental only (D5); never approved | 54 | 2026-04-28 | 2026-11-14 |
| C07 | maxun | added | added | [getmaxun/maxun](https://github.com/getmaxun/maxun) | `99c6bd0d42b14336b706ba121a3757f62a9814f7` | AGPL-3.0 | 18,382 | 2026-11-09 | 2026-11-14 |
| C07 | openbusiness | named | named | [wanikua/OpenBusiness](https://github.com/wanikua/OpenBusiness) | `3f9a1bbeda010649c5735fef58c6d1209602efdf` | MIT | 12 | 2026-06-02 | 2026-11-14 |
| C07 | openbusiness | named | add-on | [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | `ddd4db36208d9c8e49f3b2436efda97baecb5433` | Apache-2.0 | 30,679 | 2026-11-12 | 2026-11-14 |
| C07 | opengtm | named | named | [debpalash/OpenGTM](https://github.com/debpalash/OpenGTM) | `0b126e9007f7ee3fa8457a2232d3a24204e4489a` | AGPL-3.0 | 110 | 2026-11-14 | 2026-11-14 |
| C07 | scrapegraph-ai | added | added | [ScrapeGraphAI/Scrapegraph-ai](https://github.com/ScrapeGraphAI/Scrapegraph-ai) | `194055e203afce41ed4e70365dbc416bad756115` | MIT | 32,773 | 2026-10-06 | 2026-11-14 |
| C07 | scrapling | added | added | [D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) | `bb223f2f5fc8f743772751a5ce283ef7851ca6be` | BSD-3-Clause | 102,678 | 2026-11-11 | 2026-11-14 |
| C07 | scrapy | added | added | [scrapy/scrapy](https://github.com/scrapy/scrapy) | `e63a574c767d7a9438c21db158f605f1c44c6e6a` | BSD-3-Clause | 65,383 | 2026-11-13 | 2026-11-14 |
| C07 | searxng | named | named | [searxng/searxng](https://github.com/searxng/searxng) | `a7128d5d1d5af2837a68fbeaaee9c3e8391aa9cf` | AGPL-3.0 | 39,540 | 2026-11-14 | 2026-11-14 |
| C08 | astryx | named | named | [meta/astryx](https://github.com/meta/astryx) | `c441c235f047412e2f3d57c932968b4142839a8e` | MIT | 27,736 | 2026-11-14 | 2026-11-14 |
| C08 | baseline-ui | named | named | [ibelick/ui-skills](https://github.com/ibelick/ui-skills) | `65cc0edb4f64fe8bfe7e9c59466074de25bece76` | MIT — canonical home of the baseline-ui skill (R03 pin) | 11,054 | 2026-11-14 | 2026-11-14 |
| C08 | chrome-devtools-mcp | named | named | [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) | `8ba2ac945ebaf1adb92208c29f3a30e73a920956` | Apache-2.0 | 55,878 | 2026-11-13 | 2026-11-14 |
| C08 | deepagents-open-lovable | named-unlicensed | add-on | [firecrawl/open-lovable](https://github.com/firecrawl/open-lovable) | `806b8072f28afea11fa2b028cac1449eff74c511` | MIT | 28,909 | 2026-10-09 | 2026-11-14 |
| C08 | deepagents-open-lovable | named-unlicensed | add-on | [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) | `a93aed4bca3a5e4d45bff393e16092222767e6c3` | MIT | 31,279 | 2026-11-14 | 2026-11-14 |
| C08 | design-linter | named-not-found | add-on | [GoogleChrome/lighthouse](https://github.com/GoogleChrome/lighthouse) | `4875928438c01b39abbd4bc1f9923c16d23ab32d` | Apache-2.0 | 31,079 | 2026-11-13 | 2026-11-14 |
| C08 | frontend-design-skill | named | named | [anthropics/skills](https://github.com/anthropics/skills) | `2c5958ecac7cee2b583967a2c4981d0f4a75c579` | Apache-2.0 — skills/frontend-design/LICENSE.txt is Apache-2.0; other skills in the repo differ | 194,339 | 2026-11-14 | 2026-11-14 |
| C08 | nexity | named | named | [Pagepro/nexity](https://github.com/Pagepro/nexity) | `2097cfb684c6b21339fe6a0474a1bd9e240c33f4` | MIT | 26 | 2026-11-13 | 2026-11-14 |
| C08 | nexity | named | named | [sanity-io/sanity](https://github.com/sanity-io/sanity) | `08b506252df967bbe4f0e991485a51bf38a1aa79` | MIT | 6,394 | 2026-11-14 | 2026-11-14 |
| C08 | nexity | named | add-on | [payloadcms/payload](https://github.com/payloadcms/payload) | `56033d9561275b2f3457fc86666d8da232a8528e` | MIT | 45,811 | 2026-11-14 | 2026-11-14 |
| C08 | open-design | named | named | [nexu-io/open-design](https://github.com/nexu-io/open-design) | `59e4f2ae85de7e7318a5e6bdcf3a34584c4b7582` | Apache-2.0 | 107,601 | 2026-11-14 | 2026-11-14 |
| C08 | open-pages | named-not-found | add-on | [dyad-sh/dyad](https://github.com/dyad-sh/dyad) | `a15e23340ff3f12c24c3f54d5aaf28eac0366ca3` | Apache-2.0 — Apache-2.0 outside src/pro/; do not use src/pro/ | 22,296 | 2026-11-14 | 2026-11-14 |
| C08 | syntheon | named-unlicensed | add-on | [dyad-sh/dyad](https://github.com/dyad-sh/dyad) | `a15e23340ff3f12c24c3f54d5aaf28eac0366ca3` | Apache-2.0 — Apache-2.0 outside src/pro/ | 22,296 | 2026-11-14 | 2026-11-14 |
| C08 | tastemaker | named | named | [Harrypatria/tastemaker](https://github.com/Harrypatria/tastemaker) | `921637b69cfd9f98268c9ef68b914ac481ba309a` | MIT | 5 | 2026-10-30 | 2026-11-14 |
| C08 | ui-ux-pro-max | named | named | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | `6ae86f61f520d6ca229d2f40e070410638c908c5` | MIT | 149,276 | 2026-11-10 | 2026-11-14 |
| C09 | chatwoot | added | added | [chatwoot/chatwoot](https://github.com/chatwoot/chatwoot) | `1ef1d2b45ae0a17a35c5f1bd055e4ddf04dadabf` | MIT — MIT outside enterprise/; do not use enterprise/ | 39,858 | 2026-11-13 | 2026-11-14 |
| C09 | openwa | named | named | [rmyndharis/OpenWA](https://github.com/rmyndharis/OpenWA) | `bf97fbd2436d3d4bef33c3c6fe5b300cbf1e9701` | MIT | 16,840 | 2026-11-14 | 2026-11-14 |
| C09 | postiz | named | named | [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | `132859f32d854830ce44b509da87409c3ec10a77` | AGPL-3.0 | 41,574 | 2026-11-13 | 2026-11-14 |
| C09 | postmill-ai | named | named | [postmill-ai/postmill-app](https://github.com/postmill-ai/postmill-app) | `e06b4796fe534697f4eef77180c7d1f58c9df7fb` | AGPL-3.0 | 315 | 2026-11-14 | 2026-11-14 |
| C09 | social0 | named | named | [Abhishek-B-R/social0-oss](https://github.com/Abhishek-B-R/social0-oss) | `217744b5118a271c3b48d161b3bb4318d7beb256` | AGPL-3.0 | 4 | 2026-11-03 | 2026-11-14 |
| C10 | claude-ads | named | named | [AgriciDaniel/claude-ads](https://github.com/AgriciDaniel/claude-ads) | `fc3908e786c318776df89a3a098333da377364be` | MIT | 11,019 | 2026-11-01 | 2026-11-14 |
| C10 | google-ads-mcp | named | named | [googleads/google-ads-mcp](https://github.com/googleads/google-ads-mcp) | `cda852701fb5787dc4d79281f37da795ac09b97d` | Apache-2.0 — spec location google-marketing-solutions/google_ads_mcp is not public; canonical official repo pinned (R03); named-vendor exception | 1,176 | 2026-11-10 | 2026-11-14 |
| C10 | helio | named | named | [achref-soua/helio](https://github.com/achref-soua/helio) | `63d0cedb2193f569b98ddf81f101b43bfa128560` | AGPL-3.0 | 24 | 2026-06-29 | 2026-11-14 |
| C10 | helio | named | add-on | [PostHog/posthog](https://github.com/PostHog/posthog) | `e060b5d349184643f6b355aa9e865ed4895d4ae0` | MIT — MIT outside ee/; do not use ee/ | 40,777 | 2026-11-14 | 2026-11-14 |
| C10 | listmonk | added | added | [knadh/listmonk](https://github.com/knadh/listmonk) | `e735e0b23421192a4c1b18b6221f4708b872fcd5` | AGPL-3.0 | 24,292 | 2026-11-14 | 2026-11-14 |
| C10 | mautic | named | named | [mautic/mautic](https://github.com/mautic/mautic) | `6711577a1df4e46cadeb739415574b49c3345771` | GPL-3.0 | 10,985 | 2026-11-13 | 2026-11-14 |
| C10 | mjml | added | added | [mjmlio/mjml](https://github.com/mjmlio/mjml) | `40ddfbb4c04e13dd9572aa0d5b1c58826a163289` | MIT | 18,295 | 2026-11-10 | 2026-11-14 |
| C10 | netsendo | named-unlicensed | add-on | [knadh/listmonk](https://github.com/knadh/listmonk) | `e735e0b23421192a4c1b18b6221f4708b872fcd5` | AGPL-3.0 | 24,292 | 2026-11-14 | 2026-11-14 |
| C10 | nocodb | named-unlicensed | add-on | [teableio/teable](https://github.com/teableio/teable) | `b8425f5a60d056205adc456b9e8011ff7d622a29` | AGPL-3.0 — AGPL core apps; MIT packages/ | 21,982 | 2026-11-13 | 2026-11-14 |
| C10 | postal | added | added | [postalserver/postal](https://github.com/postalserver/postal) | `d96eddbadeda600595d6247486f9ceb8e99cbc15` | MIT | 16,956 | 2026-11-14 | 2026-11-14 |
| C10 | react-email | added | added | [resend/react-email](https://github.com/resend/react-email) | `f27d9e20825233cf7152053590b8dbd9bcf848ad` | MIT | 19,936 | 2026-11-14 | 2026-11-14 |
| C10 | twenty | named | named | [twentyhq/twenty](https://github.com/twentyhq/twenty) | `1dd1c249ad213de6883be5296deb3bbba8420a22` | AGPL-3.0 — AGPLv3 except files marked @license Enterprise; do not use those | 60,918 | 2026-11-14 | 2026-11-14 |
| C10 | univer | named | named | [dream-num/univer](https://github.com/dream-num/univer) | `0d7923dd7a26e6bea56f1bc791a03618235a4618` | Apache-2.0 | 24,243 | 2026-11-14 | 2026-11-14 |
| C11 | evalforge | named | named | [heManKuMAR6/evalforge](https://github.com/heManKuMAR6/evalforge) | `7931647894572756517c815bcdbd8758487605cc` | MIT | 9 | 2026-05-14 | 2026-11-14 |
| C11 | evalforge | named | add-on | [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | `45f68f0d77db9435a0d1a5a7971b208cc71f8e26` | MIT | 27,159 | 2026-11-14 | 2026-11-14 |
| C11 | gitreins | named | named | [totalwindupflightsystems/gitreins](https://github.com/totalwindupflightsystems/gitreins) | `9e0bf429f2d1f088e7942ef2e0cadf42be6bb053` | MIT | 1 | 2026-11-14 | 2026-11-14 |
| C11 | gitreins | named | add-on | [pre-commit/pre-commit](https://github.com/pre-commit/pre-commit) | `ba5c4209a6d561b0dff5db24620778d2133d068e` | MIT | 15,695 | 2026-11-09 | 2026-11-14 |
| C11 | veripipe | named | named | [zhangyy0423/veripipe](https://github.com/zhangyy0423/veripipe) | `bd557a3b1712f69af70cfd754662c9fd30efe33d` | MIT | 1 | 2026-10-19 | 2026-11-14 |
| C12 | duckdb | named | named | [duckdb/duckdb](https://github.com/duckdb/duckdb) | `b678afa97b529d5856731e115e31542a72d2d978` | MIT | 43,055 | 2026-11-13 | 2026-11-14 |
| C12 | plausible | named | named | [plausible/analytics](https://github.com/plausible/analytics) | `8e5982c237c8d17be02170e8063b3dd9b8e76085` | AGPL-3.0 | 29,844 | 2026-11-13 | 2026-11-14 |
| C12 | postgres | named | named | [postgres/postgres](https://github.com/postgres/postgres) | `70c4a57b64d39c526eb4c44a925eb92a6e56f3c5` | PostgreSQL | 22,820 | 2026-11-13 | 2026-11-14 |
| C12 | tares | named | named | [glassflow/tares](https://github.com/glassflow/tares) | `f1b3b23fab78a0e94a1c1da7c3643544f1040eb4` | MIT — MIT outside ee/ and the tares_ee package | 47 | 2026-11-14 | 2026-11-14 |
| C12 | tares | named | add-on | [duckdb/duckdb](https://github.com/duckdb/duckdb) | `b678afa97b529d5856731e115e31542a72d2d978` | MIT | 43,055 | 2026-11-13 | 2026-11-14 |
| C12 | umami | added | added | [umami-software/umami](https://github.com/umami-software/umami) | `b18d5144dfe7342edeeca6f61d13ba3baabed9ad` | MIT | 40,139 | 2026-11-14 | 2026-11-14 |
| C13 | agentjet | named | named | [modelscope/AgentJet](https://github.com/modelscope/AgentJet) | `25118bbcb314e0da898bbc0043a1bf4ab74eade7` | Apache-2.0 | 243 | 2026-08-25 | 2026-11-14 |
| C13 | agentjet | named | add-on | [verl-project/verl](https://github.com/verl-project/verl) | `4191e7f910d85d69acb8c45f4840f10faa535165` | Apache-2.0 | 24,229 | 2026-11-14 | 2026-11-14 |
| C13 | curio | named-not-found | add-on | [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | `ddd4db36208d9c8e49f3b2436efda97baecb5433` | Apache-2.0 | 30,679 | 2026-11-12 | 2026-11-14 |
| C13 | myelinate | named | named | [notaaaronfr/myelinate](https://github.com/notaaaronfr/myelinate) | `f8d20d4f5b4824accfccaa79912fff613a619f64` | MIT | 7 | 2026-11-13 | 2026-11-14 |
| C13 | myelinate | named | add-on | [mem0ai/mem0](https://github.com/mem0ai/mem0) | `f1791daa86d469249c9b002f62644d58a1eb96a0` | Apache-2.0 | 68,950 | 2026-11-06 | 2026-11-14 |
| C13 | openforgerl | named-unlicensed | add-on | [OpenRLHF/OpenRLHF](https://github.com/OpenRLHF/OpenRLHF) | `26494490bc237f6c3af62dab6117e6bbb0a78dba` | Apache-2.0 | 10,152 | 2026-11-03 | 2026-11-14 |
| C13 | openspace | named | named | [HKUDS/OpenSpace](https://github.com/HKUDS/OpenSpace) | `e5a81e7635009869d34dde8fbfd045d191296f3f` | MIT | n/a (hidden from search) | — | 2026-11-14 |
| C13 | openspace | named | add-on | [letta-ai/letta](https://github.com/letta-ai/letta) | `8816d3a8516893bfdc0fa14bfb1235226012e295` | Apache-2.0 | 25,434 | 2026-10-18 | 2026-11-14 |
| C13 | orchard | named-not-found | add-on | [huggingface/trl](https://github.com/huggingface/trl) | `8ad18ec1b6493b85cf9fffbd87d376767ceb8611` | Apache-2.0 | 19,734 | 2026-11-14 | 2026-11-14 |
| C13 | pgvector | added | added | [pgvector/pgvector](https://github.com/pgvector/pgvector) | `10a73eceefe033ac944f91782c553b5fc67eccb9` | PostgreSQL | 23,678 | 2026-11-14 | 2026-11-14 |
| C13 | qdrant | added | added | [qdrant/qdrant](https://github.com/qdrant/qdrant) | `95d89e51427f4217bf7b496e039ef0a069ebe342` | Apache-2.0 | 35,550 | 2026-11-13 | 2026-11-14 |
| C14 | chatterbox | added | added | [resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox) | `ab55923c27757c90cfcc407baa57dc25a7d25217` | MIT | 27,809 | 2026-11-04 | 2026-11-14 |
| C14 | comfyui | added | added | [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI) | `eee59185ff4f43ae2d9ad122b245619d27d9daad` | GPL-3.0 | 146,764 | 2026-11-14 | 2026-11-14 |
| C14 | diffusers | added | added | [huggingface/diffusers](https://github.com/huggingface/diffusers) | `43e30028af5120d8b0868cb6975b9fad39cc4fab` | Apache-2.0 | 34,919 | 2026-11-14 | 2026-11-14 |
| C14 | ffmpeg | added | added | [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) | `604ef3784d6fae44baf62fdbe9b3e4e5cfc3c681` | LGPL-2.1 — build without --enable-gpl / --enable-nonfree to stay LGPL | 67,240 | 2026-11-14 | 2026-11-14 |
| C14 | invokeai | added | added | [invoke-ai/InvokeAI](https://github.com/invoke-ai/InvokeAI) | `48b83d98daa57315e8bf8e7754bdbc65aac86b8d` | Apache-2.0 | 29,089 | 2026-11-14 | 2026-11-14 |
| C14 | losslesscut | added | added | [mifi/lossless-cut](https://github.com/mifi/lossless-cut) | `4c7ab1cb0c9acaefabb48e997bc909562dc3624d` | GPL-2.0 | 46,025 | 2026-11-14 | 2026-11-14 |
| C14 | ltx-video | added | added | [Lightricks/LTX-Video](https://github.com/Lightricks/LTX-Video) | `50f0aef1297574a4b29acbdb874e3a363a6d5f2e` | Apache-2.0 — code Apache-2.0; check the model weights license per checkpoint before commercial use | 11,383 | 2026-11-02 | 2026-11-14 |
| C14 | moneyprinterturbo | added | added | [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | `ce289ffb61a118779c56d6b4a34181905dbed2b9` | MIT | 143,459 | 2026-11-13 | 2026-11-14 |
| C14 | moviepy | added | added | [Zulko/moviepy](https://github.com/Zulko/moviepy) | `211e4b15f6ce4f34a6a9efbfff40590e43a68f77` | MIT | 15,150 | 2026-08-26 | 2026-11-14 |
| C14 | obs-studio | added | added | [obsproject/obs-studio](https://github.com/obsproject/obs-studio) | `fe1ed7955f300efd17fc59f65938388e43d8bb06` | GPL-2.0 | 79,539 | 2026-11-11 | 2026-11-14 |
| C14 | penpot | added | added | [penpot/penpot](https://github.com/penpot/penpot) | `9c5260314a359ec17fbadb33a59dada7052f5fb1` | MPL-2.0 | 62,345 | 2026-11-14 | 2026-11-14 |
| C14 | rembg | added | added | [danielgatis/rembg](https://github.com/danielgatis/rembg) | `991927b77667946dab59c50df31f7d4640e80457` | MIT | 25,459 | 2026-11-06 | 2026-11-14 |
| C14 | shotcut | added | added | [mltframework/shotcut](https://github.com/mltframework/shotcut) | `f291f3f2531f6861e62cdbf90650ff0a6a072f03` | GPL-3.0 | 15,678 | 2026-11-13 | 2026-11-14 |
| C14 | upscayl | added | added | [upscayl/upscayl](https://github.com/upscayl/upscayl) | `a00d55fee90e0f9435d5eaa86e76700df8199af8` | AGPL-3.0 | 52,545 | 2026-11-14 | 2026-11-14 |
| C14 | video-use | added | added | [browser-use/video-use](https://github.com/browser-use/video-use) | `43cfc566833548093455c9d4a46bd69913b7e552` | MIT | 31,038 | 2026-10-08 | 2026-11-14 |
| C14 | wan-video | added | added | [Wan-Video/Wan2.2](https://github.com/Wan-Video/Wan2.2) | `1ea34ff48f87168174e12956e200b1d908b1c5ff` | Apache-2.0 | 18,643 | 2026-09-21 | 2026-11-14 |
| C14 | whisperx | added | added | [m-bain/whisperX](https://github.com/m-bain/whisperX) | `b904f02b7e1f26fd10fb04840d655ff27e88e464` | BSD-2-Clause | 25,256 | 2026-11-12 | 2026-11-14 |
| C15 | docling | added | added | [docling-project/docling](https://github.com/docling-project/docling) | `5e600e8d37a11f70b62f795ea1e3ce3a4052e551` | MIT | 70,567 | 2026-11-14 | 2026-11-14 |
| C15 | nib | named | named | [daniel-alexander4/nib](https://github.com/daniel-alexander4/nib) | `1f23f70bb25a41eedef79acdc5068db438933ed3` | AGPL-3.0 | 10 | 2026-11-08 | 2026-11-14 |
| C15 | nib | named | add-on | [Stirling-Tools/Stirling-PDF](https://github.com/Stirling-Tools/Stirling-PDF) | `ad38e38ce9bb59ee6b16cbc2d727b6a54c0fbda0` | MIT — MIT core; proprietary portions excluded | 96,552 | 2026-11-13 | 2026-11-14 |
| C15 | nib | named | add-on | [ocrmypdf/OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) | `3343116ba204c99c9fee762d538dc1b668711bfb` | MPL-2.0 | 35,314 | 2026-11-14 | 2026-11-14 |
| C15 | paddleocr | added | added | [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | `dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf` | Apache-2.0 | 92,693 | 2026-09-16 | 2026-11-14 |
| C15 | pdfcraft | named | named | [storytold/pdfcraft](https://github.com/storytold/pdfcraft) | `358e33a3077bbc116c26a6e6468f984acc3426e1` | Apache-2.0 | 20,674 | 2026-11-14 | 2026-11-14 |
| C17 | autosecscan | named | named | [jhammant/AutoSecScan](https://github.com/jhammant/AutoSecScan) | `881d9602bfa1e45d8e0df021df4dd6b247df92f0` | MIT | 1 | 2026-07-03 | 2026-11-14 |
| C17 | egress-proxy | named | named | [envoyproxy/envoy](https://github.com/envoyproxy/envoy) | `e989d8c73262931f60f1ab638a780c7b3af3e68a` | Apache-2.0 | n/a (hidden from search) | — | 2026-11-14 |
| C17 | open-kritt | named | named | [Kritt-ai/open-kritt](https://github.com/Kritt-ai/open-kritt) | `ab240adc8d5731a45f8a8218ff03a6a3ac382e6e` | AGPL-3.0 | 2,430 | 2026-11-09 | 2026-11-14 |
| C17 | openhack | named | named | [openhackai/OpenHack](https://github.com/openhackai/OpenHack) | `6a0675ebd1287e8d7a651cccffae9b8f5d1e02a2` | MIT | 442 | 2026-10-17 | 2026-11-14 |
| C17 | secrets-vault | added | added | [Infisical/infisical](https://github.com/Infisical/infisical) | `8218dcf23cb99b8a1a55b732879996c4b3092b8a` | MIT — MIT outside ee/; do not use ee/ | 30,509 | 2026-11-14 | 2026-11-14 |
| C17 | strix | named | named | [usestrix/strix](https://github.com/usestrix/strix) | `4719329d1c3eb0db796714397551945c514a2301` | Apache-2.0 | 75,506 | 2026-11-13 | 2026-11-14 |
| C17 | vulnhunter | named | named | [capitalone/VulnHunter](https://github.com/capitalone/VulnHunter) | `6d25b5c58b7820809b391ecda6a102537effe3ba` | Apache-2.0 | 1,171 | 2026-10-07 | 2026-11-14 |
| C18 | observability | named | named | [open-telemetry/opentelemetry-collector-contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib) | `e0e1cb6463e1916b077bfa838fae2aaebed6ea62` | Apache-2.0 | 5,050 | 2026-11-14 | 2026-11-14 |
| C18 | observability | named | add-on | [SigNoz/signoz](https://github.com/SigNoz/signoz) | `e010c4fa037e15733e9a722714246211eb9026d4` | MIT — MIT outside ee/ and cmd/enterprise/ | 32,638 | 2026-11-14 | 2026-11-14 |
| C18 | observability | named | add-on | [prometheus/prometheus](https://github.com/prometheus/prometheus) | `8e974df217129350a7276d852a403ba7db06531c` | Apache-2.0 | 67,599 | 2026-11-14 | 2026-11-14 |
| C18 | observability | named | add-on | [jaegertracing/jaeger](https://github.com/jaegertracing/jaeger) | `3b69761c0b7c9f8601ae4dbee7e9889d32747452` | Apache-2.0 | 23,409 | 2026-11-14 | 2026-11-14 |
| — | awesome-claude-code | reference-only | named | [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | `18153158dd02b590c3ba3ab83533210ddca91a1c` | CC-BY-NC-ND-4.0 — index only: non-commercial, no-derivatives; never vendored or redistributed | 57,976 | 2026-11-14 | 2026-11-14 |

## Runtime images and source builds

| Component | What runs | Pin | Why this pin |
| --- | --- | --- | --- |
| C05 stalwart-mail | `stalwartlabs/stalwart` image | `v0.15.5` | AgenticMail's own upstream pin: 0.16+ moved to JSON config and ignores the TOML layout AgenticMail provisions against |
| C05 agenticmail | built from source (`infra/mail/agenticmail.Dockerfile`) | `af1e0ef546b5862c1f7134649e761f56356c688a` | named component, pinned commit; Node 22 for `node:sqlite` |
| C03/C17 bubblewrap | built from source (`python.Dockerfile`, `scripts/build-bwrap.sh` in CI) | `1fb0aa26d3eb66254f7742e704add7f82f41a582` (0.13.2) | same binary in compose and CI; no distro AppArmor profile in the way |
| Q7 AutoSecScan | built from source in `security.yml` | `881d9602bfa1e45d8e0df021df4dd6b247df92f0` | the action's own image is a floating `:latest` |
| C17 egress | `envoyproxy/envoy` | `v1.40.2` | |
| C18 observability | `otel/opentelemetry-collector-contrib` | `0.164.0` | |
| state | `postgres` | `16-alpine` | major pinned |

Hosted fallbacks (proprietary, spec 2.1) are reached only with credentials in the vault and,
for paid resources, an approval: AgentMail API `v0` (`/v0/inboxes`), Browser Use Cloud API
`v2` (`/profiles`, `/sessions`), and the imAPI MCP bridge at a configured URL. Phone numbers
(46elks or Twilio) are paid carrier resources and are never allocated automatically.

## Removed at the star gate (re-evaluated next cycle)

- **pdf-viewer-editor**: SuperiorAg/PDF_Viewer_Editor has 0 stars; Stirling-PDF and PDFCraft cover it
- **flux:black-forest-labs/flux**: last commit 2025-07-31, outside the 90-day star-gate window; re-evaluated next cycle
- **framepack:lllyasviel/FramePack**: last commit 2025-10-16, outside the 90-day star-gate window; re-evaluated next cycle
- **open-sora:hpcaitech/Open-Sora**: last commit 2026-04-09, outside the 90-day star-gate window; re-evaluated next cycle
- **liveportrait:KlingAIResearch/LivePortrait**: last commit 2026-06-01, outside the 90-day star-gate window; re-evaluated next cycle
- **motion-canvas:motion-canvas/motion-canvas**: last commit 2026-07-02, outside the 90-day star-gate window; re-evaluated next cycle
- **jina-reader:jina-ai/reader**: last commit 2026-05-22, outside the 90-day star-gate window; re-evaluated next cycle

## License scope

AGPL and GPL projects run as separate services or programs and are never linked into
RevenueOS code; modifying one and offering it over a network requires publishing those
changes. Open-core projects are used only outside their enterprise directories (noted per
row). `hesreallyhim/awesome-claude-code` is CC-BY-NC-ND: read as an index, never vendored.
NocoDB moved to the Sustainable Use License (not OSI) in January 2026; Teable is its D1
equivalent.
