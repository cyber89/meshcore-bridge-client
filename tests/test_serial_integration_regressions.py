"""Response ownership, cancellation and firmware-advertised channel capacity."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from meshcore.events import Event, EventType

from src.serial.sdk_adapter import MeshcoreSDKAdapter


def adapter():
    result = MeshcoreSDKAdapter("VIRTUAL", timeout_sec=0.05)
    result.is_connected = True
    result.mc = SimpleNamespace(
        cx=SimpleNamespace(send=AsyncMock()),
        commands=SimpleNamespace(get_time=AsyncMock(return_value=Event(EventType.CURRENT_TIME, {"time": 1}))),
        channels={}, self_info={"max_channels": 32}, disconnect=AsyncMock(),
    )
    return result


async def test_contacts_stream_owns_response_slot_until_end():
    serial = adapter()
    frames = []
    serial.set_companion_rx_callback(frames.append)
    raw = asyncio.create_task(serial.send_raw_companion_frame(b"\x04"))
    await asyncio.sleep(0)
    sdk = asyncio.create_task(serial.run_sdk_command("get_time"))
    serial._observe_companion_frame(b"\x02\x01\x00\x00\x00")
    serial._observe_companion_frame(b"\x80advert")
    serial._observe_companion_frame(b"\x03contact")
    await asyncio.sleep(0)
    assert not raw.done()
    serial.mc.commands.get_time.assert_not_awaited()
    serial._observe_companion_frame(b"\x04\x00\x00\x00\x00")
    assert await raw is True
    assert (await sdk).type == EventType.CURRENT_TIME
    assert [frame[0] for frame in frames] == [2, 128, 3, 4]


async def test_raw_timeout_does_not_resend_or_claim_confirmation():
    serial = adapter()
    assert await serial.send_raw_companion_frame(b"\x14") is False
    serial.mc.cx.send.assert_awaited_once()
    assert serial._raw_command_future is None
    assert not serial._command_lock.locked()


async def test_raw_firmware_error_is_not_success():
    serial = adapter()
    raw = asyncio.create_task(serial.send_raw_companion_frame(b"\x14"))
    await asyncio.sleep(0)
    serial._observe_companion_frame(b"\x01\x02")
    assert await raw is False


async def test_disconnect_settles_pending_raw_command():
    serial = adapter()
    raw = asyncio.create_task(serial.send_raw_companion_frame(b"\x14"))
    await asyncio.sleep(0)
    await serial.disconnect()
    assert await raw is False
    assert not serial._command_lock.locked()


async def test_all_advertised_channel_slots_are_queried():
    serial = adapter()

    async def get_channel(index):
        name = "Extra" if index == 31 else ""
        return Event(EventType.CHANNEL_INFO, {"channel_idx": index, "channel_name": name,
            "channel_secret": b"x" * 16 if name else bytes(16), "channel_hash": "11"})

    serial.mc.commands.get_channel = AsyncMock(side_effect=get_channel)
    channels = await serial.get_channels()
    assert serial.mc.commands.get_channel.await_count == 32
    assert any(channel["index"] == 31 for channel in channels)


async def test_channel_write_accepts_firmware_advertised_slot():
    serial = adapter()
    serial.mc.commands.set_channel = AsyncMock(return_value=Event(EventType.OK, {}))
    result = await serial.set_channel(31, "Extra", "11" * 16)
    assert result["status"] == "OK"
    serial.mc.commands.set_channel.assert_awaited_once()
    with pytest.raises(ValueError):
        await serial.set_channel(32, "Outside", "11" * 16)


async def test_cross_thread_sdk_callback_is_owned_and_cancelled_on_disconnect():
    serial = adapter()
    serial._loop = asyncio.get_running_loop()
    callbacks = {}
    serial.mc.subscribe = lambda kind, callback: callbacks.setdefault(kind, callback)
    entered = asyncio.Event()

    async def event_handler(kind, data):
        entered.set()
        await asyncio.Event().wait()

    serial._on_sdk_event = event_handler
    serial._register_event_handlers()
    await asyncio.to_thread(callbacks[EventType.BATTERY], Event(EventType.BATTERY, {"level": 4000}))
    await asyncio.wait_for(entered.wait(), 1)
    assert serial._background_tasks
    await serial.disconnect()
    assert not serial._background_tasks
