import pytest

from app.config import Settings


def test_defaults_when_no_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner-sub")
    s = Settings()
    assert s.env == "development"
    assert s.job_retention_days == 30
    assert s.max_upload_mb == 500
    assert s.oidc_scopes == "openid profile email"
    assert s.session_cookie_name == "tc_session"


def test_production_refuses_auth_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OWNER_OPEN_ID", "owner-sub")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("AUTH_DISABLED", "true")
    with pytest.raises(ValueError, match="AUTH_DISABLED"):
        Settings()
