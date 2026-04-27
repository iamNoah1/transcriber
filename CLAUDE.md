# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
cd backend
uv sync                          # install deps
uv run uvicorn app.main:app --reload --port 3030
uv run pytest                    # all tests
uv run pytest tests/test_pipeline.py::test_file_upload_worker_download  # single test
```

### Frontend
```bash
cd web
pnpm install
pnpm dev       # http://localhost:5173 — proxies /api → :3030
pnpm test      # Vitest
pnpm build     # output to web/dist
```

### Docker (full stack)
```bash
docker compose up --build        # http://localhost:3030
```

## Architecture

Single-user app: the OIDC `sub` of the owner is stored in `OWNER_OPEN_ID`; anyone else gets a 403 on the callback.

### Request / job lifecycle
1. **FastAPI** (`backend/app/main.py`) creates the app, wires up auth, the SQLite DB, storage, and a `Worker`.
2. **`/api/jobs` or `/api/jobs/files`** (`jobs.py`) inserts a row into SQLite and calls `worker.submit(job_id)`.
3. **`Worker`** (`workers.py`) drops the job onto a `ThreadPoolExecutor` (max 1 worker).
4. **`JobRunner.run_job`** runs in that thread. It calls `asyncio.run()` (not `await`) for every DB write — this is intentional because the thread has no event loop. Tests exploit this by setting `app.state.submit_job = pending.append` and calling `runner.run_job()` directly from the sync test thread.
5. **`LocalProvider`** (`providers/local.py`) shells out to `audiotap` (download) and `whisperbatch` (transcription). Both binaries emit `\r`-rewriting progress lines; `_run_cli` splits on `[\r\n]` to capture them.
6. After transcription, outputs are either served directly (single file) or zipped (`Storage.zip_output`). Input files are deleted from disk once transcription finishes.

### Key modules
| Module | Role |
|---|---|
| `app/auth.py` | OIDC PKCE flow + session cookie (JWT HS256). `AUTH_DISABLED=true` bypasses auth and returns `{"open_id": "dev"}`. |
| `app/config.py` | `pydantic-settings` `Settings`; reads `.env`. `AUTH_DISABLED` must be false in production. |
| `app/db.py` | `aiosqlite` wrapper. `Database.connect()` opens a new connection per call (no pool). Schema migration is inline and idempotent. |
| `app/storage.py` | Manages `storage/jobs/<job_id>/{input,output}/`. `zip_output` bundles all output files. |
| `app/providers/base.py` | `TranscriptionProvider` Protocol — the seam for testing. |

### Docker layout
Three-stage build: `web-build` (Node/pnpm) → `audiotap-bin` (copies binary) → `runtime` (whisperbatch base adds Python deps). The React SPA lands at `backend/app/static` and is served by FastAPI's `StaticFiles` + catch-all SPA route.

Volume mounts in production:
- `/app/data` — SQLite database
- `/app/storage` — job file storage

### Frontend
Vite + React + React Router. Four pages: `Login`, `Home` (submit form), `Jobs` (list), `JobDetail` (poll status, download). All API calls go through `web/src/api.ts` which redirects to `/login` on 401. The dev proxy in `vite.config.ts` forwards `/api` to `:3030`.

## Environment variables
See `.env.example`. Required at runtime: `OWNER_OPEN_ID`, `JWT_SECRET`. For production also: `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `AUTH_DISABLED=false`.
