"""Manual CAD writes stay local, typed and distinct from verified hardware state."""
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


def preference_admin(value: bool = True) -> tuple[AdminCommandHandler, Any]:
    adapter = SimpleNamespace(
        set_firmware_preference=AsyncMock(return_value={
            "preference": "cad", "value": value,
            "acknowledged": True, "hardware_verified": False,
        }),
        run_firmware_cli=AsyncMock(return_value={"command": "get cad", "text": "> on"}),
    )
    ctx = AdminContext(
        mc_provider=lambda: SimpleNamespace(self_info={}, commands=SimpleNamespace()),
        node_registry=NodeRegistry(), repeater_manager=RepeaterManager(),
        mqtt=MagicMock(), execute_tx=AsyncMock(), serial_adapter=adapter,
    )
    return AdminCommandHandler(ctx), adapter


@pytest.mark.parametrize("value", [False, True])
async def test_manual_cad_ack_does_not_claim_hardware_application_or_read_back(value: bool) -> None:
    admin, adapter = preference_admin(value)
    result = await admin.handle({
        "action": "set_preference", "scope": "firmware", "preference": "cad", "value": value,
    }, manual=True)
    assert result == {
        "status": "ok", "scope": "firmware", "action": "set_preference",
        "preference": "cad", "value": value, "acknowledged": True,
        "hardware_verified": False,
    }
    adapter.set_firmware_preference.assert_awaited_once_with("cad", value)
    adapter.run_firmware_cli.assert_not_awaited()
    admin._ctx.execute_tx.assert_not_awaited()
    admin._ctx.mqtt.publish_safe.assert_not_called()


@pytest.mark.parametrize("change", [
    {"value": 1}, {"value": 0}, {"value": "on"}, {"value": "false"}, {"value": None},
    {"value": []}, {"preference": "CAD"}, {"preference": "cad "},
    {"preference": "radio.rxgain"}, {"preference": "path.hash.mode"},
    {"preference": ["cad"]}, {"scope": "bridge"}, {"scope": None},
    {"command": "set cad on"}, {"cmd": "set cad on"}, {"params": {}},
    {"target_node": "local"}, {"repeater": "local"}, {"target": None}, {"to": None},
    {"password": "secret"}, {"unknown": True},
])
async def test_invalid_or_ambiguous_preference_requests_fail_before_adapter(change: dict[str, Any]) -> None:
    admin, adapter = preference_admin()
    result = await admin.handle({
        "action": "set_preference", "scope": "firmware", "preference": "cad", "value": True,
        **change,
    })
    assert result["status"] == "error"
    assert result["code"] == 422
    adapter.set_firmware_preference.assert_not_awaited()
    adapter.run_firmware_cli.assert_not_awaited()
    admin._ctx.execute_tx.assert_not_awaited()
    admin._ctx.mqtt.publish_safe.assert_not_called()


@pytest.mark.parametrize("missing", ["scope", "preference", "value"])
async def test_preference_request_requires_explicit_fields(missing: str) -> None:
    admin, adapter = preference_admin()
    payload: dict[str, Any] = {
        "action": "set_preference", "scope": "firmware", "preference": "cad", "value": True,
    }
    del payload[missing]
    result = await admin.handle(payload)
    assert result["code"] == 422
    adapter.set_firmware_preference.assert_not_awaited()


@pytest.mark.parametrize("extra", [{"preference": "cad"}, {"value": True}])
async def test_getter_cannot_silently_ignore_preference_write_fields(extra: dict[str, Any]) -> None:
    admin, adapter = preference_admin()
    result = await admin.handle({"action": "cli", "scope": "firmware", "command": "get cad", **extra})
    assert result["code"] == 422
    adapter.set_firmware_preference.assert_not_awaited()
    adapter.run_firmware_cli.assert_not_awaited()


@pytest.mark.parametrize("error,status", [
    (TimeoutError("secret"), 503), (ConnectionError("secret"), 503),
    (NotImplementedError("secret"), 503), (RuntimeError("secret"), 400),
])
async def test_preference_failure_keeps_http_status_and_never_retries(error: Exception, status: int) -> None:
    admin, adapter = preference_admin()
    adapter.set_firmware_preference.side_effect = error
    controller = RepeaterController(ApiContext(
        bridge=SimpleNamespace(handle_admin=admin.handle), recent_messages=deque(), system_logs=deque(),
        log_system_event=lambda *args, **kwargs: None,
    ))
    code, body = await controller.execute_admin_command({
        "action": "set_preference", "scope": "firmware", "preference": "cad", "value": True,
    })
    assert code == status
    assert "secret" not in str(body)
    adapter.set_firmware_preference.assert_awaited_once_with("cad", True)
    adapter.run_firmware_cli.assert_not_awaited()
    admin._ctx.mqtt.publish_safe.assert_not_called()


@pytest.mark.parametrize("reply", [
    None, {}, {"preference": "cad", "value": True, "acknowledged": False, "hardware_verified": False},
    {"preference": "cad", "value": False, "acknowledged": True, "hardware_verified": False},
    {"preference": "cad", "value": True, "acknowledged": True, "hardware_verified": True},
])
async def test_unconfirmed_adapter_result_is_not_reported_as_success(reply: Any) -> None:
    admin, adapter = preference_admin()
    adapter.set_firmware_preference.return_value = reply
    result = await admin.handle({
        "action": "set_preference", "scope": "firmware", "preference": "cad", "value": True,
    })
    assert result["status"] == "error"
    assert result["code"] == 400


async def test_legacy_adapter_without_preference_method_returns_unavailable() -> None:
    admin, _ = preference_admin()
    admin._ctx.serial_adapter = SimpleNamespace()
    result = await admin.handle({
        "action": "set_preference", "scope": "firmware", "preference": "cad", "value": False,
    })
    assert result["code"] == 503
