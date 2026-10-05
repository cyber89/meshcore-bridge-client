"""Admin responses redact credentials at public boundaries, keeping device state private."""
from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeRegistry
from src.protocol_types import redact_command_str, redact_sensitive_mapping
from src.repeater_manager import RepeaterManager
from src.shared_utils import redact_sensitive_command


@pytest.fixture
def admin() -> AdminCommandHandler:
    sdk = SimpleNamespace(self_info={}, commands=SimpleNamespace())
    return AdminCommandHandler(AdminContext(
        mc_provider=lambda: sdk, node_registry=NodeRegistry(),
        repeater_manager=RepeaterManager(), mqtt=MagicMock(), execute_tx=AsyncMock(),
    ))


def private_config(admin: AdminCommandHandler) -> dict[str, Any]:
    snapshot = {
        "pin": 654321, "password": "synthetic-private-password",
        "nested": {"channels": [{"psk": "synthetic-private-psk", "name": "Weather"}],
                   "sdk": {"private_key": "synthetic-private-key", "rssi": -75}},
    }
    admin._local_config.update(deepcopy(snapshot))
    return snapshot


def assert_public(snapshot: dict[str, Any]) -> None:
    assert snapshot["pin"] == 0
    assert snapshot["has_pin"] is True
    assert snapshot["password"] == "********"
    assert snapshot["nested"]["channels"] == [{"psk": "********", "name": "Weather"}]
    assert snapshot["nested"]["sdk"] == {"private_key": "********", "rssi": -75}


@pytest.mark.parametrize("action", ["get_config", "get_local_config", "config get", "show config", "info"])
async def test_public_admin_configuration_never_exposes_credentials(admin: AdminCommandHandler, action: str) -> None:
    original = private_config(admin)
    result = await admin.handle({"action": action, "request_id": "privacy-audit"})
    assert result["status"] == "ok"
    assert result["request_id"] == "privacy-audit"
    assert_public(result["config"])
    published = json.loads(admin._ctx.mqtt.publish_safe.call_args.args[1])
    assert_public(published["config"])
    for key, value in original.items():
        assert admin._local_config[key] == value
    assert admin.get_local_config()["pin"] == 654321


async def test_direct_cli_entry_point_sanitizes_return_and_publication(admin: AdminCommandHandler) -> None:
    private_config(admin)
    result = await admin._cli_executor.execute("config get", {"status": "ok"}, None)
    assert_public(result["config"])
    assert_public(json.loads(admin._ctx.mqtt.publish_safe.call_args.args[1])["config"])


async def test_sdk_response_nested_credentials_are_redacted_without_mutation(admin: AdminCommandHandler) -> None:
    private_response = {"status": "ok", "sdk": {"pin": 123456, "payload": [{"token": "synthetic-token", "frequency": 915.0}]}}
    original = deepcopy(private_response)
    admin._handle = AsyncMock(return_value=private_response)
    result = await admin.handle({"action": "synthetic-sdk-operation"})
    assert result == {"status": "ok", "sdk": {"pin": 0, "has_pin": True, "payload": [{"token": "********", "frequency": 915.0}]}}
    assert private_response == original


def test_executor_mqtt_boundary_sanitizes_json_payload(admin: AdminCommandHandler) -> None:
    private = {"status": "ok", "sdk": {"pin": 654321, "secret": "synthetic-sdk-secret", "battery_mv": 4100}}
    admin._publish_safe("audit/admin/status", json.dumps(private), qos=2)
    args = admin._ctx.mqtt.publish_safe.call_args
    assert args.args[0] == "audit/admin/status"
    assert args.kwargs["qos"] == 2
    assert json.loads(args.args[1]) == {"status": "ok", "sdk": {"pin": 0, "has_pin": True, "secret": "********", "battery_mv": 4100}}
    assert private["sdk"]["pin"] == 654321


@pytest.mark.parametrize("pin, presence", [(0, False), (None, False), (123456, True)])
async def test_pin_presence_remains_truthful(admin: AdminCommandHandler, pin: Any, presence: bool) -> None:
    admin._local_config["pin"] = pin
    response = await admin.handle({"action": "get_config"})
    assert response["config"]["pin"] == 0
    assert response["config"]["has_pin"] is presence


async def test_cli_pin_failure_does_not_echo_secret(admin: AdminCommandHandler) -> None:
    admin._cli_executor._handle_set_local_config = AsyncMock(side_effect=RuntimeError("SDK rejected PIN 654321"))
    response = await admin.handle({"action": "set pin 654321"})
    assert response["status"] == "error"
    assert "654321" not in json.dumps(response)
    assert "654321" not in admin._ctx.mqtt.publish_safe.call_args.args[1]
    admin._cli_executor._handle_set_local_config.assert_awaited_once()
    assert admin._cli_executor._handle_set_local_config.call_args.args[0]["params"]["pin"] == 654321


@pytest.mark.parametrize("command", ["set pin 654321", "set_pin 654321", "set ble_pin 654321", "set_ble_pin 654321", "SET devicepin 654321", "login synthetic-credential", "set prv.key synthetic-credential"])
def test_sensitive_command_redaction_is_canonical_and_idempotent(command: str) -> None:
    redacted = redact_sensitive_command(command)
    assert redacted == redact_command_str(command)
    assert redacted.endswith("********")
    assert redact_sensitive_command(redacted) == redacted
    assert command.split()[-1] not in redacted


@pytest.mark.parametrize("text", ["set radio 915,125,7,5", "temperature=23", "I forgot the PIN of my device", "get pin", "set pinpoint 42"])
def test_normal_text_is_not_redacted(text: str) -> None:
    assert redact_sensitive_command(text) == text
    assert redact_command_str(text) == text


@pytest.mark.parametrize("key", ["pin", "ble_pin", "blepin", "devicepin"])
def test_pin_aliases_preserve_presence_on_repeated_redaction(key: str) -> None:
    private = {key: 123456, "temperature": 22}
    public = redact_sensitive_mapping(private)
    assert public == {key: 0, "has_pin": True, "temperature": 22}
    assert redact_sensitive_mapping(public) == public
    assert private[key] == 123456


def test_malformed_executor_payload_is_not_published(admin: AdminCommandHandler) -> None:
    admin._publish_safe("audit/admin/status", "invalid JSON with synthetic-secret")
    admin._ctx.mqtt.publish_safe.assert_not_called()
