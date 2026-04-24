# ---- Stage 1: build the React SPA ----
FROM node:20-alpine AS web-build
WORKDIR /web
RUN corepack enable && corepack prepare pnpm@9 --activate
COPY web/package.json web/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY web/ ./
RUN pnpm build

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps: ffmpeg for whisper; curl to fetch tool binaries
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps via uv
RUN pip install uv==0.4.25
WORKDIR /app
COPY backend/pyproject.toml ./backend/pyproject.toml
RUN cd backend && uv sync --no-dev

# Install openai-whisper and yt-dlp up-front (whisperbatch will find them)
RUN pip install --no-cache-dir openai-whisper yt-dlp

# Pull audiotap and whisperbatch binaries from GitHub Releases
ARG TC_AUDIOTAP_VERSION=latest
ARG TC_WHISPERBATCH_VERSION=latest
RUN set -eux; \
    arch="$(uname -m)"; case "$arch" in x86_64) arch=amd64;; aarch64) arch=arm64;; esac; \
    for tool in audiotap whisperbatch; do \
      url="https://github.com/iamNoah1/${tool}/releases/${TC_AUDIOTAP_VERSION}/download/${tool}_linux_${arch}.tar.gz"; \
      [ "$tool" = "whisperbatch" ] && url="https://github.com/iamNoah1/${tool}/releases/${TC_WHISPERBATCH_VERSION}/download/${tool}_linux_${arch}.tar.gz"; \
      curl -fsSL -o "/tmp/${tool}.tgz" "$url"; \
      tar -xzf "/tmp/${tool}.tgz" -C /usr/local/bin; \
      chmod +x "/usr/local/bin/${tool}"; \
      rm "/tmp/${tool}.tgz"; \
    done

# Copy backend code
COPY backend/ ./backend/

# Copy the compiled SPA into the FastAPI static dir
COPY --from=web-build /web/dist ./backend/app/static

WORKDIR /app/backend
ENV DATA_DIR=/app/data \
    STORAGE_DIR=/app/storage \
    ENV=production

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
