"""Local WiFi Companion configuration contracts, write-only password redaction and HTTP/admin boundary."""

from __future__ import annotations

import asyncio
import logging
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
from meshcore import EventType
from meshcore.events import Event

from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeRegistry
from src.diagnostics import SystemLogHandler
from src.protocol_types import redact_command_str
from src.repeater_manager import RepeaterManager
from src.serial.sdk_adapter import MeshcoreSDKAdapter
from src.station_database import StationDatabase
from src.web.api_router import WebAPIRouter
from src.web.asgi_server import create_asgi_app


async def wifi_adapter(replies: list[str] | None = None) -> MeshcoreSDKAdapter:
    adapter = MeshcoreSDKAdapter("tcp://127.0.0.1:4000")
    queue = list(replies or ["> wifi.ssid is now MeshStation", "> wifi.pwd updated", "> wifi.enabled is now on"])

    async def run_cli_command(command: str) -> Event:
        text = queue.pop(0) if queue else "> ok"
        return Event(EventType.CLI_REPLY, {"text": text})

    adapter.mc = SimpleNamespace(commands=SimpleNamespace(
        run_cli_command=AsyncMock(side_effect=run_cli_command),
    ))
    adapter.is_connected = True
    await adapter._handle_device_info(Event(EventType.DEVICE_INFO, {"fw ver": 14, "ver": "1.18.0"}))
    return adapter


@pytest.mark.parametrize("command,reply", [
    ("get wifi.ssid", "> MeshStation"),
    ("get wifi.enabled", "> on"),
    ("get wifi.status", "> connected"),
    ("get wifi.ip", "> 192.168.1.44"),
])
async def test_safe_wifi_getters_execute_single_local_read(command: str, reply: str) -> None:
    adapter = await wifi_adapter([reply])
    assert await adapter.run_firmware_cli(command) == {"command": command, "text": reply}
    adapter.mc.commands.run_cli_command.assert_awaited_once_with(command)


@pytest.mark.parametrize("command", [
    "get wifi.pwd", "get wifi.password", "GET wifi.ssid", "set wifi.ssid Mesh",
    "set wifi.pwd secret", "wifi.clear",
])
async def test_getter_allowlist_blocks_wifi_password_and_raw_wifi_mutations(command: str) -> None:
    adapter = await wifi_adapter()
    with pytest.raises(ValueError, match="invalid_firmware_command"):
        await adapter.run_firmware_cli(command)
    adapter.mc.commands.run_cli_command.assert_not_awaited()


async def test_set_firmware_wifi_executes_ordered_steps_and_never_echoes_password() -> None:
    adapter = await wifi_adapter([
        "> wifi.ssid is now MeshStation (reboot needed to apply)",
        "> wifi.pwd updated (reboot needed to apply)",
        "> wifi.enabled is now on (reboot needed to apply)",
    ])
    secret = "TopSecret-WiFi-Canary-99!"
    result = await adapter.set_firmware_wifi(ssid="MeshStation", password=secret, enabled=True)
    assert result == {
        "ssid": "MeshStation",
        "password_updated": True,
        "enabled": True,
        "cleared": False,
        "reboot_required": True,
        "acknowledged": True,
        "hardware_verified": False,
    }
    assert secret not in str(result)
    assert [call.args[0] for call in adapter.mc.commands.run_cli_command.await_args_list] == [
        "set wifi.ssid MeshStation",
        f"set wifi.pwd {secret}",
        "set wifi.enabled on",
    ]


async def test_clear_firmware_wifi_executes_wifi_clear_exclusively() -> None:
    adapter = await wifi_adapter(["> wifi config cleared (reboot needed to apply)"])
    result = await adapter.set_firmware_wifi(clear=True)
    assert result == {
        "ssid": None,
        "password_updated": False,
        "enabled": False,
        "cleared": True,
        "reboot_required": True,
        "acknowledged": True,
        "hardware_verified": False,
    }
    adapter.mc.commands.run_cli_command.assert_awaited_once_with("wifi.clear")


@pytest.mark.parametrize("kwargs", [
    {},
    {"clear": False},
    {"clear": "true"},
    {"clear": True, "ssid": "MeshStation"},
    {"clear": True, "password": "secret"},
    {"clear": True, "enabled": False},
    {"ssid": ""},
    {"ssid": "   "},
    {"ssid": "A" * 33},
    {"ssid": "Mesh\nStation"},
    {"ssid": "Mesh\x00Station"},
    {"ssid": 123},
    {"password": ""},
    {"password": "   "},
    {"password": "P" * 64},
    {"password": "secret\rreboot"},
    {"password": 123},
    {"enabled": "on"},
    {"enabled": 1},
])
async def test_invalid_wifi_arguments_fail_before_sdk_dispatch(kwargs: dict[str, Any]) -> None:
    adapter = await wifi_adapter()
    with pytest.raises(ValueError, match="invalid_firmware_wifi"):
        await adapter.set_firmware_wifi(**kwargs)
    adapter.mc.commands.run_cli_command.assert_not_awaited()


async def test_partial_wifi_failure_rejects_without_leaking_password_or_rolling_back() -> None:
    adapter = await wifi_adapter([
        "> wifi.ssid is now MeshStation",
        "> Error: invalid password canary-secret",
    ])
    secret = "SuperSecretCanary123"
    with pytest.raises(RuntimeError) as exc_info:
        await adapter.set_firmware_wifi(ssid="MeshStation", password=secret, enabled=True)
    assert str(exc_info.value) == "firmware_wifi_rejected"
    assert secret not in str(exc_info.value)
    assert "canary-secret" not in str(exc_info.value)
    assert adapter.mc.commands.run_cli_command.await_count == 2


def test_redaction_strips_sdk_cli_and_raw_packet_wifi_secrets() -> None:
    secret = "MyWiFiSecret2026!"
    cli_log = f"Sending cli command: set wifi.pwd {secret}"
    pkt_log = f"sending pkt : b'\\x42set wifi.pwd {secret}' (len=30)"
    assert secret not in redact_command_str(cli_log)
    assert secret not in redact_command_str(pkt_log)

    handler = SystemLogHandler(level=logging.DEBUG)
    record = logging.LogRecord(
        name="meshcore", level=logging.DEBUG, pathname=__file__, lineno=1,
        msg="Sending cli command: %s", args=(f"set wifi.pwd {secret}",), exc_info=None,
    )
    handler.emit(record)
    assert len(handler.buffer) == 1
    assert secret not in handler.buffer[0].message


@dataclass
class WifiHTTPFixture:
    client: httpx.AsyncClient
    sdk_read: AsyncMock
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
async def wifi_http(tmp_path: Path) -> AsyncIterator[WifiHTTPFixture]:
    replies = [
        "> wifi.ssid is now MeshField",
        "> wifi.pwd updated",
        "> wifi.enabled is now on",
    ]

    async def sdk_cli(command: str) -> Event:
        text = replies.pop(0) if replies else "> wifi config cleared"
        return Event(EventType.CLI_REPLY, {"text": text})

    sdk_read = AsyncMock(side_effect=sdk_cli)
    sdk = SimpleNamespace(
        commands=SimpleNamespace(run_cli_command=sdk_read, send=AsyncMock(return_value=Event(EventType.OK, {}))),
        self_info={"public_key": "ab" * 32, "name": "QA companion"},
    )
    adapter = MeshcoreSDKAdapter("VIRTUAL-WIFI-HTTP")
    adapter.mc = sdk
    adapter.is_connected = True
    adapter.self_info = sdk.self_info
    await adapter._handle_device_info({"fw ver": 14, "ver": "1.18.0", "model": "QA radio"})
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
            yield WifiHTTPFixture(client, sdk_read, mqtt)
    finally:
        router.cancel_notifications()
        await asyncio.gather(*router.owned_notification_tasks(), return_exceptions=True)
        router.map_tile_service.close()


async def test_wifi_http_requires_session_csrf_and_never_returns_password(
    wifi_http: WifiHTTPFixture,
) -> None:
    secret = "HttpWiFiSecretCanary42!"
    payload = {
        "action": "set_wifi",
        "scope": "firmware",
        "ssid": "MeshField",
        "password": secret,
        "enabled": True,
    }
    unauth = await wifi_http.client.post("/api/admin", json=payload, headers={"Origin": "http://localhost"})
    assert unauth.status_code == 401
    headers = await wifi_http.owner_headers()
    no_csrf = await wifi_http.client.post("/api/admin", json=payload, headers={"Origin": "http://localhost"})
    assert no_csrf.status_code == 403
    wifi_http.sdk_read.assert_not_awaited()

    response = await wifi_http.client.post("/api/admin", json=payload, headers=headers)
    assert response.status_code == 200
    assert secret not in response.text
    assert response.json()["result"] == {
        "status": "ok",
        "scope": "firmware",
        "action": "set_wifi",
        "ssid": "MeshField",
        "password_updated": True,
        "enabled": True,
        "cleared": False,
        "reboot_required": True,
        "acknowledged": True,
        "hardware_verified": False,
    }
    wifi_http.mqtt.publish_safe.assert_not_called()
