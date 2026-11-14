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

FROM python:3.12-slim
ARG PACKAGES
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client util-linux \
 && rm -rf /var/lib/apt/lists/*
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
ENV REVENUEOS_CONFIG_DIR=/src/config PYTHONUNBUFFERED=1
