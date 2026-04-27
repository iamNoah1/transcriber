# Pinned upstream image versions — bump these when audiotap/whisperbatch release.
ARG AUDIOTAP_VERSION=v0.2.1
ARG WHISPERBATCH_VERSION=v0.3.1

# ---- Stage 1: build the React SPA ----
FROM node:20-alpine AS web-build
WORKDIR /web
RUN corepack enable && corepack prepare pnpm@9 --activate
COPY web/package.json web/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY web/ ./
RUN pnpm exec vite build

# ---- Stage 2: pull the audiotap binary from its official image ----
FROM ghcr.io/iamnoah1/audiotap:${AUDIOTAP_VERSION} AS audiotap-bin

# ---- Stage 3: runtime — whisperbatch base provides python 3.12 + ffmpeg + openai-whisper ----
FROM ghcr.io/iamnoah1/whisperbatch:${WHISPERBATCH_VERSION} AS runtime

# Reset the upstream ENTRYPOINT (which would otherwise run whisperbatch as the CLI).
ENTRYPOINT []

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# curl for HEALTHCHECK; yt-dlp pre-installed so audiotap skips its first-run download;
# uv to manage the backend's Python deps.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir yt-dlp uv==0.4.25

COPY --from=audiotap-bin /usr/local/bin/audiotap /usr/local/bin/audiotap

WORKDIR /app
COPY backend/pyproject.toml ./backend/pyproject.toml
RUN cd backend && uv sync --no-dev

COPY backend/ ./backend/
COPY --from=web-build /web/dist ./backend/app/static

WORKDIR /app/backend
ENV DATA_DIR=/app/data \
    STORAGE_DIR=/app/storage \
    ENV=production

EXPOSE 3030

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS http://localhost:3030/api/health || exit 1

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3030"]
