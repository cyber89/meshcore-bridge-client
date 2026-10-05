"""Route changes reach the registry through SDK dispatch, without mesh queries."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from meshcore.events import Event, EventType

from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.rx_router import RxEventRouter, RxRouterContext
from src.serial.sdk_adapter import MeshcoreSDKAdapter

REMOTE = "ab" * 32
LOCAL = "cd" * 32


@pytest_asyncio.fixture
async def route_router() -> AsyncIterator[RxEventRouter]:
    registry = NodeRegistry()
    registry.set_local_pubkey(LOCAL)
    registry.add_or_update(REMOTE, NodeContactUpdate(name="Route repeater", role="REPEATER"))
    serial = MeshcoreSDKAdapter("UNUSED_VIRTUAL")
    serial.is_connected = True
    serial.mc = SimpleNamespace(commands=SimpleNamespace(get_contact_by_key=AsyncMock(
        return_value=Event(EventType.NEXT_CONTACT, {
            "public_key": REMOTE, "out_path": "0002", "out_path_len": 2,
            "out_path_hash_mode": 0, "flags": 0,
        }),
    )))
    router = RxEventRouter(RxRouterContext(
        mqtt=MagicMock(), node_registry=registry, repeater_manager=MagicMock(),
        deduplicator=MagicMock(), serial_adapter=serial,
        web_server=SimpleNamespace(broadcast_event=AsyncMock()),
        loop=asyncio.get_running_loop(), background_tasks=set(),
        counters=SimpleNamespace(rx_count=0, tx_count=0, tx_error_count=0, err_count=0),
    ))
    try:
        yield router
    finally:
        tasks = list(router._ctx.background_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def settle(router: RxEventRouter) -> None:
    for _ in range(8):
        await asyncio.gather(*list(router._ctx.background_tasks))
        await asyncio.sleep(0)


async def test_path_update_reads_official_contact_and_broadcasts_once(route_router: RxEventRouter) -> None:
    router = route_router
    serial = router._ctx.serial_adapter
    router.handle_event(Event(EventType.PATH_UPDATE, {"public_key": REMOTE}))
    await settle(router)
    serial.mc.commands.get_contact_by_key.assert_awaited_once_with(bytes.fromhex(REMOTE))
    node = router._ctx.node_registry.get(REMOTE)
    assert node.out_path == "0002" and node.out_path_len == 2 and node.flags == 0
    assert node.role == "REPEATER"
    updates = [call.args[0] for call in router._ctx.web_server.broadcast_event.call_args_list
               if call.args[0].get("type") == "contact_updated"]
    assert len(updates) == 1 and updates[0]["contact"]["out_path"] == "0002"
    assert router._ctx.mqtt.publish_safe.call_count == 1  # original system event survives
    assert router._ctx.counters.rx_count == 0  # local notification is not a received RF packet


@pytest.mark.parametrize("result", [
    Event(EventType.ERROR, {"code": 2}),
    Event(EventType.NEXT_CONTACT, {"public_key": LOCAL, "out_path": "01", "out_path_len": 1}),
    Event(EventType.OK, {}),
])
async def test_bad_contact_reply_keeps_previous_route(route_router: RxEventRouter, result: Any) -> None:
    router = route_router
    router._ctx.node_registry.add_or_update(REMOTE, NodeContactUpdate(out_path="03", out_path_len=1))
    router._ctx.serial_adapter.mc.commands.get_contact_by_key.return_value = result
    router.handle_event(Event(EventType.PATH_UPDATE, {"public_key": REMOTE}))
    await settle(router)
    router._ctx.serial_adapter.mc.commands.get_contact_by_key.assert_awaited_once()
    assert router._ctx.node_registry.get(REMOTE).out_path == "03"
    assert not any(call.args[0].get("type") == "contact_updated"
                   for call in router._ctx.web_server.broadcast_event.call_args_list)


@pytest.mark.parametrize("key", [LOCAL, "bad", REMOTE[:12]])
async def test_local_or_incomplete_path_key_never_queries(route_router: RxEventRouter, key: str) -> None:
    route_router.handle_event(Event(EventType.PATH_UPDATE, {"public_key": key}))
    await settle(route_router)
    route_router._ctx.serial_adapter.mc.commands.get_contact_by_key.assert_not_awaited()


async def test_rx_log_preserves_zero_hashes_and_publishes_observation(route_router: RxEventRouter) -> None:
    router = route_router
    router.handle_event(Event(EventType.RX_LOG_DATA, {
        "adv_key": REMOTE, "path": "0002", "path_len": 2, "path_hash_size": 1,
        "route_typename": "FLOOD", "payload_typename": "ADVERT", "rssi": -90, "snr": 5,
    }))
    await settle(router)
    node = router._ctx.node_registry.get(REMOTE)
    assert node.last_rx_route is not None
    assert node.last_rx_route["count"] == 2 and node.last_rx_route["hashes"] == ("00", "02")
    assert node.role == "REPEATER" and node.last_rssi == -90
    assert router._ctx.counters.rx_count == 0  # log is not a second RF capture
    router._ctx.serial_adapter.mc.commands.get_contact_by_key.assert_not_awaited()
    updates = [call.args[0] for call in router._ctx.web_server.broadcast_event.call_args_list
               if call.args[0].get("type") == "contact_updated"]
    assert len(updates) == 1 and updates[0]["contact"]["last_rx_route"]["count"] == 2


async def test_local_rx_log_never_creates_remote_neighbor(route_router: RxEventRouter) -> None:
    route_router.handle_event(Event(EventType.RX_LOG_DATA, {
        "adv_key": LOCAL, "path": "0102", "path_len": 2, "path_hash_size": 1,
        "route_typename": "FLOOD", "payload_typename": "ADVERT",
    }))
    await settle(route_router)
    node = route_router._ctx.node_registry.get(LOCAL)
    assert node is None or node.last_rx_route is None
    assert not any(call.args[0].get("type") == "contact_updated"
                   for call in route_router._ctx.web_server.broadcast_event.call_args_list)
