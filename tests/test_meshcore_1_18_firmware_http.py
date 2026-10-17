"""Real ASGI/auth/router/handler contracts for manual local firmware reads."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from meshcore.events import Event, EventType

from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeRegistry
from src.repeater_manager import RepeaterManager
from src.serial.sdk_adapter import MeshcoreSDKAdapter
from src.station_database import StationDatabase
from src.web.api_router import WebAPIRouter
from src.web.asgi_server import create_asgi_app


@dataclass
class FirmwareHTTP:
    client: httpx.AsyncClient
    adapter: MeshcoreSDKAdapter
    sdk_read: AsyncMock
    sdk_send: AsyncMock
    mqtt: MagicMock

    async def owner_headers(self) -> dict[str, str]:
        response = await self.client.post(
            "/api/auth/login",
            json={"username": "qa-owner", "password": "isolated firmware password", "remember": False},
            headers={"Origin": "http://localhost"},
        )
        assert response.status_code == 200
        return {"Origin": "http://localhost", "X-CSRF-Token": response.json()["csrf_token"]}


@pytest_asyncio.fixture
async def firmware_http(tmp_path: Path) -> AsyncIterator[FirmwareHTTP]:
    sdk_read = AsyncMock(return_value=Event(EventType.CLI_REPLY, {"text": "> 915.000"}))
    sdk_send = AsyncMock(return_value=Event(EventType.OK, {}))
    sdk = SimpleNamespace(
        commands=SimpleNamespace(run_cli_command=sdk_read, send=sdk_send),
        self_info={"public_key": "ab" * 32, "name": "QA companion"},
    )
    adapter = MeshcoreSDKAdapter("VIRTUAL-FIRMWARE-HTTP")
    adapter.mc = sdk
    adapter.is_connected = True
    adapter.self_info = sdk.self_info
    await adapter._handle_device_info({
        "fw ver": 14, "ver": "1.18.0", "model": "QA radio", "ble_pin": 654321,
    })
    mqtt = MagicMock()
    admin = AdminCommandHandler(AdminContext(
        mc_provider=lambda: sdk, node_registry=NodeRegistry(), repeater_manager=RepeaterManager(),
        mqtt=mqtt, execute_tx=AsyncMock(), serial_adapter=adapter,
    ))
    database = StationDatabase(tmp_path / "station.sqlite3")
    await asyncio.to_thread(database.initialize)
    bridge = SimpleNamespace(
        admin_handler=admin, handle_admin=admin.handle, serial_adapter=adapter,
        database=database, start_time=time.time(),
    )
    router = WebAPIRouter(bridge)
    app = create_asgi_app(router, shutdown_budget_s=1)
    store = app.state.authentication.store
    await asyncio.to_thread(store.initialize)
    await asyncio.to_thread(store.bootstrap, "qa-owner", "isolated firmware password")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            yield FirmwareHTTP(client, adapter, sdk_read, sdk_send, mqtt)
    finally:
        router.cancel_notifications()
        await asyncio.gather(*router.owned_notification_tasks(), return_exceptions=True)
        router.map_tile_service.close()


@pytest.mark.parametrize("method,path", [("GET", "/api/config"), ("POST", "/api/admin")])
async def test_firmware_http_requires_authentication(
    firmware_http: FirmwareHTTP, method: str, path: str
) -> None:
    response = await firmware_http.client.request(
        method, path, json={"action": "cli", "scope": "firmware", "command": "get freq"},
        headers={"Origin": "http://localhost"},
    )
    assert response.status_code == 401
    firmware_http.sdk_read.assert_not_awaited()


async def test_firmware_http_cookie_read_requires_csrf_and_same_origin(
    firmware_http: FirmwareHTTP,
) -> None:
    headers = await firmware_http.owner_headers()
    payload = {"action": "cli", "scope": "firmware", "command": "get freq"}
    no_csrf = await firmware_http.client.post(
        "/api/admin", json=payload, headers={"Origin": "http://localhost"},
    )
    assert no_csrf.status_code == 403
    cross_origin = await firmware_http.client.post(
        "/api/admin", json=payload, headers={**headers, "Origin": "https://evil.example"},
    )
    assert cross_origin.status_code == 403
    firmware_http.sdk_read.assert_not_awaited()

    response = await firmware_http.client.post("/api/admin", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["result"] == {
        "status": "ok", "scope": "firmware", "action": "cli",
        "command": "get freq", "result": "> 915.000",
    }
    assert response.headers["cache-control"] == "no-store"
    firmware_http.sdk_read.assert_awaited_once_with("get freq")
    firmware_http.mqtt.publish_safe.assert_not_called()


async def test_firmware_http_config_exposes_capability_without_getter_or_pin(
    firmware_http: FirmwareHTTP,
) -> None:
    await firmware_http.owner_headers()
    response = await firmware_http.client.get("/api/config")
    assert response.status_code == 200
    capabilities = response.json()["data"]["capabilities"]["firmware_cli"]
    assert capabilities["state"] == "present"
    assert capabilities["companion_protocol"] == 14
    assert capabilities["firmware_version"] == "1.18.0"
    assert capabilities["safe_commands"] == [
        "get radio", "get freq", "get cad", "get radio.rxgain", "get path.hash.mode",
        "get wifi.ssid", "get wifi.enabled", "get wifi.status", "get wifi.ip",
    ]
    assert capabilities["writable_preferences"] == ["cad", "wifi"]
    assert "654321" not in response.text
    assert "ble_pin" not in capabilities
    firmware_http.sdk_read.assert_not_awaited()


async def test_cad_write_requires_session_csrf_and_origin_without_automatic_readback(
    firmware_http: FirmwareHTTP,
) -> None:
    payload = {"action": "set_preference", "scope": "firmware", "preference": "cad", "value": True}
    response = await firmware_http.client.post("/api/admin", json=payload)
    assert response.status_code == 401
    headers = await firmware_http.owner_headers()
    response = await firmware_http.client.post("/api/admin", json=payload, headers={"Origin": "http://localhost"})
    assert response.status_code == 403
    response = await firmware_http.client.post("/api/admin", json=payload, headers={**headers, "Origin": "https://evil.example"})
    assert response.status_code == 403
    firmware_http.sdk_read.assert_not_awaited()
    firmware_http.sdk_read.return_value = Event(EventType.CLI_REPLY, {"text": "OK"})
    response = await firmware_http.client.post("/api/admin", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["result"] == {
        "status": "ok", "scope": "firmware", "action": "set_preference", "preference": "cad",
        "value": True, "acknowledged": True, "hardware_verified": False,
    }
    firmware_http.sdk_read.assert_awaited_once_with("set cad on")
    firmware_http.mqtt.publish_safe.assert_not_called()
    firmware_http.mqtt.publish_safe.assert_not_called()


async def test_firmware_scope_name_keeps_existing_flood_scope_admin_action(
    firmware_http: FirmwareHTTP,
) -> None:
    headers = await firmware_http.owner_headers()
    response = await firmware_http.client.post(
        "/api/admin", json={"action": "set_flood_scope", "scope": "firmware"}, headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["result"]["flood_scope"]["scope_name"] == "#firmware"
    sent_call = firmware_http.sdk_send.await_args
    assert sent_call is not None
    sent_frame = sent_call.args[0]
    assert sent_frame[0] == 63
    assert sent_frame[1:32].rstrip(b"\0") == b"#firmware"
    firmware_http.sdk_read.assert_not_awaited()


@pytest.mark.parametrize("payload", [
    {"action": "cli", "scope": "firmware", "command": ["get freq"]},
    {"action": "cli", "scope": "firmware", "command": "get wifi.pwd"},
    {"action": "cli", "scope": "firmware", "command": "set radio 915,125,7,5"},
    {"action": "cli", "scope": "firmware", "command": "get freq", "target_node": "ab" * 32},
])
async def test_firmware_http_invalid_input_fails_before_sdk_dispatch(
    firmware_http: FirmwareHTTP, payload: dict[str, Any]
) -> None:
    headers = await firmware_http.owner_headers()
    response = await firmware_http.client.post("/api/admin", json=payload, headers=headers)
    assert response.status_code == 422
    firmware_http.sdk_read.assert_not_awaited()
    firmware_http.mqtt.publish_safe.assert_not_called()


@pytest.mark.parametrize("action", ["CLI", ""])
async def test_firmware_http_invalid_scope_never_falls_back_to_bridge_console(
    firmware_http: FirmwareHTTP, action: str
) -> None:
    headers = await firmware_http.owner_headers()
    response = await firmware_http.client.post(
        "/api/admin", json={"action": action, "scope": "firmwar", "command": "nodes"},
        headers=headers,
    )
    assert response.status_code == 422
    firmware_http.sdk_read.assert_not_awaited()
    firmware_http.mqtt.publish_safe.assert_not_called()


@pytest.mark.parametrize("failure,status", [("legacy", 503), ("timeout", 503), ("semantic", 400)])
async def test_firmware_http_preserves_transceiver_failure_status(
    firmware_http: FirmwareHTTP, failure: str, status: int
) -> None:
    headers = await firmware_http.owner_headers()
    if failure == "legacy":
        await firmware_http.adapter._handle_device_info({"fw ver": 13, "ver": "1.17.1"})
    elif failure == "timeout":
        firmware_http.sdk_read.return_value = Event(EventType.ERROR, {"reason": "no_event_received"})
    else:
        firmware_http.sdk_read.return_value = Event(EventType.CLI_REPLY, {"text": "Error private-firmware-detail"})
    response = await firmware_http.client.post(
        "/api/admin", json={"action": "cli", "scope": "firmware", "command": "get freq"},
        headers=headers,
    )
    assert response.status_code == status
    assert "private-firmware-detail" not in response.text
    firmware_http.mqtt.publish_safe.assert_not_called()
    if failure == "legacy":
        firmware_http.sdk_read.assert_not_awaited()
