"""Firmware read scope stays local, explicit, private and separate from bridge CLI."""
from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeRegistry
from src.repeater_manager import RepeaterManager
from src.web.controllers.base import ApiContext
from src.web.controllers.repeater_controller import RepeaterController


def firmware_admin() -> tuple[AdminCommandHandler, Any]:
    adapter = SimpleNamespace(
        firmware_capabilities={"state": "present", "reason": "available", "companion_protocol": 14,
                               "safe_commands": ["get radio", "get freq"]},
        run_firmware_cli=AsyncMock(return_value={"command": "get radio", "text": "> 915,125,7,5"}),
    )
    sdk = SimpleNamespace(self_info={}, commands=SimpleNamespace())
    ctx = AdminContext(mc_provider=lambda: sdk, node_registry=NodeRegistry(),
                       repeater_manager=RepeaterManager(), mqtt=MagicMock(), execute_tx=AsyncMock(),
                       serial_adapter=adapter)
    return AdminCommandHandler(ctx), adapter


async def test_explicit_firmware_getter_returns_text_without_mqtt_publication() -> None:
    admin, adapter = firmware_admin()
    result = await admin.handle({"action": "cli", "scope": "firmware", "command": "get radio"})
    assert result["status"] == "ok"
    assert result["result"] == "> 915,125,7,5"
    assert result["scope"] == "firmware"
    assert "config" not in result
    admin._ctx.mqtt.publish_safe.assert_not_called()
    adapter.run_firmware_cli.assert_awaited_once_with("get radio")


@pytest.mark.parametrize("extra", [
    {"target_node": "ab" * 32}, {"repeater": "local"}, {"target": "remote"}, {"to": "remote"},
    {"action": "reboot"}, {"command": None}, {"command": ["get radio"]}, {"scope": "firmwar"},
    {"action": "CLI", "scope": "firmwar"}, {"action": "", "scope": "firmwar"},
])
async def test_ambiguous_firmware_requests_fail_before_any_dispatch(extra: dict[str, Any]) -> None:
    admin, adapter = firmware_admin()
    result = await admin.handle({"action": "cli", "scope": "firmware", "command": "get radio", **extra})
    assert result["status"] == "error"
    assert result["code"] == 422
    adapter.run_firmware_cli.assert_not_awaited()
    admin._ctx.execute_tx.assert_not_awaited()
    admin._ctx.mqtt.publish_safe.assert_not_called()


async def test_bridge_console_does_not_fallback_to_firmware() -> None:
    admin, adapter = firmware_admin()
    result = await admin.handle({"action": "cli", "command": "get radio"})
    assert result["status"] == "error"
    adapter.run_firmware_cli.assert_not_awaited()
    nodes = await admin.handle({"action": "cli", "command": "nodes"})
    assert nodes["status"] == "ok"


@pytest.mark.parametrize("error,status", [
    (ValueError("bad-input-secret"), 422), (NotImplementedError("awaiting_device_info"), 503),
    (ConnectionError("disconnected"), 503), (TimeoutError("late-secret"), 503),
    (RuntimeError("firmware-error-secret"), 400),
])
async def test_firmware_errors_keep_http_failure_and_do_not_echo_exception(error: Exception, status: int) -> None:
    admin, adapter = firmware_admin()
    adapter.run_firmware_cli.side_effect = error
    controller = RepeaterController(ApiContext(
        bridge=SimpleNamespace(handle_admin=admin.handle), recent_messages=deque(), system_logs=deque(),
        log_system_event=lambda *args, **kwargs: None,
    ))
    code, body = await controller.execute_admin_command({"action": "cli", "scope": "firmware", "command": "get radio"})
    assert code == status
    assert "secret" not in str(body)
    admin._ctx.mqtt.publish_safe.assert_not_called()


def test_config_snapshot_adds_capability_without_aliasing_adapter() -> None:
    admin, adapter = firmware_admin()
    result = admin.get_local_config()
    assert result["capabilities"]["firmware_cli"]["companion_protocol"] == 14
    assert result["capabilities"]["telemetry_interval"] is False
    result["capabilities"]["firmware_cli"]["safe_commands"].clear()
    assert adapter.firmware_capabilities["safe_commands"] == ["get radio", "get freq"]


def test_virtual_or_legacy_adapter_never_claims_firmware_support() -> None:
    admin, _ = firmware_admin()
    admin._ctx.serial_adapter = SimpleNamespace()
    result = admin.get_local_config()
    assert result["capabilities"]["firmware_cli"]["state"] == "unknown"
    assert result["capabilities"]["firmware_cli"]["safe_commands"] == []
