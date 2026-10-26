"""ROOM repeat activation is refused before administrative side effects."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from meshcore.events import Event, EventType

from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.repeater_manager import RepeaterManager

KEY = "ab" * 32


def administration(role: str = "ROOM", version: str | None = None) -> tuple[AdminCommandHandler, Any, RepeaterManager]:
    registry = NodeRegistry()
    registry.add_or_update(KEY, NodeContactUpdate(name="Community", alias="bbs", role=role, firmware_version=version))
    manager = RepeaterManager()
    vars(manager).update(
        check_airtime_cooldown=MagicMock(return_value=(True, 0.0)),
        record_command_sent=MagicMock(),
    )
    commands = SimpleNamespace(
        add_contact=AsyncMock(return_value=Event(EventType.OK, {})),
        send_cmd=AsyncMock(return_value=Event(EventType.OK, {})),
        send_login_sync=AsyncMock(return_value=Event(EventType.LOGIN_SUCCESS, {"permissions": 3})),
    )
    sdk = SimpleNamespace(commands=commands, contacts={KEY: {"public_key": KEY, "type": 3 if role == "ROOM" else 2, "adv_name": "Community", "out_path_len": 0}})
    admin = AdminCommandHandler(AdminContext(
        mc_provider=lambda: sdk, node_registry=registry, repeater_manager=manager,
        mqtt=MagicMock(), execute_tx=AsyncMock(),
    ))
    admin._repeater_executor._wait_for_repeater_response = AsyncMock(return_value={"text": "OK"})
    return admin, sdk, manager


def assert_no_dispatch(admin: AdminCommandHandler, sdk: Any, manager: RepeaterManager) -> None:
    sdk.commands.send_cmd.assert_not_awaited()
    sdk.commands.send_login_sync.assert_not_awaited()
    sdk.commands.add_contact.assert_not_awaited()
    assert isinstance(manager.check_airtime_cooldown, MagicMock)
    manager.check_airtime_cooldown.assert_not_called()
    assert isinstance(manager.record_command_sent, MagicMock)
    manager.record_command_sent.assert_not_called()
    assert isinstance(admin._ctx.execute_tx, AsyncMock)
    admin._ctx.execute_tx.assert_not_awaited()


@pytest.mark.parametrize("version", [None, "v1.17.1", "v1.18.0 (Build: 15 Oct 2026)"])
@pytest.mark.parametrize("action", ["set_repeat", "repeat_settings", "repeat", "set_repeat_enabled", "repeat_enabled"])
async def test_room_repeat_aliases_reject_before_login_or_cooldown(version: str | None, action: str) -> None:
    admin, sdk, manager = administration(version=version)
    result = await admin.handle({"target_node": KEY, "action": action, "repeat": True, "password": "secret"})
    assert result["status"] == "error"
    assert result["code"] == 422
    assert_no_dispatch(admin, sdk, manager)
    node = admin._ctx.node_registry.get_by_key_or_prefix(KEY)
    assert node is not None and node.repeat_enabled is None


@pytest.mark.parametrize("command", ["set repeat on", " set repeat on ", "AA|set repeat on", " AA|set repeat on", "set   repeat on", "SET REPEAT ON", "\tAA|set repeat on"])
async def test_room_preformatted_activation_cannot_bypass_with_spaces_or_prefix(command: str) -> None:
    admin, sdk, manager = administration()
    result = await admin.handle({"target_node": KEY, "action": "cli", "command": command, "password": "secret"})
    assert result["status"] == "error"
    assert result["code"] == 422
    assert_no_dispatch(admin, sdk, manager)


@pytest.mark.parametrize("alias,value", [("repeat", True), ("repeat_enabled", "on"), ("repeat", 1)])
async def test_room_batch_rejects_entire_plan_before_first_setter(alias: str, value: Any) -> None:
    admin, sdk, manager = administration()
    result = await admin.handle({"target_node": "bbs", "action": "remote_repeater_set_config", "password": "secret", "params": {"name": "New name", "tx_power": 20, alias: value}})
    assert result["status"] == "error"
    assert result["code"] == 422
    assert_no_dispatch(admin, sdk, manager)
    node = admin._ctx.node_registry.get_by_key_or_prefix(KEY)
    assert node is not None and node.name == "Community"


@pytest.mark.parametrize("role,enabled", [("ROOM", False), ("REPEATER", True)])
async def test_room_repeat_off_and_repeater_activation_keep_existing_administration(role: str, enabled: bool) -> None:
    admin, sdk, _ = administration(role)
    result = await admin.handle({"target_node": KEY, "action": "set_repeat", "repeat": enabled})
    assert result["status"] == "ok"
    assert sdk.commands.send_cmd.await_args.args[1] == ("00|set repeat on" if enabled else "00|set repeat off")


async def test_room_guard_ignores_role_and_version_from_untrusted_request() -> None:
    admin, sdk, manager = administration()
    result = await admin.handle({"target_node": KEY, "action": "set repeat on", "role": "REPEATER", "firmware_version": "v1.17.1"})
    assert result["status"] == "error"
    assert result["code"] == 422
    assert_no_dispatch(admin, sdk, manager)


async def test_ambiguous_prefix_cannot_select_a_repeater_instead_of_room() -> None:
    admin, sdk, manager = administration("REPEATER")
    other_key = "ab" * 6 + "cd" * 26
    admin._ctx.node_registry.add_or_update(other_key, NodeContactUpdate(name="Other room", role="ROOM"))
    sdk.contacts[other_key] = {"public_key": other_key, "type": 3}
    result = await admin.handle({"target_node": KEY[:12], "action": "set repeat on"})
    assert result["status"] == "error"
    assert result["code"] == 422
    assert_no_dispatch(admin, sdk, manager)


async def test_repeater_repeat_guard_preserves_existing_alias_cooldown_key() -> None:
    admin, sdk, manager = administration("REPEATER")
    assert isinstance(manager.check_airtime_cooldown, MagicMock)
    manager.check_airtime_cooldown.return_value = (False, 1.0)
    result = await admin.handle({"target_node": "bbs", "action": "set_repeat", "repeat": True})
    assert result["code"] == 429
    manager.check_airtime_cooldown.assert_called_once_with("bbs", is_full_query=False)
    sdk.commands.send_cmd.assert_not_awaited()


async def test_final_room_guard_blocks_internal_send_before_sdk_dispatch() -> None:
    admin, sdk, _ = administration()
    with pytest.raises(ValueError, match="room_repeat_unsupported"):
        await admin._repeater_executor._send_rf_command(
            sdk, sdk.contacts[KEY], "AA|set repeat on", KEY, None,
        )
    sdk.commands.send_cmd.assert_not_awaited()


async def test_room_name_containing_command_text_is_not_treated_as_repeat_action() -> None:
    admin, sdk, _ = administration()
    result = await admin.handle({"target_node": KEY, "action": "set_name", "name": "set repeat on"})
    assert result["status"] == "ok"
    assert sdk.commands.send_cmd.await_args.args[1] == "00|set name set repeat on"


@pytest.mark.parametrize("type_field", ["type", "adv_type"])
async def test_sdk_room_object_is_blocked_without_a_registry_entry(type_field: str) -> None:
    admin, sdk, manager = administration()
    admin._ctx.node_registry = NodeRegistry()
    sdk.contacts[KEY] = SimpleNamespace(public_key=KEY, **{type_field: 3})
    result = await admin.handle({"target_node": KEY, "action": "set repeat on", "password": "secret"})
    assert result["status"] == "error"
    assert result["code"] == 422
    assert_no_dispatch(admin, sdk, manager)


async def test_sdk_contact_without_public_key_is_rejected_before_effects() -> None:
    admin, sdk, manager = administration()
    sdk.contacts[KEY] = {"type": 2, "adv_name": "Community"}
    result = await admin.handle({"target_node": KEY, "action": "set repeat on", "password": "secret"})
    assert result["status"] == "error"
    assert result["code"] == 404
    assert_no_dispatch(admin, sdk, manager)


async def test_internal_send_room_object_guard_is_independent_of_registry() -> None:
    admin, sdk, _ = administration()
    admin._ctx.node_registry = NodeRegistry()
    destination = SimpleNamespace(public_key=KEY, adv_type=3)
    with pytest.raises(ValueError, match="room_repeat_unsupported"):
        await admin._repeater_executor._send_rf_command(sdk, destination, "set repeat on", KEY, None)
    sdk.commands.send_cmd.assert_not_awaited()
