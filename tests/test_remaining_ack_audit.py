"""ACK lifetime/capacity regressions with memory state and synthetic clocks."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeRegistry
from src.routers.base import RxMeta
from src.routers.repeater_handler import RepeaterAdminHandler


def bridge():
    instance = MeshCoreBridge.__new__(MeshCoreBridge)
    instance._pending_acks = {}
    return instance


def test_expired_ack_cannot_correlate(monkeypatch):
    instance = bridge()
    monkeypatch.setattr("src.bridge_core.time.monotonic", lambda: 100)
    instance.register_pending_ack("1234abcd", "expired", "remote")
    monkeypatch.setattr("src.bridge_core.time.monotonic", lambda: 3700)
    assert instance.resolve_pending_ack("1234abcd") is None
    assert not instance._pending_acks


def test_ack_is_consumed_once():
    instance = bridge()
    instance.register_pending_ack("0x1234ABCD", "request", "remote")
    assert instance.resolve_pending_ack("1234abcd")["req_id"] == "request"
    assert instance.resolve_pending_ack("1234abcd") is None


def test_recent_ack_table_has_hard_cap_and_visible_rejection(caplog):
    instance = bridge()
    outcomes = [instance.register_pending_ack(f"{i+1:08x}", str(i), "remote") for i in range(201)]
    assert len(instance._pending_acks) == 200
    assert outcomes[-1] == "capacity_exceeded"
    assert "capacity_exceeded" in caplog.text
    assert instance.resolve_pending_ack("00000001")["req_id"] == "0"


def test_conflicting_code_does_not_replace_original_request():
    instance = bridge()
    instance.register_pending_ack("1234abcd", "original", "remote")
    assert instance.register_pending_ack("1234abcd", "different", "other") == "collision"
    assert instance.resolve_pending_ack("1234abcd")["req_id"] == "original"


def test_duplicate_registration_does_not_extend_ttl(monkeypatch):
    instance = bridge()
    monkeypatch.setattr("src.bridge_core.time.monotonic", lambda: 10)
    instance.register_pending_ack("1234abcd", "same", "remote")
    monkeypatch.setattr("src.bridge_core.time.monotonic", lambda: 100)
    instance.register_pending_ack("1234abcd", "same", "remote")
    monkeypatch.setattr("src.bridge_core.time.monotonic", lambda: 3610)
    assert instance.resolve_pending_ack("1234abcd") is None


def test_register_prunes_expired_entries_below_cap(monkeypatch):
    instance = bridge()
    monkeypatch.setattr("src.bridge_core.time.monotonic", lambda: 1)
    instance.register_pending_ack("1234abcd", "old", "remote")
    monkeypatch.setattr("src.bridge_core.time.monotonic", lambda: 4000)
    instance.register_pending_ack("1234abce", "new", "remote")
    assert set(instance._pending_acks) == {"1234abce"}


@pytest.mark.asyncio
async def test_tracking_capacity_is_visible_without_claiming_send_failure():
    instance = bridge()
    for i in range(200):
        instance.register_pending_ack(f"{i+1:08x}", str(i), "remote")
    instance._tx_metrics_lock = asyncio.Lock()
    instance.tx_count = instance.tx_error_count = 0
    instance.node_registry = NodeRegistry()
    instance.serial_adapter = SimpleNamespace(is_connected=True, send_message=AsyncMock(return_value={
        "status": "sent", "expected_ack": "1234abcd"}))
    instance.publish_mqtt_safe = MagicMock()
    instance._record_tx_packet = MagicMock()
    result = await instance._execute_tx({"to": "broadcast", "text": "test", "request_id": "new"})
    assert result["status"] == "sent"
    assert result["delivery_tracking"] == "capacity_exceeded"
    published = json.loads(instance.publish_mqtt_safe.call_args.args[1])
    assert published["delivery_tracking"] == "capacity_exceeded"
    assert instance.resolve_pending_ack("1234abcd") is None


@pytest.mark.asyncio
async def test_ack_with_supplied_msg_id_is_correlated_and_consumed_once():
    instance = bridge()
    instance.register_pending_ack("1234abcd", "real-request", "")
    context = SimpleNamespace(bridge=instance, mqtt=MagicMock(), web_server=SimpleNamespace(broadcast_event=AsyncMock()),
                              background_tasks=set(), node_registry=NodeRegistry())
    payload = {"event_type": "ack", "ack_code": "1234abcd", "msg_id": "untrusted-request"}
    handler = RepeaterAdminHandler()
    def meta():
        return RxMeta("ACK", "ACK", "", "", "", 0, 0, None, None, 0, False)
    await handler.handle(SimpleNamespace(_ctx=context), payload, meta(), None)
    await handler.handle(SimpleNamespace(_ctx=context), payload, meta(), None)
    if context.background_tasks:
        await asyncio.gather(*context.background_tasks)
    context.web_server.broadcast_event.assert_awaited_once()
    assert context.web_server.broadcast_event.await_args.args[0]["msg_id"] == "real-request"
    publications = [json.loads(call.args[1]) for call in context.mqtt.publish_safe.call_args_list]
    assert [item["msg_id"] for item in publications if item.get("msg_id")] == ["real-request"]


@pytest.mark.asyncio
async def test_existing_maintenance_loop_expires_tracking_without_new_timer(monkeypatch):
    instance = bridge()
    monkeypatch.setattr("src.bridge_core.time.monotonic", lambda: 1)
    instance.register_pending_ack("1234abcd", "request", "")
    instance.running = True
    instance._tasks_lock = asyncio.Lock()
    instance._background_tasks = set()
    async def existing_sleep(seconds):
        assert seconds == 60.0
        instance.running = False
        monkeypatch.setattr("src.bridge_core.time.monotonic", lambda: 4000)
    monkeypatch.setattr("src.bridge_core.asyncio.sleep", existing_sleep)
    await instance._cleanup_loop()
    assert not instance._pending_acks
