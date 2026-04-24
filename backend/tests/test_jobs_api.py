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
