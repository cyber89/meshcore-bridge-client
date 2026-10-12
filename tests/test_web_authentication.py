"""Isolated authentication regressions; no station or radio dependencies."""

import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from starlette.responses import JSONResponse

from src.web.asgi_security import BridgeSecurityMiddleware
from src.web.asgi_server import trusted_proxy_ips
from src.web.auth_store import AuthStore, validate_credentials
from src.web.authentication import AuthenticationService, BridgeAuthenticationMiddleware


def test_default_account_cannot_authorize_api_and_requires_replacement(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    assert not store.has_account()
    assert store.bootstrap_default()
    session = store.login("admin", "admin", remember=True, peer="127.0.0.1")
    assert session is not None and session.must_change_credentials
    assert not store.bootstrap("owner", "correct horse battery staple")
    with pytest.raises(ValueError, match="credentials_change_required"):
        store.rotate_api_token(session.token, "admin")


def test_password_change_revokes_sessions_and_api_tokens(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    store.bootstrap("owner", "correct horse battery staple")
    first = store.login("owner", "correct horse battery staple", remember=True, peer="one")
    second = store.login("owner", "correct horse battery staple", remember=False, peer="two")
    assert first is not None and second is not None
    token = store.rotate_api_token(first.token, "correct horse battery staple")
    assert store.valid_api_token(token)
    replacement = store.change_credentials(
        first.token, "correct horse battery staple", "new-owner", "another long strong password"
    )
    assert store.session(first.token) is None
    assert store.session(second.token) is None
    assert not store.valid_api_token(token)
    assert store.session(replacement.token) is not None
    with sqlite3.connect(store.path) as connection:
        dump = "\n".join(connection.iterdump())
    assert "correct horse battery staple" not in dump
    assert replacement.token not in dump
    assert token not in dump


def test_password_and_username_constraints_preserve_default_exception() -> None:
    validate_credentials("admin", "admin", allow_default=True)
    with pytest.raises(ValueError):
        validate_credentials("owner", "short")
    with pytest.raises(ValueError):
        validate_credentials("owner\n", "correct horse battery staple")


def test_logout_removes_persistent_session(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    store.bootstrap("owner", "correct horse battery staple")
    session = store.login("owner", "correct horse battery staple", remember=True, peer="one")
    assert session is not None
    reopened = AuthStore(store.path)
    reopened.initialize()
    assert reopened.session(session.token) is not None
    reopened.logout(session.token)
    assert store.session(session.token) is None


def _application(store: AuthStore) -> tuple[BridgeSecurityMiddleware, AuthenticationService]:
    application = FastAPI()
    authentication = AuthenticationService(store)
    authentication.install_routes(application)

    async def data() -> JSONResponse:
        return JSONResponse(
            {"private": "owner-only"},
            headers={"Cache-Control": "public", "Vary": "Accept-Encoding"},
        )

    application.add_api_route("/api/private", data, methods=["GET", "POST"])
    return BridgeSecurityMiddleware(
        BridgeAuthenticationMiddleware(application, authentication), auth_managed=True
    ), authentication


async def test_api_reads_and_query_credentials_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRIDGE_API_KEY", "configured-integration-key")
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    store.bootstrap("owner", "correct horse battery staple")
    app, _ = _application(store)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        assert (await client.get("/api/private")).status_code == 401
        assert (
            await client.get("/api/private?api_key=configured-integration-key")
        ).status_code == 401
        response = await client.get(
            "/api/private", headers={"Authorization": "Bearer configured-integration-key"}
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "Accept-Encoding" in response.headers["vary"]


async def test_browser_mutations_require_csrf_and_same_origin(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    store.bootstrap("owner", "correct horse battery staple")
    app, _ = _application(store)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        body = {"username": "owner", "password": "correct horse battery staple", "remember": True}
        assert (
            await client.post(
                "/api/auth/login", json=body, headers={"Origin": "http://evil.example"}
            )
        ).status_code == 403
        response = await client.post(
            "/api/auth/login", json=body, headers={"Origin": "http://localhost"}
        )
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        assert (await client.post("/api/private", json={})).status_code == 403
        csrf = response.json()["csrf_token"]
        assert (
            await client.post(
                "/api/private",
                json={},
                headers={"X-CSRF-Token": csrf, "Origin": "http://localhost"},
            )
        ).status_code == 200
        assert (
            await client.get("/api/private", headers={"Origin": "http://evil.example"})
        ).status_code == 403


async def test_default_login_only_allows_account_replacement(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    app, authentication = _application(store)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
            headers={"Origin": "http://localhost"},
        )
        assert response.status_code == 200
        assert response.json()["must_change_credentials"]
        assert (await client.get("/api/private")).json()["error"] == "credentials_change_required"
        csrf = response.json()["csrf_token"]
        response = await client.put(
            "/api/auth/credentials",
            json={
                "username": "owner",
                "password": "correct horse battery staple",
                "current_password": "admin",
            },
            headers={"Origin": "http://localhost", "X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        assert not response.json()["must_change_credentials"]
        assert (await client.get("/api/private")).status_code == 200
        cookie = client.cookies.get("meshcore_session")
        scope = {
            "type": "websocket",
            "headers": [(b"cookie", f"meshcore_session={cookie}".encode())],
        }
        assert await authentication.websocket_authorized(scope)
        store.logout(str(cookie))
        assert not await authentication.websocket_authorized(scope)


def test_proxy_trust_requires_exact_ip_addresses() -> None:
    assert trusted_proxy_ips("") == ""
    assert trusted_proxy_ips("127.0.0.1, ::1") == "127.0.0.1,::1"
    for value in ("*", "10.0.0.0/8", "proxy.example"):
        with pytest.raises(ValueError):
            trusted_proxy_ips(value)
