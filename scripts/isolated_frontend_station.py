"""Own a temporary virtual station for explicitly requested browser inspections."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from src.bridge_core import MeshCoreBridge

QA_USERNAME = "inspection-owner"
QA_PASSWORD = "temporary isolated inspection password"


@asynccontextmanager
async def isolated_frontend_station() -> AsyncIterator[tuple[MeshCoreBridge, str]]:
    """Never load .env, start a real transport, or open the operator's state."""
    with TemporaryDirectory(prefix="meshcore-inspection-") as temporary, ExitStack() as patches:
        patches.enter_context(patch("dotenv.load_dotenv", return_value=False))
        import config
        from src.bridge_core import MeshCoreBridge
        from src.virtual_mesh_adapter import VirtualMeshAdapter

        root = Path(temporary).resolve()
        safe_values = {
            "DATA_DIR": str(root), "DATABASE_PATH": str(root / "meshcore.sqlite3"),
            "NODE_REGISTRY_STORAGE_PATH": str(root / "node_registry.json"),
            "AIRTIME_HISTORY_FILE": str(root / "airtime_history.json"),
            "CHANNELS_JSON_PATH": str(root / "channels.json"),
            "LOG_DIR": str(root / "logs"), "LOG_FILE_PATH": str(root / "logs/bridge.log"),
            "LOG_ERROR_FILE_PATH": str(root / "logs/error.log"),
            "WEB_ENABLED": True, "WEB_HOST": "127.0.0.1", "WEB_PORT": 0,
            "TCP_SERVER_ENABLED": False, "TCP_SERVER_HOST": "127.0.0.1",
            "MQTT_BROKER": "127.0.0.1", "MQTT_USER": None, "MQTT_PASSWORD": None,
            "MQTT_TLS": False, "MQTT_TLS_CA_FILE": None,
            "MQTT_TLS_CERT_FILE": None, "MQTT_TLS_KEY_FILE": None,
        }
        for name, value in safe_values.items():
            patches.enter_context(patch.object(config, name, value, create=True))
        previous_handlers = set(logging.getLogger().handlers)
        bridge = None
        try:
            bridge = await MeshCoreBridge.create(data_dir=root)
            if bridge.database.path.resolve().parent != root:
                raise RuntimeError("Inspection database escaped the temporary directory")
            server = bridge.web_server
            if server is None:
                raise RuntimeError("Inspection requires the virtual HTTP server")
            # Create a non-bootstrap owner only in this disposable station.
            store = server.app.state.authentication.store
            await asyncio.to_thread(store.initialize)
            await asyncio.to_thread(store.bootstrap, QA_USERNAME, QA_PASSWORD)
            adapter = VirtualMeshAdapter(event_callback=bridge.on_mesh_event)
            bridge.serial_adapter = adapter
            await adapter.connect()
            if adapter._sim_task:
                adapter._sim_task.cancel()
                await asyncio.gather(adapter._sim_task, return_exceptions=True)
                adapter._sim_task = None
            server.host, server.port = "127.0.0.1", 0
            await server.start()
            if server.server is None:
                raise RuntimeError("Virtual HTTP listener did not start")
            port = server.server.sockets[0].getsockname()[1]
            yield bridge, f"http://127.0.0.1:{port}"
        finally:
            try:
                if bridge is not None:
                    try:
                        await bridge.stop()
                    finally:
                        if bridge.web_server is not None:
                            bridge.web_server.tile_service.close()
            finally:
                for handler in set(logging.getLogger().handlers) - previous_handlers:
                    logging.getLogger().removeHandler(handler)
                    handler.close()


async def login_inspection_context(context: object, origin: str) -> None:
    """Authenticate browser inspections through the ordinary HTTP login route."""
    from typing import Any, cast

    browser_context = cast(Any, context)
    response = await browser_context.request.post(
        origin + "/api/auth/login",
        data={"username": QA_USERNAME, "password": QA_PASSWORD, "remember": False},
        headers={"Origin": origin},
    )
    if response.status != 200:
        raise RuntimeError(f"Isolated inspection login failed: HTTP {response.status}")
