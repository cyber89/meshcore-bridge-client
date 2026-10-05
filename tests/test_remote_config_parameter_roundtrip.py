"""Remote preferences require a correlated firmware reply, never a local MSG_SENT."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from meshcore.events import Event, EventType

from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.repeater_manager import RepeaterManager
from src.web.controllers.base import ApiContext
from src.web.controllers.repeater_controller import RepeaterController

LOCAL = "ab" * 32
REMOTE = "cd" * 32


@pytest.fixture
def remote_station(monkeypatch: pytest.MonkeyPatch) -> tuple[AdminCommandHandler, AdminContext, Any, dict[str, Any]]:
    async def immediate_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("src.admin.repeater_executor.asyncio.sleep", immediate_sleep)
    registry = NodeRegistry()
    registry.set_local_pubkey(LOCAL)
    registry.add_or_update(REMOTE, NodeContactUpdate(name="Before", role="REPEATER", frequency=915, tx_power=20))
    state: dict[str, Any] = {"name": "Before", "tx_power": 20, "frequency": 915, "bandwidth": 250, "spreading_factor": 11, "coding_rate": "4/5"}
    mc = SimpleNamespace(
        self_info={"public_key": LOCAL},
        contacts={REMOTE: {"public_key": REMOTE, "adv_name": "Before", "type": 2}},
        commands=SimpleNamespace(),
    )
    mc.get_contact_by_key_prefix = lambda prefix: mc.contacts.get(REMOTE) if REMOTE.startswith(prefix) else None
    mc.get_contact_by_name = lambda name: None
    ctx = AdminContext(lambda: mc, registry, RepeaterManager(min_cmd_interval_s=0, min_telemetry_interval_s=0), MagicMock(), AsyncMock())
    handler = AdminCommandHandler(ctx)

    async def send_cmd(target: Any, wire_command: str) -> Event:
        tag, command = wire_command.split("|", 1)
        reply: str | None = state.pop("next_response", None)
        if reply is None and not state.get("drop_response"):
            if command.startswith(("set ", "password ", "setperm ")):
                fields = ctx.repeater_manager.command_parameters(command)
                state.update(fields)
                reply = "password now: topsecret" if command.startswith("password ") else ("OK - reboot to apply" if command.startswith("set radio ") else "OK")
            elif command == "get radio":
                reply = f"> {state['frequency']},{state['bandwidth']},{state['spreading_factor']},{str(state['coding_rate']).split('/')[-1]}"
            else:
                mapping = {"get name": "name", "get tx": "tx_power", "get lat": "latitude", "get lon": "longitude", "get owner.info": "owner_info", "get repeat": "repeat_enabled", "get advert.interval": "advert_interval", "get flood.advert.interval": "flood_advert_interval", "get allow.read.only": "allow_read_only"}
                value = state.get(mapping.get(command, ""), "")
                reply = "> " + ("on" if value is True else "off" if value is False else str(value))
        if reply is not None:
            assert handler.notify_command_response(REMOTE, {"text": f"{tag}|{reply}"})
        return Event(EventType.MSG_SENT, {})

    mc.commands.send_cmd = AsyncMock(side_effect=send_cmd)
    mc.commands.add_contact = AsyncMock(return_value=Event(EventType.OK, {}))
    return handler, ctx, mc, state


@pytest.mark.parametrize("params, expected", [
    ({"name": "New Name"}, {"name": "New Name"}),
    ({"owner_info": "Line1|Line2"}, {"owner_info": "Line1\nLine2"}),
    ({"latitude": -33.456789}, {"latitude": -33.456789}),
    ({"longitude": -70.123456}, {"longitude": -70.123456}),
    ({"tx_power": -9}, {"tx_power": -9}),
    ({"repeat": False}, {"repeat_enabled": False}),
    ({"advert_interval": 62}, {"advert_interval": 62}),
    ({"flood_advert_interval": 3}, {"flood_advert_interval": 3}),
    ({"guest_password": "guest-new"}, {"guest_password": "********"}),
    ({"new_password": "topsecret"}, {"admin_password": "********"}),
    ({"public_key": "ef" * 32, "permission": 3}, {"public_key": "ef" * 32, "permission": 3}),
])
async def test_each_remote_set_requires_remote_reply(remote_station: Any, params: dict[str, Any], expected: dict[str, Any]) -> None:
    handler, ctx, mc, state = remote_station
    result = await handler.handle({"action": "remote_repeater_set_config", "target_node": REMOTE, "params": params})
    assert result["status"] == "ok"
    assert result["applied"] == expected
    assert result["unconfirmed"] == {}
    assert len(mc.commands.send_cmd.await_args_list) == 1
    assert "topsecret" not in json.dumps(result)
    for call in ctx.mqtt.publish_safe.call_args_list:
        assert "topsecret" not in call.args[1]


@pytest.mark.parametrize("setter, query, field, value", [
    ({"name": "New Name"}, "get name", "name", "New Name"),
    ({"latitude": -12.125}, "get lat", "latitude", -12.125),
    ({"longitude": 45.25}, "get lon", "longitude", 45.25),
    ({"tx_power": -9}, "get tx", "tx_power", -9),
    ({"repeat": False}, "get repeat", "repeat_enabled", False),
    ({"owner_info": "Address"}, "get owner.info", "owner_info", "Address"),
    ({"advert_interval": 62}, "get advert.interval", "advert_interval", 62),
    ({"flood_advert_interval": 3}, "get flood.advert.interval", "flood_advert_interval", 3),
])
async def test_scalar_readback_and_registry_reload(remote_station: Any, tmp_path: Path, setter: dict[str, Any], query: str, field: str, value: Any) -> None:
    handler, ctx, mc, state = remote_station
    saved = await handler.handle({"action": "remote_repeater_set_config", "target_node": REMOTE, "params": setter})
    assert saved["status"] == "ok"
    read = await handler.handle({"action": query, "target_node": REMOTE})
    assert read["status"] == "ok"
    assert read["telemetry"][field] == value
    assert ctx.node_registry.get_node(REMOTE).to_dict()[field] == value
    path = tmp_path / "observed-remote.json"
    assert ctx.node_registry.save_to_file(path, force=True)
    restored = NodeRegistry()
    assert restored.load_from_file(path) == 1
    assert restored.get_node(REMOTE).to_dict()[field] == value


async def test_radio_saved_prefs_are_not_reported_as_active(remote_station: Any) -> None:
    handler, ctx, mc, state = remote_station
    fields = {"frequency": 868, "bandwidth": 125, "spreading_factor": 12, "coding_rate": "4/5"}
    result = await handler.handle({"action": "remote_repeater_set_config", "target_node": REMOTE, "params": fields})
    assert result["status"] == "ok"
    assert result["pending_reboot"] is True
    assert result["applied"] == {}
    assert result["saved"] == fields
    read = await handler.handle({"action": "get radio", "target_node": REMOTE})
    assert read["saved"] == fields
    assert read["radio_settings_source"] == "saved_preferences"
    assert ctx.node_registry.get_node(REMOTE).frequency == 915


async def test_batch_stops_at_error_and_keeps_only_confirmed_fields(remote_station: Any) -> None:
    handler, ctx, mc, state = remote_station
    original = mc.commands.send_cmd.side_effect
    count = 0

    async def second_fails(target: Any, wire_command: str) -> Event:
        nonlocal count
        count += 1
        if count == 2:
            state["next_response"] = "unknown config: lat"
        return await original(target, wire_command)

    mc.commands.send_cmd.side_effect = second_fails
    result = await handler.handle({"action": "remote_repeater_set_config", "target_node": REMOTE, "params": {"tx_power": 22, "latitude": 12, "name": "Unsent"}})
    assert result["status"] == "partial"
    assert result["applied"] == {"tx_power": 22}
    assert len(result["results"]) == 2
    assert mc.commands.send_cmd.await_count == 2
    assert ctx.node_registry.get_node(REMOTE).name == "Before"
    assert ctx.node_registry.get_node(REMOTE).latitude is None


async def test_local_dispatch_without_reply_does_not_apply(remote_station: Any) -> None:
    handler, ctx, mc, state = remote_station
    state["drop_response"] = True
    handler._repeater_executor._wait_for_repeater_response = AsyncMock(return_value=None)
    result = await handler.handle({"action": "remote_repeater_set_config", "target_node": REMOTE, "params": {"name": "Unconfirmed"}})
    assert result["status"] == "dispatched"
    assert result["applied"] == {}
    assert result["unconfirmed"] == {"name": "Unconfirmed"}
    assert "pending_reboot" not in result
    assert ctx.node_registry.get_node(REMOTE).name == "Before"


async def test_reply_requires_matching_tag_and_source(remote_station: Any) -> None:
    handler, ctx, mc, state = remote_station
    fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
    handler._waiters.register([REMOTE, REMOTE[:8]], fut)
    setattr(fut, "_command_tag", "af")  # noqa: B010
    assert not handler.notify_command_response(REMOTE, {"text": "ae|OK"})
    assert not handler.notify_command_response("ef" * 32, {"text": "af|OK"})
    assert not handler.notify_command_response(REMOTE, {"text": "OK"})
    assert not fut.done()
    assert handler.notify_command_response(REMOTE, {"text": "af|OK"})
    assert fut.result()["text"] == "OK"
    handler._waiters.unregister([REMOTE, REMOTE[:8]], fut)


@pytest.mark.parametrize("action,params", [
    ("set_name", {"name": "x" * 32}), ("set_name", {"name": "bad:name"}),
    ("set_name", {"name": "New\nreboot"}), ("set_owner_info", {"owner_info": "x" * 120}),
    ("set_tx_power", {"tx_power": 12.5}), ("set_tx_power", {"tx_power": True}),
    ("set_tx_power", {"tx_power": 31}), ("set_repeat", {"repeat": "bogus"}),
    ("set_lat", {"lat": float("nan")}), ("set_lon", {"lon": 180.1}),
    ("set_radio", {"freq": float("inf"), "bw": 125, "sf": 12, "cr": 5}),
    ("set_radio", {"freq": 915, "bw": 125, "sf": 11.5, "cr": 5}),
    ("set_advert_interval", {"advert_interval": 61}),
    ("set_flood_advert_interval", {"flood_advert_interval": 3.5}),
    ("set_password", {"password": "x" * 16}), ("set_guest_password", {"guest_password": "a\nb"}),
    ("setperm", {"public_key": "ef" * 31, "permission": 3}),
])
def test_invalid_remote_values_do_not_compile(action: str, params: dict[str, Any]) -> None:
    assert RepeaterManager().build_repeater_command_payload(action, params) is None


@pytest.mark.parametrize("command", ["set repeat garbage", "set name " + "x" * 32, "set tx 12.5", "set radio 915,125,11.5,5", "set advert.interval 61", "login plaintext"])
def test_raw_cli_cannot_bypass_configuration_validation(command: str) -> None:
    assert RepeaterManager().build_repeater_command_payload(command, {}) is None


async def test_sensitive_scalar_reply_never_becomes_telemetry(remote_station: Any) -> None:
    handler, ctx, mc, state = remote_station
    state["next_response"] = "> sf: 12, tx_power: 25"
    result = await handler.handle({"action": "get guest.password", "target_node": REMOTE})
    assert result["response"] == "********"
    assert "telemetry" not in result
    assert ctx.node_registry.get_node(REMOTE).tx_power == 20
    assert "sf:" not in json.dumps(result)


async def test_remote_empty_owner_readback_clears_previous_value(remote_station: Any) -> None:
    handler, ctx, mc, state = remote_station
    ctx.node_registry.add_or_update(REMOTE, NodeContactUpdate(owner_info="Old owner"))
    state["owner_info"] = ""
    result = await handler.handle({"action": "get owner.info", "target_node": REMOTE})
    assert result["status"] == "ok"
    assert result["telemetry"]["owner_info"] == ""
    assert ctx.node_registry.get_node(REMOTE).owner_info == ""


async def test_binary_owner_updates_the_same_observed_configuration(remote_station: Any) -> None:
    handler, ctx, mc, state = remote_station
    mc.commands.req_owner_sync = AsyncMock(return_value={"name": "Official Owner", "owner": "Info"})
    result = await handler.handle({"action": "req_owner", "target_node": REMOTE})
    assert result["status"] == "ok"
    assert result["telemetry"] == {"name": "Official Owner", "owner_info": "Info"}
    assert ctx.node_registry.get_node(REMOTE).owner_info == "Info"
    assert ctx.node_registry.get_node(REMOTE).name == "Official Owner"
    mc.commands.send_cmd.assert_not_awaited()


async def test_binary_status_decodes_official_units_and_persists_received_fields(remote_station: Any) -> None:
    handler, ctx, mc, state = remote_station
    mc.commands.req_status_sync = AsyncMock(return_value={"bat": 4100, "nb_sent": 42, "nb_recv": 58, "airtime": 1.25, "uptime": 120, "tx_queue_len": 0, "direct_dups": 2, "flood_dups": 3, "noise_floor": -110})
    result = await handler.handle({"action": "req_status", "target_node": REMOTE})
    assert result["status"] == "ok"
    telemetry = result["telemetry"]
    assert telemetry["voltage_v"] == 4.1
    assert telemetry["packets_sent"] == 42
    assert telemetry["packets_recv"] == 58
    assert telemetry["airtime_ms"] == 1250
    assert telemetry["queue_len"] == 0
    assert telemetry["duplicate_packets"] == 5
    assert ctx.node_registry.get_node(REMOTE).airtime_ms == 1250
    assert ctx.node_registry.get_node(REMOTE).packets_sent == 42
    assert ctx.node_registry.get_node(REMOTE).packets_recv == 58
    assert ctx.node_registry.get_node(REMOTE).queue_len == 0
    mc.commands.send_cmd.assert_not_awaited()


@pytest.mark.parametrize("maximum,allowed", [(None, True), (18, False), (22, True)])
async def test_remote_tx_limit_uses_only_a_reported_hardware_maximum(remote_station: Any, maximum: int | None, allowed: bool) -> None:
    handler, ctx, mc, state = remote_station
    if maximum is not None:
        ctx.node_registry.add_or_update(REMOTE, NodeContactUpdate(max_tx_power=maximum))
    result = await handler.handle({"action": "remote_repeater_set_config", "target_node": REMOTE, "params": {"tx_power": 22}})
    assert (result["status"] == "ok") is allowed
    assert mc.commands.send_cmd.await_count == (1 if allowed else 0)


@pytest.mark.parametrize("action", ["req_acl", "acl", "get_acl"])
async def test_acl_read_aliases_use_the_binary_table(remote_station: Any, action: str) -> None:
    handler, ctx, mc, state = remote_station
    mc.commands.req_acl_sync = AsyncMock(return_value=[{"public_key": "ef" * 32, "permissions": 3}])
    result = await handler.handle({"action": action, "target_node": REMOTE})
    assert result["status"] == "ok"
    assert result["acl_data"][0]["permissions"] == 3
    mc.commands.req_acl_sync.assert_awaited_once()
    mc.commands.send_cmd.assert_not_awaited()


@pytest.mark.parametrize("response", ["ERROR: failed", "Err - invalid params", "(ERR: bad)", "unknown config: x", "??: bad", "denied"])
def test_firmware_error_variants_never_parse_as_state(response: str) -> None:
    mgr = RepeaterManager()
    assert mgr.response_is_error(response)
    assert mgr.parse_command_response("get name", response) == {}


@pytest.mark.parametrize("value", ["ErrorNode", "Unknown Station", "SF12", "tx_power 25", "Battery 3000"])
def test_scalar_name_is_not_interpreted_as_error_or_telemetry(value: str) -> None:
    mgr = RepeaterManager()
    assert not mgr.response_is_error(f"> {value}")
    assert mgr.parse_command_response("get name", f"> {value}") == {"name": value}


@pytest.mark.parametrize("result", [None, False, {"status": "error", "code": "garbage"}, {"status": "partial", "applied": {"name": "Partial"}}, {"status": "unexpected"}])
async def test_remote_controller_rejects_non_success_envelopes(result: Any) -> None:
    from collections import deque

    ctx = ApiContext(SimpleNamespace(handle_admin=AsyncMock(return_value=result)), deque(), deque(), MagicMock())
    code, body = await RepeaterController(ctx).set_remote_config({"target_node": REMOTE, "params": {"name": "After"}})
    assert code >= 400
    assert body["status"] == code
