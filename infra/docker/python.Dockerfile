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
FROM python:3.12-slim AS bwrap
ARG BWRAP_SHA=1fb0aa26d3eb66254f7742e704add7f82f41a582
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates meson ninja-build gcc libc6-dev \
      libcap-dev pkg-config \
 && git clone -q https://github.com/containers/bubblewrap /bw && git -C /bw checkout -q "$BWRAP_SHA" \
 && meson setup /bw/build /bw -Dman=disabled -Dselinux=disabled -Dtests=false -Dbash_completion=disabled \
      -Dzsh_completion=disabled -Dpython=/usr/local/bin/python3 \
 && ninja -C /bw/build bwrap && install -m 0755 /bw/build/bwrap /usr/local/bin/bwrap

FROM python:3.12-slim
ARG PACKAGES
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client util-linux libcap2 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=bwrap /usr/local/bin/bwrap /usr/local/bin/bwrap
WORKDIR /src
COPY packages/pycommon packages/pycommon
COPY packages/contracts/python packages/contracts/python
COPY packages/mcp-common packages/mcp-common
COPY services services
COPY mcp mcp
COPY infra/egress infra/egress
COPY infra/sandbox-supervisor infra/sandbox-supervisor
COPY scripts scripts
COPY config /src/config
COPY --from=contracts /src/packages/contracts/generated packages/contracts/generated
RUN pip install --no-cache-dir "datamodel-code-generator>=0.26" \
 && ./scripts/gen-python-contracts.sh \
 && pip install --no-cache-dir ./packages/pycommon ./packages/contracts/python $PACKAGES
ENV REVENUEOS_CONFIG_DIR=/src/config PYTHONUNBUFFERED=1 HOME=/home/revenueos
# Non-root runtime. compose runs it as the host owner of infra/secrets (REVENUEOS_UID, group 0) so
# secrets stay 0600/0700; writable dirs are group-0 writable (the arbitrary-UID pattern).
RUN useradd --uid 10001 --gid 0 --home-dir /home/revenueos --create-home revenueos \
 && mkdir -p /var/lib/revenueos/duckdb /var/lib/revenueos/workspaces /var/lib/revenueos/profiles \
 && chgrp -R 0 /var/lib/revenueos /home/revenueos && chmod -R g=u /var/lib/revenueos /home/revenueos
USER 10001
