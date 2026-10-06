"""Regressions for remaining administrative audit findings; isolated SDK only."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from meshcore.events import Event, EventType

from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.repeater_manager import RepeaterManager

LOCAL = "ab" * 32
REMOTE = "cd" * 32


def station(role="REPEATER"):
    registry = NodeRegistry()
    registry.set_local_pubkey(LOCAL)
    registry.add_or_update(REMOTE, NodeContactUpdate(name="Audit", role=role))
    mc = SimpleNamespace(self_info={"public_key": LOCAL}, contacts={REMOTE: {"public_key": REMOTE, "type": 2}},
                         commands=SimpleNamespace())
    ctx = AdminContext(lambda: mc, registry, RepeaterManager(min_cmd_interval_s=0, min_telemetry_interval_s=0),
                       MagicMock(), AsyncMock())
    return AdminCommandHandler(ctx), mc, registry


@pytest.mark.asyncio
async def test_remote_clock_uses_remote_payload_not_echo_tag():
    handler, mc, registry = station()
    mc.commands.req_basic_sync = AsyncMock(return_value={"tag": (1704067200).to_bytes(4, "little").hex(),
        "data": (1791072000).to_bytes(4, "little").hex() + "00"})
    result = await handler.handle({"action": "req_clock", "target_node": REMOTE})
    assert result["clock"] == "00:00 - 04/10/2026 UTC"
    assert registry.get_node(REMOTE).clock == result["clock"]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"tag": "00e10b5e"}, {"data": "zzzzzzzz"}, {"data": "01"}, {"data": "00e10b5eZ"}])
async def test_remote_clock_rejects_invalid_data(payload):
    handler, mc, registry = station()
    mc.commands.req_basic_sync = AsyncMock(return_value=payload)
    result = await handler.handle({"action": "req_clock", "target_node": REMOTE})
    assert result["status"] == "error"
    assert registry.get_node(REMOTE).clock is None


@pytest.mark.asyncio
@pytest.mark.parametrize("input_data,method", [({"action": "set_autoadd_config", "flags": True}, "set_autoadd_config"),
    ({"action": "set_path_hash_mode", "mode": 1.9}, "set_path_hash_mode"),
    ({"action": "set_autoadd_config", "flags": 1, "max_hops": True}, "set_autoadd_config")])
async def test_original_input_types_are_validated(input_data, method):
    handler, mc, _ = station()
    command = AsyncMock(return_value=Event(EventType.OK, {}))
    setattr(mc.commands, method, command)
    result = await handler.handle(input_data)
    assert result["status"] == "error"
    assert result["code"] == 422
    command.assert_not_awaited()


@pytest.mark.asyncio
async def test_custom_vars_prevalidate_entire_batch():
    handler, mc, _ = station()
    mc.commands.set_custom_var = AsyncMock(return_value=Event(EventType.OK, {}))
    result = await handler.handle({"action": "set_custom_vars", "vars": {"gps": "0", "bad,key": "1"}})
    assert result["status"] == "error"
    mc.commands.set_custom_var.assert_not_awaited()
    assert not handler._local_config.get("custom_vars")


@pytest.mark.asyncio
async def test_custom_vars_reports_confirmed_partial_on_sdk_rejection():
    handler, mc, _ = station()
    mc.commands.set_custom_var = AsyncMock(side_effect=[Event(EventType.OK, {}), Event(EventType.ERROR, {})])
    result = await handler.handle({"action": "set_custom_vars", "vars": {"gps": "0", "tz": "1"}})
    assert result["status"] == "partial"
    assert result["applied"] == {"custom_vars": {"gps": "0"}}
    assert handler._local_config["custom_vars"] == {"gps": "0"}


@pytest.mark.asyncio
async def test_refresh_without_responses_is_error(monkeypatch):
    handler, mc, _ = station()
    mc.commands.send_cmd = AsyncMock(return_value=Event(EventType.MSG_SENT, {}))
    handler._repeater_executor._wait_for_repeater_response = AsyncMock(return_value=None)
    monkeypatch.setattr("src.admin.repeater_executor.asyncio.sleep", AsyncMock())
    result = await handler.handle({"action": "refresh_telemetry", "target_node": REMOTE})
    assert result["status"] == "error"
    assert result["telemetry"] == {}
    assert "get pwrmgt.bootmv" not in result["dispatched"]


@pytest.mark.asyncio
@pytest.mark.parametrize("texts,status,confirmed", [(["v1", None, None, None], "partial", 1),
    (["v1", "12:00", "915,250,11,5", "5%"], "ok", 4),
    (["ERROR", None, None, None], "error", 0)])
async def test_refresh_status_depends_on_real_responses(monkeypatch, texts, status, confirmed):
    handler, mc, _ = station()
    mc.commands.send_cmd = AsyncMock(return_value=Event(EventType.MSG_SENT, {}))
    handler._repeater_executor._wait_for_repeater_response = AsyncMock(side_effect=[{"text": text} if text else None for text in texts])
    monkeypatch.setattr("src.admin.repeater_executor.asyncio.sleep", AsyncMock())
    result = await handler.handle({"action": "refresh_telemetry", "target_node": REMOTE})
    assert result["status"] == status
    assert result["confirmed_count"] == confirmed
    assert result["requested_count"] == 4


@pytest.mark.asyncio
async def test_refresh_keeps_live_battery_and_reports_binary_confirmation(monkeypatch):
    handler, mc, registry = station()
    mc.commands.send_cmd = AsyncMock(return_value=Event(EventType.MSG_SENT, {}))
    mc.commands.req_status_sync = AsyncMock(return_value={"bat": 3900})
    handler._repeater_executor._wait_for_repeater_response = AsyncMock(return_value=None)
    monkeypatch.setattr("src.admin.repeater_executor.asyncio.sleep", AsyncMock())
    result = await handler.handle({"action": "refresh_telemetry", "target_node": REMOTE})
    assert result["status"] == "partial"
    assert result["binary_responses"] == ["req_status_sync"]
    assert result["confirmed_count"] == 1
    assert registry.get_node(REMOTE).voltage_v == 3.9


@pytest.mark.asyncio
@pytest.mark.parametrize("reading", [0, 100, 3900])
async def test_remote_battery_explicit_millivolts(reading):
    handler, mc, _ = station()
    mc.commands.req_status_sync = AsyncMock(return_value={"bat": reading})
    result = await handler.handle({"action": "get bat", "target_node": REMOTE})
    assert result["status"] == "ok"
    assert result["telemetry"]["voltage_v"] == reading / 1000
    assert result["telemetry"]["battery_pct_source"] == "voltage_estimate"
    if reading <= 100:
        assert result["telemetry"]["battery_pct"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("reading", [None, True, -1, 65536, "3900"])
async def test_remote_battery_invalid_reading_not_stored(reading):
    handler, mc, registry = station()
    mc.commands.req_status_sync = AsyncMock(return_value={"bat": reading})
    result = await handler.handle({"action": "get bat", "target_node": REMOTE})
    assert result["status"] == "error"
    assert registry.get_node(REMOTE).voltage_v is None


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["CLIENT", "ROOM", "SENSOR"])
async def test_refresh_non_repeater_sends_no_cli(role):
    handler, mc, registry = station(role)
    mc.commands.send_cmd = AsyncMock(return_value=Event(EventType.MSG_SENT, {}))
    result = await handler.handle({"action": "refresh_telemetry", "target_node": REMOTE})
    assert result["status"] == "error"
    mc.commands.send_cmd.assert_not_awaited()
    assert registry.get_node(REMOTE).role == role


@pytest.mark.asyncio
async def test_local_clock_rejection_is_error():
    handler, mc, _ = station()
    mc.commands.get_time = AsyncMock(return_value=Event(EventType.ERROR, {}))
    result = await handler.handle({"action": "clock"})
    assert result["status"] == "error"
    assert "Hora del Nodo:" not in result["result"]


@pytest.mark.asyncio
async def test_local_clock_accepts_payload_dict():
    handler, mc, _ = station()
    mc.commands.get_time = AsyncMock(return_value={"time": 1704067200})
    result = await handler.handle({"action": "clock"})
    assert "1704067200" in result["result"]


@pytest.mark.asyncio
async def test_local_acl_does_not_invent_permissions():
    handler, _, _ = station()
    result = await handler.handle({"action": "acl"})
    assert result["status"] == "error"
    assert result["unsupported"] is True
    assert "ADMIN / OPERATOR" not in result["result"]


@pytest.mark.asyncio
async def test_tuning_uses_dimensionless_base():
    handler, _, _ = station()
    handler._local_config["rx_delay"] = 10
    result = await handler.handle({"action": "tuning"})
    assert "Base RX: 10" in result["result"]
    assert "10s" not in result["result"]


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["set tx abc", "set freq xyz", "set sf abc", "set bw abc", "set cr nonsense",
    "set radio 915 250", "set tuning 10", "set pin abc", "set coords abc,1", "set coords 1", "set tx",
    "set radio 915 250 abc 5", "set tuning x 1", "set repeat nonsense"])
async def test_invalid_cli_reports_error_and_no_write(command):
    handler, mc, _ = station()
    result = await handler.handle({"action": command})
    assert result["status"] == "error"
    assert result["code"] == 422
    assert vars(mc.commands) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("frequency,bandwidth", [(915.0009, 250.0009), (512.002, 62.501), (915.999999, 500)])
async def test_radio_reports_effective_wire_precision(frequency, bandwidth):
    handler, mc, _ = station()
    wire = {}
    async def apply(freq, bw, sf, cr, repeat):
        wire.update(frequency=int(freq * 1000) / 1000, bandwidth=int(bw * 1000) / 1000)
        return Event(EventType.OK, {})
    mc.commands.set_radio = AsyncMock(side_effect=apply)
    result = await handler.handle({"action": "set_local_config", "params": {
        "frequency": frequency, "bandwidth": bandwidth, "spreading_factor": 11, "coding_rate": 5}})
    assert result["status"] == "ok"
    assert result["applied"]["frequency"] == wire["frequency"]
    assert result["applied"]["bandwidth"] == wire["bandwidth"]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["bat", "get_bat", "get bat", "battery", "GET BAT"])
async def test_remote_battery_reads_current_status(action):
    handler, mc, registry = station()
    mc.commands.req_status_sync = AsyncMock(return_value={"bat": 3875})
    mc.commands.send_cmd = AsyncMock()
    result = await handler.handle({"action": action, "target_node": REMOTE})
    assert result["status"] == "ok"
    assert result["telemetry"]["voltage_v"] == 3.875
    assert result["telemetry"]["battery_mv"] == 3875
    assert registry.get_node(REMOTE).voltage_v == 3.875
    mc.commands.req_status_sync.assert_awaited_once()
    mc.commands.send_cmd.assert_not_awaited()


@pytest.mark.asyncio
async def test_remote_battery_timeout_does_not_use_boot_voltage():
    handler, mc, _ = station()
    mc.commands.req_status_sync = AsyncMock(return_value=None)
    mc.commands.send_cmd = AsyncMock()
    result = await handler.handle({"action": "get bat", "target_node": REMOTE})
    assert result["status"] == "error"
    mc.commands.send_cmd.assert_not_awaited()


@pytest.mark.parametrize("text", ["3900", "> 3900 mV"])
def test_boot_voltage_is_not_current_battery(text):
    manager = RepeaterManager()
    parsed = manager.parse_command_response("get pwrmgt.bootmv", text)
    assert "voltage_v" not in parsed
    assert "battery_pct" not in parsed
    assert parsed["boot_voltage_mv"] == 3900


def test_unused_repeater_transmit_callback_is_deprecated_without_invocation():
    callback = MagicMock()
    with pytest.warns(DeprecationWarning, match="not invoked"):
        manager = RepeaterManager(transmit_callback=callback)
    manager.build_repeater_command_payload("ver", {})
    callback.assert_not_called()
