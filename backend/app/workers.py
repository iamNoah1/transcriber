from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app.db import Database
from app.memory import insufficient_memory_message
from app.providers.base import TranscriptionProvider
from app.storage import Storage

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_PERCENT_RE = re.compile(r"\b(\d{1,3})%")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


class JobRunner:
    """Synchronous job executor. Safe to call inside a worker thread."""

    def __init__(self, *, db: Database, storage: Storage, provider: TranscriptionProvider):
        self.db = db
        self.storage = storage
        self.provider = provider

    def _run(self, coro):
        return asyncio.run(coro)

    def _progress_writer(self, job_id: str, phase: str):
        # Throttled callback: parses NN% out of each progress line, mirrors a
        # cleaned-up version into `message`, and writes progress to the DB at
        # most twice per second. Errors during write are swallowed so a
        # transient hiccup never aborts the underlying transcription.
        state = {"last_t": 0.0}

        def on_output(line: str) -> None:
            now = time.monotonic()
            if now - state["last_t"] < 0.5:
                return
            cleaned = _strip_ansi(line).strip()
            if not cleaned:
                return
            updates: dict = {"message": f"{phase}: {cleaned}"[:400]}
            m = _PERCENT_RE.search(cleaned)
            if m:
                v = int(m.group(1))
                if 0 <= v <= 100:
                    updates["progress"] = v
            state["last_t"] = now
            try:
                self._run(self.db.update_job(job_id, **updates))
            except Exception:  # noqa: BLE001 — transient DB hiccup must not kill the job
                pass

        return on_output

    def run_job(self, job_id: str) -> None:
        log.info("[job:%s] starting", job_id)
        try:
            self._run(self.db.update_job(
                job_id, status="running", started_at=_now(),
                message="Preparing…", progress=None,
            ))
            row = self._run(self.db.get_job(job_id))
            if row is None:
                log.warning("[job:%s] not found in DB, aborting", job_id)
                return
            paths = self.storage.job_paths(job_id)
            options = json.loads(row["options_json"])
            inputs = json.loads(row["inputs_json"])

            if row["input_kind"] == "urls":
                log.info("[job:%s] downloading %d URL(s)", job_id, len(inputs))
                self._run(self.db.update_job(job_id, message="Downloading audio…", progress=None))
                self.provider.download_urls(
                    inputs, paths.input,
                    on_output=self._progress_writer(job_id, "Downloading"),
                )
                log.info("[job:%s] download complete", job_id)

            count_in = sum(1 for _ in paths.input.iterdir() if _.is_file())
            log.info("[job:%s] transcribing %d file(s), formats=%s, model=%s",
                     job_id, count_in, options["formats"], options.get("model"))

            err = insufficient_memory_message(options.get("model"))
            if err:
                raise RuntimeError(err)

            self._run(self.db.update_job(
                job_id, message=f"Transcribing {count_in} file(s)…", progress=None,
            ))
            self.provider.transcribe(
                paths.input,
                paths.output,
                formats=options["formats"],
                model=options.get("model"),
                on_output=self._progress_writer(job_id, "Transcribing"),
            )

            outputs = sorted(p for p in paths.output.iterdir() if p.is_file())
            if not outputs:
                raise RuntimeError(
                    "Transcription produced no output files. "
                    "Check that the audio format is supported (wav, mp3, m4a, flac, ogg)."
                )
            if len(outputs) == 1:
                result_path = outputs[0]
                file_count = 1
            else:
                result_path = self.storage.zip_output(job_id)
                file_count = len(outputs)

            self.storage.clear_input(job_id)
            log.info("[job:%s] done — %d output file(s) at %s", job_id, file_count, result_path)

            self._run(self.db.update_job(
                job_id,
                status="done",
                finished_at=_now(),
                message=None,
                progress=100,
                result_path=str(result_path),
                file_count=file_count,
            ))
        except Exception as e:  # noqa: BLE001 — top-level worker guard
            log.exception("[job:%s] failed: %s", job_id, e)
            self._run(self.db.update_job(
                job_id,
                status="failed",
                finished_at=_now(),
                message=str(e)[:4000],
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
