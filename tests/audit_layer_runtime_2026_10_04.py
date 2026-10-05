"""Explicit audit reproductions. These assert observed defects, not fixed contracts.

Run explicitly with pytest; the filename excludes the maintained default suite.
All state is in memory or the isolated conftest temporary directory.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from meshcore.events import EventType

from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.rate_limiter import CustomTxQueue, TxItem
from src.routers.base import RxMeta
from src.routers.repeater_handler import RepeaterAdminHandler
from src.rx_router import RxEventRouter, RxRouterContext
from src.serial.sdk_adapter import MeshcoreSDKAdapter


def make_router() -> RxEventRouter:
    registry = NodeRegistry()
    registry.add_or_update("ab" * 32, NodeContactUpdate(name="Audit remote", role="REPEATER"))
    context = RxRouterContext(
        mqtt=MagicMock(), node_registry=registry, repeater_manager=MagicMock(),
        deduplicator=MagicMock(), serial_adapter=SimpleNamespace(
            heartbeat=lambda: None, resolve_sender_name=lambda key: key, mc=None,
        ),
        web_server=None, loop=asyncio.get_running_loop(), background_tasks=set(),
        counters=SimpleNamespace(rx_count=0, tx_count=0, tx_error_count=0, err_count=0),
    )
    return RxEventRouter(context)


async def drain(router: RxEventRouter) -> None:
    tasks = list(router._ctx.background_tasks)
    if tasks:
        await asyncio.gather(*tasks)


async def test_path_update_shadowed_by_system_strategy() -> None:
    router = make_router()
    router._handle_path_update = MagicMock()
    router.handle_event(SimpleNamespace(type=EventType.PATH_UPDATE, payload={"public_key": "ab" * 32}))
    await drain(router)
    router._handle_path_update.assert_not_called()
    assert router._ctx.mqtt.publish_safe.called
    assert router._ctx.node_registry.get("ab" * 32).out_path is None
    print("RUNTIME-01: PATH_UPDATE published as generic system event; route synchronizer calls=0")


async def test_rx_log_route_shadowed_but_direct_control_updates() -> None:
    router = make_router()
    payload = {
        "adv_key": "ab" * 32, "path": "0102", "path_len": 2, "path_hash_size": 1,
        "route_typename": "FLOOD", "payload_typename": "ADVERT", "rssi": -90, "snr": 5,
    }
    router.handle_event(SimpleNamespace(type=EventType.RX_LOG_DATA, payload=payload))
    await drain(router)
    assert router._ctx.node_registry.get("ab" * 32).last_rx_route is None
    meta = RxMeta("RX_LOG_DATA", "RX_LOG_DATA", "", "", "", 0, 0, -90, 5, 0, False)
    router._handle_rf_log_observation(payload, meta)
    node = router._ctx.node_registry.get("ab" * 32)
    assert node.last_rx_route is not None
    assert node.last_rx_route["count"] == 2
    print("RUNTIME-01: RX_LOG_DATA normal route=None; direct handler route.count=2")


async def test_rx_semaphore_does_not_bound_pending_tasks() -> None:
    router = make_router()
    entered = 0
    gate = asyncio.Event()

    class SlowHandler:
        def can_handle(self, meta: object, payload: object) -> bool:
            return True

        async def handle(self, *args: object) -> bool:
            nonlocal entered
            entered += 1
            await gate.wait()
            return True

    router._handlers = [SlowHandler()]
    event = SimpleNamespace(type=EventType.PATH_UPDATE, payload={"public_key": "ab" * 32})
    try:
        for _ in range(1000):
            router.handle_event(event)
        await asyncio.sleep(0)
        retained = len(router._ctx.background_tasks)
        assert retained == 1000
        assert 0 < entered < retained
        print(f"RUNTIME-02: 1000 input events -> retained tasks={retained}; active handlers={entered}")
    finally:
        gate.set()
        await drain(router)
    assert not router._ctx.background_tasks


async def test_expired_ack_still_publishes_old_delivery() -> None:
    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge._pending_acks = {}
    with patch("src.bridge_core.time.time", return_value=100.0):
        bridge.register_pending_ack("1234abcd", "expired-request", "ab" * 32)
    ctx = SimpleNamespace(mqtt=MagicMock(), web_server=None, node_registry=NodeRegistry(), bridge=bridge)
    meta = RxMeta("ACK", "ACK", "", "", "", 0, 0, None, None, 0, False)
    with patch("src.bridge_core.time.time", return_value=7300.0):
        await RepeaterAdminHandler().handle(SimpleNamespace(_ctx=ctx), {"ack_code": "1234abcd"}, meta, None)
    emitted = json.loads(ctx.mqtt.publish_safe.call_args.args[1])
    assert emitted["msg_id"] == "expired-request"
    assert "1234abcd" in bridge._pending_acks
    print("RUNTIME-03: ACK after 7200 seconds correlates expired-request; entry retained")


def test_recent_pending_ack_table_not_capped_at_prune_threshold() -> None:
    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge._pending_acks = {}
    with patch("src.bridge_core.time.time", return_value=100.0):
        for idx in range(1, 1001):
            bridge.register_pending_ack(f"{idx:08x}", f"request-{idx}")
    assert len(bridge._pending_acks) == 1000
    print("RUNTIME-03: 1000 recent distinct ACK entries retained despite pruning threshold=200")


def test_analytics_invents_unknown_repeater_measurements() -> None:
    registry = NodeRegistry()
    registry.add_or_update("ab" * 32, NodeContactUpdate(name="Audit repeater", role="REPEATER"))
    registry.add_or_update("cd" * 32, NodeContactUpdate(name="Audit client", role="CLIENT"))
    original = registry.get("ab" * 32)
    assert original.tx_power is None and original.hop_limit is None and not original.neighbors
    analytics = registry.get_analytics_summary()["top_repeaters_by_clients"][0]
    assert analytics["tx_power"] == 20
    assert analytics["hop_limit"] == 3
    assert analytics["connected_clients_count"] == 2
    print("RUNTIME-04: Unknown repeater measurements emitted as TX=20, hop_limit=3, clients=2")


def test_registry_persists_presentation_defaults_as_observed_fields(tmp_path: Path) -> None:
    registry = NodeRegistry()
    registry.add_or_update("ab" * 32, NodeContactUpdate(name="Audit repeater", role="REPEATER"))
    original = registry.get("ab" * 32)
    assert original.hop_limit is None
    assert original.max_tx_power is None
    assert original.repeat_enabled is None
    storage_path = tmp_path / "audit_registry.json"
    assert registry.save_to_file(storage_path)
    restored = NodeRegistry()
    assert restored.load_from_file(storage_path) == 1
    node = restored.get("ab" * 32)
    assert node.hop_limit == 3
    assert node.max_tx_power == 22
    assert node.repeat_enabled is True
    print("RUNTIME-04: JSON roundtrip changes unknown fields to hop_limit=3, max_tx_power=22, repeat_enabled=True")


async def test_raw_setter_accepts_unrelated_battery_response() -> None:
    adapter = MeshcoreSDKAdapter(port="TEST_UNUSED", timeout_sec=0.2)
    adapter.is_connected = True

    async def respond_with_battery(_: bytes) -> None:
        # Official BATTERY response code 0x0C cannot confirm SET_NAME (opcode 8).
        adapter._observe_companion_frame(bytes.fromhex("0ce40c00000000"))

    adapter.mc = SimpleNamespace(cx=SimpleNamespace(send=respond_with_battery), self_info={})
    result = await adapter.send_raw_companion_frame(b"\x08Audit name")
    assert result is True
    print("RUNTIME-05: SET_NAME raw opcode 8 confirmed True by unrelated BATTERY response 0x0C")


async def test_unsolicited_self_info_reintroduces_unsigned_tx_power() -> None:
    router = make_router()
    router._ctx.admin_handler = SimpleNamespace(_local_config={"tx_power": -9}, _ctx=SimpleNamespace())
    adapter = MeshcoreSDKAdapter(port="TEST_UNUSED")
    adapter.rx_callback = router.handle_event
    await adapter._handle_self_info(SimpleNamespace(type=EventType.SELF_INFO, payload={
        "public_key": "cd" * 32, "name": "Audit local", "tx_power": 247,
    }))
    await drain(router)
    assert adapter._self_info["tx_power"] == 247
    assert router._ctx.admin_handler._local_config["tx_power"] == 247
    print("RUNTIME-06: Signed TX=-9 SDK representation=247 overwrites normalized cache with 247")


def test_priority_queue_fifo_changes_when_wall_clock_moves_back() -> None:
    queue = CustomTxQueue(maxsize=10)
    queue.put_nowait(TxItem(priority=1, created_at=100, counter=1, payload="first"))
    queue.put_nowait(TxItem(priority=1, created_at=90, counter=2, payload="second"))
    observed = [queue.get_nowait().payload, queue.get_nowait().payload]
    queue.task_done()
    queue.task_done()
    assert observed == ["second", "first"]
    print("RUNTIME-07: Same-priority FIFO with backward clock: second transmitted before first")


async def test_sdk_disconnect_resolves_raw_waiter_control() -> None:
    adapter = MeshcoreSDKAdapter(port="TEST_UNUSED")
    adapter.mc = SimpleNamespace(disconnect=AsyncMock())
    adapter.is_connected = True
    adapter._raw_command_future = asyncio.get_running_loop().create_future()
    pending = adapter._raw_command_future
    await adapter.disconnect()
    assert pending.result() is False
    assert adapter.mc is None
    print("CONTROL: SDK disconnect completes owned raw waiter False and clears mc")


def test_unused_name_index_does_not_affect_lookup_control() -> None:
    registry = NodeRegistry()
    registry.add_or_update("ab" * 32, NodeContactUpdate(name="Audit node", alias="Audit alias"))
    registry._nodes_by_name.clear()
    assert registry.find_by_name("Audit node").public_key == "ab" * 32
    assert registry.get_by_key_or_prefix("Audit alias").public_key == "ab" * 32
    print("RUNTIME-CODE-01: Clearing maintained private name index does not affect actual name/alias lookup")
