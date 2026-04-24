from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import Settings, get_settings
from app.db import Database

ONE_YEAR = timedelta(days=365)

STATE_COOKIE = "tc_oidc_state"
VERIFIER_COOKIE = "tc_oidc_verifier"
TEN_MIN_SECONDS = 600


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


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


async def _oidc_metadata(settings: Settings) -> dict[str, Any]:
    url = settings.oidc_issuer_url.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.json()


async def _exchange_and_userinfo(
    settings: Settings, code: str, redirect_uri: str, verifier: str
) -> dict[str, Any]:
    meta = await _oidc_metadata(settings)
    async with AsyncOAuth2Client(
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        token_endpoint_auth_method="client_secret_post",
    ) as oc:
        token = await oc.fetch_token(
            meta["token_endpoint"],
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=verifier,
            grant_type="authorization_code",
        )
        resp = await oc.get(meta["userinfo_endpoint"], token=token)
        resp.raise_for_status()
        return resp.json()


def _validate_state(request: Request, state_qp: str) -> str:
    state_cookie = request.cookies.get(STATE_COOKIE)
    verifier = request.cookies.get(VERIFIER_COOKIE)
    if not state_cookie or state_cookie != state_qp:
        raise HTTPException(status_code=400, detail="invalid state")
    if not verifier:
        raise HTTPException(status_code=400, detail="missing verifier")
    return verifier


def _cookie_opts(request: Request) -> dict[str, Any]:
    secure = request.url.scheme == "https"
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "path": "/",
    }


def _origin(request: Request) -> str:
    fp = request.headers.get("x-forwarded-proto", request.url.scheme)
    fh = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    return f"{fp}://{fh}"


def register_oauth_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/api/auth/login")
    async def login(request: Request):
        if settings.auth_disabled:
            return RedirectResponse("/", status_code=302)
        meta = await _oidc_metadata(settings)
        state = _b64url(secrets.token_bytes(16))
        verifier, challenge = _make_pkce_pair()
        redirect_uri = f"{_origin(request)}/api/auth/callback"
        params = {
            "client_id": settings.oidc_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": settings.oidc_scopes,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        auth_url = meta["authorization_endpoint"] + "?" + str(httpx.QueryParams(params))
        resp = RedirectResponse(auth_url, status_code=302)
        opts = _cookie_opts(request)
        resp.set_cookie(STATE_COOKIE, state, max_age=TEN_MIN_SECONDS, **opts)
        resp.set_cookie(VERIFIER_COOKIE, verifier, max_age=TEN_MIN_SECONDS, **opts)
        return resp

    @app.get("/api/auth/callback")
    async def callback(request: Request, code: str, state: str):
        if settings.auth_disabled:
            return RedirectResponse("/", status_code=302)
        verifier = _validate_state(request, state)
        redirect_uri = f"{_origin(request)}/api/auth/callback"
        userinfo = await _exchange_and_userinfo(settings, code, redirect_uri, verifier)
        sub = userinfo.get("sub")
        if not sub:
            raise HTTPException(status_code=400, detail="sub missing")
        if sub != settings.owner_open_id:
            raise HTTPException(status_code=403, detail="not authorised")

        db: Database = app.state.db
        name = userinfo.get("name") or userinfo.get("preferred_username") or userinfo.get("email")
        await db.upsert_user(open_id=sub, name=name, email=userinfo.get("email"))

        token = issue_session_token(settings, open_id=sub, name=name)
        resp = RedirectResponse("/", status_code=302)
        opts = _cookie_opts(request)
        resp.set_cookie(settings.session_cookie_name, token, max_age=365 * 24 * 3600, **opts)
        resp.delete_cookie(STATE_COOKIE, path="/")
        resp.delete_cookie(VERIFIER_COOKIE, path="/")
        return resp

    @app.post("/api/auth/logout")
    async def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(settings.session_cookie_name, path="/")
        return resp

    @app.get("/api/auth/me")
    async def me(request: Request):
        return current_user(request)
