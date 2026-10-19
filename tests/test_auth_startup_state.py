"""Initial setup is station state, independent of the browser's session cookie."""

from pathlib import Path

import httpx
from test_web_authentication import _application

from src.web.asgi_openapi import build_openapi_schema
from src.web.auth_store import AuthStore


async def test_anonymous_setup_state_tracks_password_change_and_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "station.sqlite3"
    app, _ = _application(AuthStore(path))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        initial = (await client.get("/api/auth/session")).json()
        assert initial.get("requires_initial_setup") is True
        assert initial["authenticated"] is False
        assert initial["username"] is None and initial["csrf_token"] is None
        login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"},
                                  headers={"Origin": "http://localhost"})
        assert login.status_code == 200
        changed = await client.put("/api/auth/credentials", json={"username": "owner", "password": "qa-owner-password"},
                                   headers={"Origin": "http://localhost", "X-CSRF-Token": login.json()["csrf_token"]})
        assert changed.status_code == 200
        assert changed.json().get("requires_initial_setup") is False
        client.cookies.clear()
        anonymous = (await client.get("/api/auth/session")).json()
        assert anonymous.get("requires_initial_setup") is False
        assert anonymous["authenticated"] is False
        assert anonymous["username"] is None and anonymous["csrf_token"] is None
    reopened, _ = _application(AuthStore(path))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=reopened), base_url="http://localhost") as client:
        assert (await client.get("/api/auth/session")).json().get("requires_initial_setup") is False


def test_initial_setup_flag_is_documented_in_session_contract() -> None:
    schema = build_openapi_schema()["components"]["schemas"]["AuthSession"]
    assert "requires_initial_setup" in schema["required"]
    assert schema["properties"]["requires_initial_setup"]["type"] == "boolean"
