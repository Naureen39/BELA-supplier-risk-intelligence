# Web image (Next.js). Build from the repository root:
#   docker build -f infra/docker/web.Dockerfile --build-arg API_ORIGIN=http://api:8000 -t provenance-web .
# The API address is baked into the build because Next.js resolves its /api rewrite at build time.
FROM node:24-slim AS build
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
ARG API_ORIGIN=http://api:8000
ARG NEXT_PUBLIC_DEMO_MODE=false
ARG NEXT_PUBLIC_DEMO_VIEWER_PASSWORD=
ENV API_ORIGIN=$API_ORIGIN NEXT_PUBLIC_DEMO_MODE=$NEXT_PUBLIC_DEMO_MODE \
    NEXT_PUBLIC_DEMO_VIEWER_PASSWORD=$NEXT_PUBLIC_DEMO_VIEWER_PASSWORD NEXT_TELEMETRY_DISABLED=1
RUN npm run build && npm prune --omit=dev

FROM node:24-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /web
COPY --from=build --chown=node:node /web/.next ./.next
COPY --from=build --chown=node:node /web/node_modules ./node_modules
COPY --from=build --chown=node:node /web/public ./public
COPY --from=build --chown=node:node /web/package.json /web/next.config.mjs ./
COPY --from=build --chown=node:node /web/messages ./messages
COPY --from=build --chown=node:node /web/src/i18n ./src/i18n
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 CMD curl -fsS http://127.0.0.1:3000/ >/dev/null || exit 1
CMD ["npx", "next", "start", "-p", "3000"]
