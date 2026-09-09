FROM node:22-alpine AS base
RUN corepack enable && apk add --no-cache libc6-compat openssl
WORKDIR /repo
COPY package.json pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/schema/package.json packages/schema/
COPY packages/ui/package.json packages/ui/
RUN pnpm install --frozen-lockfile=false
COPY packages ./packages
COPY apps/web ./apps/web
WORKDIR /repo/apps/web
RUN pnpm prisma generate && pnpm next build
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["sh", "-c", "pnpm prisma db push --skip-generate --accept-data-loss && node prisma/seed.mjs && pnpm next start -p 3000"]
