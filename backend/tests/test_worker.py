import asyncio
import json
from pathlib import Path

import pytest

from app import memory
from app.db import Database
from app.storage import Storage
from app.workers import JobRunner


class FakeProvider:
    def __init__(self):
        self.downloads: list[tuple[list[str], Path]] = []
        self.transcribes: list[tuple[Path, Path, list[str], str | None]] = []

    def download_urls(self, urls, input_dir: Path, *, on_output=None):
        self.downloads.append((urls, input_dir))
        (input_dir / f"{urls[0].split('/')[-1]}.opus").write_bytes(b"\x00")

    def transcribe(self, input_dir: Path, output_dir: Path, *, formats, model, on_output=None):
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
    await asyncio.get_event_loop().run_in_executor(None, runner.run_job, job_id)
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
    await asyncio.get_event_loop().run_in_executor(None, runner.run_job, job_id)
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
    await asyncio.get_event_loop().run_in_executor(None, runner.run_job, job_id)
    row = await db.get_job(job_id)
    assert row["status"] == "failed"
    assert "boom" in row["message"]


@pytest.mark.asyncio()
async def test_run_job_fails_fast_on_low_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(memory, "available_ram_mb", lambda: 100)
    db = Database(tmp_path / "db.sqlite"); await db.init()
    await db.upsert_user(open_id="u", name=None, email=None)
    storage = Storage(tmp_path)
    provider = FakeProvider()
    runner = JobRunner(db=db, storage=storage, provider=provider)
    job_id = await db.insert_job(
        user_id="u", input_kind="urls",
        inputs_json=json.dumps(["https://youtu.be/a"]),
        options_json=json.dumps({"formats": ["txt"], "model": "large"}),
    )
    storage.create_job_dirs(job_id)
    await asyncio.get_event_loop().run_in_executor(None, runner.run_job, job_id)
    row = await db.get_job(job_id)
    assert row["status"] == "failed"
    assert "memory" in row["message"].lower()
    # Download happened (URL job), but transcribe must not have been invoked.
    assert provider.transcribes == []


@pytest.mark.asyncio()
async def test_run_job_fails_when_provider_writes_no_output(tmp_path: Path):
    """Transcriber exits cleanly but writes nothing (e.g. unsupported format) → failed, not done."""
    class SilentProvider(FakeProvider):
        def transcribe(self, *a, **kw):
            pass  # writes nothing to output_dir

    db = Database(tmp_path / "db.sqlite"); await db.init()
    await db.upsert_user(open_id="u", name=None, email=None)
    storage = Storage(tmp_path)
    runner = JobRunner(db=db, storage=storage, provider=SilentProvider())
    job_id = await db.insert_job(
        user_id="u", input_kind="urls",
        inputs_json=json.dumps(["https://youtu.be/a"]),
        options_json=json.dumps({"formats": ["txt"], "model": None}),
    )
    storage.create_job_dirs(job_id)
    await asyncio.get_event_loop().run_in_executor(None, runner.run_job, job_id)
    row = await db.get_job(job_id)
    assert row["status"] == "failed"
    assert "no output files" in row["message"].lower()
