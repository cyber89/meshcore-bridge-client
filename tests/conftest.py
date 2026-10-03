"""Isolated files and a virtual loopback bridge for the maintained test suite."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import AsyncExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from playwright.async_api import Page, Request, Route, async_playwright

with patch("dotenv.load_dotenv", return_value=False):
    import config
from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate
from src.virtual_mesh_adapter import VirtualMeshAdapter
from src.web.map_tile_service import MapTileService


@pytest.fixture(autouse=True)
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Keep JSON, logs and map databases away from the operator's working data."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    defaults = {
        "BRIDGE_API_KEY": "", "BRIDGE_ALLOWED_ORIGINS": "",
        "COMPANION_TOKEN": "", "COMPANION_ALLOWED_IPS": "",
        "MQTT_BROKER": "127.0.0.1", "MQTT_USER": None, "MQTT_PASSWORD": None,
        "WEB_ENABLED": True, "TCP_SERVER_ENABLED": True,
    }
    for name, value in defaults.items():
        monkeypatch.setattr(config, name, value)
        monkeypatch.setenv(name, "" if value is None else str(value))
    paths = {
        "DATA_DIR": str(tmp_path),
        "NODE_REGISTRY_STORAGE_PATH": str(tmp_path / "node_registry.json"),
        "AIRTIME_HISTORY_FILE": str(tmp_path / "airtime_history.json"),
        "CHANNELS_JSON_PATH": str(tmp_path / "channels.json"),
        "CHANNELS_FILE": str(tmp_path / "channels.json"),
        "LOG_DIR": str(tmp_path / "logs"),
        "LOG_FILE_PATH": str(tmp_path / "logs" / "bridge.log"),
        "LOG_ERROR_FILE_PATH": str(tmp_path / "logs" / "error.log"),
    }
    for name, value in paths.items():
        monkeypatch.setenv(name, value)
        monkeypatch.setattr(config, name, value)
    monkeypatch.setenv("CHANNELS_STORAGE_PATH", paths["CHANNELS_JSON_PATH"])
    monkeypatch.setattr(config, "WEB_HOST", "127.0.0.1")
    monkeypatch.setattr(config, "TCP_SERVER_HOST", "127.0.0.1")
    map_init = MapTileService.__init__

    def isolated_map_init(self: MapTileService, data_dir: str | Path | None = None) -> None:
        map_init(self, data_dir if data_dir is not None else tmp_path)

    monkeypatch.setattr(MapTileService, "__init__", isolated_map_init)
    handlers_before = set(logging.getLogger().handlers)
    yield tmp_path
    for handler in set(logging.getLogger().handlers) - handlers_before:
        logging.getLogger().removeHandler(handler)
        handler.close()


@pytest_asyncio.fixture
async def virtual_bridge(isolated_state: Path) -> AsyncIterator[MeshCoreBridge]:
    """Run only virtual radio, in-memory MQTT and an OS-assigned loopback HTTP port."""
    bridge = MeshCoreBridge(loop=asyncio.get_running_loop())
    bridge.mqtt.publish_safe = MagicMock(return_value=True)
    bridge.mqtt.is_connected = True
    async with AsyncExitStack() as cleanup:
        cleanup.push_async_callback(_cancel_bridge_tasks, bridge)
        assert bridge.web_server is not None
        cleanup.callback(bridge.web_server.tile_service.close)
        cleanup.push_async_callback(bridge.web_server.stop)
        adapter = VirtualMeshAdapter(event_callback=bridge.on_mesh_event)
        cleanup.push_async_callback(adapter.disconnect)
        cleanup.push_async_callback(bridge.rate_limiter.stop)
        adapter.mc.self_info["public_key"] = "ab" * 32
        bridge.serial_adapter = adapter
        await adapter.connect()
        # Deterministic tests inject their own RX; background scenery is unnecessary.
        if adapter._sim_task:
            adapter._sim_task.cancel()
            await asyncio.gather(adapter._sim_task, return_exceptions=True)
            adapter._sim_task = None
        bridge.node_registry.set_local_pubkey(adapter.mc.self_info["public_key"])
        for node in await adapter.sync_all_contacts():
            bridge.node_registry.add_or_update(
                node["public_key"],
                NodeContactUpdate(name=node["name"], alias=node["alias"], role=node["role"]),
            )
        bridge.web_server.host = "127.0.0.1"
        bridge.web_server.port = 0
        bridge.web_server.router.channels_ctrl.channels = {
            index: dict(channel) for index, channel in adapter.channels.items()
        }
        await bridge.web_server.start()
        bridge.rate_limiter.start()
        yield bridge


async def _cancel_bridge_tasks(bridge: MeshCoreBridge) -> None:
    tasks = list(bridge._background_tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@pytest_asyncio.fixture
async def browser_page(virtual_bridge: MeshCoreBridge) -> AsyncIterator[Page]:
    """Exercise the real SPA offline; fonts and CDN map rendering are separate checks."""
    server = virtual_bridge.web_server
    assert server is not None and server.server is not None
    origin = f"http://127.0.0.1:{server.server.sockets[0].getsockname()[1]}"
    external_requests: list[str] = []
    async with async_playwright() as playwright, AsyncExitStack() as cleanup:
        browser = await playwright.chromium.launch(headless=True)
        cleanup.push_async_callback(browser.close)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        cleanup.push_async_callback(context.close)
        await context.grant_permissions(["local-network-access"], origin=origin)
        await context.add_init_script(
            "if (!localStorage.getItem('mc_lang')) localStorage.setItem('mc_lang', 'es');"
        )

        async def local_only(route: Route) -> None:
            if not route.request.url.startswith(origin + "/"):
                external_requests.append(route.request.url)
                await route.abort()
            elif route.request.resource_type == "document":
                response = await route.fetch()
                html = await response.text()
                # Omit optional remote fonts/Leaflet, never substitute product JS or APIs.
                html = re.sub(r'<link\b[^>]*href="https://[^>]*>', "", html)
                html = re.sub(r'<script\b[^>]*src="https://[^>]*></script>', "", html)
                await route.fulfill(response=response, body=html)
            else:
                await route.continue_()

        await context.route("**/*", local_only)
        page = await context.new_page()
        errors: list[str] = []
        console_errors: list[str] = []
        failures: list[str] = []

        def record_request_failure(request: Request) -> None:
            # Leaflet removes obsolete tile images on resize/zoom. Chromium reports
            # those intentional cancellations as ERR_ABORTED. Local assets/APIs,
            # unexpected external requests and all other failures still fail QA.
            cancelled_external_image = (
                request.resource_type == "image"
                and not request.url.startswith(origin + "/")
                and request.failure == "net::ERR_ABORTED"
            )
            if not cancelled_external_image:
                failures.append(f"{request.failure} {request.url}")

        page.on("pageerror", lambda error: errors.append(error.stack or str(error)))
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("response", lambda response: failures.append(f"{response.status} {response.url}") if response.status >= 400 else None)
        page.on("requestfailed", record_request_failure)
        await page.goto(origin, wait_until="domcontentloaded")
        await page.locator('#channelListUi [data-channel-idx="1"]').wait_for()
        for _ in range(100):
            if server.active_websockets:
                break
            await asyncio.sleep(0.01)
        assert server.active_websockets, f"SPA WebSocket did not connect: {console_errors}"
        yield page
        assert not errors, f"Uncaught JavaScript errors: {errors}"
        assert not console_errors, f"Browser console errors: {console_errors}"
        assert not failures, f"Failed local HTTP responses: {failures}"
        assert not external_requests, f"Unexpected external requests: {external_requests}"
