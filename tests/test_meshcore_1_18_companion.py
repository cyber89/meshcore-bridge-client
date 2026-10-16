"""Companion 1.18 responses must keep their transaction owner and reply type."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.protocol_types import CommandType, PacketType
from src.serial.sdk_adapter import MeshcoreSDKAdapter


def test_local_cli_opcode_matches_official_companion_v14() -> None:
    assert CommandType.RUN_CLI_COMMAND == 66
    assert PacketType.CLI_REPLY == 29


@pytest.mark.parametrize("reply,success", [(b"\x1d> 868.000", True), (b"\x01\x02", False), (b"\x0f", False)])
async def test_cli_transaction_accepts_only_cli_reply_or_error(reply: bytes, success: bool) -> None:
    adapter = MeshcoreSDKAdapter("VIRTUAL", timeout_sec=0.1)
    adapter.is_connected = True
    adapter.mc = SimpleNamespace(cx=SimpleNamespace(send=AsyncMock()), self_info={})
    forwarded: list[bytes] = []
    adapter.set_companion_rx_callback(forwarded.append)
    command = b"\x42get freq"
    pending = asyncio.create_task(adapter.send_raw_companion_frame(command))
    try:
        await asyncio.sleep(0)
        adapter._observe_companion_frame(b"\x00")
        # A push is delivered asynchronously without completing the CLI command.
        push = b"\x8c\x00\x01\x00\x00\x00payload"
        adapter._observe_companion_frame(push)
        await asyncio.sleep(0)
        assert not pending.done()
        assert forwarded == [push]
        adapter._observe_companion_frame(reply)
        assert await pending is success
        assert forwarded == [push, reply]
        adapter.mc.cx.send.assert_awaited_once_with(command)
    finally:
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


async def test_cli_timeout_does_not_retry_or_report_ok() -> None:
    adapter = MeshcoreSDKAdapter("VIRTUAL", timeout_sec=0.01)
    adapter.is_connected = True
    adapter.mc = SimpleNamespace(cx=SimpleNamespace(send=AsyncMock()), self_info={})
    assert await adapter.send_raw_companion_frame(b"\x42get freq") is False
    adapter.mc.cx.send.assert_awaited_once()
