"""Reject non-finite metrics and preserve coordinate/TTL semantics."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from meshcore.events import Event, EventType

import src.deduplicator as dedup_module
from src.contact_manager import NodeRegistry
from src.deduplicator import PacketDeduplicator
from src.routers.advert_handler import AdvertHandler
from src.routers.base import RxMeta
from src.routers.telemetry_handler import TelemetryHandler
from src.rx_router import RxEventRouter
from src.shared_utils import clean_numeric_value

KEY = "ab" * 32


def _meta(event_type: str) -> RxMeta:
    return RxMeta(event_type, event_type, KEY, "Alice", "", 0, 0, -80, 8.0, 0, False)


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        node_registry=NodeRegistry(), mqtt=MagicMock(), web_server=None,
        serial_adapter=MagicMock(), repeater_manager=MagicMock(),
        deduplicator=SimpleNamespace(is_duplicate=AsyncMock(return_value=False)),
        loop=asyncio.get_running_loop(), background_tasks=set(),
        counters=SimpleNamespace(rx_count=0, tx_count=0, tx_error_count=0, err_count=0),
        admin_handler=MagicMock(), packet_buffer=None, bridge=None,
        last_rx_rssi=-80, last_rx_snr=8.0,
        register_task=None,
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 10 ** 400, "9" * 400])
def test_nonfinite_numeric_input_is_missing_not_a_metric(value: object) -> None:
    assert clean_numeric_value(value) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_nonfinite_rf_log_cannot_poison_previous_metrics(value: float) -> None:
    ctx = _context()
    # Strategies receive the router, which owns passive route observations.
    router = RxEventRouter(ctx)
    await TelemetryHandler().handle(router, {"rssi": value, "snr": value}, _meta("RX_LOG_DATA"), None)
    assert ctx.last_rx_rssi == -80
    assert ctx.last_rx_snr == 8.0


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_nonfinite_sdk_ingress_is_rejected_without_router_exception(value: float) -> None:
    ctx = _context()
    router = RxEventRouter(ctx)
    router.handle_event(Event(EventType.RX_LOG_DATA, {"rssi": value, "snr": value}))
    if ctx.background_tasks:
        await asyncio.gather(*list(ctx.background_tasks))
    assert ctx.counters.err_count == 0
    assert ctx.last_rx_rssi == -80
    assert ctx.last_rx_snr == 8.0


@pytest.mark.asyncio
@pytest.mark.parametrize("lat,lon", [(0, 30), (30, 0), (-90, -180), (90, 180)])
async def test_advert_accepts_equator_meridian_and_coordinate_boundaries(lat: float, lon: float) -> None:
    registry = NodeRegistry()
    ctx = SimpleNamespace(_ctx=SimpleNamespace(node_registry=registry), _handle_mesh_telemetry_msg=MagicMock())
    raw = {"public_key": KEY, "adv_name": "Alice", "type": 1, "adv_lat": lat, "adv_lon": lon}
    await AdvertHandler().handle(ctx, raw, _meta("CONTACT"), raw)
    node = registry.get(KEY)
    assert (node.latitude, node.longitude) == (lat, lon)


@pytest.mark.asyncio
@pytest.mark.parametrize("lat,lon", [(0, 30), (30, 0), (-90, -180), (90, 180)])
async def test_sdk_advert_coordinates_survive_presence_and_telemetry_normalization(lat: float, lon: float) -> None:
    ctx = _context()
    ctx.repeater_manager.parse_repeater_telemetry_or_response.return_value = {}
    raw = {"public_key": KEY, "adv_name": "Alice", "type": 1, "adv_lat": lat, "adv_lon": lon}
    router = RxEventRouter(ctx)
    router.handle_event(Event(EventType.NEW_CONTACT, raw))
    if ctx.background_tasks:
        await asyncio.gather(*list(ctx.background_tasks))
    node = ctx.node_registry.get(KEY)
    assert (node.latitude, node.longitude) == (lat, lon)
    assert ctx.counters.err_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("lat,lon", [(95, 30), (-95, 30), (30, 181), (30, -181), (float("nan"), 30), (float("inf"), 30), (0, 0)])
async def test_invalid_or_firmware_absent_advert_location_is_not_registered(lat: float, lon: float) -> None:
    ctx = _context()
    ctx.repeater_manager.parse_repeater_telemetry_or_response.return_value = {}
    raw = {"public_key": KEY, "adv_name": "Alice", "type": 1, "adv_lat": lat, "adv_lon": lon}
    router = RxEventRouter(ctx)
    router.handle_event(Event(EventType.NEW_CONTACT, raw))
    if ctx.background_tasks:
        await asyncio.gather(*list(ctx.background_tasks))
    node = ctx.node_registry.get(KEY)
    if lat == 0 and lon == 0:
        assert node.latitude is None and node.longitude is None
    elif not -90 <= lat <= 90:
        assert node.latitude is None
    else:
        assert node.longitude is None
    assert ctx.counters.err_count == 0


@pytest.mark.asyncio
async def test_nonfinite_advert_battery_does_not_abort_contact_import() -> None:
    ctx = _context()
    raw = {"public_key": KEY, "adv_name": "Alice", "type": 1, "battery": float("inf")}
    router = RxEventRouter(ctx)
    router.handle_event(Event(EventType.NEW_CONTACT, raw))
    if ctx.background_tasks:
        await asyncio.gather(*list(ctx.background_tasks))
    assert ctx.counters.err_count == 0
    assert ctx.node_registry.get(KEY).battery_pct is None


@pytest.mark.asyncio
@pytest.mark.parametrize("wall_delta,mono_delta,duplicate", [(-900, 61, False), (100000, 1, True)])
async def test_dedup_ttl_uses_elapsed_time_despite_wall_clock_jump(monkeypatch: pytest.MonkeyPatch, wall_delta: float, mono_delta: float, duplicate: bool) -> None:
    wall, elapsed = [1000.0], [10.0]
    monkeypatch.setattr(dedup_module, "time", SimpleNamespace(time=lambda: wall[0], monotonic=lambda: elapsed[0]))
    dedup = PacketDeduplicator(window_seconds=60)
    assert not await dedup.is_duplicate("packet")
    wall[0] += wall_delta
    elapsed[0] += mono_delta
    assert await dedup.is_duplicate("packet") is duplicate
    assert dedup.window_seconds == 60
