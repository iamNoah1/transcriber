# transcribe-cloud

Cloud-hosted wrapper around [audiotap](https://github.com/iamNoah1/audiotap) and [whisperbatch](https://github.com/iamNoah1/whisperbatch). Drop YouTube URLs, YouTube playlists, or audio files into a simple React UI; get transcripts back as a file or a zip. Single-user, Pocket ID OIDC.

## Local development

### Backend

```bash
cd backend
uv sync
cp ../.env.example ../.env
# set JWT_SECRET, OWNER_OPEN_ID; leave AUTH_DISABLED=true for dev
uv run uvicorn app.main:app --reload --port 3030
```

### Frontend

```bash
cd web
pnpm install
pnpm dev       # http://localhost:5173, proxies /api to :3030
```

### Docker (full stack)

```bash
cp .env.example .env
docker compose up --build
# http://localhost:3030
```

## Deployment (Coolify)

1. Point Coolify at this repo. It builds `Dockerfile`.
2. Configure env vars:
   - `ENV=production`
   - `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`
   - `OWNER_OPEN_ID` (your Pocket ID `sub`)
   - `JWT_SECRET` (random 32+ bytes)
   - `AUTH_DISABLED=false`
3. Mount persistent volumes on `/app/data` and `/app/storage`.
4. Healthcheck is `GET /api/health` (built into the image).

## Tests

```bash
cd backend && uv run pytest
cd web && pnpm test
```

## Design

See `docs/superpowers/specs/2026-04-23-transcribe-cloud-design.md`.
