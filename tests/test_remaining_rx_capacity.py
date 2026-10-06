"""Bounded asynchronous ingress uses only a temporary virtual context."""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from meshcore.events import Event, EventType

from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeRegistry
from src.rx_router import RxEventRouter, RxRouterContext


def make_router() -> RxEventRouter:
    return RxEventRouter(RxRouterContext(
        mqtt=MagicMock(), node_registry=NodeRegistry(), repeater_manager=MagicMock(),
        deduplicator=MagicMock(), serial_adapter=SimpleNamespace(heartbeat=lambda: None),
        web_server=None, loop=asyncio.get_running_loop(), background_tasks=set(),
        counters=SimpleNamespace(rx_count=0, tx_count=0, tx_error_count=0, err_count=0),
    ))


async def test_rx_burst_has_bounded_tasks_and_visible_overflow() -> None:
    router = make_router()
    gate = asyncio.Event()

    class SlowHandler:
        def can_handle(self, *_: Any) -> bool:
            return True

        async def handle(self, *_: Any) -> None:
            await gate.wait()

    router._handlers = [SlowHandler()]  # type: ignore[list-item]
    try:
        for number in range(1000):
            router.handle_event(Event(EventType.ACK, {"ack": str(number)}))
        await asyncio.sleep(0)
        assert len(router._ctx.background_tasks) <= 20
        assert router._ctx.counters.err_count > 0
    finally:
        gate.set()
        await asyncio.gather(*list(router._ctx.background_tasks))


async def test_rx_replaces_only_same_observation_and_preserves_critical() -> None:
    router = make_router()
    received: list[int] = []

    async def observe(number: int) -> None:
        received.append(number)

    assert router._enqueue_work(lambda: observe(1), observation_key="advert:ab")
    assert router._enqueue_work(lambda: observe(2), observation_key="advert:ab")
    assert router._enqueue_work(lambda: observe(3))
    await asyncio.gather(*list(router._ctx.background_tasks))
    assert received == [2, 3]


async def test_rx_queue_capacity_and_critical_admission() -> None:
    router = make_router()
    received: list[int] = []

    async def observe(number: int) -> None:
        received.append(number)

    for number in range(256):
        assert router._enqueue_work(lambda number=number: observe(number), observation_key=f"advert:{number}")
    assert len(router._pending_rx) == 256
    assert router._enqueue_work(lambda: observe(999))
    assert len(router._pending_rx) == 256
    await asyncio.gather(*list(router._ctx.background_tasks))
    assert 999 in received and len(received) == 256
    assert router._ctx.counters.err_count == 1


async def test_rx_cancel_clears_factories_and_accepts_restart() -> None:
    router = make_router()
    gate = asyncio.Event()
    for _ in range(256):
        assert router._enqueue_work(gate.wait)
    await asyncio.sleep(0)
    tasks = list(router._ctx.background_tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert not router._pending_rx
    gate.set()
    assert router._enqueue_work(gate.wait)
    await asyncio.gather(*list(router._ctx.background_tasks))


async def test_system_sink_cannot_create_unbounded_child_tasks() -> None:
    router = make_router()
    gate = asyncio.Event()
    router._ctx.web_server = SimpleNamespace(broadcast_event=AsyncMock(side_effect=lambda _: gate.wait()))
    # A real async sink, rather than a mock returning an unawaited coroutine.
    async def slow_broadcast(_: Any) -> None:
        await gate.wait()
    router._ctx.web_server.broadcast_event.side_effect = slow_broadcast
    try:
        for number in range(1000):
            router.handle_event(Event(EventType.STATS_CORE, {"number": number}))
        for _ in range(3):
            await asyncio.sleep(0)
        assert len(router._ctx.background_tasks) <= 20
    finally:
        gate.set()
        await asyncio.gather(*list(router._ctx.background_tasks))


async def test_bridge_log_notifications_share_rx_ownership() -> None:
    router = make_router()
    gate = asyncio.Event()
    async def slow_broadcast(_: Any) -> None:
        await gate.wait()
    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge.running = True
    bridge._custom_loop = asyncio.get_running_loop()
    bridge.rx_router = router
    bridge.web_server = SimpleNamespace(broadcast_event=slow_broadcast)
    bridge._background_tasks = router._ctx.background_tasks
    def register(task: asyncio.Task) -> asyncio.Task:
        bridge._background_tasks.add(task)
        task.add_done_callback(bridge._background_tasks.discard)
        return task
    bridge._add_background_task = register
    try:
        for number in range(1000):
            bridge._broadcast_system_log({"type": "system_log", "message": str(number)})
        await asyncio.sleep(0)
        assert len(bridge._background_tasks) <= 20
    finally:
        gate.set()
        await asyncio.gather(*list(bridge._background_tasks))


async def test_worker_failure_does_not_rebroadcast_into_failing_sink() -> None:
    router = make_router()
    attempts: list[int] = []

    async def failing_sink() -> None:
        attempts.append(len(attempts))
        # Finite failure injection keeps the defective implementation reproducible.
        if len(attempts) < 4:
            raise RuntimeError("isolated sink failure")

    class LogBroadcast(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.msg == "[RX-ROUTER] Worker failed processing queued work" and not getattr(record, "skip_broadcast", False):
                router._enqueue_work(failing_sink)

    handler = LogBroadcast()
    logging.getLogger().addHandler(handler)
    try:
        assert router._enqueue_work(failing_sink)
        await asyncio.gather(*list(router._ctx.background_tasks))
        assert len(attempts) == 1
        assert router._ctx.counters.err_count == 1
    finally:
        logging.getLogger().removeHandler(handler)
