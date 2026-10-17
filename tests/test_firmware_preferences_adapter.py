"""Explicit local preference operations; no radio, retry or automatic readback."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from meshcore import EventType
from meshcore.events import Event

from src.serial.sdk_adapter import MeshcoreSDKAdapter


async def preference_adapter(text: str = "OK") -> MeshcoreSDKAdapter:
    adapter = MeshcoreSDKAdapter("tcp://127.0.0.1:4000")
    adapter.mc = SimpleNamespace(commands=SimpleNamespace(
        run_cli_command=AsyncMock(return_value=Event(EventType.CLI_REPLY, {"text": text})),
    ))
    adapter.is_connected = True
    await adapter._handle_device_info(Event(EventType.DEVICE_INFO, {"fw ver": 14, "ver": "1.18.0"}))
    return adapter


@pytest.mark.parametrize("command,text", [
    ("get cad", "> on"), ("get radio.rxgain", "> off"), ("get path.hash.mode", "> 2"),
])
async def test_new_preference_getters_make_one_local_request(command: str, text: str) -> None:
    adapter = await preference_adapter(text)
    assert await adapter.run_firmware_cli(command) == {"command": command, "text": text}
    adapter.mc.commands.run_cli_command.assert_awaited_once_with(command)


@pytest.mark.parametrize("value,command", [(True, "set cad on"), (False, "set cad off")])
async def test_cad_write_reports_only_acknowledgement_without_readback(value: bool, command: str) -> None:
    adapter = await preference_adapter()
    assert await adapter.set_firmware_preference("cad", value) == {
        "preference": "cad", "value": value, "acknowledged": True, "hardware_verified": False,
    }
    adapter.mc.commands.run_cli_command.assert_awaited_once_with(command)


@pytest.mark.parametrize("preference,value", [
    ("radio.rxgain", True), ("path.hash.mode", 1), ("cad", 1), ("cad", "on"),
    ("cad", None), ("cad", []), ("cad ", True), ("CAD", True), ("cad\nreboot", False),
])
async def test_unapproved_settings_and_coercions_never_reach_sdk(preference: str, value: Any) -> None:
    adapter = await preference_adapter()
    with pytest.raises(ValueError):
        await adapter.set_firmware_preference(preference, value)
    adapter.mc.commands.run_cli_command.assert_not_awaited()


@pytest.mark.parametrize("text", ["Error: unsupported", "Unknown command", "OK pending", "> on", "secret-canary"])
async def test_non_ack_reply_never_claims_applied_preference(text: str) -> None:
    adapter = await preference_adapter(text)
    with pytest.raises(RuntimeError) as error:
        await adapter.set_firmware_preference("cad", True)
    assert "secret-canary" not in str(error.value)
    assert adapter.mc.commands.run_cli_command.await_count == 1


async def test_getter_scope_still_rejects_cad_setters() -> None:
    adapter = await preference_adapter()
    with pytest.raises(ValueError):
        await adapter.run_firmware_cli("set cad on")
    adapter.mc.commands.run_cli_command.assert_not_awaited()


async def test_timeout_blocks_further_reads_and_writes_until_reconnect() -> None:
    adapter = await preference_adapter()
    adapter.mc.commands.run_cli_command.return_value = None
    with pytest.raises(TimeoutError):
        await adapter.set_firmware_preference("cad", True)
    assert adapter.firmware_capabilities["writable_preferences"] == []
    with pytest.raises(NotImplementedError):
        await adapter.set_firmware_preference("cad", False)
    with pytest.raises(NotImplementedError):
        await adapter.run_firmware_cli("get cad")
    assert adapter.mc.commands.run_cli_command.await_count == 1


async def test_older_protocol_cannot_write_cad() -> None:
    adapter = await preference_adapter()
    await adapter._handle_device_info(Event(EventType.DEVICE_INFO, {"fw ver": 13}))
    assert adapter.firmware_capabilities["writable_preferences"] == []
    with pytest.raises(NotImplementedError):
        await adapter.set_firmware_preference("cad", True)
    adapter.mc.commands.run_cli_command.assert_not_awaited()


async def test_new_sdk_session_has_distinct_generation_even_with_identical_device_info() -> None:
    adapter = await preference_adapter()
    previous = adapter.firmware_capabilities["session_generation"]
    adapter.mc = SimpleNamespace(commands=adapter.mc.commands)
    await adapter._handle_device_info(Event(EventType.DEVICE_INFO, {"fw ver": 14, "ver": "1.18.0"}))
    snapshot = adapter.firmware_capabilities
    assert type(snapshot["session_generation"]) is int
    assert snapshot["session_generation"] > previous
    assert snapshot["writable_preferences"] == ["cad", "wifi"]
