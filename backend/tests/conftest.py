import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure required settings are present at module-import time so that
# `from app.main import create_app` (which instantiates `app` at module level)
# can read env vars. Per-test fixtures still override these values via monkeypatch.
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OWNER_OPEN_ID", "dev")
os.environ.setdefault("AUTH_DISABLED", "true")

from app.main import create_app  # noqa: E402


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
