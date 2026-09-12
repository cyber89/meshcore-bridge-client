"""
Unit tests for LocalConfigExecutor, TracerouteExecutor, and RepeaterAdminExecutor.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import config
from src.admin import (
    LocalConfigExecutor,
    RemoteRepeaterRequest,
    RepeaterAdminExecutor,
    TracerouteExecutor,
    WaiterRegistry,
)
from src.admin_handler import AdminContext
from src.contact_manager import NodeContactUpdate, NodeRegistry


class MockRadioCommands:
    def __init__(self) -> None:
        self.send_appstart = AsyncMock(return_value={"public_key": "aabbccdd11223344", "name": "LocalNode"})
        self.send_device_query = AsyncMock(return_value={"hardware_board": "Heltec V3", "max_tx_power": 22})
        self.get_radio_params = AsyncMock(return_value={"freq": 915.0, "tx_power": 20})
        self.get_battery_level = AsyncMock(return_value={"battery_pct": 95, "voltage": 4.1})
        self.get_stats_core = AsyncMock(return_value={"rx_packets": 10, "tx_packets": 5})
        self.get_stats_radio = AsyncMock(return_value={"noise_floor": -115})
        self.get_self_telemetry = AsyncMock(return_value={"temperature_c": 24.5, "humidity_pct": 50})
        self.set_name = MagicMock(return_value=None)
        self.set_radio_params = MagicMock(return_value=None)
        self.set_coordinates = MagicMock(return_value=None)
        self.send_trace = AsyncMock(return_value=True)


class MockMC:
    def __init__(self) -> None:
        self.commands = MockRadioCommands()
        self.self_info = {
            "public_key": "aabbccdd11223344",
            "name": "LocalStation",
            "adv_lat": 40.7128,
            "adv_lon": -74.0060,
            "altitude": 10,
            "tx_power": 20,
            "radio_freq": 915.0,
            "sf": 7,
            "bw": 125,
            "cr": 5,
        }


@pytest.fixture
def admin_context(tmp_path: Any) -> tuple[AdminContext, MockMC, NodeRegistry, list[tuple[str, str, int]]]:
    registry = NodeRegistry()
    registry.set_local_pubkey("aabbccdd11223344")

    mock_mc = MockMC()
    published_msgs: list[tuple[str, str, int]] = []

    def mock_publish(topic: str, payload: str, qos: int = 0) -> None:
        published_msgs.append((topic, payload, qos))

    mock_repeater_mgr = MagicMock()
    mock_repeater_mgr.build_repeater_command_payload.side_effect = lambda action, p: f"{action}={list(p.values())[0]}" if p else action
    mock_repeater_mgr.get_repeater.return_value = None

    mock_mqtt = MagicMock()
    mock_mqtt.publish_safe = mock_publish

    execute_tx = AsyncMock(return_value={"status": "dispatched"})

    ctx = AdminContext(
        mc_provider=lambda: mock_mc,
        node_registry=registry,
        repeater_manager=mock_repeater_mgr,
        mqtt=mock_mqtt,
        execute_tx=execute_tx,
        web_server=None,
        start_time=time.time() - 100,
    )
    return ctx, mock_mc, registry, published_msgs


def test_local_config_executor_get_config(admin_context: Any) -> None:
    ctx, mock_mc, registry, published = admin_context
    local_cfg = {"name": "TestLocal", "frequency": 915.0}

    executor = LocalConfigExecutor(
        ctx=ctx,
        local_config=local_cfg,
        init_time=time.time() - 50,
        publish_safe=lambda t, p, q: published.append((t, p, q)),
    )

    cfg = executor.get_local_config()
    assert cfg["public_key"] == "aabbccdd11223344"
    assert cfg["name"] == "LocalStation"
    assert cfg["latitude"] == 40.7128
    assert cfg["longitude"] == -74.0060
    assert cfg["tx_power"] == 20
    assert "uptime_str" in cfg
    assert "min_tx_power" in cfg
    assert "max_tx_power" in cfg


def test_local_config_executor_callable_self_info(admin_context: Any) -> None:
    ctx, mock_mc, registry, published = admin_context
    info_dict = {"public_key": "ffeeddcc11223344", "name": "CallableNode"}
    mock_mc.self_info = lambda: info_dict

    executor = LocalConfigExecutor(
        ctx=ctx,
        local_config={},
        init_time=time.time(),
        publish_safe=lambda t, p, q: None,
    )

    cfg = executor.get_local_config()
    assert cfg["public_key"] == "ffeeddcc11223344"
    assert cfg["name"] == "CallableNode"


@pytest.mark.asyncio
async def test_local_config_executor_set_local_config(admin_context: Any) -> None:
    ctx, mock_mc, registry, published = admin_context
    local_cfg = {"name": "OldName", "public_key": "aabbccdd11223344"}

    executor = LocalConfigExecutor(
        ctx=ctx,
        local_config=local_cfg,
        init_time=time.time(),
        publish_safe=lambda t, p, q: published.append((t, p, q)),
    )

    res: dict[str, Any] = {}
    admin_data = {
        "params": {
            "name": "NewStationName",
            "tx_power": 22,
            "frequency": 915.5,
            "latitude": 37.7749,
            "longitude": -122.4194,
        }
    }

    result = await executor.set_local_config(admin_data, res, mock_mc)
    assert result["status"] == "ok"
    assert result["applied"]["name"] == "NewStationName"
    assert result["applied"]["tx_power"] == 22
    assert result["applied"]["frequency"] == 915.5

    # Check that node registry was updated for local pubkey
    local_node = registry.get_by_key_or_prefix("aabbccdd11223344")
    assert local_node is not None
    assert local_node.name == "NewStationName"
    assert local_node.role == "LOCAL"

    # Check MQTT publication
    assert len(published) > 0
    assert any(p[0] == config.TOPIC_ADMIN_STAT for p in published)


@pytest.mark.asyncio
async def test_local_config_executor_fetch_device_config_cooldown(admin_context: Any) -> None:
    ctx, mock_mc, registry, published = admin_context
    local_cfg = {"name": "Initial", "public_key": "aabbccdd11223344"}

    executor = LocalConfigExecutor(
        ctx=ctx,
        local_config=local_cfg,
        init_time=time.time(),
        publish_safe=lambda t, p, q: None,
    )

    # First fetch executes queries
    await executor.fetch_device_config()
    assert mock_mc.commands.send_appstart.call_count == 1

    # Second fetch without force respects 30s cooldown and does not call again
    await executor.fetch_device_config(force=False)
    assert mock_mc.commands.send_appstart.call_count == 1

    # Fetch with force=True bypasses cooldown
    await executor.fetch_device_config(force=True)
    assert mock_mc.commands.send_appstart.call_count == 2


def test_traceroute_executor_path_parsing(admin_context: Any) -> None:
    ctx, mock_mc, registry, published = admin_context
    executor = TracerouteExecutor(
        ctx=ctx,
        get_local_config=lambda: {},
        publish_safe=lambda t, p, q: None,
    )

    assert executor._parse_path_list("node1, node2, node3") == ["node1", "node2", "node3"]
    assert executor._parse_path_list(["0x1234", "0x5678"]) == ["0x1234", "0x5678"]
    assert executor._parse_path_list(None) == []


def test_traceroute_executor_format_trace_hops(admin_context: Any) -> None:
    ctx, mock_mc, registry, published = admin_context
    # Add a node to registry to test prefix matching
    registry.add_or_update("abcdef1234567890", NodeContactUpdate(name="Relay1"))

    executor = TracerouteExecutor(
        ctx=ctx,
        get_local_config=lambda: {},
        publish_safe=lambda t, p, q: None,
    )

    # Valid hex path
    hops_str, flags = executor._format_trace_hops(["0xABCD", "1234"])
    assert hops_str is not None
    assert "abcd" in hops_str
    assert "1234" in hops_str

    # Registry lookup fallback
    hops_str2, flags2 = executor._format_trace_hops(["abcdef12"])
    assert hops_str2 is not None
    assert "abcd" in hops_str2
    assert flags2 == 1

    # Empty path
    assert executor._format_trace_hops([]) == (None, 0)


@pytest.mark.asyncio
async def test_traceroute_executor_execution(admin_context: Any) -> None:
    ctx, mock_mc, registry, published = admin_context
    mock_web = MagicMock()
    mock_web.broadcast_event = AsyncMock()
    ctx.web_server = mock_web

    executor = TracerouteExecutor(
        ctx=ctx,
        get_local_config=lambda: {"latitude": 40.0, "longitude": -3.0},
        publish_safe=lambda t, p, q: published.append((t, p, q)),
    )

    admin_data = {"path": "0x1234, 0x5678"}
    res: dict[str, Any] = {}

    out = await executor.execute(admin_data, "traceroute", "target_node_xyz", res, mock_mc)
    assert out["action"] == "traceroute"
    assert out["target_node"] == "target_node_xyz"
    assert out["total_hops"] >= 1
    assert "hops_breakdown" in out
    assert mock_mc.commands.send_trace.called
    assert mock_web.broadcast_event.called

    # Check MQTT publications
    topics = [p[0] for p in published]
    assert any("trace" in t for t in topics)
    assert config.TOPIC_ADMIN_STAT in topics


@pytest.mark.asyncio
async def test_repeater_admin_executor_client_rejected(admin_context: Any) -> None:
    ctx, mock_mc, registry, published = admin_context
    # Register target node as CLIENT with standard name
    registry.add_or_update("1122334455667788", NodeContactUpdate(name="AliceMobile", role="CLIENT"))

    waiters = WaiterRegistry(cmd_waiters={}, ping_waiters={})
    executor = RepeaterAdminExecutor(
        ctx=ctx,
        waiters=waiters,
        publish_safe=lambda t, p, q: published.append((t, p, q)),
        resolve_target=lambda t, ch: t,
        wait_for_repeater_response=AsyncMock(return_value=None),
    )

    req = RemoteRepeaterRequest(
        admin_data={},
        action="reboot",
        req_id="req_123",
        target_node="1122334455667788",
    )

    res = await executor.execute(req)
    assert res["status"] == "error"
    assert "exclusivos para repetidores" in res["message"]


@pytest.mark.asyncio
async def test_repeater_admin_executor_batch_config(admin_context: Any) -> None:
    ctx, mock_mc, registry, published = admin_context
    # Register node as REPEATER
    registry.add_or_update("2233445566778899", NodeContactUpdate(name="R-Mountain", role="REPEATER"))

    waiters = WaiterRegistry(cmd_waiters={}, ping_waiters={})
    executor = RepeaterAdminExecutor(
        ctx=ctx,
        waiters=waiters,
        publish_safe=lambda t, p, q: published.append((t, p, q)),
        resolve_target=lambda t, ch: t,
        wait_for_repeater_response=AsyncMock(return_value=None),
    )

    req = RemoteRepeaterRequest(
        admin_data={
            "params": {
                "tx_power": 22,
                "lat": 40.5,
                "lon": -3.5,
            }
        },
        action="remote_repeater_set_config",
        req_id="batch_01",
        target_node="2233445566778899",
        password="secretpassword",
    )

    res = await executor.execute(req)
    assert "dispatched_commands" in res
    assert len(res["dispatched_commands"]) >= 2
    # Verify execute_tx was called with password login and set commands
    assert ctx.execute_tx.call_count >= 2
