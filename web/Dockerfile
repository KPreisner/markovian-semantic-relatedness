# syntax=docker/dockerfile:1
# The web app (Next.js UI + BFF).
#
#   deps     node_modules from package-lock.json
#   dev      `next dev`; compose-overrides/compose.web-dev.yaml mounts the source over it
#   builder  `next build` with `output: "standalone"`
#   prod     only the standalone server, as the non-root `nextjs` user

# Node matches web/.nvmrc (CI) and compose.yaml's web-tools.
ARG NODE_IMAGE=node:24.22.1-alpine3.24

FROM ${NODE_IMAGE} AS base
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app


FROM base AS deps
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund


FROM deps AS dev
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]


FROM deps AS builder
COPY . .
# Baked into the build: next.config.ts's /fastapi rewrite is resolved at build time.
ARG MSR_API_URL=http://api:8000
ENV MSR_API_URL=${MSR_API_URL}
RUN npm run build


FROM base AS prod
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000
RUN addgroup -S -g 1001 nextjs && adduser -S -u 1001 -G nextjs nextjs
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nextjs /app/public ./public
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
