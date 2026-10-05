"""SELF_INFO int8 power must survive adapter, RX routing and configuration reads."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from meshcore.events import Event, EventType

from src.bridge_core import MeshCoreBridge
from src.protocol_types import normalize_tx_power
from src.serial.sdk_adapter import MeshcoreSDKAdapter
from tests.test_local_config_save_roundtrip import station


@pytest_asyncio.fixture
async def power_bridge(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MeshCoreBridge]:
    bridge = MeshCoreBridge(loop=asyncio.get_running_loop())
    bridge.running = True
    assert isinstance(bridge.serial_adapter, MeshcoreSDKAdapter)
    bridge.mqtt.publish_safe = MagicMock(return_value=True)
    assert bridge.web_server is not None
    monkeypatch.setattr(bridge.web_server, "broadcast_event", AsyncMock())
    try:
        yield bridge
    finally:
        tasks = list(bridge._background_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        bridge.web_server.tile_service.close()


@pytest.mark.parametrize("raw_power,expected", [(247, -9), (-9, -9), (0, 0), (30, 30)])
async def test_sdk_self_info_normalizes_without_mutating_private_payload(
    power_bridge: MeshCoreBridge, raw_power: int, expected: int,
) -> None:
    bridge = power_bridge
    adapter = bridge.serial_adapter
    assert isinstance(adapter, MeshcoreSDKAdapter)
    payload = {"public_key": "cd" * 32, "name": "Local power", "tx_power": raw_power}
    original = deepcopy(payload)
    adapter.mc = SimpleNamespace(self_info=payload, _self_info=payload)
    bridge.admin_handler._local_config["tx_power"] = -9
    await adapter._handle_self_info(Event(EventType.SELF_INFO, payload))
    await asyncio.gather(*list(bridge._background_tasks))
    assert adapter.self_info["tx_power"] == expected
    assert bridge.admin_handler._local_config["tx_power"] == expected
    assert bridge.admin_handler.get_local_config()["tx_power"] == expected
    assert payload == original
    assert adapter.self_info is not payload


@pytest.mark.parametrize("raw_power", [None, True, 3.5, "247", 256, -129])
async def test_missing_or_invalid_sdk_power_does_not_invent_a_value(
    power_bridge: MeshCoreBridge, raw_power: Any,
) -> None:
    bridge = power_bridge
    adapter = bridge.serial_adapter
    assert isinstance(adapter, MeshcoreSDKAdapter)
    adapter.self_info = {"tx_power": -9}
    bridge.admin_handler._local_config["tx_power"] = -9
    payload = {"public_key": "cd" * 32, "name": "Local power", "tx_power": raw_power}
    adapter.mc = SimpleNamespace(self_info=payload, _self_info=payload)
    original = deepcopy(payload)
    await adapter._handle_self_info(Event(EventType.SELF_INFO, payload))
    await asyncio.gather(*list(bridge._background_tasks))
    expected = None if raw_power is None else -9
    assert adapter.self_info["tx_power"] == expected
    assert bridge.admin_handler._local_config["tx_power"] == expected
    assert bridge.admin_handler.get_local_config()["tx_power"] == expected
    assert payload == original


@pytest.mark.parametrize("raw_power,expected", [(247, -9), (-9, -9), (0, 0), (30, 30), (None, None)])
def test_direct_config_read_preserves_signed_and_unknown_power(raw_power: Any, expected: Any) -> None:
    _router, admin, mc, _adapter, _physical = station()
    mc.self_info["tx_power"] = raw_power
    original = deepcopy(mc.self_info)
    assert admin.get_local_config()["tx_power"] == expected
    assert mc.self_info == original


def test_adapter_initial_snapshot_and_sdk_fallback_never_modify_source() -> None:
    payload = {"tx_power": 247, "max_tx_power": 30}
    adapter = MeshcoreSDKAdapter(port="UNUSED_TEST_PORT")
    adapter.mc = SimpleNamespace(self_info=payload)
    assert adapter.self_info["tx_power"] == -9
    assert adapter.self_info["max_tx_power"] == 30
    assert adapter.self_info is adapter.self_info
    assert payload == {"tx_power": 247, "max_tx_power": 30}
    adapter.self_info = payload
    assert adapter.self_info["tx_power"] == -9
    assert adapter.self_info is not payload
    assert payload["tx_power"] == 247


@pytest.mark.parametrize("raw_power,expected", [
    (-128, -128), (127, 127), (128, -128), (255, -1), (247, -9),
    (None, None), (True, None), ("247", None), (3.5, None), (256, None), (-129, None),
])
def test_normalize_tx_power_wire_values_without_hardware_clamping(raw_power: Any, expected: Any) -> None:
    assert normalize_tx_power(raw_power) == expected
