"""Observable core regressions, isolated from brokers and physical radios."""
from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from meshcore.events import Event, EventType

import config
from src.admin_handler import AdminCommandHandler, AdminContext
from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.diagnostics import DiagnosticManager
from src.health_reporter import HealthReporter
from src.mqtt_client import AsyncBridgeMQTTClient, MQTTConfig
from src.mqtt_dispatcher import MqttInboundContext, MqttInboundDispatcher
from src.rate_limiter import CustomTxQueue, TxItem, TxRateLimiter


def admin() -> tuple[AdminCommandHandler, Any, AdminContext]:
    mc = SimpleNamespace(commands=SimpleNamespace(send_advert=AsyncMock()), self_info={})
    ctx = AdminContext(lambda: mc, NodeRegistry(), MagicMock(), MagicMock(), AsyncMock())
    return AdminCommandHandler(ctx), mc, ctx


@pytest.mark.parametrize("payload", ['{"action":"set_config","params":{"name":"Casa"},"request_id":"req"}', '"get_config"', 'get_config'])
async def test_mqtt_admin_retains_action_and_request_envelope(payload: str) -> None:
    handle = AsyncMock()
    ctx = MqttInboundContext(asyncio.get_running_loop(), set(), MagicMock(), MagicMock(), handle)
    await MqttInboundDispatcher(ctx)._handle_admin_request(payload)
    data = handle.await_args.args[0]
    assert data["action"] in ("set_config", "get_config")
    if data["action"] == "set_config":
        assert data["params"] == {"name": "Casa"}
        assert data["request_id"] == "req"


async def test_mqtt_handler_failure_is_not_retried_as_another_command() -> None:
    handle = AsyncMock(side_effect=RuntimeError("firmware error"))
    mqtt = SimpleNamespace(topic_tx="test/tx", topic_admin_cmd="test/admin/cmd")
    ctx = MqttInboundContext(asyncio.get_running_loop(), set(), mqtt, MagicMock(), handle)
    await MqttInboundDispatcher(ctx)._process_mqtt_input(f"{config.TOPIC_ADMIN_REPEATER}/abcdef/cmd", '{"action":"reboot"}')
    handle.assert_awaited_once()


@pytest.mark.parametrize("response", [None, Event(EventType.ERROR, {})])
async def test_advert_failure_is_explicit_and_never_chat_fallback(response: Any) -> None:
    handler, mc, ctx = admin()
    mc.commands.send_advert.return_value = response
    result = await handler.broadcast_advert()
    assert result["status"] == "error"
    ctx.execute_tx.assert_not_awaited()


async def test_custom_variable_error_return_reaches_admin_client() -> None:
    handler, mc, ctx = admin()
    handler.set_custom_var = AsyncMock(return_value={"status": "error", "message": "reject"})
    result = await handler.handle({"action": "set_custom_var", "key": "mode", "value": "new"})
    assert result["status"] == "error"


def bare_bridge() -> MeshCoreBridge:
    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge.running = True
    bridge._is_stopped = False
    bridge._background_tasks = set()
    bridge._tx_metrics_lock = asyncio.Lock()
    bridge.node_registry = NodeRegistry()
    bridge.serial_adapter = SimpleNamespace(is_connected=True, send_message=AsyncMock())
    bridge.tx_count = 0
    bridge.tx_error_count = 0
    bridge.publish_mqtt_safe = MagicMock()
    bridge._record_tx_packet = MagicMock()
    bridge._pending_acks = {}
    return bridge


@pytest.mark.parametrize("response", [None, {"status": "error", "error": "reject"}, {"event": Event(EventType.ERROR, {})}])
async def test_transmission_rejection_is_not_reported_sent(response: Any) -> None:
    bridge = bare_bridge()
    bridge.serial_adapter.send_message.return_value = response
    result = await bridge._execute_tx({"to": "broadcast", "text": "hello"})
    assert result["status"] == "error"
    assert bridge.tx_error_count == 1


def test_chat_tokens_do_not_bypass_repeater_role_guard() -> None:
    bridge = bare_bridge()
    bridge.node_registry.add_or_update("cd" * 32, NodeContactUpdate(role="REPEATER", name="Relay"))
    assert bridge._validate_tx_target("cd" * 32, "get hello", False) is not None


async def test_health_requires_mqtt_and_serial_connection() -> None:
    ctx = SimpleNamespace(serial_adapter=SimpleNamespace(is_connected=True), mqtt=SimpleNamespace(is_connected=False),
        start_time=time.time(), node_registry=MagicMock(), rate_limiter=MagicMock(),
        counters=SimpleNamespace(rx_count=0, tx_count=0, tx_error_count=0, err_count=0))
    result = await HealthReporter(ctx, 60).build_payload()
    assert result["status"] == "degraded"


async def test_evicted_queue_future_settles_and_join_completes() -> None:
    queue = CustomTxQueue(maxsize=1)
    future = asyncio.get_running_loop().create_future()
    queue.put_nowait(TxItem(priority=2, created_at=time.time(), counter=1, payload="old", future=future))
    queue.put_nowait(TxItem(priority=0, created_at=time.time(), counter=2, payload="new"))
    assert future.done()
    with pytest.raises(RuntimeError):
        await future
    queue.get_nowait()
    queue.task_done()
    await asyncio.wait_for(queue.join(), 0.1)


async def test_worker_cancellation_settles_active_future() -> None:
    entered = asyncio.Event()
    async def transmit(item: Any) -> Any:
        entered.set()
        await asyncio.Event().wait()
    limiter = TxRateLimiter(transmit_callback=transmit, history_file=None)
    limiter.start()
    future = await limiter.submit("hello")
    await entered.wait()
    await limiter.stop()
    assert future.done()


async def test_rejected_transmission_does_not_increment_airtime() -> None:
    limiter = TxRateLimiter(transmit_callback=AsyncMock(return_value={"status": "error"}), history_file=None)
    limiter.start()
    try:
        future = await limiter.submit("hello")
        assert (await future)["status"] == "error"
        assert limiter.airtime_tracker.total_packets == 0
    finally:
        await limiter.stop()


def test_mqtt_publish_error_code_is_not_success() -> None:
    client = AsyncBridgeMQTTClient(MQTTConfig())
    client.is_connected = True
    client.client = SimpleNamespace(publish=MagicMock(return_value=SimpleNamespace(rc=4)))
    assert client.publish_safe("test/status", "{}") is False
    assert client.total_published == 0


async def test_tcp_raw_send_failure_propagates() -> None:
    bridge = bare_bridge()
    bridge.serial_adapter.send_raw_companion_frame = AsyncMock(return_value=False)
    assert await bridge.handle_tcp_companion_command(b"\x03", None) is False


def test_sdk_constructor_failure_does_not_select_memory_parser_as_hardware(monkeypatch) -> None:
    bridge = bare_bridge()

    def unavailable(**kwargs):
        raise ValueError("SDK initialization failed")

    monkeypatch.setattr("src.bridge_core.MeshcoreSDKAdapter", unavailable)
    with pytest.raises(RuntimeError, match="SDK"):
        MeshCoreBridge._create_serial_adapter(bridge)


def test_diagnostics_debug_cannot_enable_sdk_secret_hexdumps() -> None:
    logger = logging.getLogger("meshcore")
    old = logger.level
    root_old = logging.getLogger().level
    try:
        DiagnosticManager(SimpleNamespace()).set_log_level("DEBUG")
        assert logger.getEffectiveLevel() >= logging.INFO
    finally:
        logger.setLevel(old)
        logging.getLogger().setLevel(root_old)
