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


def test_list_jobs_returns_recent_first(api):
    import time
    for _ in range(3):
        api.post("/api/jobs", json={"urls": ["u"], "options": {}})
        time.sleep(0.01)  # ensure distinguishable timestamps
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


def test_delete_job_removes_row_and_tree(api):
    created = api.post("/api/jobs", json={"urls": ["u"], "options": {}}).json()
    r = api.delete(f"/api/jobs/{created['id']}")
    assert r.status_code == 204
    r = api.get(f"/api/jobs/{created['id']}")
    assert r.status_code == 404


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
