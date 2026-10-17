"""Companion transport selection never connects or mutates a running radio."""

from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.companion_connection import companion_connection_snapshot, normalize_companion_port
from src.services_config import (
    ServicesConfig,
    load_services_config,
    to_redacted_dict,
    update_services_config,
)
from src.services_manager import ServicesManager
from src.station_database import StationDatabase
from src.web.controllers.base import ApiContext
from src.web.controllers.services_controller import ServicesController


@pytest.mark.parametrize(
    "value",
    [
        "",
        "AUTO",
        "COM3",
        "/dev/serial/by-id/radio",
        "tcp://radio.local:4000",
        "tcp://192.168.1.4:1",
        "tcp://localhost:65535",
        "tcp://host.:4000",
    ],
)
def test_accepts_explicit_companion_endpoints(value: str) -> None:
    assert normalize_companion_port(value) == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        4000,
        True,
        "tcp://host",
        "tcp://host:0",
        "tcp://host:65536",
        "tcp://host:1.5",
        "tcp://host:4000/",
        "tcp://host:4000?q=x",
        "tcp://host:4000#x",
        "tcp://user:secret@host:4000",
        "tcp://[::1]:4000",
        "tcp://::1:4000",
        "tcp://999.2.3.4:4000",
        "udp://host:4000",
        "tcp://host:4000\n",
        "COM3\t",
        "/dev/radio\u0085",
        "random-device",
        "\\\\host\\radio",
    ],
)
def test_rejects_invalid_or_secret_endpoints(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_companion_port(value)


def test_resolved_auto_port_does_not_require_restart() -> None:
    state = companion_connection_snapshot("", "AUTO", "COM3", "AUTO")
    assert state == {
        "configured_port": "",
        "effective_port": "AUTO",
        "active_port": "COM3",
        "restart_required": False,
    }
    assert (
        companion_connection_snapshot("tcp://radio.local:4000", "AUTO", "COM3", "AUTO")[
            "restart_required"
        ]
        is True
    )


def test_snapshot_does_not_expose_credentials_from_environment() -> None:
    state = companion_connection_snapshot(
        "", "tcp://user:secret@host:4000", "tcp://user:secret@host:4000"
    )
    assert "secret" not in str(state)
    assert "secret" not in str(
        to_redacted_dict(ServicesConfig(companion_port="tcp://user:secret@host:4000"))
    )


def test_omission_preserves_override_and_empty_resets_to_environment() -> None:
    cfg = ServicesConfig(companion_port="tcp://radio.local:4000")
    assert (
        update_services_config(cfg, {"tcp_server": {"enabled": False}}).companion_port
        == cfg.companion_port
    )
    assert update_services_config(cfg, {"companion_port": ""}).companion_port == ""
    assert cfg.companion_port == "tcp://radio.local:4000"


def test_old_sqlite_document_inherits_environment(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    database.write_document("services", {"version": 1, "tcp_server": {"enabled": False}})
    assert load_services_config(database=database).companion_port == ""


@pytest.mark.parametrize(
    "override,expected", [("", "COM7"), ("tcp://radio.local:4000", "tcp://radio.local:4000")]
)
def test_next_start_passes_saved_endpoint_to_adapter(
    monkeypatch: pytest.MonkeyPatch, override: str, expected: str
) -> None:
    from src.bridge_core import MeshCoreBridge

    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge.services_manager = SimpleNamespace(
        services_config=ServicesConfig(companion_port=override)
    )
    bridge.node_registry = Mock()
    factory = Mock()
    monkeypatch.setattr("config.SERIAL_PORT", "COM7")
    monkeypatch.setattr("src.bridge_core.MeshcoreSDKAdapter", factory)
    assert bridge._create_serial_adapter() is factory.return_value
    assert factory.call_args.kwargs["port"] == expected
    assert bridge._companion_startup_port == expected


@pytest.mark.asyncio
async def test_transport_only_save_is_persisted_without_restarting_services(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    manager = ServicesManager.__new__(ServicesManager)
    manager.services_config = ServicesConfig()
    manager.database = database
    manager._lifecycle_lock = asyncio.Lock()
    manager._configuration_write_task = None
    # Companion-only changes must never inspect or restart these transports.
    manager.local_mqtt = Mock()
    manager.external_mqtt = Mock()
    manager.tcp_server = Mock()
    result = await manager.reload_services({"companion_port": "tcp://radio.local:4000"})
    assert result["reloaded"] == []
    assert load_services_config(database=database).companion_port == "tcp://radio.local:4000"
    assert manager.local_mqtt.mock_calls == []
    assert manager.external_mqtt.mock_calls == []
    assert manager.tcp_server.mock_calls == []


@pytest.mark.asyncio
async def test_controller_rejects_invalid_endpoint_before_any_reload() -> None:
    bridge = SimpleNamespace(reload_services=AsyncMock())
    controller = ServicesController(ApiContext(bridge, deque(), deque(), Mock()))
    status, body = await controller.set_services_config(
        {"companion_port": "tcp://user:secret@host:4000", "local_mqtt": {"enabled": False}}
    )
    assert status == 422
    assert "secret" not in str(body)
    bridge.reload_services.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_returns_pending_and_active_connections_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = ServicesConfig(companion_port="tcp://radio.local:4000")
    adapter = SimpleNamespace(port="COM7", reconnect=AsyncMock())
    bridge = SimpleNamespace(
        services_config=cfg,
        serial_adapter=adapter,
        _companion_startup_port="AUTO",
        reload_services=AsyncMock(return_value={"reloaded": []}),
    )
    monkeypatch.setattr("config.SERIAL_PORT", "AUTO")
    controller = ServicesController(ApiContext(bridge, deque(), deque(), Mock()))
    status, body = await controller.set_services_config({"companion_port": cfg.companion_port})
    assert status == 200
    assert body["data"]["companion_connection"] == {
        "configured_port": "tcp://radio.local:4000",
        "effective_port": "tcp://radio.local:4000",
        "active_port": "COM7",
        "restart_required": True,
    }
    read_status, read_body = await controller.get_services_config()
    assert read_status == 200
    assert read_body["data"]["companion_connection"] == body["data"]["companion_connection"]
    adapter.reconnect.assert_not_awaited()
