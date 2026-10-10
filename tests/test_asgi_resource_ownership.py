"""Isolated regressions for ASGI notification and map lifecycle ownership.

These scenarios use temporary storage, controlled worker threads and, for one
restart, an OS-assigned loopback listener. No radio, broker or operator data.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.web.api_router import WebAPIRouter
from src.web.asgi_server import AsgiWebServer


class ControlledMaps:
    """Observe lifecycle calls and hold disk operations without blocking asyncio."""

    def __init__(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.close_gate = threading.Event()
        self.reload_gate = threading.Event()
        self.close_gate.set()
        self.reload_gate.set()
        self.close_started = asyncio.Event()
        self.close_finished = asyncio.Event()
        self.reload_started = asyncio.Event()
        self.calls: list[str] = []
        self.closed = False

    def close(self) -> None:
        self.calls.append("close_started")
        self.loop.call_soon_threadsafe(self.close_started.set)
        if not self.close_gate.wait(timeout=5.0):
            raise RuntimeError("Controlled close was not released by its fixture")
        self.closed = True
        self.calls.append("close_finished")
        self.loop.call_soon_threadsafe(self.close_finished.set)

    def reload_mbtiles(self) -> None:
        self.calls.append("reload_started")
        self.loop.call_soon_threadsafe(self.reload_started.set)
        if not self.reload_gate.wait(timeout=5.0):
            raise RuntimeError("Controlled reload was not released by its fixture")
        self.closed = False
        self.calls.append("reload_finished")


async def make_resources(
    tmp_path: Path, *, owns_maps: bool,
) -> tuple[WebAPIRouter, ControlledMaps, AsgiWebServer]:
    bridge = SimpleNamespace(start_time=time.time(), web_server=None)
    router = WebAPIRouter(bridge)
    # The autouse isolated_state fixture confines the real constructor's files.
    await asyncio.to_thread(router.map_tile_service.close)
    maps = ControlledMaps()
    router.map_tile_service = maps  # type: ignore[assignment]
    server = AsgiWebServer(
        router, host="127.0.0.1", port=0, static_dir=tmp_path,
        owns_tile_service=owns_maps, shutdown_budget_s=0.05,
    )
    bridge.web_server = server
    return router, maps, server


async def start_after_owned_cleanup(server: AsgiWebServer) -> None:
    """Observe public restart admission while the worker finishes its callback."""
    while True:
        try:
            await server.start()
            return
        except RuntimeError as error:
            if str(error) != "Previous ASGI lifecycle has not finished":
                raise
            await asyncio.sleep(0)


async def finish_map_workers(server: AsgiWebServer) -> None:
    """Join only this fixture's workers after releasing their thread gates."""
    workers = tuple(server._tile_tasks)
    if workers:
        await asyncio.wait_for(
            asyncio.gather(*(asyncio.shield(task) for task in workers), return_exceptions=True),
            timeout=2.0,
        )
    await asyncio.sleep(0)  # Let retained-result callbacks finish before restart.


@pytest.mark.asyncio
async def test_notification_failures_are_consumed_and_shutdown_cancels_deliveries(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    router, maps, server = await make_resources(tmp_path, owns_maps=False)
    failed = asyncio.Event()
    pending = asyncio.Event()
    cancelled = asyncio.Event()
    calls: list[dict[str, Any]] = []

    async def broadcast(event: dict[str, Any]) -> None:
        calls.append(event)
        if event["type"] == "failure":
            failed.set()
            raise RuntimeError("private-notification-detail")
        pending.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    router.bridge.web_server = SimpleNamespace(broadcast_event=broadcast)
    notify = router.api_ctx.broadcast_ws
    assert notify is not None
    caplog.set_level(logging.WARNING)
    try:
        notify({"type": "failure"})
        await asyncio.wait_for(failed.wait(), timeout=2.0)
        await asyncio.sleep(0)  # Deliver the task's result callback.
        failures = [r for r in caplog.records if "Web notification failed" in r.message]
        assert len(failures) == 1
        assert "RuntimeError" in failures[0].message
        assert "private-notification-detail" not in failures[0].message
        assert getattr(failures[0], "skip_broadcast", False)
        assert not router.owned_notification_tasks()

        notify({"type": "pending"})
        await asyncio.wait_for(pending.wait(), timeout=2.0)
        await server.stop()
        assert cancelled.is_set()
        assert not router.owned_notification_tasks()
        notify({"type": "after_shutdown"})
        assert len(calls) == 2
        assert maps.calls == []  # Borrowed storage belongs to its external owner.
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_owned_close_stays_off_loop_and_pending_worker_prevents_restart(
    tmp_path: Path,
) -> None:
    _, maps, server = await make_resources(tmp_path, owns_maps=True)
    maps.close_gate.clear()
    stopping = asyncio.create_task(server.stop())
    try:
        # This callback cannot reach asyncio if close() blocks its event loop.
        await asyncio.wait_for(maps.close_started.wait(), timeout=2.0)
        await asyncio.wait_for(stopping, timeout=2.0)
        assert not maps.closed
        with pytest.raises(RuntimeError, match="Previous ASGI lifecycle"):
            await server.start()

        maps.close_gate.set()
        await asyncio.wait_for(maps.close_finished.wait(), timeout=2.0)
        await asyncio.wait_for(start_after_owned_cleanup(server), timeout=2.0)
        assert server.running
        assert not maps.closed
        assert maps.calls[:4] == [
            "close_started", "close_finished", "reload_started", "reload_finished",
        ]
    finally:
        maps.close_gate.set()
        maps.reload_gate.set()
        await server.stop()
        await asyncio.wait_for(
            asyncio.gather(server.wait_closed(), stopping, return_exceptions=True),
            timeout=2.0,
        )
        await finish_map_workers(server)


@pytest.mark.asyncio
async def test_cancelled_reload_finishes_before_its_owned_close(tmp_path: Path) -> None:
    _, maps, server = await make_resources(tmp_path, owns_maps=True)
    await server.stop()
    await asyncio.wait_for(maps.close_finished.wait(), timeout=2.0)
    await finish_map_workers(server)
    maps.close_finished.clear()
    maps.reload_gate.clear()
    starting = asyncio.create_task(start_after_owned_cleanup(server))
    try:
        await asyncio.wait_for(maps.reload_started.wait(), timeout=2.0)
        starting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await starting
        assert maps.calls == ["close_started", "close_finished", "reload_started"]
        with pytest.raises(RuntimeError, match="Previous ASGI lifecycle"):
            await server.start()

        maps.reload_gate.set()
        await asyncio.wait_for(maps.close_finished.wait(), timeout=2.0)
        assert maps.calls == [
            "close_started", "close_finished", "reload_started", "reload_finished",
            "close_started", "close_finished",
        ]
        assert maps.closed
    finally:
        maps.close_gate.set()
        maps.reload_gate.set()
        await server.stop()
        await asyncio.gather(starting, return_exceptions=True)
        await finish_map_workers(server)
