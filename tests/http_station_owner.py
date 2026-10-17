"""Authenticate isolated loopback HTTP tests through the real account contract."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx


@asynccontextmanager
async def owner_client(origin: str) -> AsyncIterator[httpx.AsyncClient]:
    assert origin.startswith("http://127.0.0.1:")
    async with httpx.AsyncClient(base_url=origin) as client:
        login = await client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin", "remember": False},
            headers={"Origin": origin},
        )
        assert login.status_code == 200
        changed = await client.put(
            "/api/auth/credentials",
            json={"username": "qa-owner", "current_password": "admin", "password": "isolated map owner password"},
            headers={"Origin": origin, "X-CSRF-Token": login.json()["csrf_token"]},
        )
        assert changed.status_code == 200
        client.headers.update({"Origin": origin, "X-CSRF-Token": changed.json()["csrf_token"]})
        yield client
