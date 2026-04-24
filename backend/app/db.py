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
