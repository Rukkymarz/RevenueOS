# Python services. Stage 1 builds the zod contracts to JSON Schema; stage 2 generates the
# pydantic models from it and installs the requested workspace packages.
# Build args: PACKAGES = space-separated repo paths to install (in dependency order).
FROM node:22-slim AS contracts
WORKDIR /src
RUN corepack enable
COPY package.json tsconfig.base.json ./
COPY packages/contracts packages/contracts
RUN printf 'packages:\n  - "packages/contracts"\n' > pnpm-workspace.yaml \
 && pnpm install --filter @revenueos/contracts... \
 && pnpm --filter @revenueos/contracts build

# Bubblewrap built from the pinned commit (config/sources.yaml) for the sandbox supervisor (INV-11/12).
# nib (C15, pinned — docs/PINS.md): the PDF form CLI used by the OpenMuse attachment ->
# PDF -> filled-form -> reviewed-reply pipeline (spec 3.5).
FROM golang:1.26 AS nib
ARG NIB_SHA=1f23f70bb25a41eedef79acdc5068db438933ed3
RUN git clone https://github.com/daniel-alexander4/nib /nib && cd /nib && git checkout "$NIB_SHA" \
 && CGO_ENABLED=0 go build -trimpath -o /usr/local/bin/nib ./cmd/nib

# Aegis OS (C03, named, pinned — docs/PINS.md): the spec's "Aegis" kernel-sandbox + CoW shadow
# workspace + egress proxy, built from source at the pinned commit. Used as an opt-in engine
# (engine="aegis") in infra/sandbox-supervisor alongside our own Bubblewrap-direct path (default).
FROM rust:1.97-bookworm AS aegis
ARG AEGIS_OS_SHA=d9bdfa978d721cae0dc2bfa277ed371c9db60c5a
RUN apt-get update && apt-get install -y --no-install-recommends build-essential pkg-config git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && git clone -q https://github.com/heurion-org/aegis-os /aegis-os && cd /aegis-os && git checkout -q "$AEGIS_OS_SHA" \
 && cargo build --release --locked -p aos-cli \
 # The crate is `aos-cli`, but its own Cargo.toml names the binary `aegis-os`
 # ([[bin]] name = "aegis-os" in crates/aos-cli/Cargo.toml) -- not `aos-cli`.
 && install -m 0755 target/release/aegis-os /usr/local/bin/aegis-os

FROM python:3.12-slim AS bwrap
ARG BWRAP_SHA=1fb0aa26d3eb66254f7742e704add7f82f41a582
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates meson ninja-build gcc libc6-dev \
      libcap-dev pkg-config \
 && git clone -q https://github.com/containers/bubblewrap /bw && git -C /bw checkout -q "$BWRAP_SHA" \
 && meson setup /bw/build /bw -Dman=disabled -Dselinux=disabled -Dtests=false -Dbash_completion=disabled \
      -Dzsh_completion=disabled -Dpython=/usr/local/bin/python3 \
 && ninja -C /bw/build bwrap && install -m 0755 /bw/build/bwrap /usr/local/bin/bwrap

# C04 agent-discover (named, pinned — docs/PINS.md): the registry of record for installed MCP
# servers, built from source at the pinned commit. Its daemon runs next to the discovery service.
FROM node:22-bookworm AS agentdiscover
ARG AGENT_DISCOVER_SHA=c8a48bc73993d1cf75c00bb67352f0d20356ab3b
ENV HUSKY=0 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
RUN git clone -q https://github.com/keshrath/agent-discover /ad && cd /ad && git checkout -q "$AGENT_DISCOVER_SHA" \
 && npm ci --no-audit --no-fund && npm run build && npm prune --omit=dev --no-audit --no-fund \
 && mkdir -p /opt/agent-discover && cp -r dist node_modules package.json /opt/agent-discover/

# C04 MCPfinder (named, pinned): multi-registry search, trust signals, install-ready JSON. Built
# from source; it runs as a sandboxed stdio MCP server registered in agent-discover.
FROM node:22-bookworm AS mcpfinder
ARG MCPFINDER_SHA=4c9e2f421a4bfda47e01052ce21931d9b6026b27
RUN git clone -q https://github.com/mcpfinder/mcpfinder /mf && cd /mf && git checkout -q "$MCPFINDER_SHA" \
 && corepack enable && pnpm install --frozen-lockfile --filter "@mcpfinder/core" --filter "@mcpfinder/server" --filter "mcpfinder" \
 && pnpm --filter @mcpfinder/core build && pnpm --filter @mcpfinder/server build \
 && mkdir -p /opt/mcpfinder && cp -r package.json node_modules packages /opt/mcpfinder/

FROM python:3.12-slim
ARG PACKAGES
# DESKTOP=1 (runtime-omni, spec 3.1): a real X11 desktop for OmniPilot's GUI, screen,
# clipboard, app and notification tools.
ARG DESKTOP=0
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client util-linux libcap2 git ca-certificates \
      strace libstdc++6 libatomic1 \
 && if [ "$DESKTOP" = "1" ]; then apt-get install -y --no-install-recommends xvfb fluxbox x11vnc xterm xclip xsel \
      xdotool scrot x11-utils libnotify-bin dbus-x11 tk procps chromium libnss3-tools; fi \
 && if [ "$DESKTOP" = "1" ]; then \
      git clone https://github.com/novnc/noVNC /opt/novnc \
      && git -C /opt/novnc checkout e8b5024d4603587b29ffede4fbd28b1fa2939829 \
      && rm -rf /opt/novnc/.git; fi \
 && rm -rf /var/lib/apt/lists/*
COPY --from=bwrap /usr/local/bin/bwrap /usr/local/bin/bwrap
COPY --from=nib /usr/local/bin/nib /usr/local/bin/nib
COPY --from=aegis /usr/local/bin/aegis-os /usr/local/bin/aegis-os
# Node (for agent-discover, MCPfinder and npx-launched MCP servers inside their sandboxes).
COPY --from=agentdiscover /usr/local/bin/node /usr/local/bin/node
COPY --from=agentdiscover /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
COPY --from=agentdiscover /opt/agent-discover /opt/agent-discover
COPY --from=mcpfinder /opt/mcpfinder /opt/mcpfinder
WORKDIR /src
COPY packages/pycommon packages/pycommon
COPY packages/contracts/python packages/contracts/python
COPY packages/mcp-common packages/mcp-common
COPY packages/risk packages/risk
COPY services services
COPY mcp mcp
COPY infra/egress infra/egress
COPY infra/sandbox-supervisor infra/sandbox-supervisor
COPY infra/discovery infra/discovery
COPY scripts scripts
COPY infra/docker/runtime-omni-entrypoint.sh /usr/local/bin/runtime-omni-entrypoint
COPY config /src/config
COPY --from=contracts /src/packages/contracts/generated packages/contracts/generated
RUN pip install --no-cache-dir "datamodel-code-generator>=0.26" \
 && ./scripts/gen-python-contracts.sh \
 && pip install --no-cache-dir ./packages/pycommon ./packages/contracts/python ./packages/risk $PACKAGES \
 && pip install --no-cache-dir "mcptoon @ git+https://github.com/activeing123/mcptoon@3af4967dd24433948faf3dbe0259ca64751b8818" \
 && if [ "$DESKTOP" = "1" ]; then pip install --no-cache-dir "playwright>=1.49" "websockify>=0.11"; fi
ENV REVENUEOS_CONFIG_DIR=/src/config PYTHONUNBUFFERED=1 HOME=/home/revenueos
# Non-root runtime. compose runs it as the host owner of infra/secrets (REVENUEOS_UID, group 0) so
# secrets stay 0600/0700; writable dirs are group-0 writable (the arbitrary-UID pattern).
RUN useradd --uid 10001 --gid 0 --home-dir /home/revenueos --create-home revenueos \
 && mkdir -p /var/lib/revenueos/duckdb /var/lib/revenueos/workspaces /var/lib/revenueos/profiles /workspace \
      /var/lib/revenueos/mcp /var/lib/revenueos/agent-discover \
 && chgrp -R 0 /var/lib/revenueos /home/revenueos /workspace && chmod -R g=u /var/lib/revenueos /home/revenueos /workspace \
 && chmod 0755 /usr/local/bin/runtime-omni-entrypoint
USER 10001
