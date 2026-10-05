"""MQTT input validation must not turn malformed control objects into RF text."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import config
from src.mqtt_dispatcher import MqttInboundDispatcher


def _context() -> SimpleNamespace:
    done = asyncio.get_running_loop().create_future()
    done.set_result({"status": "sent"})
    return SimpleNamespace(
        mqtt=MagicMock(), rate_limiter=SimpleNamespace(submit=AsyncMock(return_value=done), get_queue_depth=lambda: 0),
        handle_admin=AsyncMock(), loop=asyncio.get_running_loop(), background_tasks=set(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    '{"text":"Hola","channel_idx":"bad","password":"unique-secret"}',
    '{"text":"Hola","channel_idx":{},"password":"unique-secret"}',
    '{"text":"Hola","channel_idx":true}',
    '{"text":"Hola","channel_idx":1.5}',
    '{"text": ["Hola"]}',
    '{"text":"Hola","target":{"public_key":"bad"}}',
    '{"text":"Hola"',
])
async def test_invalid_structured_tx_never_enters_radio_queue(body: str, caplog: pytest.LogCaptureFixture) -> None:
    ctx = _context()
    await MqttInboundDispatcher(ctx)._handle_tx_request(body)
    ctx.rate_limiter.submit.assert_not_called()
    assert "unique-secret" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("body,text", [("Hola amigos", "Hola amigos"), ('"Hola amigos"', "Hola amigos"), ('{"text":"Hola amigos","channel_idx":1}', "Hola amigos")])
async def test_plain_or_valid_json_text_keeps_supported_tx_contract(body: str, text: str) -> None:
    ctx = _context()
    await MqttInboundDispatcher(ctx)._handle_tx_request(body)
    assert ctx.rate_limiter.submit.await_args.kwargs["payload"] == text


@pytest.mark.asyncio
async def test_multisegment_topic_prefix_resolves_relative_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "TOPIC_ADMIN_REPEATER", "lab/north/mesh/admin/repeater")
    ctx = _context()
    ctx.mqtt.topic_admin_repeater = config.TOPIC_ADMIN_REPEATER
    await MqttInboundDispatcher(ctx)._process_mqtt_input("lab/north/mesh/admin/repeater/aabbccdd/cmd", json.dumps({"action": "status"}))
    ctx.handle_admin.assert_awaited_once_with({"action": "status", "target_node": "aabbccdd"})


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["not/aabb/cmd", "/aabb/cmd/extra", "/aabb", "/aabb/notcmd", "//cmd"])
async def test_admin_topic_requires_exact_relative_target_and_cmd(monkeypatch: pytest.MonkeyPatch, suffix: str) -> None:
    monkeypatch.setattr(config, "TOPIC_ADMIN_REPEATER", "lab/mesh/admin/repeater")
    ctx = _context()
    ctx.mqtt.topic_admin_repeater = config.TOPIC_ADMIN_REPEATER
    await MqttInboundDispatcher(ctx)._process_mqtt_input(config.TOPIC_ADMIN_REPEATER + suffix, '{"action":"status"}')
    ctx.handle_admin.assert_not_called()
