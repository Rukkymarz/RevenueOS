# microsoft/playwright-mcp (C02, named, pinned — docs/PINS.md), built from source at the pinned
# commit rather than `npx @playwright/mcp@latest` (keeps the exact version under our own control,
# same policy as the Go `nib` and Rust `aegis-os` binaries elsewhere in infra/docker). Runs the
# server's own HTTP/SSE transport (`--port`) so services/runtime-os can reach it with the same
# McpClient (packages/mcp-common) used for every other internal MCP call — see
# services/runtime-os/revenueos_runtime_os/tools.py's `browser_call`.
FROM node:22-slim
ARG PLAYWRIGHT_MCP_SHA=78eca85361efb545a4c0f59b6140aef0721c5412
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates tini \
 && rm -rf /var/lib/apt/lists/* \
 && git clone -q https://github.com/microsoft/playwright-mcp . \
 && git checkout -q "$PLAYWRIGHT_MCP_SHA" \
 && npm ci --omit=dev \
 && npx -y playwright-core install-deps chromium \
 && npx -y playwright-core install --no-shell chromium \
 && chown -R node:node /app node_modules

USER node
# Writable cwd: the server may create a default output dir in it (screenshots, traces).
WORKDIR /home/node
ENV NODE_ENV=production
# --no-sandbox: the container itself is our sandbox boundary (no host mounts, network only via
# the compose `core` network); chromium's own setuid sandbox needs privileges we don't grant it.
ENTRYPOINT ["/usr/bin/tini", "-s", "--", "node", "/app/cli.js", "--headless", "--browser", "chromium", "--no-sandbox"]
