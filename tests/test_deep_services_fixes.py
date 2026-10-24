"""Regressions for channel ownership, preset transactions and local recovery.

These tests use disposable state and never connect to physical services.
"""

from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.application.capabilities import CapabilityRegistry
from src.application.channels import ChannelService
from src.services_config import ServicesConfig
from src.web.auth_store import AuthStore
from src.web.controllers.base import ApiContext
from src.web.controllers.channels_controller import ChannelsController
from src.web.controllers.services_controller import ServicesController


def context(bridge: SimpleNamespace) -> ApiContext:
    return ApiContext(bridge, deque(), deque(), Mock())


@pytest.mark.asyncio
async def test_http_channel_sync_acquires_the_service_lock_once(tmp_path: Path) -> None:
    radio = SimpleNamespace(get_channels=AsyncMock(return_value=[{"index": 1, "name": "team", "psk": "11" * 16}]))
    service = ChannelService(tmp_path / "channels.json", serial_adapter_provider=lambda: radio)
    controller = ChannelsController(context(SimpleNamespace(channel_service=service, serial_adapter=radio)))
    async with asyncio.timeout(1):
        status, response = await controller.handle_channels_route("/api/channels/sync", "POST", {})
    assert status == 200
    assert any(channel["index"] == 1 for channel in response["data"])
    radio.get_channels.assert_awaited_once()


@pytest.mark.asyncio
async def test_channel_write_failure_does_not_poison_later_reads_or_retry(tmp_path: Path) -> None:
    database = SimpleNamespace(read_document=Mock(return_value=None), write_document=Mock(side_effect=[OSError("disk unavailable"), None]))
    service = ChannelService(tmp_path / "channels.json", database=database)
    service._dirty = True
    with pytest.raises(OSError):
        await service.save_channels_async()
    controller = ChannelsController(context(SimpleNamespace(channel_service=service)))
    status, _ = await controller.handle_channels_route("/api/channels", "GET", {})
    assert status == 200
    await service.save_channels_async()
    assert database.write_document.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("qos", 9), ("transport", "bogus")])
async def test_invalid_preset_does_not_mutate_shared_configuration(field: str, value: object) -> None:
    configuration = ServicesConfig()
    controller = ServicesController(context(SimpleNamespace(services_config=configuration)))
    status, _ = await controller.save_preset({"name": "test", "host": "localhost", field: value})
    assert status == 422
    assert configuration.custom_presets == []


def test_stopped_core_is_never_reported_healthy() -> None:
    capabilities = CapabilityRegistry(web_enabled=False)
    capabilities.core.mark_started()
    capabilities.core.mark_operational()
    assert capabilities.get_readiness()["core_ready"] is True
    capabilities.core.mark_stopped()
    assert capabilities.get_readiness()["core_ready"] is False
    assert capabilities.is_healthy() is False


def test_local_recovery_rejects_an_account_changed_during_prompt(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    store.bootstrap_default()
    generation = int(store._account()["generation"])
    store.recover_credentials("owner", "first-password", expected_generation=generation)
    with pytest.raises(ValueError, match="account_changed"):
        store.recover_credentials("owner", "second-password", expected_generation=generation)
