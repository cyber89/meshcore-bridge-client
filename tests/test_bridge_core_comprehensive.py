"""
Comprehensive Unit Tests for MeshCoreBridge (src/bridge_core.py).
Tests core lifecycle, duty cycle alerts, TCP companion commands, counter resets,
safe web event broadcasting, and subcomponent wiring.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bridge_core import MeshCoreBridge
from src.protocol_types import FrameHeader, MeshcoreFrame, PacketType, TextMessagePayload


@pytest.fixture
def mock_bridge() -> tuple[MeshCoreBridge, list[tuple[str, str, int]]]:
    loop = asyncio.new_event_loop()
    published: list[tuple[str, str, int]] = []

    with patch("src.bridge_core.MeshCoreWebServer"), patch("src.bridge_core.MeshCoreCompanionServer"):
        bridge = MeshCoreBridge(loop=loop)
        bridge.mqtt.is_connected = True
        bridge.mqtt.publish_safe = MagicMock(
            side_effect=lambda t, p, q=0, **kwargs: published.append((t, p, q))
        )
        bridge.serial_adapter.is_connected = True
        bridge.serial_adapter.send_message = AsyncMock(return_value={"status": "SENT"})
        yield bridge, published

    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()
    if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()


def test_bridge_properties_and_counters_reset(mock_bridge: Any) -> None:
    bridge, _ = mock_bridge

    # Test initial counters
    bridge.rx_count = 10
    bridge.tx_count = 5
    bridge.tx_error_count = 1
    bridge.err_count = 2

    res = bridge.reset_counters()
    assert bridge.rx_count == 0
    assert bridge.tx_count == 0
    assert bridge.tx_error_count == 0
    assert bridge.err_count == 0
    assert "nodes_reset" in res

    # Test property setters and getters
    bridge.mqtt_connected = False
    assert not bridge.mqtt_connected
    bridge.mqtt_connected = True
    assert bridge.mqtt_connected

    bridge.mqtt_reconnect_count = 42
    assert bridge.mqtt_reconnect_count == 42

    bridge.last_serial_activity = 12345.6
    assert bridge.last_serial_activity == 12345.6

    mock_sdk = MagicMock()
    bridge.mc = mock_sdk
    assert bridge.mc is mock_sdk


@pytest.mark.asyncio
async def test_bridge_duty_cycle_alert(mock_bridge: Any) -> None:
    bridge, published = mock_bridge
    mock_web = MagicMock()
    mock_web.broadcast_event = AsyncMock()
    bridge.web_server = mock_web
    bridge.running = True

    stats = {
        "hourly_duty_cycle_pct": 1.25,
        "hourly_limit_pct": 1.0,
        "warn_threshold_pct": 80.0,
        "hourly_used_ms": 45000,
    }

    bridge._on_duty_cycle_alert("critical", stats)
    await asyncio.sleep(0.02)

    # Check MQTT publication
    assert len(published) == 1
    topic, payload, qos = published[0]
    assert "alert" in topic
    assert '"level": "critical"' in payload
    assert '"status_level": "critical"' in payload

    # Check Web UI broadcast
    assert mock_web.broadcast_event.called


@pytest.mark.asyncio
async def test_bridge_tcp_companion_handling(mock_bridge: Any) -> None:
    bridge, _ = mock_bridge
    bridge.serial_adapter.send_raw_companion_frame = AsyncMock()

    # Empty payload is ignored
    await bridge.handle_tcp_companion_command(b"", None)
    bridge.serial_adapter.send_raw_companion_frame.assert_not_called()

    # Non-empty payload is forwarded to serial adapter
    test_frame = b"\x10\x20\x30\x40"
    await bridge.handle_tcp_companion_command(test_frame, None)
    bridge.serial_adapter.send_raw_companion_frame.assert_awaited_once_with(test_frame)


@pytest.mark.asyncio
async def test_bridge_broadcast_raw_companion_frame_rx(mock_bridge: Any) -> None:
    bridge, _ = mock_bridge
    mock_tcp = MagicMock()
    mock_tcp.broadcast_companion_frame = AsyncMock()
    bridge.tcp_server = mock_tcp
    bridge.running = True

    bridge._on_raw_companion_frame_rx(b"\xaa\xbb\xcc")
    await asyncio.sleep(0.01)

    mock_tcp.broadcast_companion_frame.assert_awaited_once_with(b"\xaa\xbb\xcc")


@pytest.mark.asyncio
async def test_bridge_on_mesh_event_routing(mock_bridge: Any) -> None:
    bridge, _ = mock_bridge
    bridge.rx_router.handle_event = MagicMock()

    # Simulate an incoming frame event
    header = FrameHeader(
        packet_type=PacketType.CHANNEL_MSG_RECV,
        seq_num=1,
        src_node_id=0x1234,
        dst_node_id=0xFFFF,
        hop_limit=3,
        payload_len=4,
    )
    frame = MeshcoreFrame(
        header=header,
        payload=TextMessagePayload(channel_idx=0, sender_alias="Node", text="Test"),
        raw_payload=b"Test",
        crc16=0,
        is_valid=True,
    )

    bridge.on_mesh_event(frame)
    bridge.rx_router.handle_event.assert_called_once_with(frame)


@pytest.mark.asyncio
async def test_bridge_on_mqtt_message_compatibility(mock_bridge: Any) -> None:
    bridge, _ = mock_bridge
    bridge.mqtt_dispatcher.handle_incoming = MagicMock()

    mock_msg = MagicMock()
    mock_msg.topic = "meshcore/tx"
    mock_msg.payload = b'{"text": "Hello Mesh", "to": "broadcast"}'

    bridge.on_mqtt_message(None, None, mock_msg)
    bridge.mqtt_dispatcher.handle_incoming.assert_called_once_with(
        "meshcore/tx", '{"text": "Hello Mesh", "to": "broadcast"}'
    )


@pytest.mark.asyncio
async def test_bridge_safe_web_broadcast_error_handling(mock_bridge: Any) -> None:
    bridge, _ = mock_bridge
    mock_web = MagicMock()
    mock_web.broadcast_event = AsyncMock(side_effect=RuntimeError("Web broadcast failed"))
    bridge.web_server = mock_web
    bridge.running = True

    # Should not raise exception
    bridge._broadcast_system_log({"type": "test_event"})
    await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)
