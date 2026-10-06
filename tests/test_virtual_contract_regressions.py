"""The same virtual device state is observed through SDK and Companion reads."""

import struct
from types import SimpleNamespace
from typing import Any

import pytest
from meshcore.reader import MessageReader

from src.virtual_mesh_adapter import VirtualMeshAdapter


@pytest.mark.parametrize('target', ['channel_999', 'channel_-1', 'channel_bad', 'channel', 'channel_²'])
async def test_invalid_channel_alias_never_schedules_echo(target: str) -> None:
    adapter = VirtualMeshAdapter()
    adapter.is_connected = True
    try:
        result = await adapter.send_message('audit', target=target, channel_idx=0)
        assert result['status'] == 'ERROR'
        assert not adapter._background_tasks
    finally:
        await adapter.disconnect()


@pytest.mark.parametrize('channel', [0, 7])
async def test_valid_channel_alias_resolves_before_validation(channel: int) -> None:
    adapter = VirtualMeshAdapter()
    adapter.is_connected = True
    try:
        result = await adapter.send_message('audit', target=f'channel_{channel}', channel_idx=999)
        assert result['status'] == 'ok'
        assert result['channel'] == channel
    finally:
        await adapter.disconnect()


async def test_clock_set_get_raw_and_elapsed_time_share_virtual_rtc(monkeypatch: pytest.MonkeyPatch) -> None:
    tick = [100.0]
    monkeypatch.setattr('src.virtual_mesh_adapter.time.monotonic', lambda: tick[0])
    adapter = VirtualMeshAdapter()
    adapter.is_connected = True
    replies = []
    adapter.set_companion_rx_callback(replies.append)
    try:
        assert (await adapter.mc.commands.set_time(1704067200))['status'] == 'ok'
        tick[0] += 3.25
        assert (await adapter.mc.commands.get_time())['time'] == 1704067203
        assert await adapter.send_raw_companion_frame(b'\x05')
        assert struct.unpack('<BI', replies[-1]) == (9, 1704067203)
        assert await adapter.send_raw_companion_frame(b'\x06' + struct.pack('<I', 1704067210))
        assert replies[-1] == b'\x00'
        assert (await adapter.mc.commands.get_time())['time'] == 1704067210
    finally:
        await adapter.disconnect()


@pytest.mark.parametrize(('subtype', 'command'), [(0, 'get_stats_core'), (1, 'get_stats_radio'), (2, 'get_stats_packets')])
async def test_sdk_and_raw_statistics_are_same_snapshot(subtype: int, command: str) -> None:
    adapter = VirtualMeshAdapter()
    adapter.is_connected = True
    frames: list[bytes] = []
    events: list[Any] = []

    async def capture(event: Any) -> None:
        events.append(event)

    adapter.set_companion_rx_callback(frames.append)
    try:
        sdk = await getattr(adapter.mc.commands, command)()
        assert await adapter.send_raw_companion_frame(bytes([56, subtype]))
        reader = MessageReader(SimpleNamespace(dispatch=capture))
        await reader.handle_rx(bytearray(frames[-1]))
        assert events
        for key, value in events[-1].payload.items():
            assert sdk[key] == value
    finally:
        await adapter.disconnect()


async def test_self_info_and_battery_raw_reads_follow_sdk_setters() -> None:
    adapter = VirtualMeshAdapter()
    adapter.is_connected = True
    replies = []
    adapter.set_companion_rx_callback(replies.append)
    try:
        await adapter.mc.commands.set_name('Prueba ñ')
        await adapter.mc.commands.set_coords(-20.125, 30.75)
        await adapter.mc.commands.set_tx_power(-9)
        await adapter.mc.commands.set_radio(868.125, 125.0, 9, 7)
        assert await adapter.send_raw_companion_frame(b'\x01')
        info = replies[-1]
        assert info[0] == 5 and info[2] == 247
        assert struct.unpack('<ii', info[36:44]) == (-20125000, 30750000)
        assert struct.unpack('<II', info[48:56]) == (868125, 125000)
        assert tuple(info[56:58]) == (9, 7)
        assert info[58:].decode() == 'Prueba ñ'
        assert await adapter.send_raw_companion_frame(b'\x14')
        assert struct.unpack('<BHII', replies[-1])[1] == (await adapter.mc.commands.get_bat())['battery_mv']
    finally:
        await adapter.disconnect()
