"""Core lifecycle regressions using mocked subsystems and isolated asyncio tasks."""
from __future__ import annotations

import asyncio
import logging
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bridge_core import MeshCoreBridge
from src.diagnostics import SystemLogHandler
from src.rate_limiter import TxPriority, TxRateLimiter


def bridge() -> MeshCoreBridge:
    obj = MeshCoreBridge.__new__(MeshCoreBridge)
    obj.running = True
    obj._is_stopped = False
    obj._custom_loop = asyncio.get_running_loop()
    obj._background_tasks = set()
    obj._cleanup_task = None
    obj._health_task = None
    obj._tasks_lock = asyncio.Lock()
    obj.rate_limiter = SimpleNamespace(start=MagicMock(), stop=AsyncMock())
    obj.mqtt = SimpleNamespace(start=MagicMock(), stop=MagicMock())
    obj.mqtt.publish_safe = MagicMock()
    obj.serial_adapter = SimpleNamespace(connect=AsyncMock(return_value=True), disconnect=AsyncMock(), port="mock")
    obj.watchdog = SimpleNamespace(start=MagicMock(), stop=AsyncMock())
    obj.web_server = SimpleNamespace(start=AsyncMock(), stop=AsyncMock(), broadcast_event=AsyncMock())
    obj.tcp_server = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    obj.node_registry = SimpleNamespace(save_to_file=MagicMock())
    obj.preflight = SimpleNamespace(run_all=MagicMock(return_value={"status": "OK", "checks": []}))
    obj.health_reporter = SimpleNamespace(start=MagicMock(side_effect=lambda: asyncio.create_task(asyncio.Event().wait())), stop=AsyncMock())
    obj._auto_bootstrap_heltec_state = AsyncMock()
    return obj


async def test_owned_background_exception_is_consumed_without_broadcast_feedback(caplog: Any) -> None:
    obj = bridge()
    async def fail() -> None:
        raise RuntimeError("observable failure")
    task = obj._add_background_task(asyncio.create_task(fail()))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not task._log_traceback
    assert task not in obj._background_tasks
    records = [r for r in caplog.records if "observable failure" in r.getMessage()]
    assert records and getattr(records[-1], "skip_broadcast", False)


async def test_thread_broadcast_becomes_owned_task() -> None:
    obj = bridge()
    entered = asyncio.Event()
    released = asyncio.Event()
    async def broadcast(payload: dict[str, Any]) -> None:
        entered.set()
        await released.wait()
    obj.web_server.broadcast_event = broadcast
    await asyncio.to_thread(obj._broadcast_system_log, {"type": "test"})
    await entered.wait()
    tasks = list(obj._background_tasks)
    try:
        assert len(tasks) == 1
    finally:
        released.set()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_shutdown_cancels_and_joins_owned_tasks() -> None:
    obj = bridge()
    cleaned = asyncio.Event()
    entered = asyncio.Event()
    async def pending() -> None:
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            cleaned.set()
    task = obj._add_background_task(asyncio.create_task(pending()))
    await entered.wait()
    try:
        await obj.stop()
        assert cleaned.is_set()
        assert task.cancelled()
        assert not obj._background_tasks
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_failed_start_cleans_started_subsystems() -> None:
    obj = bridge()
    obj.web_server.start.side_effect = RuntimeError("startup failure")
    try:
        with pytest.raises(RuntimeError, match="startup failure"):
            await obj.start()
        obj.rate_limiter.stop.assert_awaited_once()
        obj.serial_adapter.disconnect.assert_awaited_once()
        obj.mqtt.stop.assert_called_once()
        assert not obj.running
    finally:
        for task in list(obj._background_tasks):
            task.cancel()
        await asyncio.gather(*obj._background_tasks, return_exceptions=True)


async def test_preflight_runs_outside_asyncio_thread_and_restart_can_stop() -> None:
    obj = bridge()
    loop_thread = threading.get_ident()
    threads: list[int] = []
    def preflight(**kwargs: Any) -> dict[str, Any]:
        threads.append(threading.get_ident())
        return {"status": "OK", "checks": []}
    obj.preflight.run_all.side_effect = preflight
    try:
        await obj.start()
        await obj.stop()
        await obj.start()
        await obj.stop()
        assert all(thread != loop_thread for thread in threads)
        assert len(threads) == 2
        assert obj.serial_adapter.disconnect.await_count == 2
    finally:
        for task in list(obj._background_tasks):
            task.cancel()
        await asyncio.gather(*obj._background_tasks, return_exceptions=True)


def test_internal_background_failure_log_is_stored_without_callback() -> None:
    callback = MagicMock()
    handler = SystemLogHandler(broadcast_callback=callback)
    record = logging.LogRecord("bridge", logging.ERROR, __file__, 1, "task failed", (), None)
    record.skip_broadcast = True
    handler.handle(record)
    assert handler.error_count == 1
    assert len(handler.buffer) == 1
    callback.assert_not_called()


async def test_start_protects_sdk_log_level_and_serializes_double_start() -> None:
    obj = bridge()
    sdk_logger = logging.getLogger("meshcore")
    previous = sdk_logger.level
    sdk_logger.setLevel(logging.DEBUG)
    try:
        await asyncio.gather(obj.start(), obj.start())
        assert sdk_logger.getEffectiveLevel() >= logging.INFO
        obj.serial_adapter.connect.assert_awaited_once()
        assert len(obj._background_tasks) == 2
    finally:
        await obj.stop()
        for task in list(obj._background_tasks):
            task.cancel()
        await asyncio.gather(*obj._background_tasks, return_exceptions=True)
        sdk_logger.setLevel(previous)


@pytest.mark.parametrize("hook", ["_on_duty_cycle_alert", "_on_airtime_cutoff_change"])
async def test_airtime_thread_broadcasts_are_owned(hook: str) -> None:
    obj = bridge()
    entered = asyncio.Event()
    released = asyncio.Event()
    async def broadcast(payload: dict[str, Any]) -> None:
        entered.set()
        await released.wait()
    obj.web_server.broadcast_event = broadcast
    method = getattr(obj, hook)
    args = ("warning", {}) if hook == "_on_duty_cycle_alert" else (True, 40.0)
    await asyncio.to_thread(method, *args)
    # One loop turn runs the callback queued by the worker thread.
    await asyncio.sleep(0)
    tasks = list(obj._background_tasks)
    try:
        assert len(tasks) == 1
        await entered.wait()
    finally:
        released.set()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_cleanup_retains_task_set_shared_with_dispatchers(monkeypatch: pytest.MonkeyPatch) -> None:
    obj = bridge()
    shared = obj._background_tasks
    async def end_loop(delay: float) -> None:
        obj.running = False
    monkeypatch.setattr(asyncio, "sleep", end_loop)
    await obj._cleanup_loop()
    assert obj._background_tasks is shared


async def test_cancelled_start_rolls_back_and_preserves_cancellation() -> None:
    obj = bridge()
    entered = asyncio.Event()
    async def connect() -> bool:
        entered.set()
        await asyncio.Event().wait()
        return True
    obj.serial_adapter.connect = connect
    task = asyncio.create_task(obj.start())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    obj.serial_adapter.disconnect.assert_awaited_once()
    obj.rate_limiter.stop.assert_awaited_once()
    obj.mqtt.stop.assert_called_once()
    assert not obj.running


async def test_raw_thread_callback_captures_response_owner_before_scheduling() -> None:
    obj = bridge()
    owner = object()
    obj.tcp_server.get_response_owner = MagicMock(return_value=owner)
    obj.tcp_server.broadcast_companion_frame = AsyncMock()
    await asyncio.to_thread(obj._on_raw_companion_frame_rx, b"\x04end")
    obj.tcp_server.get_response_owner.return_value = None
    await asyncio.sleep(0)
    obj.tcp_server.broadcast_companion_frame.assert_awaited_once_with(b"\x04end", response_owner=owner)


async def test_broadcast_failure_does_not_generate_another_broadcast() -> None:
    obj = bridge()
    obj.web_server.broadcast_event.side_effect = RuntimeError("websocket disconnected")
    handler = SystemLogHandler(broadcast_callback=obj._broadcast_system_log)
    logging.getLogger().addHandler(handler)
    try:
        obj._broadcast_system_log({"event": "test"})
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        obj.web_server.broadcast_event.assert_awaited_once()
        assert handler.error_count == 1
    finally:
        logging.getLogger().removeHandler(handler)
        for task in list(obj._background_tasks):
            task.cancel()
        await asyncio.gather(*obj._background_tasks, return_exceptions=True)


@pytest.mark.parametrize("payload,channel,target", [
    (b"\x03\x00\x02" + bytes(4) + b"hello", 2, None),
    (b"\x02\x00\x00" + bytes(4) + bytes.fromhex("cd" * 6) + b"hello", 0, "cd" * 6),
])
async def test_tcp_chat_uses_existing_rate_queue(payload: bytes, channel: int, target: str | None) -> None:
    obj = bridge()
    obj.serial_adapter.send_raw_companion_frame = AsyncMock(return_value=True)
    future = asyncio.get_running_loop().create_future()
    future.set_result({"status": "sent"})
    obj.rate_limiter.submit = AsyncMock(return_value=future)
    assert await obj.handle_tcp_companion_command(payload, None) is True
    obj.rate_limiter.submit.assert_awaited_once_with(payload=payload, priority=TxPriority.NORMAL,
                                                  target=target, channel_idx=channel)
    obj.serial_adapter.send_raw_companion_frame.assert_not_awaited()


@pytest.mark.parametrize("success", [True, False])
async def test_raw_queued_chat_is_sent_as_bytes_and_accounts_confirmed_airtime(success: bool) -> None:
    obj = bridge()
    obj._tx_metrics_lock = asyncio.Lock()
    obj.tx_count = obj.tx_error_count = 0
    obj.serial_adapter.is_connected = True
    obj.serial_adapter.send_message = AsyncMock(return_value={"status": "sent"})
    obj.serial_adapter.send_raw_companion_frame = AsyncMock(return_value=success)
    obj.publish_mqtt_safe = MagicMock()
    obj._record_tx_packet = MagicMock()
    obj.rate_limiter = TxRateLimiter(transmit_callback=obj._execute_tx_transmission, history_file=None)
    obj.rate_limiter.start()
    payload = b"\x03\x00\x02" + bytes(4) + b"hello"
    try:
        future = await obj.rate_limiter.submit(payload, channel_idx=2)
        result = await future
        assert result["status"] == ("sent" if success else "error")
        obj.serial_adapter.send_raw_companion_frame.assert_awaited_once_with(payload)
        obj.serial_adapter.send_message.assert_not_awaited()
        assert obj.rate_limiter.airtime_tracker.total_packets == int(success)
    finally:
        await obj.rate_limiter.stop()


async def test_raw_cli_and_local_commands_keep_the_serial_gateway() -> None:
    obj = bridge()
    obj.serial_adapter.send_raw_companion_frame = AsyncMock(return_value=True)
    obj.rate_limiter.submit = AsyncMock()
    for payload in (b"\x03", b"\x02\x01\x00" + bytes(4) + bytes.fromhex("cd" * 6) + b"reboot", b"\x16"):
        if payload == b"\x03":
            assert await obj.handle_tcp_companion_command(payload, None) is False
        else:
            assert await obj.handle_tcp_companion_command(payload, None) is True
    obj.rate_limiter.submit.assert_not_awaited()


async def test_cancelled_queued_tcp_chat_is_never_transmitted_later() -> None:
    obj = bridge()
    obj._tx_metrics_lock = asyncio.Lock()
    obj.tx_count = obj.tx_error_count = 0
    obj.serial_adapter.send_raw_companion_frame = AsyncMock(return_value=True)
    obj.rate_limiter = TxRateLimiter(transmit_callback=obj._execute_tx_transmission, history_file=None)
    payload = b"\x03\x00\x02" + bytes(4) + b"hello"
    task = asyncio.create_task(obj.handle_tcp_companion_command(payload, None))
    await asyncio.sleep(0)
    assert obj.rate_limiter.get_queue_depth() == 1
    obj.serial_adapter.send_raw_companion_frame.assert_not_awaited()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    obj.rate_limiter.start()
    try:
        await asyncio.sleep(0)
        obj.serial_adapter.send_raw_companion_frame.assert_not_awaited()
        assert obj.rate_limiter.airtime_tracker.total_packets == 0
    finally:
        await obj.rate_limiter.stop()
