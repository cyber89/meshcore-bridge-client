"""Raw Companion commands only complete with their official reply type."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.serial.sdk_adapter import MeshcoreSDKAdapter


def adapter() -> MeshcoreSDKAdapter:
    result = MeshcoreSDKAdapter("VIRTUAL", timeout_sec=0.1)
    result.is_connected = True
    result.mc = SimpleNamespace(cx=SimpleNamespace(send=AsyncMock()), self_info={})
    return result


async def test_setter_ignores_battery_before_its_ok() -> None:
    serial = adapter()
    forwarded: list[bytes] = []
    serial.set_companion_rx_callback(forwarded.append)
    pending = asyncio.create_task(serial.send_raw_companion_frame(b"\x08Audit name"))
    try:
        await asyncio.sleep(0)
        serial._observe_companion_frame(bytes.fromhex("0ce40c00000000"))
        await asyncio.sleep(0)
        assert forwarded == []
        assert not pending.done()
        serial._observe_companion_frame(b"\x00")
        assert await pending is True
        assert forwarded == [b"\x00"]
        serial.mc.cx.send.assert_awaited_once_with(b"\x08Audit name")
    finally:
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.parametrize("command,reply", [
    (b"\x05", b"\x09\x01\x00\x00\x00"),
    (b"\x14", b"\x0c\xe4\x0c"),
    (b"\x16\x03", b"\x0ddevice"),
    (b"\x1f\x00", b"\x12channel"),
    (b"\x21", b"\x13signature-start"),
    (b"\x23", b"\x14signature"),
    (b"\x28", b"\x15gps:0"),
    (b"\x2b", b"\x17tuning"),
    (b"\x38\x01", b"\x18\x01stats"),
    (b"\x3b", b"\x19\x00\x00"),
    (b"\x3c", b"\x1aallowed-frequencies"),
    (b"\x40", b"\x1c"),
])
async def test_getter_requires_its_reply_not_generic_ok(command: bytes, reply: bytes) -> None:
    serial = adapter()
    forwarded: list[bytes] = []
    serial.set_companion_rx_callback(forwarded.append)
    pending = asyncio.create_task(serial.send_raw_companion_frame(command))
    try:
        await asyncio.sleep(0)
        serial._observe_companion_frame(b"\x00")
        await asyncio.sleep(0)
        assert not pending.done()
        assert forwarded == []
        serial._observe_companion_frame(reply)
        assert await pending is True
        assert forwarded == [reply]
    finally:
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.parametrize("reply", [b"\x01\x02", b"\x0f"])
async def test_error_or_disabled_is_a_failure(reply: bytes) -> None:
    serial = adapter()
    pending = asyncio.create_task(serial.send_raw_companion_frame(b"\x08name"))
    await asyncio.sleep(0)
    serial._observe_companion_frame(reply)
    assert await pending is False


async def test_unrelated_only_times_out_without_resending() -> None:
    serial = adapter()
    pending = asyncio.create_task(serial.send_raw_companion_frame(b"\x08name"))
    await asyncio.sleep(0)
    serial._observe_companion_frame(b"\x0c\xe4\x0c")
    assert await pending is False
    serial.mc.cx.send.assert_awaited_once()


async def test_contacts_stream_keeps_owner_after_unrelated_reply() -> None:
    serial = adapter()
    forwarded: list[bytes] = []
    serial.set_companion_rx_callback(forwarded.append)
    pending = asyncio.create_task(serial.send_raw_companion_frame(b"\x04"))
    try:
        await asyncio.sleep(0)
        for reply in (b"\x02start", b"\x03contact", b"\x0cbattery", b"\x80advert"):
            serial._observe_companion_frame(reply)
        await asyncio.sleep(0)
        assert not pending.done()
        serial._observe_companion_frame(b"\x04end")
        assert await pending is True
        assert forwarded == [b"\x02start", b"\x03contact", b"\x80advert", b"\x04end"]
    finally:
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
