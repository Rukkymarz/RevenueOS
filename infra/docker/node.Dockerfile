# Node apps (api, command-center, admin). Build args: APP = workspace package name, APP_DIR = its path.
FROM node:22-slim AS build
ARG APP
WORKDIR /src
RUN corepack enable
COPY package.json pnpm-workspace.yaml tsconfig.base.json turbo.json ./
COPY packages packages
COPY apps apps
RUN pnpm install --filter "${APP}..." && pnpm turbo run build --filter "${APP}..."

FROM node:22-slim
ARG APP_DIR
WORKDIR /src
COPY --from=build /src /src
WORKDIR /src/${APP_DIR}
ENV NODE_ENV=production
# Non-root runtime (the image's built-in `node` user); compose may override the UID to read secrets.
ENV HOME=/tmp
USER node
