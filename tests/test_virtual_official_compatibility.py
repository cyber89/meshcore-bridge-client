"""Virtual regressions use the real SDK reader for the advertised wire subset."""

import asyncio
from types import SimpleNamespace

import pytest
from meshcore import EventType
from meshcore.reader import MessageReader

from src.serial.raw_framing import RawSerialFramingAdapter
from src.virtual_mesh_adapter import VirtualMeshAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,args", [
    ("set_channel", (1, "Test", "")),
    ("delete_channel", (1,)),
    ("add_contact", ({"public_key": "ab" * 32},)),
    ("remove_contact", ("ab" * 32,)),
])
async def test_memory_raw_adapter_does_not_confirm_unimplemented_operations(operation, args):
    adapter = RawSerialFramingAdapter("VIRTUAL")
    response = await getattr(adapter, operation)(*args)
    assert response["status"] == "NOT_SUPPORTED"


@pytest.mark.asyncio
async def test_virtual_disconnect_cancels_all_its_tasks():
    adapter = VirtualMeshAdapter()
    waiting = asyncio.create_task(asyncio.sleep(60))
    adapter._background_tasks.add(waiting)
    try:
        await adapter.disconnect()
        assert waiting.done()
        assert not adapter._background_tasks
    finally:
        waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)


@pytest.mark.asyncio
async def test_virtual_connect_is_idempotent():
    adapter = VirtualMeshAdapter()
    try:
        await adapter.connect()
        first = adapter._sim_task
        await adapter.connect()
        assert adapter._sim_task is first
    finally:
        await adapter.disconnect()
        for task in tuple(adapter._background_tasks):
            task.cancel()
        await asyncio.gather(*adapter._background_tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("destination", ["a1b2c3d4e5f6", "11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff"])
async def test_virtual_adapter_rejects_repeater_and_self_chat(destination):
    adapter = VirtualMeshAdapter()
    adapter.is_connected = True
    try:
        response = await adapter.send_message("hello", destination)
        assert response["status"].upper() == "ERROR"
        assert not adapter._background_tasks
    finally:
        await adapter.disconnect()
        for task in tuple(adapter._background_tasks):
            task.cancel()
        await asyncio.gather(*adapter._background_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_virtual_send_while_disconnected_is_not_success():
    adapter = VirtualMeshAdapter()
    try:
        response = await adapter.send_message("hello", "d7e8f9012345")
        assert response["status"].upper() == "ERROR"
    finally:
        await adapter.disconnect()
        for task in tuple(adapter._background_tasks):
            task.cancel()
        await asyncio.gather(*adapter._background_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_virtual_advert_roles_match_canonical_simulated_nodes():
    adapter = VirtualMeshAdapter()
    events = []
    adapter.set_rx_callback(events.append)
    adapter._emit_node_presence(adapter.node_alpha)
    assert events[0]["role"] == "REPEATER"
    assert events[0]["adv_type"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("command,event_type", [
    (b"\x04", EventType.CONTACTS),
    (b"\x16\x03", EventType.DEVICE_INFO),
    (b"\x38\x00", EventType.STATS_CORE),
    (b"\x38\x01", EventType.STATS_RADIO),
    (b"\x38\x02", EventType.STATS_PACKETS),
    (b"\xff", EventType.ERROR),
])
async def test_virtual_wire_can_be_parsed_by_official_sdk(command, event_type):
    adapter = VirtualMeshAdapter()
    adapter.is_connected = True
    frames = []
    events = []

    async def capture(event):
        events.append(event)

    reader = MessageReader(SimpleNamespace(dispatch=capture))
    adapter.set_companion_rx_callback(frames.append)
    assert await adapter.send_raw_companion_frame(command)
    for frame in frames:
        await reader.handle_rx(bytearray(frame))
    matches = [event for event in events if event.type == event_type]
    assert matches
    if event_type == EventType.CONTACTS:
        assert len(matches[0].payload) == len(adapter.nodes)
        by_prefix = {key[:12]: contact for key, contact in matches[0].payload.items()}
        assert by_prefix["a1b2c3d4e5f6"]["type"] == 2
        assert by_prefix["d7e8f9012345"]["type"] == 1
        assert by_prefix["c3d4e5f6a7b8"]["type"] == 4
        assert by_prefix["6f7e8d9c0b1a"]["type"] == 3
    elif event_type == EventType.DEVICE_INFO:
        assert matches[0].payload["fw ver"] == 10
        assert matches[0].payload["max_channels"] == len(adapter.channels)
