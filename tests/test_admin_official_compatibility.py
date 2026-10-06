"""Isolated administrative regressions using official SDK result contracts."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from meshcore import EventType
from meshcore.events import Event

from src.admin import (
    CliCommandExecutor,
    LocalConfigExecutor,
    RemoteRepeaterRequest,
    RepeaterAdminExecutor,
    TracerouteExecutor,
    WaiterRegistry,
)
from src.admin_handler import AdminContext
from src.contact_manager import NodeContactUpdate, NodeRegistry


def context() -> tuple[AdminContext, Any, dict[str, Any]]:
    commands = SimpleNamespace(**{name: AsyncMock(return_value=Event(EventType.OK, {})) for name in (
        "set_name", "set_coords", "set_tx_power", "set_radio", "set_time", "get_time", "get_tuning",
        "set_tuning", "set_other_params_from_infos", "set_devicepin", "set_path_hash_mode", "set_custom_var",
        "set_autoadd_config", "send_advert", "send_cmd", "send_trace", "add_contact", "send_login_sync",
        "req_status_sync",
    )})
    mc = SimpleNamespace(commands=commands, self_info={"public_key": "ab" * 32, "name": "Before"}, _contacts={})
    registry = NodeRegistry()
    registry.set_local_pubkey("ab" * 32)
    manager = MagicMock()
    manager.check_airtime_cooldown.return_value = (True, 0)
    manager.check_traceroute_cooldown.return_value = (True, 0)
    manager.build_repeater_command_payload.side_effect = lambda action, data: action
    ctx = AdminContext(mc_provider=lambda: mc, node_registry=registry, repeater_manager=manager,
                       mqtt=MagicMock(), execute_tx=AsyncMock(return_value={"status": "dispatched"}))
    return ctx, mc, {"name": "Before", "public_key": "ab" * 32, "frequency": 915.0}


def local_executor(ctx: AdminContext, cfg: dict[str, Any]) -> LocalConfigExecutor:
    return LocalConfigExecutor(ctx, cfg, time.time(), lambda *args: None)


def cli_executor(ctx: AdminContext, cfg: dict[str, Any]) -> CliCommandExecutor:
    return CliCommandExecutor(ctx, cfg, lambda: dict(cfg), lambda *args, **kwargs: None,
                              AsyncMock(), AsyncMock(), time.time())


def repeater_executor(ctx: AdminContext, cfg: dict[str, Any]) -> RepeaterAdminExecutor:
    return RepeaterAdminExecutor(ctx, WaiterRegistry({}, {}), lambda *args: None,
                                lambda target, length: target,
                                AsyncMock(return_value={"text": "reply"}), lambda: cfg)


@pytest.mark.parametrize("params,command", [({"name": "After"}, "set_name"), ({"frequency": 916.0}, "set_radio"), ({"pin": 123456}, "set_devicepin")])
async def test_local_configuration_does_not_commit_rejected_hardware(params: dict[str, Any], command: str) -> None:
    ctx, mc, cfg = context()
    getattr(mc.commands, command).return_value = Event(EventType.ERROR, {"error_code": 2})
    before = dict(cfg)
    result = await local_executor(ctx, cfg).set_local_config({"params": params}, {}, mc)
    assert result["status"] == "error"
    assert cfg == before
    assert result["applied"] == {}


async def test_rtc_error_does_not_become_confirmed_device_time() -> None:
    ctx, mc, cfg = context()
    mc.commands.set_time.return_value = Event(EventType.ERROR, {"reason": "timeout"})
    result = await local_executor(ctx, cfg).sync_device_clock(1700000000)
    assert result["status"] == "error"
    assert "device_epoch_time" not in cfg


async def test_official_battery_payload_level_is_used() -> None:
    ctx, mc, cfg = context()
    mc.commands.get_bat = AsyncMock(return_value=Event(EventType.BATTERY, {"level": 4100}))
    await local_executor(ctx, cfg)._query_hardware_device_and_battery(mc)
    assert cfg["battery_mv"] == 4100
    assert cfg["voltage"] == 4.1


async def test_repeat_string_false_is_encoded_as_zero() -> None:
    ctx, mc, cfg = context()
    # A repeat-only write must use the complete, device-reported radio baseline.
    mc.self_info.update({"radio_freq": 915.0, "bw": 125.0, "sf": 7, "cr": 5})
    result = await local_executor(ctx, cfg).set_local_config({"params": {"repeat": "false"}}, {}, mc)
    assert result["status"] == "ok"
    mc.commands.set_radio.assert_awaited_once_with(915.0, 125.0, 7, 5, 0)
    assert mc.commands.set_radio.await_args.args[-1] == 0


async def test_cli_tuning_calls_the_official_sdk_method() -> None:
    ctx, mc, cfg = context()
    mc.commands.get_tuning.return_value = Event(EventType.TUNING_PARAMS, {"rx_delay": 1000, "airtime_factor": 2000})
    result = await cli_executor(ctx, cfg).execute("tuning", {}, mc)
    mc.commands.get_tuning.assert_awaited_once()
    assert "Base RX: 1.0 (adimensional)" in result["result"]
    assert "2.0x" in result["result"]


async def test_cli_unknown_command_is_not_reported_as_processed_by_firmware() -> None:
    ctx, mc, cfg = context()
    result = await cli_executor(ctx, cfg).execute("does_not_exist", {}, mc)
    assert result["status"] == "error"


async def test_cli_clock_error_is_propagated() -> None:
    ctx, mc, cfg = context()
    mc.commands.set_time.return_value = Event(EventType.ERROR, {"error_code": 2})
    result = await cli_executor(ctx, cfg).execute("sync_clock", {}, mc)
    assert result["status"] == "error"
    assert "device_epoch_time" not in cfg


async def test_client_cannot_become_repeater_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx, mc, cfg = context()
    ctx.node_registry.add_or_update("cd" * 32, NodeContactUpdate(name="R-REPEATER", role="CLIENT"))
    # Supply the authoritative role directly; registry classification is audited separately.
    monkeypatch.setattr(ctx.node_registry, "list_nodes", lambda: [{"public_key": "cd" * 32, "name": "R-REPEATER", "role": "CLIENT"}])
    result = await repeater_executor(ctx, cfg).execute(RemoteRepeaterRequest({}, "reboot", "req", "cd" * 32, mc=mc))
    assert result["status"] == "error"
    mc.commands.send_cmd.assert_not_awaited()


@pytest.mark.parametrize("action", ["remote_repeater_set_config", "refresh_telemetry"])
async def test_all_remote_entrypoints_reject_local_identity(action: str) -> None:
    ctx, mc, cfg = context()
    executor = repeater_executor(ctx, cfg)
    executor._execute_batch_config = AsyncMock(return_value={"status": "ok"})
    executor._execute_batch_telemetry_query = AsyncMock(return_value={"status": "ok"})
    result = await executor.execute(RemoteRepeaterRequest({}, action, "req", "ab" * 32, mc=mc))
    assert result["status"] == "error"
    executor._execute_batch_config.assert_not_awaited()
    executor._execute_batch_telemetry_query.assert_not_awaited()


async def test_repeater_sdk_error_never_falls_back_to_chat() -> None:
    ctx, mc, cfg = context()
    mc.commands.send_cmd.return_value = Event(EventType.ERROR, {"error_code": 2})
    with pytest.raises(RuntimeError):
        await repeater_executor(ctx, cfg)._send_rf_command(mc, "cd" * 32, "reboot", "cd" * 32, "req")
    ctx.execute_tx.assert_not_awaited()


async def test_repeater_contact_error_does_not_cache_fabricated_success() -> None:
    ctx, mc, cfg = context()
    mc.commands.add_contact.return_value = Event(EventType.ERROR, {"error_code": 2})
    with pytest.raises(RuntimeError):
        await repeater_executor(ctx, cfg)._ensure_radio_contact(mc, "cd" * 32, "Relay")
    assert mc._contacts == {}


async def test_trace_hash_byte_is_not_padded_to_another_node() -> None:
    ctx, mc, cfg = context()
    executor = TracerouteExecutor(ctx, lambda: cfg, lambda *args: None)
    assert executor._format_trace_hops(["ab", "cd"]) == ("ab,cd", 0)


@pytest.mark.parametrize("response", [None, Event(EventType.ERROR, {"error_code": 2})])
async def test_trace_failure_does_not_report_measured_route(response: Any) -> None:
    ctx, mc, cfg = context()
    mc.commands.send_trace.return_value = response
    result = await TracerouteExecutor(ctx, lambda: cfg, lambda *args: None).execute({"path": "ab,cd"}, "traceroute", "cd" * 32, {}, mc)
    assert result["status"] == "error"
    assert not result.get("hops_breakdown")


async def test_binary_request_cannot_skip_requested_authentication() -> None:
    ctx, mc, cfg = context()
    mc.commands.req_status_sync.return_value = {"bat": 4100}
    mc.commands.send_login_sync.return_value = Event(EventType.LOGIN_FAILED, {})
    result = await repeater_executor(ctx, cfg).execute(RemoteRepeaterRequest({}, "req_status", "req", "cd" * 32, password="secret", mc=mc))
    assert result["status"] == "error"
    mc.commands.req_status_sync.assert_not_awaited()


async def test_binary_request_respects_existing_airtime_cooldown() -> None:
    ctx, mc, cfg = context()
    ctx.repeater_manager.check_airtime_cooldown.return_value = (False, 30)
    ctx.repeater_manager.build_cooldown_error_response.return_value = {"status": "error", "reason": "cooldown"}
    mc.commands.req_status_sync.return_value = {"bat": 4100}
    result = await repeater_executor(ctx, cfg).execute(RemoteRepeaterRequest({}, "req_status", "req", "cd" * 32, mc=mc))
    assert result["status"] == "error"
    mc.commands.req_status_sync.assert_not_awaited()


async def test_cli_set_preserves_name_case() -> None:
    ctx, mc, cfg = context()
    executor = cli_executor(ctx, cfg)
    executor._handle_set_local_config = local_executor(ctx, cfg).set_local_config
    result = await executor.execute("set name Casa Norte", {}, mc)
    assert result.get("status") != "error"
    assert cfg["name"] == "Casa Norte"


async def test_cli_set_cannot_overwrite_firmware_failure_with_success() -> None:
    ctx, mc, cfg = context()
    executor = cli_executor(ctx, cfg)
    executor._handle_set_local_config = local_executor(ctx, cfg).set_local_config
    mc.commands.set_name.return_value = Event(EventType.ERROR, {})
    result = await executor.execute("set name After", {}, mc)
    assert result["status"] == "error"
    assert "✓" not in result["result"]


async def test_binary_timeout_does_not_send_fallback_radio_command() -> None:
    ctx, mc, cfg = context()
    mc.commands.req_status_sync.return_value = None
    result = await repeater_executor(ctx, cfg).execute(RemoteRepeaterRequest({}, "req_status", "req", "cd" * 32, mc=mc))
    assert result["status"] == "error"
    mc.commands.send_cmd.assert_not_awaited()


@pytest.mark.parametrize("payload", [{"pubkey_prefix": "ef" * 6, "is_admin": True}, {"pubkey_prefix": "cd" * 6, "is_admin": False}])
async def test_remote_login_requires_matching_identity_and_admin_permission(payload: dict[str, Any]) -> None:
    ctx, mc, cfg = context()
    mc.commands.send_login_sync.return_value = Event(EventType.LOGIN_SUCCESS, payload)
    result = await repeater_executor(ctx, cfg).execute(RemoteRepeaterRequest({}, "req_status", "req", "cd" * 32, password="secret", mc=mc))
    assert result["status"] == "error"
    mc.commands.req_status_sync.assert_not_awaited()


async def test_failed_device_read_does_not_pollute_custom_variables() -> None:
    ctx, mc, cfg = context()
    cfg["custom_vars"] = {"mode": "before"}
    mc.commands.get_custom_vars = AsyncMock(return_value=Event(EventType.ERROR, {"reason": "timeout"}))
    result = await local_executor(ctx, cfg).get_custom_vars()
    assert cfg["custom_vars"] == {"mode": "before"}
    assert result != {"reason": "timeout"}


def test_invalid_trace_path_cannot_become_an_empty_radio_route() -> None:
    ctx, mc, cfg = context()
    with pytest.raises(ValueError):
        TracerouteExecutor(ctx, lambda: cfg, lambda *args: None)._format_trace_hops(["missing-node"])


async def test_trace_snr_from_final_local_receiver_is_not_target_snr() -> None:
    ctx, mc, cfg = context()
    hops = TracerouteExecutor(ctx, lambda: cfg, lambda *args: None)._build_hops_breakdown(["cd"], "cd" * 32, 10.0,
        {"path": [{"hash": "cd", "snr": 3.0}, {"snr": -7.0}]})
    assert hops[0]["snr"] == -7.0
    assert hops[1]["snr"] == 3.0
    assert hops[-1]["snr"] is None


async def test_ping_zero_restores_existing_contact_route_and_flags() -> None:
    ctx, mc, cfg = context()
    ctx.repeater_manager.check_ping_cooldown.return_value = (True, 0)
    contact = {"public_key": "cd" * 32, "adv_name": "Relay", "type": 2, "flags": 1,
               "out_path": "beef", "out_path_len": 1, "out_path_hash_mode": 1,
               "adv_lat": 0.0, "adv_lon": 0.0, "last_advert": 1}
    mc._contacts[contact["public_key"]] = dict(contact)
    executor = repeater_executor(ctx, cfg)
    executor._resolve_target = lambda target, length: dict(contact)
    result = await executor.execute(RemoteRepeaterRequest({}, "ping_zero", "req", contact["public_key"], mc=mc))
    assert result["status"] == "ok"
    assert mc.commands.add_contact.await_args_list[0].args[0]["flags"] == 1
    assert mc._contacts[contact["public_key"]] == contact
    assert mc.commands.add_contact.await_args_list[-1].args[0] == contact


async def test_repeater_registry_broadcast_completes_in_request_lifecycle() -> None:
    ctx, mc, cfg = context()
    ctx.web_server = SimpleNamespace(broadcast_event=AsyncMock())
    mc.commands.req_telemetry_sync = AsyncMock(return_value={"temperature_c": 20.0})
    result = await repeater_executor(ctx, cfg).execute(RemoteRepeaterRequest({}, "req_telemetry", "req", "cd" * 32, mc=mc))
    assert result["status"] == "ok"
    ctx.web_server.broadcast_event.assert_awaited_once()


def test_unknown_local_telemetry_is_unavailable_and_retains_valid_snapshot() -> None:
    ctx, mc, cfg = context()
    result = local_executor(ctx, cfg).get_local_config()
    assert result["battery_mv"] is None
    assert result["temperature_c"] is None
    assert result["power_source"] == "desconocida"
    cfg.update({"battery_mv": 4120, "temperature_c": 22.4})
    result = local_executor(ctx, cfg).get_local_config()
    assert result["battery_mv"] == 4120
    assert result["temperature_c"] == 22.4


@pytest.mark.parametrize("command", ["version", "board", "battery"])
async def test_cli_does_not_invent_unavailable_hardware_information(command: str) -> None:
    ctx, mc, cfg = context()
    result = await cli_executor(ctx, cfg).execute(command, {}, mc)
    text = result["result"]
    assert any(word in text.lower() for word in ("desconoc", "sin lectura", "no disponible"))
    assert "v1.6.0" not in text and "2026-08-20" not in text
    assert "SX1262" not in text and "5.00 V" not in text
