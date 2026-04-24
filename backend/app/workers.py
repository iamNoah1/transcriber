from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

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
                print(f"[retention] failed: {e}")
            await asyncio.sleep(interval_hours * 3600)

    return asyncio.create_task(_loop())
