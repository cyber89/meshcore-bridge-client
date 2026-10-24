"""Regressions for canonical chat targets, strict channels and durable MQTT admission."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.command_policy import CommandLedgerPolicy
from src.application.messaging import MessageService
from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.mqtt_dispatcher import MqttInboundDispatcher
from src.station_database import StationDatabase

PEER = "ab" * 32


@pytest.mark.parametrize("target", ["Alice", PEER[:12], PEER.upper()])
def test_chat_resolves_one_canonical_identity_before_enqueue(target: str) -> None:
    registry = NodeRegistry()
    registry.add_or_update(PEER, NodeContactUpdate(name="Alice", role="CLIENT"))
    result = MessageService(node_registry=registry).validate_tx_request("hola", target)
    assert result.is_valid
    assert result.clean_target == PEER


@pytest.mark.parametrize("channel", [1.9, 1.0, True, None, [], {}])
def test_noninteger_channels_are_rejected_before_radio(channel: object) -> None:
    result = MessageService().validate_tx_request("hola", "broadcast", channel)
    assert not result.is_valid
    assert result.error_code == "invalid_channel_index"


def test_ambiguous_name_is_not_admitted_to_chat() -> None:
    registry = NodeRegistry()
    for key in (PEER, "cd" * 32):
        registry.add_or_update(key, NodeContactUpdate(name="Alice", role="CLIENT"))
    result = MessageService(node_registry=registry).validate_tx_request("hola", "Alice")
    assert not result.is_valid


def test_sdk_advert_type_blocks_repeater_even_with_a_misleading_role() -> None:
    sdk = SimpleNamespace(contacts={PEER: {
        "public_key": PEER, "name": "Router", "type": 2, "role": "CLIENT",
    }})
    result = MessageService(mc_provider=lambda: sdk).validate_tx_request("hola", "Router")
    assert not result.is_valid
    assert result.error_code == "tx_to_repeater_forbidden"


def test_identified_command_fails_closed_without_database() -> None:
    reservation = CommandLedgerPolicy(None).reserve("mqtt", "one", "tx", {"text": "hola"})
    assert not reservation.admitted
    assert not reservation.is_legacy


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ["hola", '{"text":"hola"}'])
async def test_legacy_mqtt_defaults_to_broadcast_with_the_real_validator(body: str) -> None:
    future = asyncio.get_running_loop().create_future()
    future.set_result({"status": "sent"})
    limiter = SimpleNamespace(submit=AsyncMock(return_value=future), get_queue_depth=lambda: 0)
    context = SimpleNamespace(
        database=None, mqtt=MagicMock(), handle_admin=AsyncMock(), rate_limiter=limiter,
        message_service=MessageService(), loop=asyncio.get_running_loop(), background_tasks=set(),
    )
    dispatcher = MqttInboundDispatcher(context)
    try:
        await dispatcher._handle_tx_request(body)
        limiter.submit.assert_awaited_once()
        assert limiter.submit.await_args.kwargs["target"] is None
    finally:
        await dispatcher.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["Alice", PEER[:12]])
async def test_direct_send_persists_and_dispatches_the_same_full_key(tmp_path: Path, target: str) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    await asyncio.to_thread(database.initialize)
    registry = NodeRegistry()
    registry.add_or_update(PEER, NodeContactUpdate(name="Alice", role="CLIENT"))
    station = object.__new__(MeshCoreBridge)
    station.node_registry = registry
    station.database = database
    station.message_service = MessageService(node_registry=registry, database=database)
    station.serial_adapter = SimpleNamespace(is_connected=True, send_message=AsyncMock(return_value={"status": "sent"}))
    station.web_server = None
    station.mqtt = SimpleNamespace(publish_safe=MagicMock(return_value=False))
    station._tx_metrics_lock = asyncio.Lock()
    station.tx_count = station.tx_error_count = 0
    result = await station._execute_tx({"to": target, "text": "hola", "request_id": "canonical"})
    assert result["status"] == "sent"
    station.serial_adapter.send_message.assert_awaited_once_with(text="hola", target=PEER, channel_idx=0)
    history = await asyncio.to_thread(database.history, f"dm_{PEER}")
    assert len(history["messages"]) == 1
    assert history["messages"][0]["status"] == "sent"


@pytest.mark.asyncio
async def test_pending_admin_duplicate_cannot_dispatch_twice(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    await asyncio.to_thread(database.initialize)
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(command: dict[str, object]) -> dict[str, object]:
        started.set()
        await release.wait()
        return {"status": "ok"}

    context = SimpleNamespace(
        database=database, mqtt=MagicMock(), handle_admin=AsyncMock(side_effect=handler),
        rate_limiter=MagicMock(), loop=asyncio.get_running_loop(), background_tasks=set(),
    )
    dispatcher = MqttInboundDispatcher(context)
    body = json.dumps({"action": "status", "command_id": "same"})
    first = asyncio.create_task(dispatcher._handle_admin_request(body))
    try:
        await asyncio.wait_for(started.wait(), 1)
        await dispatcher._handle_admin_request(body)
        assert context.handle_admin.await_count == 1
    finally:
        release.set()
        await first
        await dispatcher.close()


@pytest.mark.asyncio
async def test_repeater_topic_uses_the_same_admin_ledger(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    await asyncio.to_thread(database.initialize)
    mqtt = SimpleNamespace(
        topic_admin_repeater="meshcore/admin/repeater", publish_safe=MagicMock(),
    )
    context = SimpleNamespace(
        database=database, mqtt=mqtt, handle_admin=AsyncMock(return_value={"status": "ok"}),
        rate_limiter=MagicMock(), loop=asyncio.get_running_loop(), background_tasks=set(),
    )
    dispatcher = MqttInboundDispatcher(context)
    body = json.dumps({"action": "status", "command_id": "same"})
    try:
        for _ in range(2):
            await dispatcher._process_mqtt_input(f"meshcore/admin/repeater/{PEER}/cmd", body)
        context.handle_admin.assert_awaited_once()
    finally:
        await dispatcher.close()


@pytest.mark.asyncio
async def test_ledger_reservation_runs_outside_the_event_loop(tmp_path: Path) -> None:
    class RecordingDatabase(StationDatabase):
        worker_ident: int | None = None

        def reserve_command(self, *args: str, **kwargs: str) -> tuple[bool, str, dict[str, object] | None]:
            self.worker_ident = threading.get_ident()
            return super().reserve_command(*args, **kwargs)

    database = RecordingDatabase(tmp_path / "station.sqlite3")
    await asyncio.to_thread(database.initialize)
    policy = CommandLedgerPolicy(database)
    await policy.reserve_async("mqtt", "one", "tx", {"text": "hola"})
    assert database.worker_ident != threading.get_ident()
