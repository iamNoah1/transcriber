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


# append below existing tests in backend/tests/test_auth.py

from unittest.mock import AsyncMock, patch

from app.auth import register_oauth_routes
from app.db import Database


@pytest.fixture()
def oidc_app(monkeypatch: pytest.MonkeyPatch, tmp_path):
    import asyncio

    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner-sub")
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://id.example")
    monkeypatch.setenv("OIDC_CLIENT_ID", "c")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "s")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from fastapi import FastAPI
    app = FastAPI()
    s = Settings()
    install_auth(app, s)
    db = Database(s.db_path)
    asyncio.run(db.init())
    app.state.db = db
    register_oauth_routes(app, s)
    return app, s, db


def test_login_redirects_to_issuer(oidc_app):
    app, s, _ = oidc_app
    client = TestClient(app)
    meta = {
        "authorization_endpoint": "https://id.example/authorize",
        "token_endpoint": "https://id.example/token",
        "userinfo_endpoint": "https://id.example/userinfo",
    }
    with patch("app.auth._oidc_metadata", new=AsyncMock(return_value=meta)):
        r = client.get("/api/auth/login", follow_redirects=False)
    assert r.status_code == 302
    assert "id.example" in r.headers["location"]
    assert "code_challenge_method=S256" in r.headers["location"]


def test_callback_rejects_non_owner(oidc_app):
    app, s, _ = oidc_app
    client = TestClient(app)
    with patch("app.auth._exchange_and_userinfo", new=AsyncMock(return_value={"sub": "stranger", "name": "S"})):
        # Also set the state+verifier cookies to simulate a valid round-trip
        r = client.get(
            "/api/auth/callback?code=c&state=s",
            cookies={"tc_oidc_state": "s", "tc_oidc_verifier": "v"},
            follow_redirects=False,
        )
    assert r.status_code == 403


def test_callback_accepts_owner_and_sets_cookie(oidc_app):
    app, s, db = oidc_app
    client = TestClient(app)
    with patch("app.auth._exchange_and_userinfo", new=AsyncMock(return_value={"sub": "owner-sub", "name": "O", "email": "o@x"})):
        r = client.get(
            "/api/auth/callback?code=c&state=s",
            cookies={"tc_oidc_state": "s", "tc_oidc_verifier": "v"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert r.headers["location"] == "/"
    assert s.session_cookie_name in r.cookies
