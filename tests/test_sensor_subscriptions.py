"""Regression tests for MeshCore 1.18 (Companion v14) BINARY_RESPONSE (0x8C) and manual sensor subscriptions (0x08/0x09)."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import config
from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.protocol_types import (
    SENSOR_SUBSCRIBE_BALANCED_DELTAS,
    SENSOR_SUBSCRIBE_BALANCED_TIMEOUT_S,
    BinaryReqType,
    build_sensor_subscribe_payload,
    parse_sensor_push_payload,
    parse_sensor_subscribe_reply,
    parse_sensor_unsubscribe_reply,
)
from src.repeater_manager import RepeaterManager
from src.rx_router import RxEventRouter, RxRouterContext
from src.station_database import StationDatabase

SENSOR_KEY = "44" * 32
REPEATER_KEY = "22" * 32
ROOM_KEY = "33" * 32
CLIENT_KEY = "11" * 32
LOCAL_KEY = "aa" * 32


def test_sensor_subscription_binary_helpers_match_firmware_layout() -> None:
    push_tag = "a1b2c3d4"
    payload = build_sensor_subscribe_payload(push_tag)
    assert payload[:4] == bytes.fromhex(push_tag)
    assert int.from_bytes(payload[4:6], "little") == SENSOR_SUBSCRIBE_BALANCED_TIMEOUT_S
    assert payload[6] == 0
    assert payload[7] == len(SENSOR_SUBSCRIBE_BALANCED_DELTAS)
    assert payload[8:] == SENSOR_SUBSCRIBE_BALANCED_DELTAS

    # SensorMesh.cpp subscribe reply (after reader.py consumes 4B tag):
    # actual_timeout_secs(2B LE) | reserved(2B = 0) | scope_name(c-string)
    reply_ok = (3600).to_bytes(2, "little") + b"\x00\x00" + b"ValleyMesh\x00\x00"
    parsed_ok = parse_sensor_subscribe_reply(reply_ok.hex())
    assert parsed_ok == {"ok": True, "actual_timeout_s": 3600, "scope_name": "ValleyMesh"}

    # Rejected subscribe reply (actual_timeout_secs == 0)
    parsed_err = parse_sensor_subscribe_reply(b"\x00\x00")
    assert parsed_err["ok"] is False
    assert parsed_err["actual_timeout_s"] == 0

    # Unsubscribe reply: 8 zero bytes + 2 random bytes
    assert parse_sensor_unsubscribe_reply((b"\x00" * 8) + b"\x9f\x1a") is True
    assert parse_sensor_unsubscribe_reply(b"\x00\x01" + (b"\x00" * 8)) is False

    # Sensor push payload (after reader.py consumes 4B push_tag):
    # sample_timestamp(4B uint32 LE) | CayenneLPP bytes
    sample_ts = 1760700000
    lpp_bytes = b"\x01\x67\x00\xe1\x01\x74\x01\x8c"
    push_raw = sample_ts.to_bytes(4, "little") + lpp_bytes
    parsed_push = parse_sensor_push_payload(push_raw.hex())
    assert parsed_push == {"sample_timestamp": sample_ts, "lpp_bytes": lpp_bytes}


def test_station_database_sensor_subscription_lifecycle_and_expiration(tmp_path: Any) -> None:
    db_path = tmp_path / "station.sqlite3"
    db = StationDatabase(db_path)
    db.initialize()

    tag = db.allocate_sensor_push_tag(SENSOR_KEY)
    assert len(tag) == 8

    saved = db.save_sensor_subscription(
        SENSOR_KEY,
        push_tag=tag,
        requested_timeout_s=3600,
        actual_timeout_s=3600,
        min_deltas_hex=SENSOR_SUBSCRIBE_BALANCED_DELTAS.hex(),
        scope_name="SensorScope",
        subscribed_at=1000.0,
    )
    assert saved["status"] == "active"
    assert saved["expires_at"] == 4600.0
    assert saved["push_tag"] == tag

    # Public view strips push_tag capability token
    pub_view = db.get_sensor_subscription_public_view(SENSOR_KEY, now=1500.0)
    assert pub_view["status"] == "active"
    assert "push_tag" not in pub_view

    # Resolve active tag and record sample
    resolved = db.resolve_sensor_subscription_by_tag(tag, now=2000.0, sample_timestamp=1700000123)
    assert resolved is not None
    assert resolved["public_key"] == SENSOR_KEY
    assert resolved["last_sample_timestamp"] == 1700000123
    assert resolved["last_push_at"] == 2000.0

    # Reopen database to verify SQLite durability across restart
    db_reopened = StationDatabase(db_path)
    db_reopened.initialize()
    assert db_reopened.get_sensor_subscription_public_view(SENSOR_KEY, now=2500.0)["status"] == "active"

    # Expiration marks status='expired' and returns None without renewing
    expired = db_reopened.resolve_sensor_subscription_by_tag(tag, now=4601.0)
    assert expired is None
    stored_after_exp = db_reopened.get_sensor_subscription(SENSOR_KEY, now=4601.0, include_tag=False)
    assert stored_after_exp is not None
    assert stored_after_exp["status"] == "expired"
    assert stored_after_exp["expires_at"] == 4600.0

    # Removal deletes the subscription record
    assert db_reopened.remove_sensor_subscription(SENSOR_KEY) is True
    assert db_reopened.get_sensor_subscription_public_view(SENSOR_KEY) == {"status": "none"}


@pytest.mark.asyncio
async def test_rx_router_correlates_active_sensor_push_and_isolates_unassociated_binary_response(
    tmp_path: Any,
) -> None:
    db = StationDatabase(tmp_path / "rx_station.sqlite3")
    db.initialize()
    registry = NodeRegistry(database=db)
    registry.set_local_pubkey(LOCAL_KEY)
    registry.add_or_update(
        SENSOR_KEY,
        NodeContactUpdate(name="WeatherSensor", role="SENSOR", hops=1),
    )

    mqtt_mock = MagicMock()
    web_mock = MagicMock()
    web_mock.broadcast_event = AsyncMock()
    router_ctx = RxRouterContext(
        mqtt=mqtt_mock,
        serial_adapter=MagicMock(),
        node_registry=registry,
        repeater_manager=RepeaterManager(),
        deduplicator=MagicMock(),
        web_server=web_mock,
        loop=asyncio.get_running_loop(),
        background_tasks=set(),
        counters=SimpleNamespace(rx_count=0, tx_count=0, tx_error_count=0, err_count=0),
    )
    router = RxEventRouter(router_ctx)

    # 1. Unassociated BINARY_RESPONSE with spoofed sender must remain opaque and never touch NodeRegistry
    spoofed_key = "99" * 32
    uncorrelated_ev = SimpleNamespace(
        type="BINARY_RESPONSE",
        payload={
            "tag": "deadbeef",
            "data": "01020304016700fa",
            "sender": spoofed_key,
            "sender_name": "SpoofedSensor",
        },
    )
    router.handle_event(uncorrelated_ev)
    await router.drain()
    assert registry.get_contact(spoofed_key) is None
    published_topics = [c.args[0] for c in mqtt_mock.publish_safe.call_args_list]
    assert config.TOPIC_RX_TELEMETRY not in published_topics
    assert web_mock.broadcast_event.await_count == 1
    bcast_opaque = web_mock.broadcast_event.await_args.args[0]
    assert bcast_opaque["event_type"] == "binary_response"
    assert bcast_opaque["sender"] is None
    assert bcast_opaque["sender_known"] is False

    # 2. Active sensor subscription push is decoded and routed as SENSOR telemetry
    mqtt_mock.reset_mock()
    web_mock.broadcast_event.reset_mock()
    push_tag = db.allocate_sensor_push_tag(SENSOR_KEY)
    db.save_sensor_subscription(
        SENSOR_KEY,
        push_tag=push_tag,
        requested_timeout_s=3600,
        actual_timeout_s=3600,
        min_deltas_hex=SENSOR_SUBSCRIBE_BALANCED_DELTAS.hex(),
        scope_name="NorthRidge",
    )

    sample_ts = 1760700500
    # CayenneLPP: ch1 temp 23.5 C (0x01 0x67 0x00 0xeb), ch1 voltage 3.95 V (0x01 0x74 0x01 0x8b)
    lpp_payload = b"\x01\x67\x00\xeb\x01\x74\x01\x8b"
    push_data_hex = (sample_ts.to_bytes(4, "little") + lpp_payload).hex()
    correlated_ev = SimpleNamespace(
        type="BINARY_RESPONSE",
        payload={"tag": push_tag, "data": push_data_hex, "rssi": -88, "snr": 6.5},
    )
    router.handle_event(correlated_ev)
    await router.drain()

    sensor_node = registry.get_contact(SENSOR_KEY)
    assert sensor_node is not None
    assert sensor_node.temperature_c == pytest.approx(23.5)
    assert sensor_node.voltage_v == pytest.approx(3.95)
    published_topics = [c.args[0] for c in mqtt_mock.publish_safe.call_args_list]
    assert config.TOPIC_RX_TELEMETRY in published_topics
    assert registry.list_client_contacts() == []


@pytest.mark.asyncio
async def test_manual_sensor_subscription_enforces_sensor_role_and_handles_ack_correlation(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = SimpleNamespace(now=time.monotonic())
    # Freeze only the manager clock; asyncio and persistence retain their real clocks.
    monkeypatch.setattr("src.repeater_manager.time", SimpleNamespace(
        monotonic=lambda: clock.now, time=time.time,
    ))
    db = StationDatabase(tmp_path / "admin_station.sqlite3")
    db.initialize()
    registry = NodeRegistry(database=db)
    registry.set_local_pubkey(LOCAL_KEY)
    registry.add_or_update(SENSOR_KEY, NodeContactUpdate(name="EnvSensor", role="SENSOR"))
    registry.add_or_update(REPEATER_KEY, NodeContactUpdate(name="HillRepeater", role="REPEATER"))
    registry.add_or_update(ROOM_KEY, NodeContactUpdate(name="TownRoom", role="ROOM"))
    registry.add_or_update(CLIENT_KEY, NodeContactUpdate(name="Alice", role="CLIENT"))

    mc = MagicMock(contacts={})
    mc._contacts = {}
    mc.commands.add_contact = AsyncMock(return_value={"type": "OK"})
    mc.commands.send_binary_req = AsyncMock(
        return_value=SimpleNamespace(
            type="MSG_SENT",
            payload={"expected_ack": bytes.fromhex("12345678"), "suggested_timeout": 3200},
        )
    )
    reply_bytes = (3600).to_bytes(2, "little") + b"\x00\x00" + b"MeshSensors\x00"
    mc.dispatcher.wait_for_event = AsyncMock(
        return_value=SimpleNamespace(
            type="BINARY_RESPONSE",
            payload={"tag": "12345678", "data": reply_bytes.hex()},
        )
    )

    admin_ctx = AdminContext(
        mqtt=MagicMock(),
        mc_provider=lambda: mc,
        node_registry=registry,
        repeater_manager=RepeaterManager(),
        execute_tx=AsyncMock(),
        web_server=SimpleNamespace(broadcast_event=AsyncMock()),
    )
    handler = AdminCommandHandler(admin_ctx)
    handler._local_config["public_key"] = LOCAL_KEY

    # Reject non-SENSOR roles (REPEATER, ROOM, CLIENT, LOCAL)
    for bad_target in (REPEATER_KEY, ROOM_KEY, CLIENT_KEY, LOCAL_KEY):
        bad_res = await handler.handle(
            {"action": "subscribe_sensor", "target_node": bad_target},
            manual=True,
        )
        assert bad_res["status"] == "error"
    assert mc.commands.send_binary_req.await_count == 0

    # Subscribe to valid SENSOR node
    sub_res = await handler.handle(
        {"action": "subscribe_sensor", "target_node": SENSOR_KEY},
        manual=True,
    )
    assert sub_res["status"] == "ok"
    assert sub_res["sensor_subscription"]["status"] == "active"
    assert sub_res["sensor_subscription"]["actual_timeout_s"] == 3600
    assert sub_res["sensor_subscription"]["scope_name"] == "MeshSensors"
    assert "push_tag" not in sub_res["sensor_subscription"]

    sent_args = mc.commands.send_binary_req.await_args
    assert sent_args.args[1] == BinaryReqType.SUBSCRIBE
    assert len(sent_args.kwargs["data"]) == 8 + len(SENSOR_SUBSCRIBE_BALANCED_DELTAS)

    # Manual unsubscribe obeys the existing command cooldown without emitting RF.
    blocked = await handler.handle(
        {"action": "unsubscribe_sensor", "target_node": SENSOR_KEY}, manual=True,
    )
    assert blocked["code"] == 429
    assert blocked["cooldown_remaining"] > 0
    assert mc.commands.send_binary_req.await_count == 1
    assert db.get_sensor_subscription(SENSOR_KEY) is not None

    # Advance by the configured interval instead of sleeping or forcing a bypass.
    clock.now += admin_ctx.repeater_manager.min_cmd_interval_s
    mc.commands.send_binary_req.return_value = SimpleNamespace(
        type="MSG_SENT",
        payload={"expected_ack": bytes.fromhex("87654321"), "suggested_timeout": 3200},
    )
    mc.dispatcher.wait_for_event.return_value = SimpleNamespace(
        type="BINARY_RESPONSE",
        payload={"tag": "87654321", "data": ((b"\x00" * 8) + b"\xaa\x55").hex()},
    )
    unsub_res = await handler.handle(
        {"action": "unsubscribe_sensor", "target_node": SENSOR_KEY},
        manual=True,
    )
    assert unsub_res["status"] == "ok"
    assert mc.commands.send_binary_req.await_count == 2
    assert mc.commands.send_binary_req.await_args.args[1] == BinaryReqType.UNSUBSCRIBE
    assert mc.commands.send_binary_req.await_args.kwargs["data"] == b""
    assert unsub_res["sensor_subscription"] == {"status": "none"}
    assert db.get_sensor_subscription(SENSOR_KEY) is None
