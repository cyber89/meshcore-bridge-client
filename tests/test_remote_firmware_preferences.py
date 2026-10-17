"""Remote preference acknowledgements never assert active radio hardware state."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.admin import RemoteRepeaterRequest, RepeaterAdminExecutor, WaiterRegistry
from src.admin_handler import AdminContext
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.repeater_manager import RepeaterManager
from src.target_resolver import TargetResolver

LOCAL = "ab" * 32
REMOTE = "cd" * 32


def preference_executor(role: str | None = "REPEATER", sdk_type: int | None = None) -> tuple[Any, Any, Any]:
    registry = NodeRegistry()
    registry.set_local_pubkey(LOCAL)
    if role is not None:
        registry.add_or_update(REMOTE, NodeContactUpdate(name="Relay", role=role))
    contacts = {} if sdk_type is None else {REMOTE: {"public_key": REMOTE, "type": sdk_type, "name": "Relay"}}
    mc = SimpleNamespace(commands=SimpleNamespace(send_cmd=AsyncMock(return_value={"status": "ok"}),
                                                  add_contact=AsyncMock(return_value={"status": "ok"})), contacts=contacts)
    ctx = AdminContext(mc_provider=lambda: mc, node_registry=registry, repeater_manager=RepeaterManager(),
                       mqtt=MagicMock(), execute_tx=AsyncMock())
    resolver = TargetResolver(lambda: mc, registry)
    wait = AsyncMock(return_value={"text": "> on"})
    executor = RepeaterAdminExecutor(ctx, WaiterRegistry({}, {}), MagicMock(),
                                    lambda target, length: resolver.resolve(target, length), wait,
                                    lambda: {"public_key": LOCAL})
    return executor, ctx, mc


@pytest.mark.parametrize("action,params,command", [
    ("get_cad", {}, "get cad"), ("get_rx_gain", {}, "get radio.rxgain"),
    ("set_cad", {"enabled": True}, "set cad on"),
    ("set_cad", {"enabled": False}, "set cad off"),
    ("set cad off", {}, "set cad off"),
])
def test_preference_commands_have_narrow_wire_forms(action: str, params: dict[str, Any], command: str) -> None:
    assert RepeaterManager().build_repeater_command_payload(action, {"params": params}) == command


@pytest.mark.parametrize("action,params", [
    ("get_cad", {"enabled": True}), ("get_rx_gain", {"unused": None}),
    ("set_cad", {"enabled": "on"}), ("set_cad", {"enabled": 1}),
    ("set_cad", {"enabled": True, "extra": None}),
    ("set cad only", {}), ("set cad on trailing", {}),
    ("set radio.rxgain on", {}), ("set radio.rxgain off", {}),
])
async def test_invalid_preference_command_has_no_radio_or_cooldown_effect(action: str, params: dict[str, Any]) -> None:
    executor, ctx, mc = preference_executor()
    result = await executor.execute(RemoteRepeaterRequest({"params": params}, action, "invalid", REMOTE, mc=mc))
    assert result["status"] == "error"
    assert result["code"] == 422
    mc.commands.send_cmd.assert_not_awaited()
    mc.commands.add_contact.assert_not_awaited()
    assert ctx.repeater_manager.check_airtime_cooldown(REMOTE) == (True, 0.0)


@pytest.mark.parametrize("role,sdk_type", [(None, None), ("CLIENT", 1), ("SENSOR", 4), ("REPEATER", 3), ("ROOM", 2)])
async def test_preference_target_requires_unambiguous_infrastructure(role: str | None, sdk_type: int | None) -> None:
    executor, ctx, mc = preference_executor(role, sdk_type)
    result = await executor.execute(RemoteRepeaterRequest({"params": {}}, "get_cad", "role", REMOTE, mc=mc))
    assert result["status"] == "error"
    mc.commands.send_cmd.assert_not_awaited()
    mc.commands.add_contact.assert_not_awaited()
    assert ctx.repeater_manager.check_airtime_cooldown(REMOTE) == (True, 0.0)


@pytest.mark.parametrize("role,sdk_type", [("REPEATER", 2), ("ROOM", 3)])
@pytest.mark.parametrize("action,field", [("get_cad", "cad"), ("get_rx_gain", "rx_gain")])
async def test_remote_read_is_saved_preference_and_preserves_registry(role: str, sdk_type: int, action: str, field: str) -> None:
    executor, ctx, mc = preference_executor(role, sdk_type)
    before = ctx.node_registry.list_nodes()
    result = await executor.execute(RemoteRepeaterRequest({"params": {}}, action, "read", "Relay", mc=mc))
    assert result["status"] == "ok"
    assert result["target_node"] == REMOTE
    assert result["preferences"] == {field: True}
    assert result["preferences_source"] == "saved_preferences"
    assert result["hardware_verified"] is False
    assert "telemetry" not in result
    assert ctx.node_registry.list_nodes() == before


async def test_cad_acknowledgement_does_not_claim_hardware_application() -> None:
    executor, ctx, mc = preference_executor()
    executor._wait_for_repeater_response.return_value = {"text": "OK"}
    result = await executor.execute(RemoteRepeaterRequest({"params": {"enabled": False}}, "set_cad", "save", REMOTE, mc=mc))
    assert result["status"] == "ok"
    assert result["saved_preferences"] == {"cad": False}
    assert result["acknowledged"] is True
    assert result["hardware_verified"] is False
    assert not any(key in result for key in ("applied", "pending_reboot", "telemetry"))
    mc.commands.send_cmd.assert_awaited_once_with(REMOTE, "00|set cad off")


async def test_registry_only_room_keeps_room_type_when_added_to_radio() -> None:
    executor, _, mc = preference_executor("ROOM")
    result = await executor.execute(RemoteRepeaterRequest({"params": {}}, "get_cad", "room", REMOTE, mc=mc))
    assert result["status"] == "ok"
    contact = mc.commands.add_contact.await_args.args[0]
    assert contact["public_key"] == REMOTE
    assert contact["type"] == 3


@pytest.mark.parametrize("reply,status", [({}, "dispatched"), ({"text": "OK"}, "error"),
                                           ({"text": "> online"}, "error"), ({"text": "Error: unsupported"}, "error")])
async def test_missing_or_invalid_read_never_invents_preference(reply: dict[str, Any], status: str) -> None:
    executor, _, mc = preference_executor()
    executor._wait_for_repeater_response.return_value = reply
    result = await executor.execute(RemoteRepeaterRequest({"params": {}}, "get_cad", "read", REMOTE, mc=mc))
    assert result["status"] == status
    assert "preferences" not in result
    assert "saved_preferences" not in result


async def test_existing_alias_cooldown_is_preserved() -> None:
    executor, ctx, mc = preference_executor()
    ctx.repeater_manager.record_command_sent("Relay")
    result = await executor.execute(RemoteRepeaterRequest({"params": {}}, "get_cad", "alias", "Relay", mc=mc))
    assert result["status"] == "error"
    assert result["code"] == 429
    mc.commands.send_cmd.assert_not_awaited()


async def test_local_public_key_is_rejected_before_radio_contact_creation() -> None:
    executor, _, mc = preference_executor()
    result = await executor.execute(RemoteRepeaterRequest({"params": {}}, "get_cad", "local", LOCAL, mc=mc))
    assert result["status"] == "error"
    mc.commands.add_contact.assert_not_awaited()
    mc.commands.send_cmd.assert_not_awaited()


async def test_ambiguous_infrastructure_alias_is_not_sent_to_first_match() -> None:
    executor, ctx, mc = preference_executor()
    ctx.node_registry.add_or_update("ef" * 32, NodeContactUpdate(name="Relay", role="ROOM"))
    result = await executor.execute(RemoteRepeaterRequest({"params": {}}, "get_cad", "ambiguous", "Relay", mc=mc))
    assert result["status"] == "error"
    mc.commands.add_contact.assert_not_awaited()
    mc.commands.send_cmd.assert_not_awaited()


async def test_sdk_contact_route_snapshot_survives_state_loading() -> None:
    executor, ctx, mc = preference_executor("REPEATER", 2)
    contact = mc.contacts[REMOTE]
    contact["out_path"] = "aabb"

    async def change_sdk_contact() -> None:
        contact["out_path"] = "ccdd"
        contact["type"] = 1

    ctx.repeater_manager.load_state = change_sdk_contact
    result = await executor.execute(RemoteRepeaterRequest({"params": {}}, "get_cad", "snapshot", REMOTE, mc=mc))
    assert result["status"] == "ok"
    destination = mc.commands.send_cmd.await_args.args[0]
    assert destination["type"] == 2
    assert destination["out_path"] == "aabb"


async def test_registry_room_type_snapshot_survives_state_loading() -> None:
    executor, ctx, mc = preference_executor("ROOM")

    async def change_registry_role() -> None:
        ctx.node_registry.add_or_update(REMOTE, NodeContactUpdate(role="REPEATER"))

    ctx.repeater_manager.load_state = change_registry_role
    result = await executor.execute(RemoteRepeaterRequest({"params": {}}, "get_cad", "room-snapshot", REMOTE, mc=mc))
    assert result["status"] == "ok"
    assert mc.commands.add_contact.await_args.args[0]["type"] == 3


@pytest.mark.parametrize("reply", ["Error: unsupported CANARY_SECRET", "> CANARY_SECRET", "login CANARY_SECRET"])
async def test_unexpected_preference_text_is_not_returned_or_published(reply: str) -> None:
    executor, _, mc = preference_executor()
    executor._wait_for_repeater_response.return_value = {"text": reply}
    result = await executor.execute(RemoteRepeaterRequest({"params": {}}, "get_cad", "canary", REMOTE, mc=mc))
    assert result["status"] == "error"
    assert "CANARY_SECRET" not in str(result)
    assert "CANARY_SECRET" not in str(executor._publish_safe.call_args_list)
