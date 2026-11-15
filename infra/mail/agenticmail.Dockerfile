# AgenticMail (named, spec 2.1) built from the commit pinned in config/sources.yaml.
FROM node:22-slim AS build
ARG AGENTICMAIL_SHA=af1e0ef546b5862c1f7134649e761f56356c688a
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN git clone -q https://github.com/agenticmail/agenticmail /app && git -C /app checkout -q "$AGENTICMAIL_SHA"
WORKDIR /app
RUN npm ci --ignore-scripts --no-audit --no-fund && npm run build:core && npm run build:api

FROM node:22-slim
COPY --from=build /app /app
COPY infra/mail/agenticmail-entrypoint.sh /usr/local/bin/agenticmail-entrypoint
# node:sqlite needs Node >= 22.5; data dir is group-0 writable for the arbitrary runtime UID.
RUN mkdir -p /data && chgrp 0 /data && chmod 0770 /data && chmod 0755 /usr/local/bin/agenticmail-entrypoint
WORKDIR /app/packages/api
ENV AGENTICMAIL_DATA_DIR=/data HOME=/data
USER node
ENTRYPOINT ["/usr/local/bin/agenticmail-entrypoint"]
CMD ["node", "dist/index.js"]
