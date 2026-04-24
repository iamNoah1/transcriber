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
