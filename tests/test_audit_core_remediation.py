"""Audit regressions with mocked transports and temporary station storage."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import config
from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeRegistry
from src.metrics_aggregator import MetricsAggregator
from src.rate_limiter import TxRateLimiter
from src.routers.base import RxMeta
from src.rx_router import RxEventRouter, RxRouterContext
from src.serial.sdk_adapter import EventType, MeshcoreSDKAdapter, companion_command_kind
from src.tcp_companion_server import MeshCoreCompanionServer


@pytest.mark.parametrize(("payload", "expected"), [
    (b"\x05", "local"), (b"\x14", "local"), (b"\x27\x00\x00\x00", "local"),
    (b"\x27\x00\x00\x00" + bytes(32), "rf"), (b"\x07", "rf"), (b"\x10" + bytes(32), "rf"),
    (b"\x19\x00abcd", "rf"), (b"\x42get freq", "local"), (b"\x42advert", None),
    (b"\x42get freq\nreboot", None), (b"\x43", None), (b"", None),
])
def test_companion_classifies_side_effects_explicitly(payload: bytes, expected: str | None) -> None:
    assert companion_command_kind(payload) == expected


@pytest.mark.parametrize("payload", [
    b"\x01", b"\x06" + bytes(3), b"\x09" + bytes(134), b"\x0b",
    b"\x0b" + bytes(9), b"\x0c", b"\x0d" + bytes(31), b"\x0e" + bytes(7),
    b"\x0f", b"\x10" + bytes(31), b"\x12" + bytes(97), b"\x13",
    b"\x15" + bytes(7), b"\x16", b"\x18" + bytes(63), b"\x19\x05abcd",
    b"\x1a" + bytes(31), b"\x1b" + bytes(31), b"\x1c", b"\x1d" + bytes(31),
    b"\x1e" + bytes(31), b"\x1f", b"\x20" + bytes(48), b"\x22", b"\x24" + bytes(9),
    b"\x25" + bytes(3), b"\x26", b"\x27" + bytes(4), b"\x29" + bytes(2),
    b"\x2a" + bytes(32), b"\x32" + bytes(32), b"\x33", b"\x34" + bytes(32),
    b"\x36", b"\x37", b"\x38", b"\x39" + bytes(32), b"\x3a", b"\x3d\x00",
    b"\x3e\x00\xff\x00", b"\x3e\x00\x82" + bytes(7),
    b"\x41\x00\x00\x00",  # Transport header declares four more bytes before path_len.
    b"\x41\x00\x01\x03ab",  # Three path bytes declared, only two supplied.
])
async def test_truncated_companion_layout_never_reaches_transport_or_tx_queue(payload: bytes) -> None:
    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge.serial_adapter = SimpleNamespace(send_raw_companion_frame=AsyncMock())
    bridge.rate_limiter = SimpleNamespace(submit=AsyncMock())
    assert await bridge.handle_tcp_companion_command(payload, None) is False
    bridge.serial_adapter.send_raw_companion_frame.assert_not_awaited()
    bridge.rate_limiter.submit.assert_not_awaited()


@pytest.mark.parametrize(("payload", "expected"), [
    (b"\x0b" + bytes(10), "local"),  # Optional repeat flag absent; radio values stay firmware-validated.
    (b"\x0b" + bytes(11), "local"),
    (b"\x09" + bytes(135), "local"),  # Mandatory contact bytes; optional GPS/lastmod absent.
    (b"\x15" + bytes(8), "local"), (b"\x26\x00", "local"),
    (b"\x3a\x00", "local"), (b"\x3f", "local"), (b"\x36\x00", "local"),
    (b"\x13reboot", "local"), (b"\x33reset", "local"), (b"\x16\x03", "local"),
    (b"\x3e\x00\xff\x01\x00", "rf"),  # Flood sentinel has no path bytes, uint16 type is present.
    (b"\x3e\x00\x82" + bytes(8), "rf"),  # Two three-byte path hashes, then uint16 type.
    (b"\x41\x00\x01\x00", "rf"),  # Dispatcher supports an empty, complete raw packet.
])
def test_complete_companion_layout_preserves_firmware_optional_fields(payload: bytes, expected: str) -> None:
    assert companion_command_kind(payload) == expected


def make_router() -> RxEventRouter:
    return RxEventRouter(RxRouterContext(
        mqtt=MagicMock(), node_registry=NodeRegistry(), repeater_manager=MagicMock(),
        deduplicator=MagicMock(), serial_adapter=SimpleNamespace(heartbeat=lambda: None),
        web_server=None, loop=asyncio.get_running_loop(), background_tasks=set(),
        counters=SimpleNamespace(rx_count=0, tx_count=0, tx_error_count=0, err_count=0),
    ))


async def test_rx_event_at_worker_completion_is_drained() -> None:
    router = make_router()
    router._rx_workers_limit = 1
    seen: list[str] = []

    async def second() -> None:
        seen.append("second")

    async def first() -> None:
        seen.append("first")
        asyncio.get_running_loop().call_soon(router._enqueue_work, second)

    router._enqueue_work(first)
    await router.drain()
    assert seen == ["first", "second"]
    assert not router._pending_rx


async def test_sdk_burst_has_one_worker_and_bounded_notifications() -> None:
    adapter = MeshcoreSDKAdapter("VIRTUAL")
    adapter.is_connected = True
    adapter.mc = SimpleNamespace()
    adapter._on_sdk_event = AsyncMock()
    for number in range(257):
        adapter._enqueue_sdk_event(adapter.mc, "ACK", number)
    assert len(adapter._pending_sdk_events) == 256
    assert len(adapter._background_tasks) == 1
    assert adapter.sdk_event_overflow_count == 1
    await asyncio.gather(*tuple(adapter._background_tasks))
    assert adapter._on_sdk_event.await_count == 256


async def test_sdk_foreign_loop_handoff_is_bounded_before_callback_schedule() -> None:
    adapter = MeshcoreSDKAdapter("VIRTUAL")
    adapter.is_connected = True
    subscriptions: dict[object, object] = {}
    callbacks: list[object] = []
    adapter.mc = SimpleNamespace(subscribe=lambda kind, handler: subscriptions.setdefault(kind, handler))
    adapter._loop = SimpleNamespace(is_closed=lambda: False, is_running=lambda: True, call_soon_threadsafe=callbacks.append)
    adapter._on_sdk_event = AsyncMock()
    adapter._register_event_handlers()
    for number in range(257):
        subscriptions[EventType.ACK](number)
    assert len(callbacks) == 256
    assert adapter.sdk_event_overflow_count == 1
    for callback in callbacks:
        callback()
    assert adapter._sdk_scheduled_callbacks == 0
    await asyncio.gather(*tuple(adapter._background_tasks))
    assert adapter._on_sdk_event.await_count == 256


async def test_watchdog_does_not_probe_busy_command_transport() -> None:
    adapter = MeshcoreSDKAdapter("VIRTUAL")
    adapter.is_connected = True
    adapter.is_hardware_alive = lambda: True
    adapter.mc = SimpleNamespace(commands=SimpleNamespace(get_time=AsyncMock()))
    await adapter._command_lock.acquire()
    try:
        assert await adapter.ping_or_check_alive() is True
        adapter.mc.commands.get_time.assert_not_awaited()
    finally:
        adapter._command_lock.release()


async def test_tcp_remote_without_access_policy_fails_before_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPANION_TOKEN", "")
    server = MeshCoreCompanionServer(SimpleNamespace(), host="0.0.0.0", port=0, allowed_ips="")
    with pytest.raises(ValueError, match="allowed_ips"):
        await server.start()
    assert server.server is None and not server.running


async def test_tcp_slow_client_drain_does_not_block_broadcast() -> None:
    gate = asyncio.Event()
    writer = MagicMock()
    writer.transport.get_write_buffer_size.return_value = 0
    writer.drain = AsyncMock(side_effect=gate.wait)
    server = MeshCoreCompanionServer(SimpleNamespace(), max_clients=2, allowed_ips="127.0.0.1")
    server.running = True
    server.active_clients.add(writer)
    await server.broadcast_companion_frame(b"\x80payload")
    await server.broadcast_companion_frame(b"\x80next")
    assert writer.write.call_count == 2
    assert len(server._writer_tasks) == 1
    gate.set()
    await asyncio.gather(*tuple(server._writer_tasks.values()))
    assert server.max_clients == 2 and server.allowed_ips == frozenset({"127.0.0.1"})


async def test_raw_admin_uses_queue_airtime_without_chat_publication() -> None:
    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge.node_registry = SimpleNamespace(is_local_key=lambda _: False)
    bridge.serial_adapter = SimpleNamespace(send_raw_companion_frame=AsyncMock(return_value=True))
    bridge._tx_metrics_lock = asyncio.Lock()
    bridge.tx_count = bridge.tx_error_count = 0
    bridge.packet_buffer = None
    bridge.publish_chat_event = AsyncMock()
    bridge.rate_limiter = TxRateLimiter(transmit_callback=bridge._execute_tx_transmission, history_file=None)
    bridge.rate_limiter.start()
    try:
        assert await bridge.handle_tcp_companion_command(b"\x07", None) is True
        assert bridge.rate_limiter.airtime_tracker.total_packets == 1
        bridge.serial_adapter.send_raw_companion_frame.assert_awaited_once_with(b"\x07")
        bridge.publish_chat_event.assert_not_awaited()
    finally:
        await bridge.rate_limiter.stop()


async def test_unknown_command_never_reaches_raw_transport() -> None:
    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge.serial_adapter = SimpleNamespace(send_raw_companion_frame=AsyncMock())
    bridge.rate_limiter = SimpleNamespace(submit=AsyncMock())
    assert await bridge.handle_tcp_companion_command(b"\xff", None) is False
    bridge.rate_limiter.submit.assert_not_awaited()
    bridge.serial_adapter.send_raw_companion_frame.assert_not_awaited()


def test_broadcast_target_hex_is_counted_as_flood() -> None:
    metrics = MetricsAggregator()
    metrics.record_packet("tx", target="0xFFFF")
    assert metrics.total_flood_tx == 1


@pytest.mark.parametrize("value", [None, "public", "3 hops", float("inf")])
async def test_malformed_numeric_metadata_preserves_received_message(value: object) -> None:
    router = make_router()
    received: list[tuple[str, int, int]] = []

    class CaptureHandler:
        def can_handle(self, *_: object) -> bool:
            return True

        async def handle(self, router: object, payload: object, meta: RxMeta, event: object) -> None:
            received.append((meta.text, meta.channel_idx, meta.hops))

    router._handlers = [CaptureHandler()]
    router.handle_event(SimpleNamespace(type="CHANNEL_MSG_RECV", payload={
        "text": "message survives", "channel_idx": value, "hop_count": value,
    }))
    await router.drain()
    assert received == [("message survives", 0, 0)]
    assert router._ctx.counters.err_count == 0


async def test_explicit_database_does_not_import_default_legacy_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolated_root = tmp_path / "isolated"
    default_nodes = Path(config.NODE_REGISTRY_STORAGE_PATH)
    default_nodes.write_text("invalid sentinel that must never be imported", encoding="utf-8")
    monkeypatch.setattr(MeshCoreBridge, "_init_adapters_and_watchdog", lambda self: None)
    monkeypatch.setattr(MeshCoreBridge, "_build_sub_components", lambda self: None)
    bridge = await MeshCoreBridge.create(db_path=isolated_root / "custom.sqlite3")
    assert bridge.database.path == isolated_root / "custom.sqlite3"
    assert bridge.data_dir == isolated_root
    assert bridge.channels_storage_path == isolated_root / "channels.json"
    assert bridge.node_storage_path == isolated_root / "node_registry.json"
    assert bridge.repeater_manager._storage_path == isolated_root / "repeater_cooldowns.json"
    assert bridge.airtime_history_file == str(isolated_root / "airtime_history.json")
    assert default_nodes.read_text(encoding="utf-8") == "invalid sentinel that must never be imported"
