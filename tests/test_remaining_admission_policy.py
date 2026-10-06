"""MQTT thread admission and persisted cooldown policy regressions."""
import asyncio
import json
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

import config
from src.mqtt_dispatcher import MqttInboundContext, MqttInboundDispatcher
from src.repeater_manager import RepeaterManager


@pytest.mark.asyncio
async def test_cross_thread_burst_reserves_before_posting(monkeypatch):
    monkeypatch.setattr(config, "MAX_MQTT_INBOUND_TASKS", 3, raising=False)
    tasks = set()
    dispatcher = MqttInboundDispatcher(MqttInboundContext(asyncio.get_running_loop(), tasks, MagicMock(), MagicMock(), AsyncMock()))
    release = asyncio.Event()
    async def process(*args):
        await release.wait()
    dispatcher._process_mqtt_input = AsyncMock(side_effect=process)
    # Block the owning loop while the foreign thread posts its complete burst.
    thread = threading.Thread(target=lambda: [dispatcher.handle_incoming("test", "{}") for _ in range(100)])
    thread.start()
    thread.join()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    try:
        assert len(tasks) <= 3
        assert dispatcher._process_mqtt_input.await_count <= 3
    finally:
        release.set()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_mqtt_shutdown_cancels_pending_handles_and_releases_capacity(monkeypatch):
    monkeypatch.setattr(config, "MAX_MQTT_INBOUND_TASKS", 3, raising=False)
    tasks = set()
    dispatcher = MqttInboundDispatcher(MqttInboundContext(asyncio.get_running_loop(), tasks, MagicMock(), MagicMock(), AsyncMock()))
    dispatcher._process_mqtt_input = AsyncMock()
    thread = threading.Thread(target=lambda: [dispatcher.handle_incoming("test", "{}") for _ in range(5)])
    thread.start()
    thread.join()
    await dispatcher.close()
    await asyncio.sleep(0)
    dispatcher._process_mqtt_input.assert_not_awaited()
    assert not dispatcher._admission_tokens


@pytest.mark.asyncio
async def test_cooldown_survives_restart_with_same_existing_interval(tmp_path, monkeypatch):
    path = tmp_path / "cooldowns.json"
    monkeypatch.setattr("src.repeater_manager.time.time", lambda: 1000)
    monkeypatch.setattr("src.repeater_manager.time.monotonic", lambda: 100)
    try:
        first = RepeaterManager(min_cmd_interval_s=5, storage_path=path)
    except TypeError:  # Reproduce the older in-memory implementation too.
        first = RepeaterManager(min_cmd_interval_s=5)
    if hasattr(first, "load_state"):
        await first.load_state()
    first.record_command_sent("ab" * 32)
    if hasattr(first, "flush_state"):
        await first.flush_state()
        await first.close()
    monkeypatch.setattr("src.repeater_manager.time.time", lambda: 1002)
    monkeypatch.setattr("src.repeater_manager.time.monotonic", lambda: 900)
    try:
        second = RepeaterManager(min_cmd_interval_s=5, storage_path=path)
    except TypeError:
        second = RepeaterManager(min_cmd_interval_s=5)
    if hasattr(second, "load_state"):
        await second.load_state()
    assert second.check_airtime_cooldown("ab" * 32) == (False, 3.0)
    if hasattr(second, "close"):
        await second.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("record,check,remaining", [("record_ping_sent", "check_ping_cooldown", 13),
    ("record_traceroute_sent", "check_traceroute_cooldown", 58),
    ("record_neighbours_sent", "check_neighbours_cooldown", 28)])
async def test_specialized_cooldowns_survive_restart(tmp_path, monkeypatch, record, check, remaining):
    path = tmp_path / "cooldowns.json"
    monkeypatch.setattr("src.repeater_manager.time.time", lambda: 1000)
    monkeypatch.setattr("src.repeater_manager.time.monotonic", lambda: 100)
    first = RepeaterManager(storage_path=path)
    await first.load_state()
    getattr(first, record)("ab" * 32)
    await first.close()
    monkeypatch.setattr("src.repeater_manager.time.time", lambda: 1002)
    monkeypatch.setattr("src.repeater_manager.time.monotonic", lambda: 900)
    second = RepeaterManager(storage_path=path)
    await second.load_state()
    assert getattr(second, check)("ab" * 32) == (False, remaining)
    await second.close()


@pytest.mark.asyncio
async def test_full_telemetry_cooldown_and_wall_clock_rollback(tmp_path, monkeypatch):
    path = tmp_path / "cooldowns.json"
    monkeypatch.setattr("src.repeater_manager.time.time", lambda: 1000)
    monkeypatch.setattr("src.repeater_manager.time.monotonic", lambda: 100)
    first = RepeaterManager(storage_path=path)
    await first.load_state()
    first.record_command_sent("ab" * 32, is_full_query=True)
    await first.close()
    monkeypatch.setattr("src.repeater_manager.time.time", lambda: 900)
    monkeypatch.setattr("src.repeater_manager.time.monotonic", lambda: 800)
    second = RepeaterManager(storage_path=path)
    await second.load_state()
    assert second.check_airtime_cooldown("ab" * 32, is_full_query=True) == (False, 30.0)
    assert second.check_airtime_cooldown("ab" * 32) == (False, 5.0)
    await second.close()


@pytest.mark.asyncio
async def test_atomic_write_failure_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "cooldowns.json"
    manager = RepeaterManager(storage_path=path)
    await manager.load_state()
    manager.record_command_sent("ab" * 32)
    await manager.flush_state()
    previous = path.read_bytes()
    manager.record_command_sent("cd" * 32)
    def failed_replace(*args):
        raise OSError("injected failure")
    with monkeypatch.context() as local_patch:
        local_patch.setattr("src.repeater_manager.os.replace", failed_replace)
        with pytest.raises(OSError, match="injected failure"):
            await manager.flush_state()
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob("*.tmp"))
    await manager.close()
    assert "cd" * 32 in json.loads(path.read_text())["timestamps"]["command"]


@pytest.mark.asyncio
async def test_cancelled_flush_retains_single_owned_writer(tmp_path, monkeypatch):
    path = tmp_path / "cooldowns.json"
    manager = RepeaterManager(storage_path=path)
    await manager.load_state()
    started, release = threading.Event(), threading.Event()
    original = manager._write_state
    writes = []
    def slow_write(destination, document):
        writes.append(document)
        if len(writes) == 1:
            started.set()
            release.wait()
        original(destination, document)
    monkeypatch.setattr(manager, "_write_state", slow_write)
    manager.record_command_sent("ab" * 32)
    flush = asyncio.create_task(manager.flush_state())
    await asyncio.to_thread(started.wait)
    flush.cancel()
    await asyncio.gather(flush, return_exceptions=True)
    manager.record_command_sent("cd" * 32)
    close = asyncio.create_task(manager.close())
    await asyncio.sleep(0)
    assert len(writes) == 1
    release.set()
    await close
    assert manager._write_task.done()
    assert len(writes) == 2
    assert set(json.loads(path.read_text())["timestamps"]["command"]) == {"ab" * 32, "cd" * 32}


@pytest.mark.asyncio
async def test_invalid_persisted_state_is_not_silently_ignored(tmp_path):
    path = tmp_path / "cooldowns.json"
    path.write_text('{"schema":1,"timestamps":{"command":{"key":true}}}')
    manager = RepeaterManager(storage_path=path)
    with pytest.raises(ValueError, match="timestamp invalid"):
        await manager.load_state()


@pytest.mark.asyncio
async def test_mqtt_owned_tasks_release_slots_after_completion(monkeypatch):
    monkeypatch.setattr(config, "MAX_MQTT_INBOUND_TASKS", 1, raising=False)
    tasks = set()
    dispatcher = MqttInboundDispatcher(MqttInboundContext(asyncio.get_running_loop(), tasks, MagicMock(), MagicMock(), AsyncMock()))
    dispatcher._process_mqtt_input = AsyncMock()
    dispatcher.handle_incoming("test", "{}")
    await asyncio.gather(*tasks)
    await asyncio.sleep(0)
    assert not dispatcher._admission_tokens
    dispatcher.handle_incoming("test", "{}")
    await asyncio.gather(*tasks)
    await dispatcher.close()
    assert dispatcher._process_mqtt_input.await_count == 2
    assert not dispatcher._inbound_tasks
