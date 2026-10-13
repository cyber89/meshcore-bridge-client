"""Isolated authentication regressions; no station or radio dependencies."""

import hashlib
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from starlette.responses import JSONResponse

from src.web.asgi_openapi import build_openapi_schema
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


@pytest.mark.parametrize("password", ["a" * 8, "a" * 64, "12345678", " " * 8, "🔒" * 8, "🔒" * 64])
def test_new_password_accepts_length_boundaries_without_complexity(password: str) -> None:
    validate_credentials("owner", password)


@pytest.mark.parametrize("password", ["a" * 7, "a" * 65, "🔒" * 7, "🔒" * 65, "admin"])
def test_new_password_rejects_outside_eight_to_sixty_four_characters(password: str) -> None:
    with pytest.raises(ValueError):
        validate_credentials("owner", password)


@pytest.mark.parametrize(
    "password,expected_status",
    [("a" * 7, 422), ("a" * 8, 200), ("a" * 64, 200), ("a" * 65, 422), ("🔒" * 64, 200)],
)
async def test_account_password_boundaries_preserve_or_replace_session(
    tmp_path: Path, password: str, expected_status: int
) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    app, _ = _application(store)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
            headers={"Origin": "http://localhost"},
        )
        old_cookie = client.cookies.get("meshcore_session")
        response = await client.put(
            "/api/auth/credentials",
            json={"username": "owner", "password": password, "current_password": "admin"},
            headers={"Origin": "http://localhost", "X-CSRF-Token": login.json()["csrf_token"]},
        )
        assert response.status_code == expected_status
        if expected_status == 200:
            assert not response.json()["must_change_credentials"]
            assert store.session(str(old_cookie)) is None
            assert (await client.get("/api/private")).status_code == 200
            assert (
                store.login("owner", password, remember=False, peer="replacement-check") is not None
            )
        else:
            assert store.session(str(old_cookie)) is not None
            assert not store.account_ready()
            assert (await client.get("/api/private")).status_code == 403


@pytest.mark.parametrize("password_length", [65, 128])
async def test_legacy_long_password_can_login_and_change_to_new_policy(
    tmp_path: Path, password_length: int
) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    old_password = "a" * password_length
    salt = bytes(range(16))
    old_hash = hashlib.scrypt(
        old_password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=64 * 1024 * 1024, dklen=32
    ).hex()
    # Represent an account persisted before the new 64-character creation limit.
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "INSERT INTO auth_owner VALUES(1,?,?,?,?,0)", ("owner", salt.hex(), old_hash, 0)
        )
    app, _ = _application(store)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        login = await client.post(
            "/api/auth/login",
            json={"username": "owner", "password": old_password},
            headers={"Origin": "http://localhost"},
        )
        assert login.status_code == 200
        response = await client.put(
            "/api/auth/credentials",
            json={"username": "owner", "password": "aaaaaaaa", "current_password": old_password},
            headers={"Origin": "http://localhost", "X-CSRF-Token": login.json()["csrf_token"]},
        )
        assert response.status_code == 200
        assert store.login("owner", "aaaaaaaa", remember=False, peer="legacy-check") is not None


def test_openapi_separates_new_password_policy_from_existing_credentials() -> None:
    paths = build_openapi_schema()["paths"]
    properties = paths["/api/auth/credentials"]["put"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["properties"]
    assert properties["password"]["minLength"] == 8
    assert properties["password"]["maxLength"] == 64
    assert properties["current_password"]["maxLength"] == 128
    login_password = paths["/api/auth/login"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]["properties"]["password"]
    assert login_password["minLength"] == 1
    assert login_password["maxLength"] == 128


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


@pytest.mark.parametrize(
    "field,value",
    [
        ("username", ""),
        ("username", "a" * 65),
        ("username", "owner\n"),
        ("username", "<script>"),
        ("username", {}),
        ("password", ""),
        ("password", "a" * 129),
        ("password", 12345678),
        ("password", ["aaaaaaaa"]),
        ("remember", "true"),
        ("remember", 1),
    ],
)
async def test_login_rejects_invalid_fields_without_creating_session(
    tmp_path: Path, field: str, value: object
) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    app, _ = _application(store)
    payload: dict[str, object] = {"username": "admin", "password": "admin", "remember": True}
    payload[field] = value
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.post(
            "/api/auth/login", json=payload, headers={"Origin": "http://localhost"}
        )
        assert response.status_code == 422
        assert client.cookies.get("meshcore_session") is None
        with sqlite3.connect(store.path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0


async def test_login_rejects_non_utf8_password_without_error_or_session(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    app, _ = _application(store)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.post(
            "/api/auth/login",
            content=b'{"username":"admin","password":"\\ud800"}',
            headers={"Origin": "http://localhost", "Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert client.cookies.get("meshcore_session") is None


@pytest.mark.parametrize("remember", [False, True])
async def test_https_login_cookie_remember_and_logout_contract(
    tmp_path: Path, remember: bool
) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    app, _ = _application(store)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://localhost"
    ) as client:
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin", "remember": remember},
            headers={"Origin": "https://localhost"},
        )
        assert response.status_code == 200
        header = response.headers["set-cookie"]
        assert "HttpOnly" in header and "Secure" in header and "SameSite=strict" in header
        if remember:
            assert "Max-Age=2592000" in header
        else:
            assert "Max-Age=" not in header
        assert response.headers["cache-control"] == "no-store"
        assert (await client.get("http://localhost/api/private")).status_code == 401
        cookie = client.cookies.get("meshcore_session")
        logout = await client.post(
            "/api/auth/logout",
            headers={"Origin": "https://localhost", "X-CSRF-Token": response.json()["csrf_token"]},
        )
        assert logout.status_code == 200
        assert store.session(str(cookie)) is None
        assert client.cookies.get("meshcore_session") is None
        assert (await client.get("/api/private")).status_code == 401


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


async def test_initial_credentials_change_does_not_require_current_password(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    app, authentication = _application(store)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        # 1. Login with default credentials
        login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
            headers={"Origin": "http://localhost"},
        )
        assert login.status_code == 200
        assert login.json()["must_change_credentials"]
        csrf = login.json()["csrf_token"]

        # 2. Change credentials on first setup without sending current_password
        response = await client.put(
            "/api/auth/credentials",
            json={
                "username": "admin_new",
                "password": "valid_new_password_123",
            },
            headers={"Origin": "http://localhost", "X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        assert not response.json()["must_change_credentials"]
        assert response.json()["username"] == "admin_new"

        # 3. Subsequent change MUST require current_password
        new_csrf = response.json()["csrf_token"]
        failed = await client.put(
            "/api/auth/credentials",
            json={
                "username": "admin_final",
                "password": "another_new_password_123",
            },
            headers={"Origin": "http://localhost", "X-CSRF-Token": new_csrf},
        )
        assert failed.status_code == 422
        assert failed.json()["error"] == "invalid_credentials_payload"

        # 4. Subsequent change succeeds with valid current_password
        succeeded = await client.put(
            "/api/auth/credentials",
            json={
                "username": "admin_final",
                "password": "another_new_password_123",
                "current_password": "valid_new_password_123",
            },
            headers={"Origin": "http://localhost", "X-CSRF-Token": new_csrf},
        )
        assert succeeded.status_code == 200
        assert succeeded.json()["username"] == "admin_final"
