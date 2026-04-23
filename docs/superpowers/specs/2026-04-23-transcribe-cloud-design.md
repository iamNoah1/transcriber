# transcribe-cloud — Design Spec

**Date:** 2026-04-23
**Status:** Approved for implementation planning
**Scope:** Phase 1, Step 1 of the Knowledge Coach System — a cloud-hosted FastAPI service with a simple React drag-and-drop UI that wraps `audiotap` and `whisperbatch` to turn YouTube URLs, YouTube playlists, and audio files into downloadable transcripts.

Related: [Knowledge Coach System — Architecture & Concept](https://www.notion.so/3499bef7bfba81d18c1eff52d0f3eba3) (Notion).

---

## 1. Goals & non-goals

**Goals**

- Single-user, cloud-hosted app accessible from any browser.
- Drop in YouTube URLs, YouTube playlist URLs, or audio files (one or many) and get back transcript files.
- Results downloadable as a single file (one input) or a zip (multiple inputs).
- Uses the user's existing CLIs (`audiotap`, `whisperbatch`) — not managed APIs.
- Low-key: one container to deploy, one volume to back up.
- Authenticated via Pocket ID (OIDC). Only the owner (`OWNER_OPEN_ID`) may access.

**Non-goals (v1)**

- Multi-user accounts, per-user isolation beyond "only me".
- n8n integration or Notion sync (explicitly deferred per user).
- Groq/OpenAI providers at runtime (interface in place, implementation deferred).
- GPU acceleration. CPU whisper on the VPS is acceptable for personal use.
- Horizontal scaling, background-worker containers (single in-process worker for v1).

---

## 2. Architecture

**Shape:** monorepo, single container. FastAPI serves `/api/*` and the compiled Vite SPA at `/`. `audiotap` and `whisperbatch` binaries live on `PATH` inside the image. SQLite and a `storage/` tree live on a Coolify-mounted persistent volume.

```
transcribe-cloud/
├── backend/                     FastAPI app
│   ├── app/
│   │   ├── main.py              FastAPI entry; mounts routes + static SPA
│   │   ├── config.py            env vars (pydantic-settings)
│   │   ├── auth.py              Pocket ID OIDC (authlib) + session middleware
│   │   ├── jobs.py              /api/jobs endpoints
│   │   ├── workers.py           ThreadPoolExecutor, run_job()
│   │   ├── db.py                SQLite schema + async access
│   │   ├── storage.py           upload dir, result dir, zipping
│   │   └── providers/
│   │       ├── base.py          Provider interface
│   │       └── local.py         shells out to audiotap + whisperbatch
│   ├── pyproject.toml           uv / ruff / pytest
│   └── tests/
├── web/                         Vite + React + Tailwind + shadcn
│   ├── src/
│   │   ├── pages/               Login, Home, Jobs, JobDetail
│   │   ├── components/          Dropzone, JobCard, shadcn/ui primitives
│   │   └── api.ts               fetch client
│   └── vite.config.ts           dev proxy to :8000
├── Dockerfile                   multi-stage: Vite build → FastAPI container
├── docker-compose.yml           local dev orchestration
└── README.md
```

**Runtime data directories** (mounted as volumes in Coolify):

```
/app/data/app.db                 SQLite database
/app/storage/
└── jobs/
    └── {job_id}/
        ├── input/               uploaded files OR audiotap output
        ├── output/              whisperbatch transcripts
        └── result.zip           (or result.{ext} for single-file jobs)
```

---

## 3. Data model (SQLite)

```sql
CREATE TABLE users (
  open_id        TEXT PRIMARY KEY,   -- Pocket ID `sub`
  name           TEXT,
  email          TEXT,
  last_signed_in TEXT                -- ISO-8601
);

CREATE TABLE jobs (
  id           TEXT PRIMARY KEY,     -- UUIDv4
  user_id      TEXT NOT NULL REFERENCES users(open_id),
  status       TEXT NOT NULL,        -- queued | running | done | failed
  input_kind   TEXT NOT NULL,        -- urls | files
  inputs_json  TEXT NOT NULL,        -- JSON array of URLs or original filenames
  options_json TEXT NOT NULL,        -- JSON {formats: [...], model: string|null}
  message      TEXT,                 -- progress / error, human-readable
  result_path  TEXT,                 -- absolute path to result artifact
  file_count   INTEGER,
  created_at   TEXT NOT NULL,
  started_at   TEXT,
  finished_at  TEXT
);

CREATE INDEX idx_jobs_user_created ON jobs(user_id, created_at DESC);
```

Migrations: a small `db.init()` called on startup, idempotent `CREATE TABLE IF NOT EXISTS`.

---

## 4. API endpoints

All routes under `/api/`. All job routes require a valid session cookie; unauthenticated requests get `401`.

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/api/auth/login`         | Redirect to Pocket ID with PKCE state + verifier cookies |
| GET    | `/api/auth/callback`      | Exchange code → gate on `OWNER_OPEN_ID` → set session cookie → 302 to `/` |
| POST   | `/api/auth/logout`        | Clear session cookie |
| GET    | `/api/auth/me`            | `{open_id, name, email}` or 401 |
| POST   | `/api/jobs`               | Create job (JSON `{urls, options}` **or** multipart `files[] + options_json`) |
| GET    | `/api/jobs`               | List current user's jobs, newest first |
| GET    | `/api/jobs/{id}`          | Full job row |
| GET    | `/api/jobs/{id}/download` | Stream result artifact |
| DELETE | `/api/jobs/{id}`          | Delete job row + its `storage/jobs/{id}/` tree |
| GET    | `/api/health`             | 200 OK for Coolify liveness |

**Options shape:**
```json
{ "formats": ["txt", "srt"], "model": "medium" }
```
`formats` defaults to `["txt"]`. `model=null` means whisperbatch auto-selects based on VRAM/RAM.

---

## 5. Job lifecycle

**Create flow (`POST /api/jobs`):**

1. Validate payload: at least one URL or one file; formats are a subset of `{txt, json, srt, vtt, tsv}`; model is null or one of `{tiny, base, medium, large}`.
2. Generate `job_id` (UUIDv4). Create `storage/jobs/{id}/input/` and `output/`.
3. For multipart uploads: stream each uploaded file to `input/` with sanitised filename; reject anything exceeding `MAX_UPLOAD_MB` per file or `MAX_TOTAL_UPLOAD_MB` per request (defaults 500 MB / 2 GB).
4. Insert row with `status="queued"`, full inputs and options serialised.
5. Submit `run_job(job_id)` to the `ThreadPoolExecutor`.
6. Return `201 {"job_id": "...", "status": "queued"}`.

**Worker (`run_job(job_id)`):**

1. `UPDATE jobs SET status='running', started_at=now(), message='Preparing…'`.
2. Dispatch on `input_kind`:
   - **`urls`** — exec `audiotap url1 url2 … --output-dir input/ --format opus --workers 2`. Stream stdout, update `message` as `"Downloaded N/M audio files"`. YouTube playlist URLs expand transparently inside `yt-dlp` → `audiotap`.
   - **`files`** — already on disk under `input/`.
3. Exec `whisperbatch -i input/ -o output/ -f txt [-f srt …] [-m model] [--overwrite]`. Stream stderr; surface progress lines as `message`.
4. Count files in `output/`. If one file: `result_path = output/{stem}.{first_format}`. If many: zip `output/` → `result.zip`, set `result_path` to the zip.
5. `UPDATE jobs SET status='done', finished_at=now(), result_path=..., file_count=...`.
6. Delete `input/` to reclaim disk; keep `output/` and `result.zip`.
7. On any exception: `status='failed'`, `message=str(e)[:500]`. Keep whatever was produced for post-mortem.

**Concurrency:** single worker thread. A second submitted job sits in `queued`; frontend shows it as such. This is a deliberate v1 simplification.

**Retention:** an asyncio task started at app boot runs every 6 hours; deletes jobs where `finished_at < now - JOB_RETENTION_DAYS` (default 30). Removes DB row and `storage/jobs/{id}/` tree.

---

## 6. Authentication (Pocket ID OIDC)

**Library:** `authlib` — handles PKCE, state, token exchange, userinfo.

**Env vars:**

| Var | Purpose |
|-----|---------|
| `OIDC_ISSUER_URL`     | Pocket ID issuer (must expose `/.well-known/openid-configuration`) |
| `OIDC_CLIENT_ID`      | OIDC client ID |
| `OIDC_CLIENT_SECRET`  | OIDC client secret |
| `OIDC_SCOPES`         | default `"openid profile email"` |
| `OWNER_OPEN_ID`       | the single `sub` allowed to sign in; anyone else is rejected |
| `JWT_SECRET`          | HS256 signing key for session cookies |
| `SESSION_COOKIE_NAME` | default `"tc_session"` |
| `AUTH_DISABLED`       | `"true"` bypasses auth with a fixed dev user; refused in production |

**Flow:**

1. `GET /api/auth/login` — authlib creates `state` + PKCE `code_verifier`/`code_challenge` (S256). Stores both in short-lived (10 min) signed cookies. 302 to `authorization_endpoint`.
2. `GET /api/auth/callback` — authlib validates `state`, exchanges `code` for tokens, fetches `/userinfo`. **Gate:** reject with 403 if `sub != OWNER_OPEN_ID` (no DB row created). On match, `upsert` the user, issue an HS256 JWT (`sub=open_id`, `name`, 1-year exp), set session cookie (`HttpOnly`, `SameSite=Lax`, `Secure` in prod), 302 to `/`.
3. `POST /api/auth/logout` — clear cookie.

**Session middleware:** `current_user()` FastAPI dependency reads the cookie, verifies the JWT, returns `{open_id, name}`. `/api/jobs*` routes depend on it. Expired/invalid → `401`.

**Dev bypass:** when `AUTH_DISABLED=true`, `current_user()` returns a fixed `{open_id: "dev", name: "Dev"}`. Startup asserts `ENV != "production"` when this flag is set.

Pattern referenced from `autonomo_llc_finance/server/_core/oauth.ts`, ported to Python.

---

## 7. Frontend

**Stack:** Vite + React + TypeScript + Tailwind + shadcn/ui. Matches the existing autonomo stack for familiarity.

**Pages:**

- `/login` — single "Sign in with Pocket ID" button → `window.location = "/api/auth/login"`.
- `/` (Home) — drag-and-drop zone (React-dropzone or HTML File API) + URL textarea (one URL per line) + format checkboxes + optional model dropdown + "Transcribe" button. On submit: `POST /api/jobs`, redirect to `/jobs/{id}`.
- `/jobs` — table/list of jobs, newest first, with status badges and row-level "Download" / "Delete" actions.
- `/jobs/{id}` — detail view. Polls `GET /api/jobs/{id}` every 2 seconds while status is `queued` or `running`. Shows `message`, input list, timings. When `done`: a "Download" button links to `/api/jobs/{id}/download`.

**API client (`api.ts`):** fetch wrapper that includes credentials, intercepts `401` and redirects to `/login`. TypeScript interfaces mirror the backend Pydantic models.

**Boot:** `App.tsx` calls `GET /api/auth/me` on mount. 401 → redirect to `/login`. 200 → render the app.

**Dev server:** Vite on `:5173` proxies `/api/*` to FastAPI on `:8000`.

---

## 8. Error handling

| Condition | Behaviour |
|-----------|-----------|
| Invalid YouTube URL (`audiotap` exits non-zero) | Job `failed`, `message` = stderr tail. Sibling URLs in same job are not attempted. |
| Per-file whisperbatch failure | whisperbatch already returns a summary; we surface `"N succeeded, M failed: ..."` as `message`. Successful transcripts still included in the result. |
| Upload exceeds size limits | `413 Payload Too Large` before handler runs. |
| Disk full during job | Job `failed`, `message="disk full"`. Boot-time check logs a warning under 2 GB free. |
| Auth failure | `403` for wrong-owner with clear body; `401` for missing/expired session. SPA handles 401 by redirecting to `/login`. |
| Unhandled worker exception | Outer try/except in `run_job`, stack trace logged, `message` truncated to 500 chars. |
| Invalid format/model in request | `400` with a validation error shape before any work starts. |

---

## 9. Testing

**Backend (`pytest`):**

- `providers/` unit tests — mock `subprocess.run`, assert command args and output parsing (filenames, progress lines).
- Job lifecycle test — fake provider writes a dummy transcript into `output/`; call `run_job()` inline; assert DB transitions (queued → running → done), result file present, inputs cleaned up.
- HTTP round-trip tests with `AUTH_DISABLED=true` — `POST /api/jobs` with JSON and multipart, poll, download.
- Auth tests — enabled path with a mocked authlib client, enforce `OWNER_OPEN_ID` gate returns 403 for non-owners.
- Opt-in real e2e (`RUN_E2E=1`) — a 5-second WAV through the real stack.

**Frontend:**

- `vitest` component tests for `Dropzone`, `JobCard`, URL parser.
- One Playwright smoke test: bypass auth → upload small file → poll to `done` → download link exists.

---

## 10. Deployment

**Dockerfile** — multi-stage:

1. `node:20-alpine`: `pnpm install` → `pnpm build` in `web/` → static dist.
2. `python:3.12-slim`: install `uv`, `uv sync` from `pyproject.toml`. Install `ffmpeg` and `yt-dlp` via apt/pip. Download release binaries of `audiotap` and `whisperbatch` from their GitHub Releases and place on `PATH`. Install `openai-whisper` via pip (whisperbatch auto-installs it too, but baking it in avoids first-run cost).
3. Copy the Vite build into `backend/app/static/`. FastAPI mounts that path for non-`/api` requests.

**`docker-compose.yml`** for local dev:

- Volumes `./data` → `/app/data`, `./storage` → `/app/storage`.
- `.env.local` loaded.
- In dev, Vite runs separately on `:5173` with proxy to FastAPI on `:8000`. In prod, FastAPI alone serves both.

**Coolify:**

- Build from the repo.
- Persistent volumes on `/app/data` and `/app/storage`.
- Env vars for OIDC + `JWT_SECRET` + `OWNER_OPEN_ID` + optional `JOB_RETENTION_DAYS`, `MAX_UPLOAD_MB`, `MAX_TOTAL_UPLOAD_MB`.
- Healthcheck: `GET /api/health`.

---

## 11. Future improvements (explicitly deferred)

These are known limitations of v1 that the user has already flagged as "OK for now, improve later":

- **Worker concurrency.** Single `ThreadPoolExecutor` worker means jobs queue serially. Upgrade path: Redis + RQ (or arq/dramatiq) in a sibling worker container. The provider interface and job table are already queue-agnostic.
- **Retention policy.** Hard 30-day delete. Add user-controlled per-job retention and "keep forever" pin.
- **Progress UX.** `message` is a free-form string. Add structured progress events and consider SSE for smoother updates.
- **Provider pluggability at runtime.** `TRANSCRIPTION_PROVIDER` env exists in the config but only `local` is implemented. Add `groq` and `openai` providers when cost/speed demand.
- **Playlist preview.** Currently a playlist URL produces N transcripts with no preview of titles. Consider a pre-flight "expand playlist, confirm N items" step.
- **Multi-user.** The `OWNER_OPEN_ID` gate is a single hard-coded allowlist. True multi-user would remove that gate and add per-user storage quotas.

---

## 12. Open questions (none blocking v1)

None — all decisions needed to start implementation have been made.
