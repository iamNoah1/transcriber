# transcribe-cloud Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cloud-hosted single-container service that lets the authenticated owner drop YouTube URLs, YouTube playlist URLs, or audio files into a React UI and download the resulting transcripts as a single file or zip.

**Architecture:** One FastAPI process with a single `ThreadPoolExecutor` worker. Jobs are shell-outs to the user's `audiotap` and `whisperbatch` CLIs; state lives in SQLite; artifacts live on a mounted `storage/` volume. React/Vite SPA served as static files by the same FastAPI process. Pocket ID OIDC (authlib) with an `OWNER_OPEN_ID` single-user gate.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, authlib, pydantic-settings, aiosqlite, pytest; React 18, TypeScript, Vite, Tailwind, shadcn/ui, react-dropzone, vitest, Playwright; Docker multi-stage, deployed to Coolify.

**Spec:** `docs/superpowers/specs/2026-04-23-transcribe-cloud-design.md`

---

## File Structure

Top-level after Phase 0:

```
transcribe-cloud/
├── backend/
│   ├── pyproject.toml
│   ├── ruff.toml
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              FastAPI app factory + static-SPA mount
│   │   ├── config.py            pydantic-settings
│   │   ├── db.py                SQLite init + query helpers
│   │   ├── storage.py           job dirs, zipping
│   │   ├── auth.py              authlib OIDC + session JWT + current_user dep
│   │   ├── jobs.py              /api/jobs routes + pydantic schemas
│   │   ├── workers.py           ThreadPoolExecutor + run_job()
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── base.py          Provider protocol
│   │       └── local.py         shells out to audiotap + whisperbatch
│   └── tests/
│       ├── conftest.py
│       ├── test_health.py
│       ├── test_config.py
│       ├── test_db.py
│       ├── test_storage.py
│       ├── test_providers_local.py
│       ├── test_auth.py
│       ├── test_jobs_api.py
│       ├── test_worker.py
│       └── test_retention.py
├── web/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api.ts
│       ├── pages/
│       │   ├── Login.tsx
│       │   ├── Home.tsx
│       │   ├── Jobs.tsx
│       │   └── JobDetail.tsx
│       ├── components/
│       │   ├── Dropzone.tsx
│       │   ├── JobCard.tsx
│       │   └── ui/              shadcn primitives (button, card, input, …)
│       └── lib/
│           └── utils.ts
├── e2e/
│   └── smoke.spec.ts
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .dockerignore
└── README.md
```

---

## Phase 0 — Repo & scaffolding

### Task 1: Root-level gitignore + env example

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `.dockerignore`

- [ ] **Step 1: Write `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
htmlcov/

# Node / Vite
node_modules/
web/dist/
backend/app/static/
.pnpm-store/

# Local data
data/
storage/

# OS / editor
.DS_Store
.idea/
.vscode/
*.swp

# Env
.env
.env.local
```

- [ ] **Step 2: Write `.env.example`**

```
# Core
ENV=development
LOG_LEVEL=INFO

# Auth (Pocket ID OIDC)
OIDC_ISSUER_URL=
OIDC_CLIENT_ID=
OIDC_CLIENT_SECRET=
OIDC_SCOPES=openid profile email
OWNER_OPEN_ID=
JWT_SECRET=change-me-please
SESSION_COOKIE_NAME=tc_session
AUTH_DISABLED=true

# Jobs
JOB_RETENTION_DAYS=30
MAX_UPLOAD_MB=500
MAX_TOTAL_UPLOAD_MB=2048

# Paths (override for Docker)
DATA_DIR=./data
STORAGE_DIR=./storage
```

- [ ] **Step 3: Write `.dockerignore`**

```
**/node_modules
**/__pycache__
**/.venv
**/.pytest_cache
**/.ruff_cache
web/dist
backend/app/static
data
storage
.git
.env
.env.local
```

- [ ] **Step 4: Commit**

```bash
cd /Users/noahispas/Desktop/workspace/gitrepo_private/transcribe-cloud
git add .gitignore .env.example .dockerignore
git commit -m "chore: add gitignore, dockerignore, env example"
```

---

### Task 2: Python backend scaffolding

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/ruff.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write `backend/pyproject.toml`**

```toml
[project]
name = "transcribe-cloud-backend"
version = "0.1.0"
description = "Cloud-hosted wrapper around audiotap + whisperbatch"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "aiosqlite>=0.20",
  "authlib>=1.3",
  "httpx>=0.27",
  "itsdangerous>=2.2",
  "pyjwt[crypto]>=2.9",
  "python-multipart>=0.0.12",
]

[dependency-groups]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "pytest-cov>=5.0",
  "httpx>=0.27",
  "respx>=0.21",
  "ruff>=0.7",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-q"

[tool.coverage.run]
source = ["app"]
omit = ["app/__init__.py"]
```

- [ ] **Step 2: Write `backend/ruff.toml`**

```toml
line-length = 100
target-version = "py312"

[lint]
select = ["E", "F", "I", "B", "UP", "SIM"]
ignore = ["E501"]
```

- [ ] **Step 3: Write `backend/app/__init__.py`** (empty file)

```python
```

- [ ] **Step 4: Write the failing health test** at `backend/tests/conftest.py`

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("OWNER_OPEN_ID", "dev")
    monkeypatch.setenv("ENV", "test")
    app = create_app()
    with TestClient(app) as c:
        yield c
```

And `backend/tests/test_health.py`:

```python
def test_health_returns_200_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 5: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_health.py -v
```

Expected: import error — `app.main` does not exist.

- [ ] **Step 6: Implement `backend/app/main.py`**

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="transcribe-cloud")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 7: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_health.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat(backend): scaffold FastAPI with /api/health"
```

---

### Task 3: React frontend scaffolding

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/tailwind.config.js`
- Create: `web/postcss.config.js`
- Create: `web/index.html`
- Create: `web/src/main.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/index.css`
- Create: `web/src/lib/utils.ts`
- Create: `web/components.json`

- [ ] **Step 1: Write `web/package.json`**

```json
{
  "name": "transcribe-cloud-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint src"
  },
  "dependencies": {
    "@radix-ui/react-slot": "^1.1.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.1",
    "lucide-react": "^0.454.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-dropzone": "^14.3.5",
    "react-router-dom": "^6.28.0",
    "tailwind-merge": "^2.5.4"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.0.1",
    "@types/node": "^22.9.0",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.3",
    "autoprefixer": "^10.4.20",
    "jsdom": "^25.0.1",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.14",
    "tailwindcss-animate": "^1.0.7",
    "typescript": "^5.6.3",
    "vite": "^5.4.11",
    "vitest": "^2.1.5"
  }
}
```

- [ ] **Step 2: Write `web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Write `web/vite.config.ts`**

```ts
import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
  },
});
```

- [ ] **Step 4: Write `web/tailwind.config.js` and `web/postcss.config.js`**

```js
// tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [require("tailwindcss-animate")],
};
```

```js
// postcss.config.js
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

- [ ] **Step 5: Write `web/index.html`, `web/src/main.tsx`, `web/src/index.css`, `web/src/App.tsx`, `web/src/setupTests.ts`, `web/src/lib/utils.ts`, `web/components.json`**

```html
<!-- web/index.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>transcribe-cloud</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

```tsx
// web/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
```

```css
/* web/src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root { height: 100%; }
body { @apply bg-slate-50 text-slate-900 antialiased; }
```

```tsx
// web/src/App.tsx
export default function App() {
  return (
    <main className="min-h-screen grid place-items-center">
      <h1 className="text-2xl font-semibold">transcribe-cloud</h1>
    </main>
  );
}
```

```ts
// web/src/setupTests.ts
import "@testing-library/jest-dom/vitest";
```

```ts
// web/src/lib/utils.ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

```json
// web/components.json (shadcn config)
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.js",
    "css": "src/index.css",
    "baseColor": "slate",
    "cssVariables": false
  },
  "aliases": { "components": "@/components", "utils": "@/lib/utils" }
}
```

- [ ] **Step 6: Install + smoke-test build**

```bash
cd web
pnpm install
pnpm build
```

Expected: Vite produces `web/dist/index.html` and asset chunks.

- [ ] **Step 7: Commit**

```bash
git add web/
git commit -m "feat(web): scaffold Vite + React + Tailwind + shadcn"
```

---

## Phase 1 — Backend infrastructure

### Task 4: Config module

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test** at `backend/tests/test_config.py`

```python
import pytest

from app.config import Settings


def test_defaults_when_no_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner-sub")
    s = Settings()
    assert s.env == "development"
    assert s.job_retention_days == 30
    assert s.max_upload_mb == 500
    assert s.oidc_scopes == "openid profile email"
    assert s.session_cookie_name == "tc_session"


def test_production_refuses_auth_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner-sub")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("AUTH_DISABLED", "true")
    with pytest.raises(ValueError, match="AUTH_DISABLED"):
        Settings()
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && uv run pytest tests/test_config.py -v
```

- [ ] **Step 3: Implement `backend/app/config.py`**

```python
from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    env: str = "development"
    log_level: str = "INFO"

    # Auth
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_scopes: str = "openid profile email"
    owner_open_id: str
    jwt_secret: str
    session_cookie_name: str = "tc_session"
    auth_disabled: bool = False

    # Jobs
    job_retention_days: int = 30
    max_upload_mb: int = 500
    max_total_upload_mb: int = 2048

    # Paths
    data_dir: Path = Field(default=Path("./data"))
    storage_dir: Path = Field(default=Path("./storage"))

    @model_validator(mode="after")
    def _no_auth_disabled_in_prod(self) -> "Settings":
        if self.env == "production" and self.auth_disabled:
            raise ValueError("AUTH_DISABLED must be false in production")
        return self

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def jobs_dir(self) -> Path:
        return self.storage_dir / "jobs"


def get_settings() -> Settings:
    return Settings()  # re-reads env each call; app code calls once at startup
```

- [ ] **Step 4: Run test to pass**

```bash
cd backend && uv run pytest tests/test_config.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat(backend): pydantic-settings config module"
```

---

### Task 5: SQLite database module

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/tests/test_db.py`

- [ ] **Step 1: Write the failing test** at `backend/tests/test_db.py`

```python
from pathlib import Path

import pytest

from app.db import Database


@pytest.mark.asyncio()
async def test_init_creates_tables(tmp_path: Path):
    db = Database(tmp_path / "x.db")
    await db.init()
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cur.fetchall()
    names = [row[0] for row in rows]
    assert "users" in names
    assert "jobs" in names


@pytest.mark.asyncio()
async def test_upsert_user_inserts_then_updates(tmp_path: Path):
    db = Database(tmp_path / "x.db")
    await db.init()
    await db.upsert_user(open_id="a", name="A", email="a@x")
    await db.upsert_user(open_id="a", name="A2", email="a2@x")
    async with db.connect() as conn:
        cur = await conn.execute("SELECT name, email FROM users WHERE open_id='a'")
        rows = await cur.fetchall()
    assert len(rows) == 1
    assert (rows[0]["name"], rows[0]["email"]) == ("A2", "a2@x")


@pytest.mark.asyncio()
async def test_insert_and_get_job(tmp_path: Path):
    db = Database(tmp_path / "x.db")
    await db.init()
    await db.upsert_user(open_id="u", name=None, email=None)
    job_id = await db.insert_job(
        user_id="u",
        input_kind="urls",
        inputs_json='["https://youtu.be/abc"]',
        options_json='{"formats":["txt"]}',
    )
    job = await db.get_job(job_id)
    assert job is not None
    assert job["status"] == "queued"
    assert job["input_kind"] == "urls"
    assert job["user_id"] == "u"
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && uv run pytest tests/test_db.py -v
```

- [ ] **Step 3: Implement `backend/app/db.py`**

```python
from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  open_id        TEXT PRIMARY KEY,
  name           TEXT,
  email          TEXT,
  last_signed_in TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(open_id),
  status       TEXT NOT NULL,
  input_kind   TEXT NOT NULL,
  inputs_json  TEXT NOT NULL,
  options_json TEXT NOT NULL,
  message      TEXT,
  result_path  TEXT,
  file_count   INTEGER,
  created_at   TEXT NOT NULL,
  started_at   TEXT,
  finished_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id, created_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self.connect() as conn:
            await conn.executescript(SCHEMA)
            await conn.commit()

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()

    async def upsert_user(
        self, *, open_id: str, name: str | None, email: str | None
    ) -> None:
        async with self.connect() as conn:
            await conn.execute(
                """
                INSERT INTO users (open_id, name, email, last_signed_in)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(open_id) DO UPDATE SET
                    name=excluded.name,
                    email=excluded.email,
                    last_signed_in=excluded.last_signed_in
                """,
                (open_id, name, email, _now()),
            )
            await conn.commit()

    async def insert_job(
        self,
        *,
        user_id: str,
        input_kind: str,
        inputs_json: str,
        options_json: str,
    ) -> str:
        job_id = str(uuid.uuid4())
        async with self.connect() as conn:
            await conn.execute(
                """
                INSERT INTO jobs (id, user_id, status, input_kind, inputs_json,
                                  options_json, created_at)
                VALUES (?, ?, 'queued', ?, ?, ?, ?)
                """,
                (job_id, user_id, input_kind, inputs_json, options_json, _now()),
            )
            await conn.commit()
        return job_id

    async def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [job_id]
        async with self.connect() as conn:
            await conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", values)
            await conn.commit()

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        async with self.connect() as conn:
            cur = await conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
            row = await cur.fetchone()
        return dict(row) if row else None

    async def list_jobs(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        async with self.connect() as conn:
            cur = await conn.execute(
                "SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def delete_job(self, job_id: str) -> None:
        async with self.connect() as conn:
            await conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            await conn.commit()

    async def expired_jobs(self, before_iso: str) -> list[dict[str, Any]]:
        async with self.connect() as conn:
            cur = await conn.execute(
                "SELECT * FROM jobs WHERE finished_at IS NOT NULL AND finished_at < ?",
                (before_iso,),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_db.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/db.py backend/tests/test_db.py
git commit -m "feat(backend): SQLite schema + async db helpers"
```

---

### Task 6: Storage module

**Files:**
- Create: `backend/app/storage.py`
- Create: `backend/tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_storage.py
from pathlib import Path

import pytest

from app.storage import Storage


def test_create_job_dirs_returns_paths(tmp_path: Path):
    s = Storage(tmp_path)
    paths = s.create_job_dirs("job-1")
    assert paths.input.is_dir() and paths.input.name == "input"
    assert paths.output.is_dir() and paths.output.name == "output"
    assert paths.root == tmp_path / "jobs" / "job-1"


def test_sanitise_filename_strips_paths_and_nulls():
    s = Storage(Path("/"))
    assert s.sanitise_filename("../../etc/passwd") == "passwd"
    assert s.sanitise_filename("a\x00b.txt") == "ab.txt"
    assert s.sanitise_filename("") == "upload"


def test_zip_output_produces_archive_with_contents(tmp_path: Path):
    s = Storage(tmp_path)
    paths = s.create_job_dirs("job-z")
    (paths.output / "a.txt").write_text("hello")
    (paths.output / "b.txt").write_text("world")
    zip_path = s.zip_output("job-z")
    assert zip_path.is_file()
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        names = sorted(z.namelist())
    assert names == ["a.txt", "b.txt"]


def test_single_output_no_zip(tmp_path: Path):
    s = Storage(tmp_path)
    paths = s.create_job_dirs("job-s")
    f = paths.output / "only.txt"
    f.write_text("x")
    single = s.single_output_file("job-s")
    assert single == f


def test_delete_job_tree(tmp_path: Path):
    s = Storage(tmp_path)
    s.create_job_dirs("job-d")
    s.delete_job("job-d")
    assert not (tmp_path / "jobs" / "job-d").exists()
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && uv run pytest tests/test_storage.py -v
```

- [ ] **Step 3: Implement `backend/app/storage.py`**

```python
from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JobPaths:
    root: Path
    input: Path
    output: Path


class Storage:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.jobs_dir = storage_dir / "jobs"

    def create_job_dirs(self, job_id: str) -> JobPaths:
        root = self.jobs_dir / job_id
        input_dir = root / "input"
        output_dir = root / "output"
        for d in (root, input_dir, output_dir):
            d.mkdir(parents=True, exist_ok=True)
        return JobPaths(root=root, input=input_dir, output=output_dir)

    def job_paths(self, job_id: str) -> JobPaths:
        root = self.jobs_dir / job_id
        return JobPaths(root=root, input=root / "input", output=root / "output")

    @staticmethod
    def sanitise_filename(name: str) -> str:
        name = name.replace("\x00", "")
        name = Path(name).name.strip()
        return name or "upload"

    def single_output_file(self, job_id: str) -> Path | None:
        output = self.job_paths(job_id).output
        if not output.exists():
            return None
        files = [p for p in output.iterdir() if p.is_file()]
        return files[0] if len(files) == 1 else None

    def zip_output(self, job_id: str) -> Path:
        paths = self.job_paths(job_id)
        zip_path = paths.root / "result.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(paths.output.iterdir()):
                if p.is_file():
                    z.write(p, arcname=p.name)
        return zip_path

    def clear_input(self, job_id: str) -> None:
        input_dir = self.job_paths(job_id).input
        if input_dir.exists():
            shutil.rmtree(input_dir)

    def delete_job(self, job_id: str) -> None:
        root = self.job_paths(job_id).root
        if root.exists():
            shutil.rmtree(root)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_storage.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage.py backend/tests/test_storage.py
git commit -m "feat(backend): job storage + zipping helpers"
```

---

### Task 7: Provider interface + local provider

**Files:**
- Create: `backend/app/providers/__init__.py` (empty)
- Create: `backend/app/providers/base.py`
- Create: `backend/app/providers/local.py`
- Create: `backend/tests/test_providers_local.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_providers_local.py
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.providers.local import LocalProvider


def test_download_urls_invokes_audiotap_with_correct_args(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    with patch("app.providers.local.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        p = LocalProvider()
        p.download_urls(["https://youtu.be/a", "https://youtu.be/b"], input_dir)
    args = run.call_args[0][0]
    assert args[0] == "audiotap"
    assert "--output-dir" in args and str(input_dir) in args
    assert "--format" in args and "opus" in args
    assert "https://youtu.be/a" in args and "https://youtu.be/b" in args


def test_download_urls_raises_on_non_zero_exit(tmp_path: Path):
    with patch("app.providers.local.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1, stdout="", stderr="bad url")
        p = LocalProvider()
        with pytest.raises(RuntimeError, match="audiotap failed"):
            p.download_urls(["bad"], tmp_path)


def test_transcribe_invokes_whisperbatch_with_formats_and_model(tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir(); output_dir.mkdir()
    with patch("app.providers.local.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        p = LocalProvider()
        p.transcribe(input_dir, output_dir, formats=["txt", "srt"], model="medium")
    args = run.call_args[0][0]
    assert args[0] == "whisperbatch"
    assert "-i" in args and str(input_dir) in args
    assert "-o" in args and str(output_dir) in args
    flags = [args[i + 1] for i, v in enumerate(args) if v == "-f"]
    assert set(flags) == {"txt", "srt"}
    assert "-m" in args and "medium" in args


def test_transcribe_omits_model_when_none(tmp_path: Path):
    with patch("app.providers.local.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        p = LocalProvider()
        p.transcribe(tmp_path, tmp_path, formats=["txt"], model=None)
    args = run.call_args[0][0]
    assert "-m" not in args
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && uv run pytest tests/test_providers_local.py -v
```

- [ ] **Step 3: Implement `backend/app/providers/base.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TranscriptionProvider(Protocol):
    def download_urls(self, urls: list[str], input_dir: Path) -> None: ...
    def transcribe(
        self,
        input_dir: Path,
        output_dir: Path,
        *,
        formats: list[str],
        model: str | None,
    ) -> None: ...
```

- [ ] **Step 4: Implement `backend/app/providers/local.py`**

```python
from __future__ import annotations

import subprocess
from pathlib import Path


class LocalProvider:
    """Shells out to the user's audiotap + whisperbatch CLIs."""

    def download_urls(self, urls: list[str], input_dir: Path) -> None:
        cmd = [
            "audiotap",
            "--output-dir", str(input_dir),
            "--format", "opus",
            "--workers", "2",
            *urls,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip().splitlines()[-5:]
            raise RuntimeError("audiotap failed: " + " | ".join(tail))

    def transcribe(
        self,
        input_dir: Path,
        output_dir: Path,
        *,
        formats: list[str],
        model: str | None,
    ) -> None:
        cmd = [
            "whisperbatch",
            "-i", str(input_dir),
            "-o", str(output_dir),
        ]
        for f in formats:
            cmd.extend(["-f", f])
        if model:
            cmd.extend(["-m", model])
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip().splitlines()[-5:]
            raise RuntimeError("whisperbatch failed: " + " | ".join(tail))
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_providers_local.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/providers/ backend/tests/test_providers_local.py
git commit -m "feat(backend): provider interface + LocalProvider wrapping CLIs"
```

---

## Phase 2 — Authentication

### Task 8: Session JWT + current_user dependency

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/tests/test_auth.py` (first chunk — dev bypass + JWT)

- [ ] **Step 1: Write the failing test** at `backend/tests/test_auth.py`

```python
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.auth import current_user, install_auth
from app.config import Settings


def _app_with_auth(settings: Settings) -> FastAPI:
    app = FastAPI()
    install_auth(app, settings)

    @app.get("/whoami")
    def whoami(user=Depends(current_user)):
        return user

    return app


def test_auth_disabled_returns_dev_user(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner")
    monkeypatch.setenv("AUTH_DISABLED", "true")
    s = Settings()
    client = TestClient(_app_with_auth(s))
    r = client.get("/whoami")
    assert r.status_code == 200
    assert r.json()["open_id"] == "dev"


def test_auth_enabled_unauthenticated_returns_401(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner")
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://id.example")
    monkeypatch.setenv("OIDC_CLIENT_ID", "c")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "s")
    s = Settings()
    client = TestClient(_app_with_auth(s))
    r = client.get("/whoami")
    assert r.status_code == 401


def test_valid_session_cookie_is_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner")
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://id.example")
    monkeypatch.setenv("OIDC_CLIENT_ID", "c")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "s")
    s = Settings()
    app = _app_with_auth(s)
    from app.auth import issue_session_token
    token = issue_session_token(s, open_id="owner", name="O")
    client = TestClient(app)
    r = client.get("/whoami", cookies={s.session_cookie_name: token})
    assert r.status_code == 200
    assert r.json() == {"open_id": "owner", "name": "O"}
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && uv run pytest tests/test_auth.py -v
```

- [ ] **Step 3: Implement `backend/app/auth.py`** (auth-disabled + JWT parts first; OIDC routes added in Task 9)

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings

ONE_YEAR = timedelta(days=365)


def issue_session_token(settings: Settings, *, open_id: str, name: str | None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": open_id,
        "name": name or "",
        "iat": int(now.timestamp()),
        "exp": int((now + ONE_YEAR).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_token(token: str, settings: Settings) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def install_auth(app: FastAPI, settings: Settings) -> None:
    app.state.settings = settings


def _get_settings_from_request(request: Request) -> Settings:
    settings: Settings | None = getattr(request.app.state, "settings", None)
    return settings or get_settings()


def current_user(request: Request) -> dict[str, Any]:
    settings = _get_settings_from_request(request)
    if settings.auth_disabled:
        return {"open_id": "dev", "name": "Dev"}
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    payload = _decode_token(token, settings)
    if not payload:
        raise HTTPException(status_code=401, detail="invalid session")
    return {"open_id": payload["sub"], "name": payload.get("name") or None}
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_auth.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth.py backend/tests/test_auth.py
git commit -m "feat(backend): session JWT + current_user dependency + dev bypass"
```

---

### Task 9: OIDC login + callback + OWNER_OPEN_ID gate

**Files:**
- Modify: `backend/app/auth.py` — add `register_oauth_routes()`
- Modify: `backend/tests/test_auth.py` — add OIDC flow tests
- Modify: `backend/app/main.py` — wire auth into the app

- [ ] **Step 1: Add failing tests to `backend/tests/test_auth.py`**

```python
# append to backend/tests/test_auth.py

from unittest.mock import AsyncMock, patch

from app.auth import register_oauth_routes
from app.db import Database


@pytest.fixture()
def oidc_app(monkeypatch: pytest.MonkeyPatch, tmp_path):
    import asyncio

    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner-sub")
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://id.example")
    monkeypatch.setenv("OIDC_CLIENT_ID", "c")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "s")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from fastapi import FastAPI
    app = FastAPI()
    s = Settings()
    install_auth(app, s)
    db = Database(s.db_path)
    asyncio.run(db.init())
    app.state.db = db
    register_oauth_routes(app, s)
    return app, s, db


def test_login_redirects_to_issuer(oidc_app):
    app, s, _ = oidc_app
    client = TestClient(app)
    r = client.get("/api/auth/login", follow_redirects=False)
    assert r.status_code == 302
    assert "id.example" in r.headers["location"]
    assert "code_challenge_method=S256" in r.headers["location"]


def test_callback_rejects_non_owner(oidc_app):
    app, s, _ = oidc_app
    client = TestClient(app)
    # Fake authlib to return a non-owner sub
    with patch("app.auth._exchange_and_userinfo", new=AsyncMock(return_value={"sub": "stranger", "name": "S"})):
        with patch("app.auth._validate_state", return_value=("verifier",)):
            r = client.get("/api/auth/callback?code=c&state=s", follow_redirects=False)
    assert r.status_code == 403


def test_callback_accepts_owner_and_sets_cookie(oidc_app):
    app, s, db = oidc_app
    client = TestClient(app)
    with patch("app.auth._exchange_and_userinfo", new=AsyncMock(return_value={"sub": "owner-sub", "name": "O", "email": "o@x"})):
        with patch("app.auth._validate_state", return_value=("verifier",)):
            r = client.get("/api/auth/callback?code=c&state=s", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/"
    assert s.session_cookie_name in r.cookies
```

- [ ] **Step 2: Run — expect failures (routes don't exist)**

```bash
cd backend && uv run pytest tests/test_auth.py -v
```

- [ ] **Step 3: Extend `backend/app/auth.py`** (append below the existing code)

```python
# --- add to backend/app/auth.py below current_user ---

import base64
import hashlib
import secrets
from typing import Tuple

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import Request
from fastapi.responses import RedirectResponse

from app.db import Database  # noqa: E402


STATE_COOKIE = "tc_oidc_state"
VERIFIER_COOKIE = "tc_oidc_verifier"
TEN_MIN_SECONDS = 600


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


async def _oidc_metadata(settings: Settings) -> dict[str, Any]:
    url = settings.oidc_issuer_url.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.json()


async def _exchange_and_userinfo(
    settings: Settings, code: str, redirect_uri: str, verifier: str
) -> dict[str, Any]:
    meta = await _oidc_metadata(settings)
    async with AsyncOAuth2Client(
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        token_endpoint_auth_method="client_secret_post",
    ) as oc:
        token = await oc.fetch_token(
            meta["token_endpoint"],
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=verifier,
            grant_type="authorization_code",
        )
        resp = await oc.get(meta["userinfo_endpoint"], token=token)
        resp.raise_for_status()
        return resp.json()


def _validate_state(request: Request, state_qp: str) -> Tuple[str]:
    state_cookie = request.cookies.get(STATE_COOKIE)
    verifier = request.cookies.get(VERIFIER_COOKIE)
    if not state_cookie or state_cookie != state_qp:
        raise HTTPException(status_code=400, detail="invalid state")
    if not verifier:
        raise HTTPException(status_code=400, detail="missing verifier")
    return (verifier,)


def _cookie_opts(request: Request) -> dict[str, Any]:
    secure = request.url.scheme == "https"
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "path": "/",
    }


def _origin(request: Request) -> str:
    fp = request.headers.get("x-forwarded-proto", request.url.scheme)
    fh = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    return f"{fp}://{fh}"


def register_oauth_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/api/auth/login")
    async def login(request: Request):
        if settings.auth_disabled:
            return RedirectResponse("/", status_code=302)
        meta = await _oidc_metadata(settings)
        state = _b64url(secrets.token_bytes(16))
        verifier, challenge = _make_pkce_pair()
        redirect_uri = f"{_origin(request)}/api/auth/callback"
        params = {
            "client_id": settings.oidc_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": settings.oidc_scopes,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        auth_url = meta["authorization_endpoint"] + "?" + httpx.QueryParams(params)
        resp = RedirectResponse(auth_url, status_code=302)
        opts = _cookie_opts(request)
        resp.set_cookie(STATE_COOKIE, state, max_age=TEN_MIN_SECONDS, **opts)
        resp.set_cookie(VERIFIER_COOKIE, verifier, max_age=TEN_MIN_SECONDS, **opts)
        return resp

    @app.get("/api/auth/callback")
    async def callback(request: Request, code: str, state: str):
        if settings.auth_disabled:
            return RedirectResponse("/", status_code=302)
        (verifier,) = _validate_state(request, state)
        redirect_uri = f"{_origin(request)}/api/auth/callback"
        userinfo = await _exchange_and_userinfo(settings, code, redirect_uri, verifier)
        sub = userinfo.get("sub")
        if not sub:
            raise HTTPException(status_code=400, detail="sub missing")
        if sub != settings.owner_open_id:
            raise HTTPException(status_code=403, detail="not authorised")

        db: Database = app.state.db
        name = userinfo.get("name") or userinfo.get("preferred_username") or userinfo.get("email")
        await db.upsert_user(open_id=sub, name=name, email=userinfo.get("email"))

        token = issue_session_token(settings, open_id=sub, name=name)
        resp = RedirectResponse("/", status_code=302)
        opts = _cookie_opts(request)
        resp.set_cookie(settings.session_cookie_name, token, max_age=365 * 24 * 3600, **opts)
        resp.delete_cookie(STATE_COOKIE, path="/")
        resp.delete_cookie(VERIFIER_COOKIE, path="/")
        return resp

    @app.post("/api/auth/logout")
    async def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(settings.session_cookie_name, path="/")
        return resp

    @app.get("/api/auth/me")
    async def me(request: Request):
        return current_user(request)
```

- [ ] **Step 4: Wire into `backend/app/main.py`**

Replace the body of `create_app()` with:

```python
from app.auth import install_auth, register_oauth_routes
from app.config import get_settings
from app.db import Database


def create_app() -> FastAPI:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="transcribe-cloud")
    install_auth(app, settings)

    db = Database(settings.db_path)
    app.state.db = db

    @app.on_event("startup")
    async def _startup() -> None:
        await db.init()

    register_oauth_routes(app, settings)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

- [ ] **Step 5: Run all auth tests**

```bash
cd backend && uv run pytest tests/test_auth.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth.py backend/app/main.py backend/tests/test_auth.py
git commit -m "feat(backend): Pocket ID OIDC login, callback, OWNER_OPEN_ID gate"
```

---

## Phase 3 — Jobs API

### Task 10: Pydantic schemas + job creation (URL variant)

**Files:**
- Create: `backend/app/jobs.py`
- Create: `backend/tests/test_jobs_api.py`
- Modify: `backend/app/main.py` — include jobs router

- [ ] **Step 1: Write failing tests** at `backend/tests/test_jobs_api.py`

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "dev")
    monkeypatch.setenv("ENV", "test")
    app = create_app()
    # Replace worker submit with a no-op so we only exercise the API
    app.state.submit_job = lambda job_id: None
    with TestClient(app) as c:
        yield c


def test_create_url_job_returns_201_and_queued(api):
    r = api.post("/api/jobs", json={"urls": ["https://youtu.be/a"], "options": {"formats": ["txt"]}})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "queued"
    assert body["id"]


def test_create_url_job_requires_at_least_one_url(api):
    r = api.post("/api/jobs", json={"urls": [], "options": {}})
    assert r.status_code == 422


def test_create_url_job_rejects_bad_format(api):
    r = api.post("/api/jobs", json={"urls": ["u"], "options": {"formats": ["doc"]}})
    assert r.status_code == 422
```

- [ ] **Step 2: Run — expect failures (no jobs router)**

```bash
cd backend && uv run pytest tests/test_jobs_api.py -v
```

- [ ] **Step 3: Implement `backend/app/jobs.py`**

```python
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.auth import current_user
from app.db import Database
from app.storage import Storage

VALID_FORMATS = {"txt", "json", "srt", "vtt", "tsv"}
VALID_MODELS = {"tiny", "base", "medium", "large"}


class Options(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["txt"])
    model: str | None = None

    @field_validator("formats")
    @classmethod
    def _fmts(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("formats cannot be empty")
        bad = set(v) - VALID_FORMATS
        if bad:
            raise ValueError(f"unknown formats: {sorted(bad)}")
        return v

    @field_validator("model")
    @classmethod
    def _model(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in VALID_MODELS:
            raise ValueError(f"unknown model: {v}")
        return v


class UrlJobRequest(BaseModel):
    urls: list[str] = Field(min_length=1)
    options: Options = Field(default_factory=Options)


class JobResponse(BaseModel):
    id: str
    status: Literal["queued", "running", "done", "failed"]
    input_kind: Literal["urls", "files"]
    inputs: list[str]
    options: Options
    message: str | None = None
    file_count: int | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


def _row_to_response(row: dict) -> JobResponse:
    return JobResponse(
        id=row["id"],
        status=row["status"],
        input_kind=row["input_kind"],
        inputs=json.loads(row["inputs_json"]),
        options=Options(**json.loads(row["options_json"])),
        message=row["message"],
        file_count=row["file_count"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", status_code=201, response_model=JobResponse)
async def create_url_job(
    request: Request,
    payload: UrlJobRequest,
    user: dict = Depends(current_user),
):
    db: Database = request.app.state.db
    storage: Storage = request.app.state.storage
    await db.upsert_user(open_id=user["open_id"], name=user.get("name"), email=None)
    job_id = await db.insert_job(
        user_id=user["open_id"],
        input_kind="urls",
        inputs_json=json.dumps(payload.urls),
        options_json=payload.options.model_dump_json(),
    )
    storage.create_job_dirs(job_id)
    submit = getattr(request.app.state, "submit_job", None)
    if submit:
        submit(job_id)
    row = await db.get_job(job_id)
    return _row_to_response(row)
```

- [ ] **Step 4: Wire router + storage into `backend/app/main.py`**

Update `create_app()` to also add:

```python
from app.jobs import router as jobs_router
from app.storage import Storage

# ... inside create_app, after register_oauth_routes(...)
app.state.storage = Storage(settings.storage_dir)
app.include_router(jobs_router)
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_jobs_api.py::test_create_url_job_returns_201_and_queued tests/test_jobs_api.py::test_create_url_job_requires_at_least_one_url tests/test_jobs_api.py::test_create_url_job_rejects_bad_format -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/jobs.py backend/app/main.py backend/tests/test_jobs_api.py
git commit -m "feat(backend): POST /api/jobs for URL submissions"
```

---

### Task 11: POST /api/jobs (multipart file variant)

**Files:**
- Modify: `backend/app/jobs.py` — add file upload endpoint
- Modify: `backend/tests/test_jobs_api.py`

- [ ] **Step 1: Add failing tests**

```python
# append to backend/tests/test_jobs_api.py
def test_create_file_job_accepts_uploads(api, tmp_path):
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"ID3\x00" + b"\x00" * 128)
    r = api.post(
        "/api/jobs/files",
        files=[("files", ("sample.mp3", audio.read_bytes(), "audio/mpeg"))],
        data={"options_json": '{"formats": ["txt"]}'},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "queued"
    assert body["input_kind"] == "files"
    assert body["inputs"] == ["sample.mp3"]


def test_create_file_job_rejects_empty_upload(api):
    r = api.post("/api/jobs/files", files=[], data={"options_json": "{}"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run — expect 404 / failure**

```bash
cd backend && uv run pytest tests/test_jobs_api.py::test_create_file_job_accepts_uploads -v
```

- [ ] **Step 3: Add handler to `backend/app/jobs.py`**

```python
# append to backend/app/jobs.py
from typing import Annotated

from fastapi import File, Form, UploadFile

@router.post("/files", status_code=201, response_model=JobResponse)
async def create_file_job(
    request: Request,
    files: Annotated[list[UploadFile], File()],
    options_json: Annotated[str, Form()],
    user: dict = Depends(current_user),
):
    if not files:
        raise HTTPException(status_code=422, detail="no files uploaded")
    try:
        options = Options.model_validate_json(options_json)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"invalid options: {e}") from e

    db: Database = request.app.state.db
    storage: Storage = request.app.state.storage
    await db.upsert_user(open_id=user["open_id"], name=user.get("name"), email=None)

    job_id = await db.insert_job(
        user_id=user["open_id"],
        input_kind="files",
        inputs_json=json.dumps([storage.sanitise_filename(f.filename or "upload") for f in files]),
        options_json=options.model_dump_json(),
    )
    paths = storage.create_job_dirs(job_id)

    total = 0
    per_limit = request.app.state.settings.max_upload_mb * 1024 * 1024
    total_limit = request.app.state.settings.max_total_upload_mb * 1024 * 1024
    for f in files:
        name = storage.sanitise_filename(f.filename or "upload")
        dest = paths.input / name
        written = 0
        with dest.open("wb") as out:
            while chunk := await f.read(1 << 20):
                written += len(chunk)
                total += len(chunk)
                if written > per_limit:
                    raise HTTPException(status_code=413, detail=f"file '{name}' exceeds per-file limit")
                if total > total_limit:
                    raise HTTPException(status_code=413, detail="total upload exceeds limit")
                out.write(chunk)

    submit = getattr(request.app.state, "submit_job", None)
    if submit:
        submit(job_id)
    row = await db.get_job(job_id)
    return _row_to_response(row)
```

Also store settings on app state. Modify `backend/app/main.py` `create_app()`:

```python
app.state.settings = settings  # add this line after install_auth(...)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_jobs_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/jobs.py backend/app/main.py backend/tests/test_jobs_api.py
git commit -m "feat(backend): POST /api/jobs/files multipart upload"
```

---

### Task 12: GET /api/jobs + GET /api/jobs/{id} + DELETE

**Files:**
- Modify: `backend/app/jobs.py`
- Modify: `backend/tests/test_jobs_api.py`

- [ ] **Step 1: Add failing tests**

```python
# append to backend/tests/test_jobs_api.py
def test_list_jobs_returns_recent_first(api):
    for _ in range(3):
        api.post("/api/jobs", json={"urls": ["u"], "options": {}})
    r = api.get("/api/jobs")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3
    ts = [row["created_at"] for row in rows]
    assert ts == sorted(ts, reverse=True)


def test_get_job_by_id(api):
    created = api.post("/api/jobs", json={"urls": ["u"], "options": {}}).json()
    r = api.get(f"/api/jobs/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_missing_job_404(api):
    r = api.get("/api/jobs/does-not-exist")
    assert r.status_code == 404


def test_delete_job_removes_row_and_tree(api, tmp_path):
    created = api.post("/api/jobs", json={"urls": ["u"], "options": {}}).json()
    r = api.delete(f"/api/jobs/{created['id']}")
    assert r.status_code == 204
    r = api.get(f"/api/jobs/{created['id']}")
    assert r.status_code == 404
```

- [ ] **Step 2: Run — expect failures**

```bash
cd backend && uv run pytest tests/test_jobs_api.py -v
```

- [ ] **Step 3: Add handlers to `backend/app/jobs.py`**

```python
# append to backend/app/jobs.py
from fastapi import status

@router.get("", response_model=list[JobResponse])
async def list_jobs(request: Request, user: dict = Depends(current_user)):
    db: Database = request.app.state.db
    rows = await db.list_jobs(user["open_id"])
    return [_row_to_response(r) for r in rows]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, request: Request, user: dict = Depends(current_user)):
    db: Database = request.app.state.db
    row = await db.get_job(job_id)
    if not row or row["user_id"] != user["open_id"]:
        raise HTTPException(status_code=404, detail="not found")
    return _row_to_response(row)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, request: Request, user: dict = Depends(current_user)):
    db: Database = request.app.state.db
    storage: Storage = request.app.state.storage
    row = await db.get_job(job_id)
    if not row or row["user_id"] != user["open_id"]:
        raise HTTPException(status_code=404, detail="not found")
    storage.delete_job(job_id)
    await db.delete_job(job_id)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_jobs_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/jobs.py backend/tests/test_jobs_api.py
git commit -m "feat(backend): list/get/delete jobs"
```

---

## Phase 4 — Worker pipeline

### Task 13: Worker + run_job() with fake provider

**Files:**
- Create: `backend/app/workers.py`
- Create: `backend/tests/test_worker.py`
- Modify: `backend/app/main.py` — instantiate executor + submit_job

- [ ] **Step 1: Write failing test** at `backend/tests/test_worker.py`

```python
import asyncio
import json
from pathlib import Path

import pytest

from app.db import Database
from app.storage import Storage
from app.workers import JobRunner


class FakeProvider:
    def __init__(self):
        self.downloads: list[tuple[list[str], Path]] = []
        self.transcribes: list[tuple[Path, Path, list[str], str | None]] = []

    def download_urls(self, urls, input_dir: Path):
        self.downloads.append((urls, input_dir))
        (input_dir / f"{urls[0].split('/')[-1]}.opus").write_bytes(b"\x00")

    def transcribe(self, input_dir: Path, output_dir: Path, *, formats, model):
        self.transcribes.append((input_dir, output_dir, formats, model))
        for audio in input_dir.iterdir():
            for fmt in formats:
                (output_dir / f"{audio.stem}.{fmt}").write_text("dummy")


@pytest.mark.asyncio()
async def test_run_job_urls_end_to_end(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite"); await db.init()
    await db.upsert_user(open_id="u", name=None, email=None)
    storage = Storage(tmp_path)
    runner = JobRunner(db=db, storage=storage, provider=FakeProvider())
    job_id = await db.insert_job(
        user_id="u", input_kind="urls",
        inputs_json=json.dumps(["https://youtu.be/abc"]),
        options_json=json.dumps({"formats": ["txt"], "model": None}),
    )
    storage.create_job_dirs(job_id)
    runner.run_job(job_id)
    row = await db.get_job(job_id)
    assert row["status"] == "done"
    assert row["file_count"] == 1
    assert row["result_path"].endswith(".txt")


@pytest.mark.asyncio()
async def test_run_job_zips_multiple_outputs(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite"); await db.init()
    await db.upsert_user(open_id="u", name=None, email=None)
    storage = Storage(tmp_path)
    runner = JobRunner(db=db, storage=storage, provider=FakeProvider())
    job_id = await db.insert_job(
        user_id="u", input_kind="urls",
        inputs_json=json.dumps(["https://youtu.be/a", "https://youtu.be/b"]),
        options_json=json.dumps({"formats": ["txt", "srt"], "model": None}),
    )
    storage.create_job_dirs(job_id)
    runner.run_job(job_id)
    row = await db.get_job(job_id)
    assert row["status"] == "done"
    assert row["result_path"].endswith("result.zip")


@pytest.mark.asyncio()
async def test_run_job_marks_failed_on_exception(tmp_path: Path):
    class BoomProvider(FakeProvider):
        def transcribe(self, *a, **kw):
            raise RuntimeError("boom")
    db = Database(tmp_path / "db.sqlite"); await db.init()
    await db.upsert_user(open_id="u", name=None, email=None)
    storage = Storage(tmp_path)
    runner = JobRunner(db=db, storage=storage, provider=BoomProvider())
    job_id = await db.insert_job(
        user_id="u", input_kind="urls",
        inputs_json=json.dumps(["https://youtu.be/a"]),
        options_json=json.dumps({"formats": ["txt"], "model": None}),
    )
    storage.create_job_dirs(job_id)
    runner.run_job(job_id)
    row = await db.get_job(job_id)
    assert row["status"] == "failed"
    assert "boom" in row["message"]
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && uv run pytest tests/test_worker.py -v
```

- [ ] **Step 3: Implement `backend/app/workers.py`**

```python
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.db import Database
from app.providers.base import TranscriptionProvider
from app.storage import Storage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobRunner:
    """Synchronous job executor. Safe to call inside a worker thread."""

    def __init__(self, *, db: Database, storage: Storage, provider: TranscriptionProvider):
        self.db = db
        self.storage = storage
        self.provider = provider

    def _run(self, coro):
        return asyncio.run(coro)

    def run_job(self, job_id: str) -> None:
        try:
            self._run(self.db.update_job(job_id, status="running", started_at=_now(), message="Preparing…"))
            row = self._run(self.db.get_job(job_id))
            if row is None:
                return
            paths = self.storage.job_paths(job_id)
            options = json.loads(row["options_json"])
            inputs = json.loads(row["inputs_json"])

            if row["input_kind"] == "urls":
                self._run(self.db.update_job(job_id, message="Downloading audio…"))
                self.provider.download_urls(inputs, paths.input)

            count_in = sum(1 for _ in paths.input.iterdir() if _.is_file())
            self._run(self.db.update_job(job_id, message=f"Transcribing {count_in} file(s)…"))
            self.provider.transcribe(
                paths.input,
                paths.output,
                formats=options["formats"],
                model=options.get("model"),
            )

            outputs = sorted(p for p in paths.output.iterdir() if p.is_file())
            if len(outputs) == 1:
                result_path = outputs[0]
                file_count = 1
            else:
                result_path = self.storage.zip_output(job_id)
                file_count = len(outputs)

            self.storage.clear_input(job_id)

            self._run(self.db.update_job(
                job_id,
                status="done",
                finished_at=_now(),
                message=None,
                result_path=str(result_path),
                file_count=file_count,
            ))
        except Exception as e:  # noqa: BLE001 — top-level worker guard
            self._run(self.db.update_job(
                job_id,
                status="failed",
                finished_at=_now(),
                message=str(e)[:500],
            ))


class Worker:
    """Thread-pool wrapper that submits run_job calls off the event loop."""

    def __init__(self, runner: JobRunner, max_workers: int = 1):
        self.runner = runner
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="tc-worker")

    def submit(self, job_id: str) -> None:
        self.pool.submit(self.runner.run_job, job_id)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_worker.py -v
```

- [ ] **Step 5: Wire worker into `backend/app/main.py`**

Update `create_app()` to add:

```python
from app.providers.local import LocalProvider
from app.workers import JobRunner, Worker

# ... after storage / include_router:
provider = LocalProvider()
runner = JobRunner(db=db, storage=app.state.storage, provider=provider)
worker = Worker(runner)
app.state.worker = worker
app.state.submit_job = worker.submit

@app.on_event("shutdown")
async def _shutdown() -> None:
    worker.shutdown()
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers.py backend/app/main.py backend/tests/test_worker.py
git commit -m "feat(backend): ThreadPoolExecutor + JobRunner pipeline"
```

---

### Task 14: GET /api/jobs/{id}/download

**Files:**
- Modify: `backend/app/jobs.py`
- Modify: `backend/tests/test_jobs_api.py`

- [ ] **Step 1: Add failing test**

```python
# append to backend/tests/test_jobs_api.py
def test_download_returns_single_file(api, tmp_path):
    import sqlite3

    created = api.post("/api/jobs", json={"urls": ["u"], "options": {}}).json()
    storage = api.app.state.storage
    settings = api.app.state.settings
    out = storage.job_paths(created["id"]).output
    out.mkdir(parents=True, exist_ok=True)
    (out / "x.txt").write_text("hello")

    conn = sqlite3.connect(str(settings.db_path))
    conn.execute(
        "UPDATE jobs SET status='done', result_path=?, file_count=1 WHERE id=?",
        (str(out / "x.txt"), created["id"]),
    )
    conn.commit()
    conn.close()

    r = api.get(f"/api/jobs/{created['id']}/download")
    assert r.status_code == 200
    assert r.content == b"hello"
    assert "attachment" in r.headers["content-disposition"].lower()


def test_download_409_when_not_done(api):
    created = api.post("/api/jobs", json={"urls": ["u"], "options": {}}).json()
    r = api.get(f"/api/jobs/{created['id']}/download")
    assert r.status_code == 409
```

- [ ] **Step 2: Run — expect 404/failure**

```bash
cd backend && uv run pytest tests/test_jobs_api.py::test_download_returns_single_file tests/test_jobs_api.py::test_download_409_when_not_done -v
```

- [ ] **Step 3: Add handler to `backend/app/jobs.py`**

```python
# append to backend/app/jobs.py
from fastapi.responses import FileResponse

@router.get("/{job_id}/download")
async def download_job(job_id: str, request: Request, user: dict = Depends(current_user)):
    db: Database = request.app.state.db
    row = await db.get_job(job_id)
    if not row or row["user_id"] != user["open_id"]:
        raise HTTPException(status_code=404, detail="not found")
    if row["status"] != "done" or not row["result_path"]:
        raise HTTPException(status_code=409, detail="job not complete")
    path = Path(row["result_path"])  # noqa
    if not path.is_file():
        raise HTTPException(status_code=410, detail="result missing")
    return FileResponse(path, filename=path.name)
```

Add at the top of the file:

```python
from pathlib import Path
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_jobs_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/jobs.py backend/tests/test_jobs_api.py
git commit -m "feat(backend): GET /api/jobs/{id}/download streams file or zip"
```

---

### Task 15: Retention cleanup loop

**Files:**
- Modify: `backend/app/workers.py` — add `start_retention_loop()`
- Create: `backend/tests/test_retention.py`
- Modify: `backend/app/main.py` — start/stop loop

- [ ] **Step 1: Failing test** at `backend/tests/test_retention.py`

```python
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.db import Database
from app.storage import Storage
from app.workers import purge_expired


@pytest.mark.asyncio()
async def test_purge_deletes_old_jobs_and_trees(tmp_path: Path):
    db = Database(tmp_path / "x.db"); await db.init()
    await db.upsert_user(open_id="u", name=None, email=None)
    storage = Storage(tmp_path)
    old = await db.insert_job(user_id="u", input_kind="urls", inputs_json="[]", options_json="{}")
    new = await db.insert_job(user_id="u", input_kind="urls", inputs_json="[]", options_json="{}")
    storage.create_job_dirs(old); storage.create_job_dirs(new)

    long_ago = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(timespec="seconds")
    recent  = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(timespec="seconds")
    await db.update_job(old, status="done", finished_at=long_ago, result_path="x")
    await db.update_job(new, status="done", finished_at=recent, result_path="x")

    await purge_expired(db, storage, retention_days=30)

    assert await db.get_job(old) is None
    assert await db.get_job(new) is not None
    assert not (tmp_path / "jobs" / old).exists()
    assert (tmp_path / "jobs" / new).exists()
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && uv run pytest tests/test_retention.py -v
```

- [ ] **Step 3: Implement in `backend/app/workers.py`**

```python
# append to backend/app/workers.py
import asyncio
from datetime import datetime, timedelta, timezone


async def purge_expired(db: Database, storage: Storage, retention_days: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat(timespec="seconds")
    expired = await db.expired_jobs(cutoff)
    for row in expired:
        storage.delete_job(row["id"])
        await db.delete_job(row["id"])
    return len(expired)


def start_retention_loop(db: Database, storage: Storage, retention_days: int, interval_hours: int = 6) -> asyncio.Task:
    async def _loop():
        while True:
            try:
                await purge_expired(db, storage, retention_days)
            except Exception as e:  # noqa: BLE001
                # Log but keep the loop alive.
                print(f"[retention] failed: {e}")
            await asyncio.sleep(interval_hours * 3600)

    return asyncio.create_task(_loop())
```

- [ ] **Step 4: Wire into `backend/app/main.py` `_startup()`**

```python
# in create_app(), extend _startup():
from app.workers import start_retention_loop

@app.on_event("startup")
async def _startup() -> None:
    await db.init()
    app.state.retention_task = start_retention_loop(
        db, app.state.storage, settings.job_retention_days
    )
```

And in `_shutdown()`:

```python
@app.on_event("shutdown")
async def _shutdown() -> None:
    task = getattr(app.state, "retention_task", None)
    if task:
        task.cancel()
    worker.shutdown()
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_retention.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers.py backend/app/main.py backend/tests/test_retention.py
git commit -m "feat(backend): nightly retention purge loop"
```

---

## Phase 5 — Frontend

### Task 16: API client + auth redirect

**Files:**
- Create: `web/src/api.ts`
- Create: `web/src/types.ts`

- [ ] **Step 1: Write `web/src/types.ts`**

```ts
export type JobStatus = "queued" | "running" | "done" | "failed";

export interface JobOptions {
  formats: string[];
  model?: string | null;
}

export interface Job {
  id: string;
  status: JobStatus;
  input_kind: "urls" | "files";
  inputs: string[];
  options: JobOptions;
  message: string | null;
  file_count: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface User {
  open_id: string;
  name: string | null;
}
```

- [ ] **Step 2: Write `web/src/api.ts`**

```ts
import type { Job, User, JobOptions } from "./types";

class UnauthenticatedError extends Error {}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(path, { credentials: "include", ...init });
  if (r.status === 401) {
    window.location.href = "/login";
    throw new UnauthenticatedError("unauthenticated");
  }
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || `${r.status} ${r.statusText}`);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export const api = {
  me: () => request<User>("/api/auth/me"),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  listJobs: () => request<Job[]>("/api/jobs"),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  deleteJob: (id: string) => request<void>(`/api/jobs/${id}`, { method: "DELETE" }),
  submitUrls: (urls: string[], options: JobOptions) =>
    request<Job>("/api/jobs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ urls, options }),
    }),
  submitFiles: (files: File[], options: JobOptions) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    fd.append("options_json", JSON.stringify(options));
    return request<Job>("/api/jobs/files", { method: "POST", body: fd });
  },
  downloadUrl: (id: string) => `/api/jobs/${id}/download`,
};
```

- [ ] **Step 3: Commit**

```bash
git add web/src/api.ts web/src/types.ts
git commit -m "feat(web): typed API client with 401 redirect"
```

---

### Task 17: Routes + auth gate in App.tsx

**Files:**
- Modify: `web/src/App.tsx`
- Create: `web/src/pages/Login.tsx`
- Create: `web/src/pages/Home.tsx` (stub)
- Create: `web/src/pages/Jobs.tsx` (stub)
- Create: `web/src/pages/JobDetail.tsx` (stub)

- [ ] **Step 1: Replace `web/src/App.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { api } from "./api";
import type { User } from "./types";

import Login from "./pages/Login";
import Home from "./pages/Home";
import Jobs from "./pages/Jobs";
import JobDetail from "./pages/JobDetail";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.me()
      .then((u) => setUser(u))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return null;

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={user ? <Home /> : <Navigate to="/login" replace />} />
      <Route path="/jobs" element={user ? <Jobs /> : <Navigate to="/login" replace />} />
      <Route path="/jobs/:id" element={user ? <JobDetail /> : <Navigate to="/login" replace />} />
    </Routes>
  );
}
```

- [ ] **Step 2: Write `web/src/pages/Login.tsx`**

```tsx
export default function Login() {
  return (
    <main className="min-h-screen grid place-items-center p-8">
      <div className="max-w-sm w-full bg-white rounded-2xl shadow p-8 text-center space-y-6">
        <h1 className="text-2xl font-semibold">transcribe-cloud</h1>
        <p className="text-slate-600">Sign in with your Pocket ID account to continue.</p>
        <a
          href="/api/auth/login"
          className="block w-full rounded-xl bg-slate-900 text-white font-medium py-3 hover:bg-slate-800 transition"
        >
          Sign in with Pocket ID
        </a>
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Write stub pages**

```tsx
// web/src/pages/Home.tsx
export default function Home() { return <main className="p-8">home</main>; }
```
```tsx
// web/src/pages/Jobs.tsx
export default function Jobs() { return <main className="p-8">jobs</main>; }
```
```tsx
// web/src/pages/JobDetail.tsx
export default function JobDetail() { return <main className="p-8">detail</main>; }
```

- [ ] **Step 4: Smoke-test build**

```bash
cd web && pnpm build
```

Expected: no TS errors, `dist/` generated.

- [ ] **Step 5: Commit**

```bash
git add web/src/App.tsx web/src/pages/
git commit -m "feat(web): auth-gated routes with login page"
```

---

### Task 18: Home page — dropzone + URL textarea + submit

**Files:**
- Create: `web/src/components/Dropzone.tsx`
- Modify: `web/src/pages/Home.tsx`

- [ ] **Step 1: Write `web/src/components/Dropzone.tsx`**

```tsx
import { useDropzone } from "react-dropzone";

import { cn } from "@/lib/utils";

type Props = {
  files: File[];
  onChange: (files: File[]) => void;
};

export function Dropzone({ files, onChange }: Props) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      "audio/*": [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".webm"],
      "video/*": [".mp4"],
    },
    onDrop: (accepted) => onChange([...files, ...accepted]),
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        "border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition",
        isDragActive ? "border-slate-900 bg-slate-100" : "border-slate-300 hover:bg-slate-50"
      )}
    >
      <input {...getInputProps()} />
      {files.length === 0 ? (
        <p className="text-slate-600">Drop audio files here or click to pick</p>
      ) : (
        <ul className="text-left space-y-1">
          {files.map((f, i) => (
            <li key={i} className="text-sm text-slate-700">
              {f.name} <span className="text-slate-400">({Math.round(f.size / 1024)} KB)</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Replace `web/src/pages/Home.tsx`**

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Dropzone } from "@/components/Dropzone";
import { api } from "@/api";
import type { JobOptions } from "@/types";

const FORMATS = ["txt", "srt", "vtt", "json", "tsv"] as const;
const MODELS = ["", "tiny", "base", "medium", "large"] as const;

export default function Home() {
  const nav = useNavigate();
  const [urlsText, setUrlsText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [formats, setFormats] = useState<string[]>(["txt"]);
  const [model, setModel] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const urls = urlsText
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  const canSubmit = (urls.length > 0 || files.length > 0) && formats.length > 0 && !submitting;

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const options: JobOptions = { formats, model: model || null };
      const job = files.length > 0
        ? await api.submitFiles(files, options)
        : await api.submitUrls(urls, options);
      nav(`/jobs/${job.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSubmitting(false);
    }
  }

  function toggle(fmt: string) {
    setFormats((f) => (f.includes(fmt) ? f.filter((x) => x !== fmt) : [...f, fmt]));
  }

  return (
    <main className="min-h-screen p-8 max-w-3xl mx-auto space-y-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">transcribe-cloud</h1>
        <a href="/jobs" className="text-sm text-slate-600 underline">Jobs</a>
      </header>

      <section className="space-y-2">
        <label className="text-sm font-medium">YouTube URLs (one per line)</label>
        <textarea
          className="w-full min-h-[120px] rounded-xl border border-slate-300 p-3 font-mono text-sm"
          value={urlsText}
          onChange={(e) => setUrlsText(e.target.value)}
          placeholder={"https://youtu.be/...\nhttps://youtube.com/playlist?list=..."}
        />
      </section>

      <section className="space-y-2">
        <label className="text-sm font-medium">…or audio files</label>
        <Dropzone files={files} onChange={setFiles} />
      </section>

      <section className="grid grid-cols-2 gap-6">
        <div className="space-y-2">
          <label className="text-sm font-medium">Output formats</label>
          <div className="flex flex-wrap gap-2">
            {FORMATS.map((f) => (
              <button
                type="button"
                key={f}
                onClick={() => toggle(f)}
                className={
                  "px-3 py-1 rounded-full text-sm border " +
                  (formats.includes(f)
                    ? "bg-slate-900 text-white border-slate-900"
                    : "bg-white text-slate-700 border-slate-300")
                }
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Model (auto if unset)</label>
          <select
            className="rounded-xl border border-slate-300 px-3 py-2 w-full"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            {MODELS.map((m) => (
              <option key={m} value={m}>{m || "auto"}</option>
            ))}
          </select>
        </div>
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        disabled={!canSubmit}
        onClick={submit}
        className="w-full rounded-xl bg-slate-900 text-white font-medium py-3 disabled:opacity-40 hover:bg-slate-800 transition"
      >
        {submitting ? "Submitting…" : "Transcribe"}
      </button>
    </main>
  );
}
```

- [ ] **Step 3: Build**

```bash
cd web && pnpm build
```

- [ ] **Step 4: Commit**

```bash
git add web/src/components/Dropzone.tsx web/src/pages/Home.tsx
git commit -m "feat(web): home page with URL + dropzone + options"
```

---

### Task 19: Jobs list + Job detail with polling

**Files:**
- Modify: `web/src/pages/Jobs.tsx`
- Modify: `web/src/pages/JobDetail.tsx`

- [ ] **Step 1: Write `web/src/pages/Jobs.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api";
import type { Job } from "@/types";

const STATUS_CLASS: Record<Job["status"], string> = {
  queued: "bg-slate-200 text-slate-700",
  running: "bg-blue-200 text-blue-800",
  done: "bg-green-200 text-green-800",
  failed: "bg-red-200 text-red-800",
};

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[] | null>(null);

  useEffect(() => {
    api.listJobs().then(setJobs).catch(() => setJobs([]));
  }, []);

  if (jobs === null) return null;

  return (
    <main className="min-h-screen p-8 max-w-3xl mx-auto space-y-4">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">Jobs</h1>
        <Link to="/" className="text-sm text-slate-600 underline">New</Link>
      </header>
      {jobs.length === 0 ? (
        <p className="text-slate-600">No jobs yet.</p>
      ) : (
        <ul className="space-y-2">
          {jobs.map((j) => (
            <li key={j.id} className="rounded-xl border border-slate-200 p-4 bg-white">
              <div className="flex items-center justify-between">
                <Link to={`/jobs/${j.id}`} className="font-medium">
                  {j.inputs[0] || "(no inputs)"}{j.inputs.length > 1 && ` +${j.inputs.length - 1}`}
                </Link>
                <span className={`px-2 py-0.5 rounded-full text-xs ${STATUS_CLASS[j.status]}`}>{j.status}</span>
              </div>
              <div className="text-xs text-slate-500 mt-1">{new Date(j.created_at).toLocaleString()}</div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Write `web/src/pages/JobDetail.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";

import { api } from "@/api";
import type { Job } from "@/types";

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    async function tick() {
      try {
        const j = await api.getJob(id);
        if (!cancelled) setJob(j);
        if (!cancelled && (j.status === "queued" || j.status === "running")) {
          setTimeout(tick, 2000);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }
    tick();
    return () => { cancelled = true; };
  }, [id]);

  if (error) return <main className="p-8">{error}</main>;
  if (!job) return null;

  return (
    <main className="min-h-screen p-8 max-w-3xl mx-auto space-y-4">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">Job</h1>
        <Link to="/jobs" className="text-sm text-slate-600 underline">All jobs</Link>
      </header>

      <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-slate-500">{job.id}</span>
          <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100">{job.status}</span>
        </div>
        <div>
          <h2 className="text-sm font-medium">Inputs</h2>
          <ul className="text-sm text-slate-700 list-disc list-inside">
            {job.inputs.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
        {job.message && <p className="text-sm text-slate-600">{job.message}</p>}
        {job.status === "done" && (
          <a
            href={api.downloadUrl(job.id)}
            className="inline-block rounded-xl bg-slate-900 text-white font-medium px-4 py-2 hover:bg-slate-800"
          >
            Download{job.file_count && job.file_count > 1 ? " (zip)" : ""}
          </a>
        )}
        {job.status === "failed" && <p className="text-sm text-red-600">{job.message}</p>}
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Build**

```bash
cd web && pnpm build
```

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/
git commit -m "feat(web): jobs list + detail page with polling"
```

---

### Task 20: Vitest component smoke test

**Files:**
- Create: `web/src/components/Dropzone.test.tsx`

- [ ] **Step 1: Write test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Dropzone } from "./Dropzone";

describe("Dropzone", () => {
  it("renders empty state", () => {
    render(<Dropzone files={[]} onChange={vi.fn()} />);
    expect(screen.getByText(/Drop audio files here/)).toBeInTheDocument();
  });

  it("renders filenames when present", () => {
    const f = new File(["x"], "hello.mp3", { type: "audio/mpeg" });
    render(<Dropzone files={[f]} onChange={vi.fn()} />);
    expect(screen.getByText(/hello\.mp3/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run**

```bash
cd web && pnpm test
```

Expected: 2 passing.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/Dropzone.test.tsx
git commit -m "test(web): Dropzone component smoke tests"
```

---

## Phase 6 — Packaging & deployment

### Task 21: Multi-stage Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
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
```

- [ ] **Step 2: Wire static SPA serving in `backend/app/main.py`**

Extend `create_app()` at the end (before `return app`):

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

static_dir = Path(__file__).parent / "static"
if static_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # Reserve /api for the API; everything else is the SPA.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        return FileResponse(static_dir / "index.html")
```

(Imports `HTTPException` already present from auth integration.)

- [ ] **Step 3: Smoke-build locally**

```bash
cd /Users/noahispas/Desktop/workspace/gitrepo_private/transcribe-cloud
docker build -t transcribe-cloud:dev .
```

Expected: image builds; `docker run --rm -p 8000:8000 -e JWT_SECRET=x -e OWNER_OPEN_ID=dev -e AUTH_DISABLED=true -e ENV=development transcribe-cloud:dev` responds `200 OK` at `/api/health`.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile backend/app/main.py
git commit -m "feat: multi-stage Dockerfile with audiotap + whisperbatch binaries"
```

---

### Task 22: docker-compose.yml for local dev

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  api:
    build: .
    image: transcribe-cloud:local
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./storage:/app/storage
    restart: unless-stopped
```

- [ ] **Step 2: Verify**

```bash
docker compose up --build
curl -s http://localhost:8000/api/health
```

Expected: `{"status":"ok"}`.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: docker-compose for local runs"
```

---

### Task 23: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# transcribe-cloud

Cloud-hosted wrapper around [audiotap](https://github.com/iamNoah1/audiotap) and [whisperbatch](https://github.com/iamNoah1/whisperbatch). Drop YouTube URLs, YouTube playlists, or audio files into a simple React UI; get transcripts back as a file or a zip. Single-user, Pocket ID OIDC.

## Local development

### Backend

```bash
cd backend
uv sync
cp ../.env.example ../.env
# set JWT_SECRET, OWNER_OPEN_ID; leave AUTH_DISABLED=true for dev
uv run uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd web
pnpm install
pnpm dev       # http://localhost:5173, proxies /api to :8000
```

### Docker (full stack)

```bash
cp .env.example .env
docker compose up --build
# http://localhost:8000
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
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with dev, docker, deploy instructions"
```

---

## Wrap-up

After Task 23, the full stack is implemented:

- Run `cd backend && uv run pytest` — all tests green.
- Run `cd web && pnpm test` — Dropzone component test green.
- Run `docker compose up --build` — the app serves at `http://localhost:8000` with `AUTH_DISABLED=true`, accepts URL and file jobs, runs them through real `audiotap` + `whisperbatch`, and lets you download the result.

Known v1 limitations (from spec §11, deliberately deferred):

- Single-thread worker — jobs queue serially.
- Hard 30-day retention, no per-job pinning.
- Coarse progress messages, no SSE.
- Only `local` provider; Groq/OpenAI providers not implemented.
- No playlist preview step.
- Single-user only (`OWNER_OPEN_ID` gate).
