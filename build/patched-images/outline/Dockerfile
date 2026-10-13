# syntax=docker/dockerfile:1
ARG NODE_BUILD_IMAGE=node:26.11.1-bookworm@sha256:f1233c415b41ffcf237c717b3dea92e9d4ea006e0e4c71edcb790605d74f5404
ARG NODE_RUN_IMAGE=node:26.11.1-bookworm-slim@sha256:86f07bc9c5dce4578cf37e5a418b7bfc7f817cda25cde66e2b66e95ed86c4567
FROM ${NODE_BUILD_IMAGE} AS build

ARG APP_PATH=/opt/outline
ARG CDN_URL
ARG SOURCE_REVISION=unknown
WORKDIR ${APP_PATH}
COPY ./package.json ./yarn.lock ./.yarnrc.yml ./
COPY ./patches ./patches
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends cmake && \
    rm -rf /var/lib/apt/lists/*
ENV NODE_OPTIONS="--max-old-space-size=3072" \
    YARN_NETWORK_CONCURRENCY=4
RUN npm install -g corepack && corepack enable && \
    yarn install --immutable --network-timeout 1000000 && yarn cache clean
COPY . .
RUN yarn build
RUN yarn workspaces focus --production && yarn cache clean

FROM ${NODE_RUN_IMAGE} AS runner

ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.source="https://github.com/outline/outline" \
      org.opencontainers.image.revision="${SOURCE_REVISION}"
ARG APP_PATH=/opt/outline
WORKDIR ${APP_PATH}
ENV NODE_ENV=production MALLOC_ARENA_MAX=2
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends wget && \
    rm -rf /var/lib/apt/lists/* && \
    addgroup --gid 1001 nodejs && \
    adduser --uid 1001 --ingroup nodejs nodejs && \
    mkdir -p /var/lib/outline && \
    chown -R nodejs:nodejs /var/lib/outline ${APP_PATH}
COPY --from=build --chown=nodejs:nodejs ${APP_PATH}/build ./build
COPY --from=build --chown=nodejs:nodejs ${APP_PATH}/server ./server
COPY --from=build --chown=nodejs:nodejs ${APP_PATH}/public ./public
COPY --from=build --chown=nodejs:nodejs ${APP_PATH}/.sequelizerc ./.sequelizerc
COPY --from=build --chown=nodejs:nodejs ${APP_PATH}/node_modules ./node_modules
COPY --from=build --chown=nodejs:nodejs ${APP_PATH}/package.json ./package.json
ENV FILE_STORAGE_LOCAL_ROOT_DIR=/var/lib/outline/data
RUN mkdir -p "$FILE_STORAGE_LOCAL_ROOT_DIR" && \
    chown -R nodejs:nodejs "$FILE_STORAGE_LOCAL_ROOT_DIR" && \
    chmod 1777 "$FILE_STORAGE_LOCAL_ROOT_DIR"
VOLUME /var/lib/outline/data
USER nodejs
HEALTHCHECK --interval=1m CMD wget -qO- "http://localhost:${PORT:-3000}/_health" | grep -q "OK" || exit 1
EXPOSE 3000
CMD ["node", "build/server/index.js"]
