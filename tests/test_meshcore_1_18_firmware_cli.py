"""Manual firmware getters require observed protocol, one owner and fresh sessions."""

from __future__ import annotations

import asyncio
import logging
from importlib.metadata import version
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from meshcore import EventType
from meshcore.events import Event

from src.serial.sdk_adapter import MeshcoreSDKAdapter


def adapter_with_sdk(*, wrapped: bool = False) -> MeshcoreSDKAdapter:
    adapter = MeshcoreSDKAdapter("tcp://127.0.0.1:4000", timeout_sec=0.05)
    send = AsyncMock(return_value=Event(EventType.CLI_REPLY, {"text": "> 868.100"}))
    commands = SimpleNamespace(send=send)

    async def run_cli_command(command: str) -> Any:
        return await commands.send(b"\x42" + command.encode("utf-8"))

    commands.run_cli_command = AsyncMock(side_effect=run_cli_command)
    adapter.mc = SimpleNamespace(
        commands=commands, self_info={"public_key": "ab" * 32}, disconnect=AsyncMock(),
    )
    adapter.is_connected = True
    if wrapped:
        adapter._serialize_sdk_response_waits()
    return adapter


async def observe_device(adapter: MeshcoreSDKAdapter, protocol: Any = 14) -> None:
    await adapter._handle_self_info(Event(EventType.SELF_INFO, {"public_key": "ab" * 32}))
    await adapter._handle_device_info(Event(EventType.DEVICE_INFO, {
        "fw ver": protocol, "ver": "v1.18.0", "model": "Fixture LR1121", "ble_pin": 123456,
    }))


async def test_capability_requires_device_info_not_self_info_or_version_text() -> None:
    adapter = adapter_with_sdk()
    adapter.self_info = {"fw ver": 14, "ver": "v1.18.0", "model": "Pretend"}
    assert adapter.firmware_capabilities["state"] == "unknown"
    assert adapter.firmware_capabilities["reason"] == "awaiting_device_info"
    with pytest.raises(NotImplementedError, match="awaiting_device_info"):
        await adapter.run_firmware_cli("get freq")
    adapter.mc.commands.run_cli_command.assert_not_awaited()


@pytest.mark.parametrize("protocol", [None, "14", True, 14.0, -1, 256])
async def test_malformed_protocol_never_enables_cli(protocol: Any) -> None:
    adapter = adapter_with_sdk()
    await observe_device(adapter, protocol)
    assert adapter.firmware_capabilities["state"] == "unknown"
    assert adapter.firmware_capabilities["companion_protocol"] is None
    with pytest.raises(NotImplementedError):
        await adapter.run_firmware_cli("get freq")
    adapter.mc.commands.run_cli_command.assert_not_awaited()


async def test_legacy_firmware_does_not_emit_cli_even_when_sdk_supports_it() -> None:
    adapter = adapter_with_sdk()
    await observe_device(adapter, 13)
    assert adapter.firmware_capabilities["state"] == "absent"
    assert adapter.firmware_capabilities["reason"] == "protocol_unsupported"
    assert adapter.firmware_capabilities["safe_commands"] == []
    with pytest.raises(NotImplementedError, match="protocol_unsupported"):
        await adapter.run_firmware_cli("get radio")
    adapter.mc.commands.run_cli_command.assert_not_awaited()


async def test_capability_snapshot_exposes_only_safe_observations_and_is_copied() -> None:
    adapter = adapter_with_sdk()
    await observe_device(adapter)
    snapshot = adapter.firmware_capabilities
    assert type(snapshot["session_generation"]) is int
    assert snapshot["session_generation"] > 0
    assert snapshot == {
        "state": "present", "reason": "available", "connected": True,
        "companion_protocol": 14, "firmware_version": "v1.18.0",
        "sdk_version": version("meshcore"), "model": "Fixture LR1121", "transport": "tcp",
        "safe_commands": ["get radio", "get freq", "get cad", "get radio.rxgain", "get path.hash.mode"],
        "writable_preferences": ["cad"],
        "session_generation": snapshot["session_generation"],
    }
    snapshot["safe_commands"].append("get wifi.pwd")
    snapshot["model"] = "Changed by caller"
    assert adapter.firmware_capabilities["safe_commands"] == ["get radio", "get freq", "get cad", "get radio.rxgain", "get path.hash.mode"]
    assert adapter.firmware_capabilities["model"] == "Fixture LR1121"


@pytest.mark.parametrize("missing_method", [None, 42])
async def test_v14_without_callable_sdk_cli_is_unavailable(missing_method: Any) -> None:
    adapter = adapter_with_sdk()
    adapter.mc.commands.run_cli_command = missing_method
    await observe_device(adapter)
    assert adapter.firmware_capabilities["reason"] == "sdk_unsupported"
    with pytest.raises(NotImplementedError, match="sdk_unsupported"):
        await adapter.run_firmware_cli("get freq")


@pytest.mark.parametrize("command", [
    None, True, 66, b"get freq", "", " get freq", "get freq ", "GET FREQ", "get  freq",
    "get wifi.pwd", "set radio 2400,250,7,5", "AA|get freq", "get freq\n", "get freq\x00",
    "get freq\rset tx 30", "get freq;reboot", "get\tfreq", "get freq" + "a" * 160,
])
async def test_cli_rejects_everything_outside_exact_read_allowlist(command: Any) -> None:
    adapter = adapter_with_sdk()
    await observe_device(adapter)
    with pytest.raises(ValueError, match="invalid_firmware_command"):
        await adapter.run_firmware_cli(command)
    adapter.mc.commands.run_cli_command.assert_not_awaited()


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("command,text", [("get freq", "> 2400.000"), ("get radio", "> 868.100,250.000,7,5")])
async def test_manual_getter_returns_only_its_reply(wrapped: bool, command: str, text: str) -> None:
    adapter = adapter_with_sdk(wrapped=wrapped)
    await observe_device(adapter)
    commands = adapter.mc.commands
    send = AsyncMock(return_value=Event(EventType.CLI_REPLY, {"text": text, "ble_pin": 123456}))
    if wrapped:
        # Replace the original send first, then install this instance's wrapper.
        adapter._serialized_commands = None
        del commands._meshcore_bridge_serialized_owner
        commands.send = send
        adapter._serialize_sdk_response_waits()
    else:
        commands.send = send
    assert await adapter.run_firmware_cli(command) == {"command": command, "text": text}
    send.assert_awaited_once_with(b"\x42" + command.encode("utf-8"))


@pytest.mark.parametrize("text", ["Error, unsupported", "ERR - not supported", "Unknown command", "> Error: nope"])
async def test_semantic_rejections_are_private_and_not_success(text: str) -> None:
    adapter = adapter_with_sdk()
    await observe_device(adapter)
    adapter.mc.commands.send.return_value = Event(EventType.CLI_REPLY, {"text": text + " secret-canary"})
    with pytest.raises(RuntimeError) as error:
        await adapter.run_firmware_cli("get radio")
    assert str(error.value) == "firmware_cli_rejected"
    assert adapter.firmware_capabilities["state"] == "present"


@pytest.mark.parametrize("response", [
    Event(EventType.OK, {}), Event(EventType.ERROR, {"error_code": 1, "reason": "secret-canary"}),
    Event(EventType.CLI_REPLY, {}), Event(EventType.CLI_REPLY, {"text": 42}),
    Event(EventType.CLI_REPLY, {"text": ""}),
])
async def test_invalid_or_error_responses_are_not_returned(response: Any) -> None:
    adapter = adapter_with_sdk()
    await observe_device(adapter)
    adapter.mc.commands.send.return_value = response
    with pytest.raises(RuntimeError) as error:
        await adapter.run_firmware_cli("get freq")
    assert "secret-canary" not in str(error.value)


@pytest.mark.parametrize("response", [None, Event(EventType.ERROR, {"reason": "timeout"}), Event(EventType.ERROR, {"reason": "no_event_received"})])
async def test_sdk_timeout_requires_reconnect_before_another_cli(response: Any) -> None:
    adapter = adapter_with_sdk()
    await observe_device(adapter)
    commands = adapter.mc.commands
    commands.send.return_value = response
    with pytest.raises(TimeoutError, match="firmware_cli_timeout"):
        await adapter.run_firmware_cli("get freq")
    await observe_device(adapter)  # A fresh query on the same session cannot clear uncertainty.
    assert adapter.firmware_capabilities["reason"] == "cli_timeout_reconnect_required"
    with pytest.raises(NotImplementedError, match="cli_timeout_reconnect_required"):
        await adapter.run_firmware_cli("get radio")
    commands.run_cli_command.assert_awaited_once()


@pytest.mark.parametrize("wrapped", [False, True])
async def test_timeout_rejects_already_queued_getter_without_a_second_send(wrapped: bool) -> None:
    adapter = adapter_with_sdk(wrapped=wrapped)
    await observe_device(adapter)
    entered = asyncio.Event()
    never = asyncio.Event()
    sends: list[bytes] = []

    async def blocked_send(data: bytes) -> Event:
        sends.append(data)
        entered.set()
        await never.wait()
        return Event(EventType.CLI_REPLY, {"text": "> late response"})

    commands = adapter.mc.commands
    if wrapped:
        adapter._serialized_commands = None
        del commands._meshcore_bridge_serialized_owner
    commands.send = blocked_send
    if wrapped:
        adapter._serialize_sdk_response_waits()
    first = asyncio.create_task(adapter.run_firmware_cli("get freq"))
    await asyncio.wait_for(entered.wait(), timeout=1)
    second = asyncio.create_task(adapter.run_firmware_cli("get radio"))
    try:
        with pytest.raises(TimeoutError):
            await first
        with pytest.raises(NotImplementedError, match="cli_timeout_reconnect_required"):
            await second
        assert sends == [b"\x42get freq"]
    finally:
        for task in (first, second):
            task.cancel()
        await asyncio.gather(first, second, return_exceptions=True)


@pytest.mark.parametrize("wrapped", [False, True])
async def test_disconnect_while_queued_prevents_emission(wrapped: bool) -> None:
    adapter = adapter_with_sdk(wrapped=wrapped)
    await observe_device(adapter)
    commands = adapter.mc.commands
    await adapter._command_lock.acquire()
    pending = asyncio.create_task(adapter.run_firmware_cli("get freq"))
    try:
        await asyncio.sleep(0)
        await adapter.disconnect()
        adapter._command_lock.release()
        with pytest.raises(ConnectionError):
            await pending
        if not wrapped:
            commands.send.assert_not_awaited()
            commands.run_cli_command.assert_not_awaited()
        assert adapter.firmware_capabilities["companion_protocol"] is None
    finally:
        if adapter._command_lock.locked():
            adapter._command_lock.release()
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


async def test_identity_change_and_sdk_disconnect_clear_observed_capabilities() -> None:
    adapter = adapter_with_sdk()
    await observe_device(adapter)
    await adapter._handle_self_info(Event(EventType.SELF_INFO, {"public_key": "cd" * 32}))
    assert adapter.firmware_capabilities["state"] == "unknown"
    assert adapter.firmware_capabilities["model"] is None
    assert adapter.firmware_capabilities["companion_protocol"] is None
    await observe_device(adapter)
    await adapter._on_sdk_event(EventType.DISCONNECTED, Event(EventType.DISCONNECTED, {}))
    await adapter._on_sdk_event(EventType.CONNECTED, Event(EventType.CONNECTED, {}))
    assert adapter.firmware_capabilities["reason"] == "awaiting_device_info"
    assert adapter.firmware_capabilities["firmware_version"] is None


async def test_reply_from_replaced_identity_is_never_returned() -> None:
    adapter = adapter_with_sdk()
    await observe_device(adapter)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def send(data: bytes) -> Event:
        entered.set()
        await release.wait()
        return Event(EventType.CLI_REPLY, {"text": "> 868.100"})

    adapter.mc.commands.send = send
    pending = asyncio.create_task(adapter.run_firmware_cli("get freq"))
    try:
        await entered.wait()
        await adapter._handle_self_info(Event(EventType.SELF_INFO, {"public_key": "cd" * 32}))
        release.set()
        with pytest.raises(ConnectionError, match="connection_changed"):
            await pending
    finally:
        release.set()
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


async def test_replacing_sdk_cannot_inherit_observed_capabilities() -> None:
    adapter = adapter_with_sdk()
    await observe_device(adapter)
    replacement = adapter_with_sdk()
    adapter.mc = replacement.mc
    assert adapter.firmware_capabilities["state"] == "unknown"
    assert adapter.firmware_capabilities["model"] is None
    with pytest.raises(NotImplementedError, match="awaiting_device_info"):
        await adapter.run_firmware_cli("get freq")
    replacement.mc.commands.run_cli_command.assert_not_awaited()


async def test_new_session_can_read_after_previous_session_timed_out() -> None:
    adapter = adapter_with_sdk()
    await observe_device(adapter)
    adapter.mc.commands.send.return_value = None
    with pytest.raises(TimeoutError):
        await adapter.run_firmware_cli("get freq")
    await adapter.disconnect()
    replacement = adapter_with_sdk()
    adapter.mc = replacement.mc
    adapter.is_connected = True
    await observe_device(adapter)
    assert await adapter.run_firmware_cli("get freq") == {"command": "get freq", "text": "> 868.100"}


@pytest.mark.parametrize("wrapped", [False, True])
async def test_cancelled_inflight_cli_requires_reconnect(wrapped: bool) -> None:
    adapter = adapter_with_sdk(wrapped=wrapped)
    await observe_device(adapter)
    entered = asyncio.Event()

    async def blocked_send(data: bytes) -> Event:
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("must be cancelled")

    commands = adapter.mc.commands
    if wrapped:
        adapter._serialized_commands = None
        del commands._meshcore_bridge_serialized_owner
    commands.send = blocked_send
    if wrapped:
        adapter._serialize_sdk_response_waits()
    pending = asyncio.create_task(adapter.run_firmware_cli("get freq"))
    try:
        await entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert adapter.firmware_capabilities["reason"] == "cli_timeout_reconnect_required"
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.parametrize("wrapped", [False, True])
async def test_getters_share_response_owner_without_overlap(wrapped: bool) -> None:
    adapter = adapter_with_sdk(wrapped=wrapped)
    await observe_device(adapter)
    entered = asyncio.Event()
    release = asyncio.Event()
    sends: list[bytes] = []

    async def send(data: bytes) -> Event:
        sends.append(data)
        if data == b"\x42get freq":
            entered.set()
            await release.wait()
            return Event(EventType.CLI_REPLY, {"text": "> 2400"})
        return Event(EventType.CLI_REPLY, {"text": "> 2400,250,7,5"})

    commands = adapter.mc.commands
    if wrapped:
        adapter._serialized_commands = None
        del commands._meshcore_bridge_serialized_owner
    commands.send = send
    if wrapped:
        adapter._serialize_sdk_response_waits()
    first = asyncio.create_task(adapter.run_firmware_cli("get freq"))
    await entered.wait()
    second = asyncio.create_task(adapter.run_firmware_cli("get radio"))
    try:
        await asyncio.sleep(0)
        assert sends == [b"\x42get freq"]
        release.set()
        assert await first == {"command": "get freq", "text": "> 2400"}
        assert await second == {"command": "get radio", "text": "> 2400,250,7,5"}
        assert sends == [b"\x42get freq", b"\x42get radio"]
    finally:
        release.set()
        for task in (first, second):
            task.cancel()
        await asyncio.gather(first, second, return_exceptions=True)


@pytest.mark.parametrize("cancel", [False, True], ids=["timeout", "cancel"])
async def test_raw_cli_uncertain_reply_blocks_all_future_cli_until_reconnect(cancel: bool) -> None:
    adapter = adapter_with_sdk(wrapped=True)
    await observe_device(adapter)
    sent = asyncio.Event()

    async def raw_send(data: bytes) -> None:
        sent.set()

    commands = adapter.mc.commands
    adapter.mc.cx = SimpleNamespace(send=AsyncMock(side_effect=raw_send))
    pending = asyncio.create_task(adapter.send_raw_companion_frame(b"\x42get freq"))
    await sent.wait()
    if cancel:
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    else:
        assert await pending is False
    assert adapter.firmware_capabilities["reason"] == "cli_timeout_reconnect_required"
    # An orphaned reply cannot complete or justify another SDK/raw CLI transaction.
    adapter._observe_companion_frame(b"\x1d> 868.100")
    with pytest.raises(NotImplementedError, match="cli_timeout_reconnect_required"):
        await adapter.run_firmware_cli("get radio")
    assert await adapter.send_raw_companion_frame(b"\x42get radio") is False
    commands.run_cli_command.assert_not_awaited()
    adapter.mc.cx.send.assert_awaited_once_with(b"\x42get freq")


@pytest.mark.parametrize("wrapped", [False, True])
async def test_sdk_transport_exception_blocks_next_getter_and_hides_detail(wrapped: bool) -> None:
    adapter = adapter_with_sdk(wrapped=wrapped)
    await observe_device(adapter)
    sends: list[bytes] = []

    async def failed_send(data: bytes) -> Event:
        sends.append(data)  # The transport failed after accepting these bytes.
        raise RuntimeError("transport-private-canary")

    commands = adapter.mc.commands
    if wrapped:
        adapter._serialized_commands = None
        del commands._meshcore_bridge_serialized_owner
    commands.send = failed_send
    if wrapped:
        adapter._serialize_sdk_response_waits()
    with pytest.raises(ConnectionError) as error:
        await adapter.run_firmware_cli("get freq")
    assert str(error.value) == "firmware_cli_failed"
    assert adapter.firmware_capabilities["reason"] == "cli_timeout_reconnect_required"
    with pytest.raises(NotImplementedError, match="cli_timeout_reconnect_required"):
        await adapter.run_firmware_cli("get radio")
    assert sends == [b"\x42get freq"]


async def test_scheduled_old_sdk_device_info_cannot_enable_replacement_radio() -> None:
    adapter = adapter_with_sdk()
    handlers: dict[Any, Any] = {}
    old_mc = adapter.mc
    old_mc.subscribe = lambda event_type, handler: handlers.__setitem__(event_type, handler)
    adapter._register_event_handlers()
    handlers[EventType.DEVICE_INFO](Event(EventType.DEVICE_INFO, {
        "fw ver": 14, "ver": "OLD-FIRMWARE", "model": "OLD-BOARD",
    }))
    # The callback has scheduled its task but the task has not run yet.
    replacement = adapter_with_sdk()
    adapter.mc = replacement.mc
    adapter.self_info = {"public_key": "cd" * 32}
    await asyncio.gather(*tuple(adapter._background_tasks))
    assert adapter.firmware_capabilities["state"] == "unknown"
    assert adapter.firmware_capabilities["reason"] == "awaiting_device_info"
    assert adapter.firmware_capabilities["firmware_version"] is None
    assert adapter.firmware_capabilities["model"] is None


async def test_old_reader_hook_cannot_complete_new_sdk_raw_cli_waiter() -> None:
    adapter = adapter_with_sdk()
    old_reader = SimpleNamespace(handle_rx=AsyncMock())
    adapter.mc._reader = old_reader
    original_receive = old_reader.handle_rx
    adapter._register_event_handlers()
    old_hook = old_reader.handle_rx
    replacement = adapter_with_sdk()
    adapter.mc = replacement.mc
    adapter.mc.cx = SimpleNamespace(send=AsyncMock())
    forwarded: list[bytes] = []
    adapter.set_companion_rx_callback(forwarded.append)
    pending = asyncio.create_task(adapter.send_raw_companion_frame(b"\x42get freq"))
    try:
        await asyncio.sleep(0)
        await old_hook(bytearray(b"\x1d> OLD-REPLY"))
        await asyncio.sleep(0)
        assert not pending.done()
        assert forwarded == []
        original_receive.assert_awaited_once()
        adapter._observe_companion_frame(b"\x1d> 915.000")
        assert await pending is True
        assert forwarded == [b"\x1d> 915.000"]
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


async def test_device_and_self_info_debug_logs_never_include_private_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = adapter_with_sdk()
    caplog.set_level(logging.DEBUG)
    await adapter._handle_device_info(Event(EventType.DEVICE_INFO, {
        "fw ver": 14, "ver": "v1.18.0", "ble_pin": 604892, "model": "Fixture",
    }))
    await adapter._handle_self_info(Event(EventType.SELF_INFO, {
        "public_key": "ab" * 32, "ble_pin": 604892,
    }))
    assert "604892" not in caplog.text
    assert "ble_pin" not in caplog.text
