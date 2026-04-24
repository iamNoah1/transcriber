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
