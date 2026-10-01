"""Raw Companion chat invariants, local-response isolation and SDK arbitration."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.serial.sdk_adapter import MeshcoreSDKAdapter
from src.tcp_companion_server import MeshCoreCompanionServer


def adapter() -> MeshcoreSDKAdapter:
    registry = NodeRegistry()
    registry.set_local_pubkey("ab" * 32)
    registry.add_or_update("cd" * 32, NodeContactUpdate(role="REPEATER"))
    result = MeshcoreSDKAdapter("VIRTUAL", node_registry=registry)
    result.is_connected = True
    async def reply(data: bytes) -> None:
        result._observe_companion_frame(b"\x00")
    result.mc = SimpleNamespace(cx=SimpleNamespace(send=AsyncMock(side_effect=reply)), self_info={"public_key": "ab" * 32})
    return result


def raw_message(key: str, message_type: int = 0) -> bytes:
    # Official MessagingCommands.send_msg/send_cmd: opcode,type,attempt,timeLE,prefix6,text.
    return bytes([2, message_type, 0]) + (0).to_bytes(4, "little") + bytes.fromhex(key)[:6] + b"test"


@pytest.mark.asyncio
@pytest.mark.parametrize("key,message_type", [("ab" * 32, 0), ("ab" * 32, 1), ("cd" * 32, 0)])
async def test_tcp_raw_chat_cannot_reach_local_or_repeater(key: str, message_type: int) -> None:
    serial = adapter()
    bridge = SimpleNamespace(serial_adapter=serial, node_registry=serial.node_registry, tcp_server=SimpleNamespace(send_frame_to_client=AsyncMock()))
    await MeshCoreBridge.handle_tcp_companion_command(bridge, raw_message(key, message_type), object())
    serial.mc.cx.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_raw_repeater_cli_admin_remains_permitted() -> None:
    serial = adapter()
    assert await serial.send_raw_companion_frame(raw_message("cd" * 32, 1))
    serial.mc.cx.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_raw_transport_cannot_send_while_sdk_owns_companion_response_slot() -> None:
    serial = adapter()
    await serial._command_lock.acquire()
    pending = asyncio.create_task(serial.send_raw_companion_frame(b"\x14"))
    try:
        await asyncio.sleep(0)
        serial.mc.cx.send.assert_not_awaited()
    finally:
        serial._command_lock.release()
        await asyncio.wait_for(pending, timeout=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [b"\x00", b"\x01\x02", b"\x05internal-self-info", b"\x0eprivate-key-bytes"])
async def test_internal_sdk_replies_are_not_broadcast_to_tcp_peers(reply: bytes) -> None:
    tasks: set[asyncio.Task[object]] = set()
    broadcast = AsyncMock()
    bridge = SimpleNamespace(tcp_server=SimpleNamespace(broadcast_companion_frame=broadcast), running=True, _add_background_task=tasks.add)
    MeshCoreBridge._on_raw_companion_frame_rx(bridge, reply)
    if tasks:
        await asyncio.gather(*tasks)
    broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsolicited_companion_push_is_still_broadcast() -> None:
    tasks: set[asyncio.Task[object]] = set()
    broadcast = AsyncMock()
    bridge = SimpleNamespace(tcp_server=SimpleNamespace(broadcast_companion_frame=broadcast), running=True, _add_background_task=tasks.add)
    bridge._schedule_background = lambda factory: tasks.add(asyncio.create_task(factory()))
    MeshCoreBridge._on_raw_companion_frame_rx(bridge, b"\x80advert")
    await asyncio.gather(*tasks)
    broadcast.assert_awaited_once_with(b"\x80advert")


@pytest.mark.asyncio
async def test_tcp_server_zero_length_command_does_not_dispatch() -> None:
    handler = AsyncMock()
    server = MeshCoreCompanionServer(SimpleNamespace(handle_tcp_companion_command=handler))
    await server._dispatch_companion_command(b"", object())
    handler.assert_not_awaited()


async def test_firmware_error_is_forwarded_once_without_synthetic_duplicate() -> None:
    owner = object()
    server = MeshCoreCompanionServer(SimpleNamespace())
    server.send_frame_to_client = AsyncMock()

    async def rejected(payload, writer):
        server.note_response_received(writer)
        await server.send_frame_to_client(writer, b"\x01\x02")
        return False

    server.bridge.handle_tcp_companion_command = rejected
    await server._dispatch_companion_command(b"\x14", owner)
    server.send_frame_to_client.assert_awaited_once_with(owner, b"\x01\x02")
