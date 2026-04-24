import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.auth import current_user, install_auth
from app.config import Settings


def _app_with_auth(settings: Settings) -> FastAPI:
    app = FastAPI()
    install_auth(app, settings)

    @app.get("/whoami")
    def whoami(user=Depends(current_user)):
        return user

    return app


def test_auth_disabled_returns_dev_user(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner")
    monkeypatch.setenv("AUTH_DISABLED", "true")
    s = Settings()
    client = TestClient(_app_with_auth(s))
    r = client.get("/whoami")
    assert r.status_code == 200
    assert r.json()["open_id"] == "dev"


def test_auth_enabled_unauthenticated_returns_401(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner")
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://id.example")
    monkeypatch.setenv("OIDC_CLIENT_ID", "c")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "s")
    s = Settings()
    client = TestClient(_app_with_auth(s))
    r = client.get("/whoami")
    assert r.status_code == 401


def test_valid_session_cookie_is_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner")
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://id.example")
    monkeypatch.setenv("OIDC_CLIENT_ID", "c")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "s")
    s = Settings()
    app = _app_with_auth(s)
    from app.auth import issue_session_token
    token = issue_session_token(s, open_id="owner", name="O")
    client = TestClient(app)
    r = client.get("/whoami", cookies={s.session_cookie_name: token})
    assert r.status_code == 200
    assert r.json() == {"open_id": "owner", "name": "O"}
