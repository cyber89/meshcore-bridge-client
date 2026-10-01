"""Regression contracts for recent ACK, channel, RF budget and authentication fixes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from meshcore.events import EventType

from src.admin import RemoteRepeaterRequest, RepeaterAdminExecutor, WaiterRegistry
from src.admin_handler import AdminContext
from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.rate_limiter import AirtimeTracker, LoRaRadioConfig, estimate_lora_airtime_ms
from src.repeater_manager import RepeaterManager
from src.routers.base import RxMeta
from src.routers.repeater_handler import RepeaterAdminHandler
from src.sensor_decoder import format_telemetry_summary
from src.serial.sdk_adapter import MeshcoreSDKAdapter


def ack_meta() -> RxMeta:
    return RxMeta("ACK", "ACK", "", "", "", 0, 0, None, None, 0, False)


@pytest.mark.parametrize("code", [None, "", " ", 0, "0", "00000000", "0x00000000", b"\x00" * 4])
async def test_null_ack_cannot_publish_delivery(code: Any) -> None:
    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge._pending_acks = {}
    context = SimpleNamespace(
        mqtt=MagicMock(), web_server=SimpleNamespace(broadcast_event=AsyncMock()),
        background_tasks=set(), node_registry=NodeRegistry(), bridge=bridge,
    )
    handler = RepeaterAdminHandler()
    assert await handler.handle(SimpleNamespace(_ctx=context), {"event_type": "ack", "ack_code": code}, ack_meta(), None)
    context.mqtt.publish_safe.assert_not_called()
    context.web_server.broadcast_event.assert_not_called()
    assert not context.background_tasks


@pytest.mark.parametrize("code", ["1234abcd", "0x1234ABCD", 0xCDAB3412, bytes.fromhex("1234abcd")])
async def test_valid_ack_correlates_real_pending_message(code: Any) -> None:
    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge._pending_acks = {}
    bridge.register_pending_ack("1234abcd", "request-17")
    context = SimpleNamespace(mqtt=MagicMock(), web_server=None, node_registry=NodeRegistry(), bridge=bridge)
    assert await RepeaterAdminHandler().handle(
        SimpleNamespace(_ctx=context), {"event_type": "ack", "ack_code": code, "trip_time_ms": 42}, ack_meta(), None,
    )
    event = json.loads(context.mqtt.publish_safe.call_args.args[1])
    assert event["msg_id"] == "request-17"
    assert event["ack_code"] == "1234abcd"
    assert event["trip_time_ms"] == 42


@pytest.mark.parametrize("code", ["", "0", "00000000", "0x00000000"])
def test_pending_table_rejects_zero_ack(code: str) -> None:
    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge._pending_acks = {}
    bridge.register_pending_ack(code, "must-not-be-delivered")
    assert not bridge._pending_acks
    assert bridge.resolve_pending_ack(code) is None


@pytest.mark.parametrize("secret", [None, "", "00" * 16, bytes(16)])
async def test_empty_channel_slot_never_reaches_rx(secret: Any) -> None:
    adapter = MeshcoreSDKAdapter(port="TEST_UNUSED")
    adapter.mc = SimpleNamespace(channels={1: {"name": "stale"}})
    adapter.rx_callback = MagicMock()
    await adapter._handle_channel_info(SimpleNamespace(payload={"channel_idx": 1, "channel_name": "", "channel_secret": secret}))
    assert 1 not in adapter.mc.channels
    adapter.rx_callback.assert_not_called()


async def test_configured_channel_preserves_secret_only_inside_sdk_cache() -> None:
    secret = bytes.fromhex("123456789abcdef0123456789abcdef0")
    adapter = MeshcoreSDKAdapter(port="TEST_UNUSED")
    adapter.mc = SimpleNamespace(channels={})
    adapter.rx_callback = MagicMock()
    await adapter._handle_channel_info(SimpleNamespace(payload={
        "channel_idx": 1, "channel_name": "Private", "channel_secret": secret, "channel_hash": "a5",
    }))
    assert adapter.mc.channels[1]["psk"] == secret.hex()
    payload = adapter.rx_callback.call_args.args[0]
    assert payload["is_local"] is True
    assert payload["event_type"] == "channel_info"
    assert "channel_secret" not in payload and "psk" not in payload and "secret" not in payload
    assert secret.hex() not in json.dumps(payload)


async def test_channel_info_is_not_rf_telemetry(virtual_bridge: MeshCoreBridge, caplog: pytest.LogCaptureFixture) -> None:
    before = virtual_bridge.rx_count
    packets_before = virtual_bridge.packet_buffer.get_packets()
    secret = "123456789abcdef0123456789abcdef0"
    virtual_bridge.mqtt.publish_safe.reset_mock()
    virtual_bridge.on_mesh_event(SimpleNamespace(type=EventType.CHANNEL_INFO, payload={
        "channel_idx": 1, "channel_name": "Private", "channel_secret": secret, "channel_hash": "a5",
    }))
    await asyncio.sleep(0)
    assert virtual_bridge.rx_count == before
    assert virtual_bridge.packet_buffer.get_packets() == packets_before
    assert secret not in caplog.text
    assert not any(secret in str(call) for call in virtual_bridge.mqtt.publish_safe.call_args_list)


def test_telemetry_summary_does_not_expose_channel_credentials() -> None:
    secret = "123456789abcdef0123456789abcdef0"
    summary = format_telemetry_summary({"channel_secret": secret, "psk": secret, "secret": secret, "channel_name": "Private"})
    assert secret not in summary
    assert "channel_secret" not in summary and "psk" not in summary


def test_airtime_budget_and_cutoff_survive_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1_000_000.0]
    monkeypatch.setattr("src.rate_limiter.time.time", lambda: now[0])
    path = str(tmp_path / "budget.json")
    tracker = AirtimeTracker(history_file=path, duty_cycle_limit_pct=1.0)
    tracker.record_tx(36000.0)
    tracker.update_channel_utilization(36.0)
    tracker.save_history(sync=True)
    restored = AirtimeTracker(history_file=path, duty_cycle_limit_pct=1.0)
    assert restored.get_stats()["hourly_used_ms"] == 36000.0
    assert restored.get_stats()["is_throttled"] is True
    assert restored._cutoff_active is True
    restored.update_channel_utilization(32.0)
    assert restored._cutoff_active is True
    restored.update_channel_utilization(29.0)
    assert restored._cutoff_active is False
    now[0] += 3601
    assert restored.get_stats()["hourly_used_ms"] == 0
    assert restored.get_stats()["is_throttled"] is False


@pytest.mark.parametrize("sf,bw,expected", [(7, 125.0, 71.936), (10, 62.5, 1069.056)])
def test_airtime_semtech_reference_points(sf: int, bw: float, expected: float) -> None:
    assert estimate_lora_airtime_ms(32, LoRaRadioConfig(sf=sf, bw_khz=bw, cr=5)) == pytest.approx(expected, abs=0.005)


@pytest.fixture
def auth_executor() -> tuple[RepeaterAdminExecutor, AdminContext, Any, NodeRegistry]:
    registry = NodeRegistry()
    registry.add_or_update("cd" * 32, NodeContactUpdate(name="Repeater Before", role="REPEATER"))
    registry.set_local_pubkey("ab" * 32)
    commands = SimpleNamespace(send_login_sync=AsyncMock(), send_login=AsyncMock(), send_cmd=AsyncMock())
    mc = SimpleNamespace(commands=commands)
    context = AdminContext(
        mc_provider=lambda: mc, node_registry=registry, repeater_manager=RepeaterManager(min_cmd_interval_s=0, min_telemetry_interval_s=0),
        mqtt=MagicMock(), execute_tx=AsyncMock(return_value={"status": "dispatched"}),
    )
    executor = RepeaterAdminExecutor(
        ctx=context, waiters=WaiterRegistry(cmd_waiters={}, ping_waiters={}), publish_safe=MagicMock(),
        resolve_target=lambda target, length: target, wait_for_repeater_response=AsyncMock(return_value={}),
        get_local_config=lambda: {"public_key": "ab" * 32},
    )
    return executor, context, mc, registry


@pytest.mark.parametrize("event_type", [EventType.ERROR, EventType.LOGIN_FAILED, EventType.MSG_SENT, None])
async def test_only_login_success_authenticates(auth_executor: Any, event_type: Any) -> None:
    executor, context, mc, registry = auth_executor
    mc.commands.send_login_sync.return_value = SimpleNamespace(type=event_type, payload={}) if event_type else None
    result = await executor.execute(RemoteRepeaterRequest(admin_data={}, action="login", req_id="auth", target_node="cd" * 32, password="secret", mc=mc))
    assert result["authenticated"] is False
    assert result["status"] == "error"
    context.execute_tx.assert_not_awaited()
    mc.commands.send_cmd.assert_not_awaited()


@pytest.mark.parametrize("event_type", [EventType.ERROR, EventType.LOGIN_FAILED, EventType.MSG_SENT, None])
async def test_batch_rejected_auth_cannot_send_or_mutate(auth_executor: Any, event_type: Any) -> None:
    executor, context, mc, registry = auth_executor
    mc.commands.send_login_sync.return_value = SimpleNamespace(type=event_type, payload={}) if event_type else None
    result = await executor.execute(RemoteRepeaterRequest(
        admin_data={"params": {"name": "Forbidden Name", "tx_power": 22}}, action="remote_repeater_set_config", req_id="batch", target_node="cd" * 32, password="secret", mc=mc,
    ))
    assert result["status"] == "error"
    context.execute_tx.assert_not_awaited()
    mc.commands.send_cmd.assert_not_awaited()
    assert registry.get_by_key_or_prefix("cd" * 32).name == "Repeater Before"


@pytest.mark.parametrize("event_type", [EventType.LOGIN_SUCCESS, "LOGIN_SUCCESS", "login_success"])
async def test_login_success_is_accepted(auth_executor: Any, event_type: Any) -> None:
    executor, context, mc, registry = auth_executor
    mc.commands.send_login_sync.return_value = SimpleNamespace(type=event_type, payload={})
    result = await executor.execute(RemoteRepeaterRequest(admin_data={}, action="login", req_id="auth", target_node="cd" * 32, password="secret", mc=mc))
    assert result["authenticated"] is True
    assert result["status"] == "ok"
    context.execute_tx.assert_not_awaited()


@pytest.mark.parametrize("response,accepted", [({"auth_status": "success"}, False), ({"event_type": "LOGIN_SUCCESS"}, True), ({}, False), ({"auth_status": "failed"}, False), ({"text": "OK"}, False)])
async def test_legacy_login_requires_explicit_auth_response(auth_executor: Any, response: dict[str, Any], accepted: bool) -> None:
    executor, context, mc, registry = auth_executor
    del mc.commands.send_login_sync
    mc.commands.send_login.return_value = SimpleNamespace(type=EventType.MSG_SENT, payload={})
    executor._wait_for_repeater_response.return_value = response
    result = await executor.execute(RemoteRepeaterRequest(admin_data={}, action="login", req_id="legacy", target_node="cd" * 32, password="secret", mc=mc))
    assert result["authenticated"] is accepted
    context.execute_tx.assert_not_awaited()


@pytest.mark.parametrize("accepted", [True, False])
async def test_sdk_login_dispatcher_requires_success_event(auth_executor: Any, accepted: bool) -> None:
    executor, context, mc, registry = auth_executor
    del mc.commands.send_login_sync
    mc.commands.send_login.return_value = SimpleNamespace(type=EventType.MSG_SENT, payload={})
    mc.dispatcher = SimpleNamespace(wait_for_event=AsyncMock(return_value=SimpleNamespace(type=EventType.LOGIN_SUCCESS, payload={}) if accepted else None))
    result = await executor.execute(RemoteRepeaterRequest(admin_data={}, action="login", req_id="sdk", target_node="cd" * 32, password="secret", mc=mc))
    assert result["authenticated"] is accepted
    mc.dispatcher.wait_for_event.assert_awaited_once_with(EventType.LOGIN_SUCCESS, timeout=6.0)
    context.execute_tx.assert_not_awaited()


async def test_missing_binary_login_never_sends_password_as_text(auth_executor: Any, caplog: pytest.LogCaptureFixture) -> None:
    executor, context, mc, registry = auth_executor
    del mc.commands.send_login_sync
    del mc.commands.send_login
    password = "binary-only-secret-123"
    result = await executor.execute(RemoteRepeaterRequest(admin_data={}, action="login", req_id="missing-sdk", target_node="cd" * 32, password=password, mc=mc))
    assert result["status"] == "error"
    assert result["authenticated"] is False
    context.execute_tx.assert_not_awaited()
    mc.commands.send_cmd.assert_not_awaited()
    assert password not in json.dumps(result)
    assert password not in caplog.text


@pytest.mark.parametrize("action", ["reboot", "refresh_telemetry"])
@pytest.mark.parametrize("event_type", [EventType.ERROR, None])
async def test_password_prelogin_rejection_blocks_commands_and_queries(auth_executor: Any, action: str, event_type: Any) -> None:
    executor, context, mc, registry = auth_executor
    mc.commands.send_login_sync.return_value = SimpleNamespace(type=event_type, payload={}) if event_type else None
    mc.commands.req_status_sync = AsyncMock()
    mc.commands.req_telemetry_sync = AsyncMock()
    result = await executor.execute(RemoteRepeaterRequest(admin_data={}, action=action, req_id="blocked", target_node="cd" * 32, password="secret", mc=mc))
    assert result["status"] == "error"
    context.execute_tx.assert_not_awaited()
    mc.commands.send_cmd.assert_not_awaited()
    mc.commands.req_status_sync.assert_not_awaited()
    mc.commands.req_telemetry_sync.assert_not_awaited()


@pytest.mark.parametrize("sender", ["ab" * 32, "abababab", "local"])
async def test_received_self_message_cannot_create_mqtt_feedback(virtual_bridge: MeshCoreBridge, sender: str) -> None:
    virtual_bridge.mqtt.publish_safe.reset_mock()
    virtual_bridge.on_mesh_event({"type": "DIRECT_MSG", "event_type": "direct", "sender": sender, "text": "No feedback", "is_direct": True})
    await asyncio.sleep(0)
    publications = [str(call) for call in virtual_bridge.mqtt.publish_safe.call_args_list]
    assert not any("No feedback" in publication for publication in publications)


async def test_stop_cancels_maintenance_and_closes_all_subsystems_once(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = MeshCoreBridge(loop=asyncio.get_running_loop())
    bridge.running = True
    task = asyncio.create_task(asyncio.sleep(3600))
    bridge._cleanup_task = task
    names = ["tcp_server", "web_server", "health_reporter", "watchdog", "rate_limiter"]
    subsystems = {name: SimpleNamespace(stop=AsyncMock()) for name in names}
    for name, subsystem in subsystems.items():
        monkeypatch.setattr(bridge, name, subsystem)
    adapter = SimpleNamespace(disconnect=AsyncMock())
    monkeypatch.setattr(bridge, "serial_adapter", adapter)
    monkeypatch.setattr(bridge.mqtt, "stop", MagicMock())
    monkeypatch.setattr(bridge.node_registry, "save_to_file", MagicMock(return_value=True))
    await bridge.stop()
    await bridge.shutdown()
    assert task.cancelled()
    assert bridge._cleanup_task is None
    assert bridge.running is False
    for subsystem in subsystems.values():
        subsystem.stop.assert_awaited_once()
    adapter.disconnect.assert_awaited_once()
    bridge.mqtt.stop.assert_called_once()
    bridge.node_registry.save_to_file.assert_called_once()
