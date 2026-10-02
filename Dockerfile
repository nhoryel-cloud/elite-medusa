# Multi-stage Dockerfile for the elite-medusa backend (pnpm monorepo).
# Build: install + medusa build. Runtime: backend only, node:22-slim.

FROM node:22-slim AS deps
ENV PNPM_HOME="/pnpm" PATH="$PNPM_HOME:$PATH"
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./
COPY apps/backend/package.json apps/backend/package.json
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile --filter @dtc/backend...

FROM node:22-slim AS build
ENV PNPM_HOME="/pnpm" PATH="$PNPM_HOME:$PATH"
RUN corepack enable
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/pnpm-lock.yaml ./
COPY apps/backend ./apps/backend
COPY package.json pnpm-workspace.yaml turbo.json ./
RUN pnpm --filter @dtc/backend build

FROM node:22-slim AS runner
ENV PNPM_HOME="/pnpm" PATH="$PNPM_HOME:$PATH" NODE_ENV=production PORT=9000 HOST=0.0.0.0
RUN corepack enable
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/apps/backend ./apps/backend
COPY package.json pnpm-workspace.yaml turbo.json ./
WORKDIR /app/apps/backend
EXPOSE 9000
CMD ["pnpm", "start"]
