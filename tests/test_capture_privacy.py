"""Public RF capture must not reveal private CLI replies or consume waiters."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from meshcore.events import Event, EventType

from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate
from src.packet_buffer import PacketBuffer, PacketInput
from src.protocol_types import FrameHeader, MeshcoreFrame, PacketType

REMOTE = "fa" * 32
SECRET = "synthetic-capture-private-credential"


@pytest_asyncio.fixture
async def capture_bridge(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MeshCoreBridge]:
    bridge = MeshCoreBridge(loop=asyncio.get_running_loop())
    bridge.running = True
    bridge.node_registry.add_or_update(REMOTE, NodeContactUpdate(name="Privacy repeater", role="REPEATER"))
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


async def flush_tasks(bridge: MeshCoreBridge) -> None:
    for _ in range(10):
        pending = [task for task in bridge._background_tasks if not task.done()]
        if pending:
            await asyncio.gather(*pending)
        await asyncio.sleep(0)


def public_outputs(bridge: MeshCoreBridge) -> str:
    assert bridge.web_server is not None
    packets, _ = bridge.packet_buffer.get_packets()
    websocket = [call.args[0] for call in bridge.web_server.broadcast_event.call_args_list]
    mqtt = [call.args[1] for call in bridge.mqtt.publish_safe.call_args_list]
    return json.dumps([packets, websocket, mqtt], default=str)


def assert_secret_absent(bridge: MeshCoreBridge, secret: str = SECRET) -> None:
    assert secret not in public_outputs(bridge)
    assert secret.encode().hex() not in public_outputs(bridge)
    packets, _ = bridge.packet_buffer.get_packets()
    assert all(secret.encode() not in bytes.fromhex(packet["raw_hex"]) for packet in packets)
    assert secret not in bridge.packet_buffer.generate_json()
    assert secret not in bridge.packet_buffer.generate_csv()
    assert secret.encode() not in bridge.packet_buffer.generate_pcap()


@pytest.mark.parametrize("shape", ["sdk", "dict"])
async def test_secret_cli_response_stays_private(
    capture_bridge: MeshCoreBridge, monkeypatch: pytest.MonkeyPatch, shape: str,
) -> None:
    bridge = capture_bridge
    waiter: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
    waiter._command_sensitive = True  # type: ignore[attr-defined]
    waiter._command_tag = "af"  # type: ignore[attr-defined]
    bridge.admin_handler._cmd_waiters[REMOTE] = [waiter]
    notify = MagicMock(wraps=bridge.admin_handler.notify_command_response)
    monkeypatch.setattr(bridge.admin_handler, "notify_command_response", notify)
    original = {"pubkey_prefix": REMOTE[:12], "text": f"af|{SECRET}", "txt_type": 1,
                "sender_timestamp": 1791110000, "raw": SECRET.encode(),
                "nested": {"result": SECRET, "raw_hex": SECRET.encode().hex()}}
    event: Any = Event(EventType.CONTACT_MSG_RECV, original) if shape == "sdk" else {
        **original, "event_type": "direct",
    }
    bridge.on_mesh_event(event)
    await flush_tasks(bridge)
    assert waiter.done() and waiter.result()["text"] == SECRET
    assert notify.call_count == 1
    assert bridge.admin_handler._cmd_waiters == {}
    assert original["text"] == f"af|{SECRET}"
    assert_secret_absent(bridge)
    packets, total = bridge.packet_buffer.get_packets()
    assert total == 1
    assert packets[0]["raw_hex"] == ""


@pytest.mark.parametrize("text", [f"af|{SECRET}", SECRET, "654321"])
async def test_uncorrelated_cli_secret_is_not_public(
    capture_bridge: MeshCoreBridge, text: str,
) -> None:
    bridge = capture_bridge
    bridge.on_mesh_event(Event(EventType.CONTACT_MSG_RECV, {
        "pubkey_prefix": REMOTE[:12], "text": text, "txt_type": 1,
    }))
    await flush_tasks(bridge)
    assert_secret_absent(bridge, text)
    node = bridge.node_registry.get_contact(REMOTE)
    assert node is not None and node.battery_pct is None


async def test_non_sensitive_associated_admin_result_remains_visible(
    capture_bridge: MeshCoreBridge,
) -> None:
    bridge = capture_bridge
    waiter: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
    waiter._command_tag = "af"  # type: ignore[attr-defined]
    bridge.admin_handler._cmd_waiters[REMOTE] = [waiter]
    bridge.on_mesh_event(Event(EventType.CONTACT_MSG_RECV, {
        "pubkey_prefix": REMOTE[:12], "text": "af|22", "txt_type": 1,
    }))
    await flush_tasks(bridge)
    assert waiter.result()["text"] == "22"
    assert bridge.web_server is not None
    responses = [call.args[0] for call in bridge.web_server.broadcast_event.call_args_list
                 if call.args[0].get("type") == "repeater_response"]
    assert len(responses) == 1 and responses[0]["text"] == "22"


@pytest.mark.parametrize("txt_type", [0, 2])
async def test_ordinary_chat_text_and_raw_capture_remain_visible(
    capture_bridge: MeshCoreBridge, txt_type: int,
) -> None:
    bridge = capture_bridge
    client = "ac" * 32
    bridge.node_registry.add_or_update(client, NodeContactUpdate(name="Alice", role="CLIENT"))
    text = "af|Mensaje normal sin credenciales"
    bridge.on_mesh_event(SimpleNamespace(type=EventType.CONTACT_MSG_RECV, payload={
        "pubkey_prefix": client[:12], "text": text, "txt_type": txt_type,
    }, raw_data=text.encode()))
    await flush_tasks(bridge)
    packets, total = bridge.packet_buffer.get_packets()
    assert total == 1 and packets[0]["text"] == text
    assert bytes.fromhex(packets[0]["raw_hex"]) == text.encode()
    assert text in public_outputs(bridge)


@pytest.mark.parametrize("as_input", [False, True])
def test_packet_buffer_defends_alternative_cli_secret_ingress(as_input: bool) -> None:
    buffer = PacketBuffer()
    values = {"packet_type": "CONTACT_MSG_RECV", "text": SECRET,
              "raw_bytes": SECRET.encode(), "payload_dict": {"txt_type": 1, "nested": {"value": SECRET}}}
    packet = buffer.record(PacketInput(**values)) if as_input else buffer.record(**values)
    assert packet is not None
    assert SECRET not in json.dumps(packet.to_dict())
    assert packet.raw_bytes == b""
    assert SECRET.encode() not in buffer.generate_pcap()


@pytest.mark.parametrize("shape", ["sdk", "raw_frame"])
async def test_local_cli_secret_is_never_publicly_captured(
    capture_bridge: MeshCoreBridge, shape: str,
) -> None:
    bridge = capture_bridge
    event: Any
    if shape == "sdk":
        original = {"text": SECRET, "raw": SECRET.encode()}
        event = SimpleNamespace(type="CLI_REPLY", payload=original)
    else:
        event = MeshcoreFrame(
            FrameHeader(PacketType.CLI_REPLY, 1, 123, 456, 0, len(SECRET)),
            SECRET.encode(), SECRET.encode(), 0, True,
        )
    bridge.on_mesh_event(event)
    await flush_tasks(bridge)
    assert_secret_absent(bridge)
    if shape == "sdk":
        assert original["text"] == SECRET
