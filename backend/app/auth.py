from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import FastAPI, HTTPException, Request

from app.config import Settings, get_settings

ONE_YEAR = timedelta(days=365)


def issue_session_token(settings: Settings, *, open_id: str, name: str | None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": open_id,
        "name": name or "",
        "iat": int(now.timestamp()),
        "exp": int((now + ONE_YEAR).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_token(token: str, settings: Settings) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def install_auth(app: FastAPI, settings: Settings) -> None:
    app.state.settings = settings


def _get_settings_from_request(request: Request) -> Settings:
    settings: Settings | None = getattr(request.app.state, "settings", None)
    return settings or get_settings()


def current_user(request: Request) -> dict[str, Any]:
    settings = _get_settings_from_request(request)
    if settings.auth_disabled:
        return {"open_id": "dev", "name": "Dev"}
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    payload = _decode_token(token, settings)
    if not payload:
        raise HTTPException(status_code=401, detail="invalid session")
    return {"open_id": payload["sub"], "name": payload.get("name") or None}
