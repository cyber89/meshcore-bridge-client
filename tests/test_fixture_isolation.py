"""Regressions for QA state restoration and cleanup when fixture setup fails."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import conftest
import pytest
import test_preflight
import test_stress_flood

import config


def test_preflight_summary_does_not_probe_an_existing_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket_factory = MagicMock()
    monkeypatch.setattr("src.preflight.socket.socket", socket_factory)
    case = test_preflight.TestPreflightChecker()
    case.setUp()
    case.test_run_all_summary()
    socket_factory.return_value.__enter__.return_value.connect.assert_not_called()


def test_stress_case_restores_global_tx_interval() -> None:
    interval_before = config.TX_INTERVAL_SEC
    case = test_stress_flood.TestStressFlood()
    case.setUp()
    try:
        case.test_flood_tx_queue_processing()
    finally:
        case.tearDown()
    assert config.TX_INTERVAL_SEC == interval_before


async def test_virtual_fixture_cleans_up_when_server_start_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = MagicMock()
    bridge._background_tasks = set()
    bridge.web_server.start = AsyncMock(side_effect=RuntimeError("server setup failed"))
    bridge.web_server.stop = AsyncMock()
    bridge.rate_limiter.stop = AsyncMock()
    adapter = MagicMock()
    adapter.mc.self_info = {}
    adapter.channels = {}
    adapter._sim_task = None
    adapter.connect = AsyncMock()
    adapter.sync_all_contacts = AsyncMock(return_value=[])
    adapter.disconnect = AsyncMock()
    monkeypatch.setattr(conftest, "MeshCoreBridge", MagicMock(return_value=bridge))
    monkeypatch.setattr(conftest, "VirtualMeshAdapter", MagicMock(return_value=adapter))
    fixture = conftest.virtual_bridge.__wrapped__(tmp_path)
    with pytest.raises(RuntimeError, match="server setup failed"):
        await anext(fixture)
    bridge.rate_limiter.stop.assert_awaited_once()
    bridge.web_server.stop.assert_awaited_once()
    bridge.web_server.tile_service.close.assert_called_once()
    adapter.disconnect.assert_awaited_once()


async def test_browser_fixture_closes_browser_when_context_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = MagicMock()
    bridge.web_server.server.sockets[0].getsockname.return_value = ("127.0.0.1", 12345)
    browser = MagicMock()
    browser.new_context = AsyncMock(side_effect=RuntimeError("context setup failed"))
    browser.close = AsyncMock()
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(conftest, "async_playwright", MagicMock(return_value=manager))
    fixture = conftest.browser_page.__wrapped__(bridge)
    with pytest.raises(RuntimeError, match="context setup failed"):
        await anext(fixture)
    browser.close.assert_awaited_once()
