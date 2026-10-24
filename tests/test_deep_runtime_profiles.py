"""Optional packages must stay optional without creating network clients."""

from __future__ import annotations

import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.check_runtime_dependencies import PROFILES
from src.application.capabilities import CapabilityRegistry
from src.bridge_core import MeshCoreBridge
from src.mqtt_client import DisabledMQTTClient, MQTTConfig
from src.services_config import LocalMqttConfig
from src.services_manager import ServicesManager
from src.web.asgi_openapi import build_openapi_schema


def test_packaged_core_and_checker_do_not_require_web_or_mqtt() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert set(project["dependencies"]) == {
        "meshcore==2.3.17", "pyserial==3.5", "python-dotenv==1.2.4",
    }
    assert {name for name, _, _ in PROFILES["core"]} == {"meshcore", "pyserial", "python-dotenv"}
    assert "paho-mqtt" not in {name for name, _, _ in PROFILES["web"]}
    assert "paho-mqtt" in {name for name, _, _ in PROFILES["all"]}


def test_disabled_mqtt_does_not_open_tls_files_or_create_paho(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.mqtt_client as module

    create = Mock(side_effect=AssertionError("Disabled integration constructed a client"))
    monkeypatch.setattr(module, "mqtt", SimpleNamespace(Client=create))
    client = DisabledMQTTClient(MQTTConfig(tls_enabled=True, tls_ca_file="missing.pem"))
    client.start()
    assert not client.publish_safe("meshcore/test", "{}")
    client.stop()
    create.assert_not_called()


def test_absent_mqtt_package_does_not_break_headless_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CapabilityRegistry, "is_mqtt_installed", staticmethod(lambda: False))
    manager = object.__new__(ServicesManager)
    manager.on_incoming_mqtt_message = None
    cfg = LocalMqttConfig(enabled=True, tls_enabled=True, tls_ca_file="missing.pem")
    assert isinstance(manager._create_local_mqtt_client(cfg), DisabledMQTTClient)


def test_core_readiness_tracks_connected_radio_and_shutdown() -> None:
    station = object.__new__(MeshCoreBridge)
    station.capabilities = CapabilityRegistry(web_enabled=False)
    station.serial_adapter = SimpleNamespace(is_connected=True)
    station._started = station.running = True
    station._is_stopped = False
    station.refresh_core_capability()
    assert station.capabilities.get_readiness()["core_ready"]
    station.serial_adapter.is_connected = False
    station.refresh_core_capability()
    assert not station.capabilities.get_readiness()["core_ready"]
    station.running = False
    station.refresh_core_capability()
    assert not station.capabilities.is_healthy()


def test_capability_operations_are_discoverable_with_auth_in_openapi() -> None:
    schema = build_openapi_schema()
    for path in ("/api/capabilities", "/api/services/capabilities"):
        operation = schema["paths"][path]["get"]
        assert operation["security"]
        assert "200" in operation["responses"]
        assert operation["x-meshcore-authentication"]["required"] is True
