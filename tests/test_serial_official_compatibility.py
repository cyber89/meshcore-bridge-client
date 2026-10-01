"""Observable serial regressions against the official Companion SDK contracts."""

from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from meshcore import EventType
from meshcore.commands import CommandHandler
from meshcore.events import Event

from src.serial import MeshcoreSDKAdapter, RawSerialFramingAdapter
from src.serial.watchdog import SerialWatchdog


def connected_adapter(contact: dict[str, Any] | None = None) -> MeshcoreSDKAdapter:
    adapter = MeshcoreSDKAdapter("tcp://127.0.0.1:4000")
    adapter.mc = SimpleNamespace(
        commands=SimpleNamespace(
            send_msg=AsyncMock(return_value=Event(EventType.MSG_SENT, {})),
            send_chan_msg=AsyncMock(return_value=Event(EventType.OK, {})),
            add_contact=AsyncMock(return_value=Event(EventType.OK, {})),
            remove_contact=AsyncMock(return_value=Event(EventType.OK, {})),
            set_channel=AsyncMock(return_value=Event(EventType.OK, {})),
            get_time=AsyncMock(return_value=Event(EventType.CURRENT_TIME, {"time": 1})),
        ),
        get_contact_by_name=lambda _: contact,
        get_contact_by_key_prefix=lambda _: contact,
        _contacts={},
        channels={1: {"name": "Before"}},
        self_info={"public_key": "ab" * 32, "name": "Base"},
        is_connected=True,
    )
    adapter.is_connected = True
    return adapter


@pytest.mark.parametrize("contact_type,is_local", [(1, True), (2, False)])
async def test_sdk_contact_cannot_bypass_chat_guards(contact_type: int, is_local: bool) -> None:
    contact = {"public_key": ("ab" if is_local else "cd") * 32, "adv_name": "Target", "type": contact_type}
    adapter = connected_adapter(contact)
    with pytest.raises(ValueError):
        await adapter.send_message("Hola", target="Target")
    adapter.mc.commands.send_msg.assert_not_awaited()
    adapter.mc.commands.add_contact.assert_not_awaited()


async def test_self_info_event_preserves_identity_and_capabilities() -> None:
    adapter = connected_adapter()
    adapter.self_info = {"max_channels": 12}
    event = Event(EventType.SELF_INFO, {"public_key": "cd" * 32, "name": "Radio"})
    await adapter._on_sdk_event(EventType.SELF_INFO, event)
    assert adapter.self_info == {"max_channels": 12, "public_key": "cd" * 32, "name": "Radio"}


@pytest.mark.parametrize("result", [None, Event(EventType.ERROR, {"reason": "timeout"})])
async def test_failed_local_probe_does_not_report_alive(result: Any) -> None:
    adapter = connected_adapter()
    adapter.mc.commands.get_time.return_value = result
    before = adapter.last_heartbeat_time
    assert await adapter.ping_or_check_alive() is False
    assert adapter.last_heartbeat_time == before


async def test_local_probe_exception_does_not_report_alive() -> None:
    adapter = connected_adapter()
    adapter.mc.commands.get_time.side_effect = ConnectionError("closed")
    assert await adapter.ping_or_check_alive() is False


@pytest.mark.parametrize("operation", ["set_channel", "delete_channel", "add_contact", "remove_contact"])
async def test_firmware_rejection_does_not_commit_cache(operation: str) -> None:
    adapter = connected_adapter()
    rejection = Event(EventType.ERROR, {"error_code": 2})
    if operation == "set_channel":
        adapter.mc.commands.set_channel.return_value = rejection
        result = await adapter.set_channel(1, "After", "11" * 16)
    elif operation == "delete_channel":
        adapter.mc.commands.set_channel.return_value = rejection
        result = await adapter.delete_channel(1)
    elif operation == "add_contact":
        adapter.mc.commands.add_contact.return_value = rejection
        result = await adapter.add_contact({"public_key": "cd" * 32, "name": "Target"})
    else:
        adapter.mc.commands.remove_contact.return_value = rejection
        result = await adapter.remove_contact("cd" * 32)
    assert result["status"] == "ERROR"
    assert adapter.mc.channels == {1: {"name": "Before"}}
    assert adapter.mc._contacts == {}


async def test_named_channel_uses_official_derived_secret_in_cache() -> None:
    adapter = connected_adapter()
    await adapter.set_channel(1, "#mesh", "11" * 16)
    expected = hashlib.sha256(b"#mesh").digest()[:16]
    adapter.mc.commands.set_channel.assert_awaited_once_with(1, "#mesh", expected)
    assert adapter.mc.channels[1]["psk"] == expected.hex()


@pytest.mark.parametrize("name", ["a" * 32, "é" * 16])
async def test_channel_name_cannot_be_truncated_by_firmware(name: str) -> None:
    adapter = connected_adapter()
    with pytest.raises(ValueError):
        await adapter.set_channel(1, name, "11" * 16)
    adapter.mc.commands.set_channel.assert_not_awaited()


@pytest.mark.parametrize("target,text", [("Target", "a" * 161), ("broadcast", "a" * 155), ("broadcast", "é" * 78)])
async def test_official_text_limits_reject_before_transmission(target: str, text: str) -> None:
    adapter = connected_adapter({"public_key": "cd" * 32, "adv_name": "Target", "type": 1})
    with pytest.raises(ValueError):
        await adapter.send_message(text, target=target)
    adapter.mc.commands.send_msg.assert_not_awaited()
    adapter.mc.commands.send_chan_msg.assert_not_awaited()


async def test_official_channel_limit_accepts_exact_boundary() -> None:
    adapter = connected_adapter()
    result = await adapter.send_message("a" * 154, target="broadcast")
    assert result["status"] == "SENT"


async def test_raw_disconnect_starts_new_stream_without_stale_frame() -> None:
    adapter = RawSerialFramingAdapter("VIRTUAL")
    adapter.process_incoming_bytes(b"\xaa\x01\x1b")
    await adapter.disconnect()
    await adapter.connect()
    adapter.process_incoming_bytes(b"\x01\x02")
    assert adapter._rx_buffer == bytearray()
    assert adapter._in_frame is False
    assert adapter._in_escape is False


async def test_local_commands_do_not_overlap_response_waits() -> None:
    adapter = connected_adapter()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    active = 0
    peak = 0

    async def command(*args: Any) -> Event:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        first_entered.set()
        await release_first.wait()
        active -= 1
        return Event(EventType.OK, {})

    adapter.mc.commands.set_channel.side_effect = command
    first = asyncio.create_task(adapter.set_channel(1, "One", "11" * 16))
    await first_entered.wait()
    second = asyncio.create_task(adapter.set_channel(2, "Two", "22" * 16))
    await asyncio.sleep(0)
    release_first.set()
    await asyncio.gather(first, second)
    assert peak == 1


async def test_tcp_transport_state_is_not_hidden_by_port_scheme() -> None:
    adapter = connected_adapter()
    adapter.mc.is_connected = False
    assert adapter.is_hardware_alive() is False
    assert adapter.is_connected is False


async def test_failed_connection_initialization_releases_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    sdk = SimpleNamespace(
        start_auto_message_fetching=AsyncMock(side_effect=RuntimeError("fetch failed")),
        disconnect=AsyncMock(),
    )
    monkeypatch.setattr("src.serial.sdk_adapter.MeshCore", SimpleNamespace(create_tcp=AsyncMock(return_value=sdk)))
    adapter = MeshcoreSDKAdapter("tcp://127.0.0.1:4000")
    assert await adapter.connect() is False
    assert adapter.mc is None
    sdk.disconnect.assert_awaited_once()


async def test_missing_tx_response_does_not_report_sent() -> None:
    adapter = connected_adapter()
    adapter.mc.commands.send_chan_msg.return_value = None
    assert (await adapter.send_message("Hola"))["status"] == "ERROR"


async def test_existing_contact_is_not_rewritten_before_every_message() -> None:
    contact = {"public_key": "cd" * 32, "adv_name": "Target", "type": 1, "flags": 1}
    adapter = connected_adapter(contact)
    adapter.mc._contacts[contact["public_key"]] = dict(contact)
    await adapter.send_message("Hola", target="Target")
    adapter.mc.commands.add_contact.assert_not_awaited()
    assert adapter.mc._contacts[contact["public_key"]]["flags"] == 1


async def test_unresolved_key_prefix_is_not_registered_as_fabricated_public_key() -> None:
    adapter = connected_adapter()
    with pytest.raises(ValueError):
        await adapter.send_message("Hola", target="cd" * 6)
    adapter.mc.commands.add_contact.assert_not_awaited()


async def test_add_contact_requires_real_full_public_key() -> None:
    adapter = connected_adapter()
    with pytest.raises(ValueError):
        await adapter.add_contact({"public_key": "cd" * 6, "name": "Target"})
    adapter.mc.commands.add_contact.assert_not_awaited()


@pytest.mark.parametrize("direct", [False, True])
async def test_message_reaches_official_sdk_wire_serializer(direct: bool) -> None:
    """Capture actual installed SDK bytes, never a radio transport."""
    contact = {"public_key": "cd" * 32, "adv_name": "Target", "type": 1}
    adapter = connected_adapter(contact)
    adapter.mc._contacts[contact["public_key"]] = contact
    commands = CommandHandler()
    response = Event(EventType.MSG_SENT if direct else EventType.OK, {"expected_ack": b"\x01\x02\x03\x04"})
    captured: list[bytes] = []

    async def capture(data: bytes, *args: Any, **kwargs: Any) -> Event:
        captured.append(data)
        return response

    commands.send = capture
    adapter.mc.commands = commands
    result = await adapter.send_message("Hola é", target="Target" if direct else "broadcast", channel_idx=3)
    data = captured[0]
    assert data[:3] == (b"\x02\x00\x00" if direct else b"\x03\x00\x03")
    assert int.from_bytes(data[3:7], "little") > 0
    assert data[7:] == (bytes.fromhex("cd" * 6) if direct else b"") + "Hola é".encode()
    assert result["expected_ack"] == "01020304"


async def test_sdk_auto_fetch_and_mutation_share_response_serialization() -> None:
    adapter = connected_adapter()
    commands = CommandHandler()
    entered = asyncio.Event()
    release = asyncio.Event()
    active = 0
    peak = 0

    async def response(data: bytes, *args: Any, **kwargs: Any) -> Event:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        entered.set()
        try:
            await release.wait()
            return Event(EventType.OK, {})
        finally:
            active -= 1

    commands.send = response
    adapter.mc.commands = commands
    adapter._register_event_handlers()
    fetch = asyncio.create_task(commands.get_msg())
    await entered.wait()
    mutation = asyncio.create_task(adapter.set_channel(1, "One", "11" * 16))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(fetch, mutation)
    assert peak == 1


async def test_serialization_reinstallation_and_cancellation_leave_lock_usable() -> None:
    adapter = connected_adapter()
    for _ in range(2):
        commands = CommandHandler()
        entered = asyncio.Event()

        async def response(data: bytes, *args: Any, entered: asyncio.Event = entered, **kwargs: Any) -> Event:
            if data == b"\x0a":
                entered.set()
                await asyncio.Event().wait()
            return Event(EventType.OK, {})

        commands.send = response
        adapter.mc.commands = commands
        adapter._register_event_handlers()
        adapter._register_event_handlers()
        fetch = asyncio.create_task(commands.get_msg())
        await entered.wait()
        fetch.cancel()
        await asyncio.gather(fetch, return_exceptions=True)
        result = await asyncio.wait_for(adapter.set_channel(1, "One", "11" * 16), timeout=1)
        assert result["status"] == "OK"


async def test_watchdog_finite_reconnect_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = connected_adapter()
    adapter.is_connected = False
    attempts = 0
    watchdog: SerialWatchdog

    def reconnect() -> None:
        nonlocal attempts
        attempts += 1
        if attempts > 2:
            watchdog._running = False

    async def no_wait(delay: float) -> None:
        return None

    monkeypatch.setattr("src.serial.watchdog.asyncio.sleep", no_wait)
    watchdog = SerialWatchdog(adapter, on_timeout_reconnect=reconnect)
    watchdog.max_reconnect_attempts = 2
    watchdog._running = True
    await watchdog._supervise_loop()
    assert attempts == 2


@pytest.mark.parametrize("operation", ["share_contact", "export_contact"])
async def test_contact_operations_do_not_invent_full_keys(operation: str) -> None:
    adapter = connected_adapter()
    command = AsyncMock(return_value=Event(EventType.OK, {}))
    setattr(adapter.mc.commands, operation, command)
    assert await getattr(adapter, operation)("cd" * 6) is None
    command.assert_not_awaited()
