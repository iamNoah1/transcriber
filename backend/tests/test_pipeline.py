"""
End-to-end pipeline tests: HTTP upload → worker → download.

Strategy: the fixture queues submitted job IDs instead of running them
immediately, and exposes a run_jobs() helper that executes them from the
test thread (which has no event loop), sidestepping the asyncio.run()
nesting restriction without any threading tricks.
"""
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.workers import JobRunner


class _FakeProvider:
    """Simulates successful transcription by writing stub text files."""

    def download_urls(self, urls: list[str], input_dir: Path, *, on_output=None) -> None:
        for i, _ in enumerate(urls):
            (input_dir / f"audio_{i}.opus").write_bytes(b"\x00")

    def transcribe(self, input_dir: Path, output_dir: Path, *, formats, model, on_output=None) -> None:
        for audio in sorted(input_dir.iterdir()):
            if audio.is_file():
                for fmt in formats:
                    (output_dir / f"{audio.stem}.{fmt}").write_text("stub transcript")


class _SilentProvider(_FakeProvider):
    """Simulates a transcriber that exits cleanly but produces no output (e.g. unsupported format)."""

    def transcribe(self, input_dir: Path, output_dir: Path, *, formats, model, on_output=None) -> None:
        pass  # writes nothing → must trigger the empty-output guard


def _make_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "dev")
    monkeypatch.setenv("ENV", "test")

    app = create_app()
    runner = JobRunner(db=app.state.db, storage=app.state.storage, provider=provider)

    # Collect job IDs instead of running them inside the ASGI event loop.
    # Tests call run_jobs() explicitly from the sync test thread, where
    # asyncio.run() (used by JobRunner internally) works without nesting.
    pending: list[str] = []
    app.state.submit_job = pending.append

    def run_jobs() -> None:
        while pending:
            runner.run_job(pending.pop(0))

    return app, run_jobs


@pytest.fixture()
def pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    app, run_jobs = _make_fixture(tmp_path, monkeypatch, _FakeProvider())
    with TestClient(app) as c:
        yield c, run_jobs


@pytest.fixture()
def silent_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    app, run_jobs = _make_fixture(tmp_path, monkeypatch, _SilentProvider())
    with TestClient(app) as c:
        yield c, run_jobs


# ---------------------------------------------------------------------------
# Happy-path pipeline tests
# ---------------------------------------------------------------------------

def test_file_upload_worker_download(pipeline, tmp_path: Path) -> None:
    """Upload a file, worker transcribes it, result is downloadable and non-empty."""
    client, run_jobs = pipeline
    audio = tmp_path / "sample.opus"
    audio.write_bytes(b"\x00" * 64)

    r = client.post(
        "/api/jobs/files",
        files=[("files", ("sample.opus", audio.read_bytes(), "audio/ogg"))],
        data={"options_json": '{"formats": ["txt"]}'},
    )
    assert r.status_code == 201
    job_id = r.json()["id"]

    run_jobs()

    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "done"
    assert status["file_count"] == 1

    dl = client.get(f"/api/jobs/{job_id}/download")
    assert dl.status_code == 200
    assert b"stub transcript" in dl.content


def test_url_job_worker_download(pipeline) -> None:
    """Submit a URL, worker downloads + transcribes, result is downloadable."""
    client, run_jobs = pipeline

    r = client.post(
        "/api/jobs",
        json={"urls": ["https://youtu.be/abc"], "options": {"formats": ["srt"]}},
    )
    assert r.status_code == 201
    job_id = r.json()["id"]

    run_jobs()

    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "done"

    dl = client.get(f"/api/jobs/{job_id}/download")
    assert dl.status_code == 200
    assert b"stub transcript" in dl.content


def test_multiple_files_multiple_formats_zipped(pipeline, tmp_path: Path) -> None:
    """Two files × two formats → four outputs bundled in a valid zip archive."""
    client, run_jobs = pipeline

    files = []
    for name in ("a.mp3", "b.mp3"):
        f = tmp_path / name
        f.write_bytes(b"\x00" * 64)
        files.append(("files", (name, f.read_bytes(), "audio/mpeg")))

    r = client.post(
        "/api/jobs/files",
        files=files,
        data={"options_json": '{"formats": ["txt", "srt"]}'},
    )
    assert r.status_code == 201
    job_id = r.json()["id"]

    run_jobs()

    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "done"
    assert status["file_count"] == 4  # 2 inputs × 2 formats

    dl = client.get(f"/api/jobs/{job_id}/download")
    assert dl.status_code == 200
    with zipfile.ZipFile(io.BytesIO(dl.content)) as z:
        assert len(z.namelist()) == 4


def test_job_not_visible_in_list_after_delete(pipeline, tmp_path: Path) -> None:
    """Deleted job disappears from list and returns 404 on direct GET."""
    client, run_jobs = pipeline

    audio = tmp_path / "x.mp3"
    audio.write_bytes(b"\x00" * 64)
    r = client.post(
        "/api/jobs/files",
        files=[("files", ("x.mp3", audio.read_bytes(), "audio/mpeg"))],
        data={"options_json": '{"formats": ["txt"]}'},
    )
    job_id = r.json()["id"]
    run_jobs()

    client.delete(f"/api/jobs/{job_id}")

    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    ids = [j["id"] for j in client.get("/api/jobs").json()]
    assert job_id not in ids


# ---------------------------------------------------------------------------
# Failure / edge-case pipeline tests
# ---------------------------------------------------------------------------

def test_unsupported_format_fails_job_not_empty_zip(silent_pipeline, tmp_path: Path) -> None:
    """When the transcriber produces no output the job must be marked failed,
    not done with an empty archive. Download must return 409, not an empty file."""
    client, run_jobs = silent_pipeline

    audio = tmp_path / "track.opus"
    audio.write_bytes(b"\x00" * 64)

    r = client.post(
        "/api/jobs/files",
        files=[("files", ("track.opus", audio.read_bytes(), "audio/ogg"))],
        data={"options_json": '{"formats": ["txt"]}'},
    )
    assert r.status_code == 201
    job_id = r.json()["id"]

    run_jobs()

    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "failed"
    assert "no output files" in status["message"].lower()

    dl = client.get(f"/api/jobs/{job_id}/download")
    assert dl.status_code == 409  # must not return an empty archive


def test_failed_job_visible_in_list(silent_pipeline, tmp_path: Path) -> None:
    """A failed job appears in the job list with status=failed."""
    client, run_jobs = silent_pipeline

    audio = tmp_path / "bad.opus"
    audio.write_bytes(b"\x00" * 64)
    r = client.post(
        "/api/jobs/files",
        files=[("files", ("bad.opus", audio.read_bytes(), "audio/ogg"))],
        data={"options_json": '{"formats": ["txt"]}'},
    )
    job_id = r.json()["id"]
    run_jobs()

    jobs = client.get("/api/jobs").json()
    match = next((j for j in jobs if j["id"] == job_id), None)
    assert match is not None
    assert match["status"] == "failed"
