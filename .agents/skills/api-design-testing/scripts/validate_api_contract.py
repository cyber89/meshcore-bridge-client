#!/usr/bin/env python3
"""Check selected REST router responses using isolated storage and fake hardware.

This is a router smoke check, not HTTP/CORS/authentication or RF interoperability
coverage. No server, MQTT client, serial connection or rate-limiter worker starts.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import runpy
import sys
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

ROOT_DIR = next(parent for parent in Path(__file__).resolve().parents if (parent / "config.py").is_file())


@contextmanager
def isolated_environment() -> Iterator[Path]:
    """Restore caller state and prevent operator dotenv/data/log/map access."""
    with tempfile.TemporaryDirectory(prefix="meshcore-api-contract-") as directory, ExitStack() as stack:
        data_dir = Path(directory)
        environment = {
            "DATA_DIR": str(data_dir),
            "NODE_REGISTRY_STORAGE_PATH": str(data_dir / "nodes.json"),
            "AIRTIME_HISTORY_FILE": str(data_dir / "airtime.json"),
            "CHANNELS_STORAGE_PATH": str(data_dir / "channels.json"),
            "CHANNELS_JSON_PATH": str(data_dir / "channels.json"),
            "LOG_DIR": str(data_dir / "logs"),
            "LOG_FILE_PATH": str(data_dir / "logs" / "bridge.log"),
            "LOG_ERROR_FILE_PATH": str(data_dir / "logs" / "error.log"),
            "WEB_HOST": "127.0.0.1",
            "TCP_SERVER_HOST": "127.0.0.1",
            "MQTT_BROKER": "127.0.0.1",
        }
        stack.enter_context(patch.dict(os.environ, environment, clear=True))
        # dotenv is a runtime dependency. Fail if unavailable rather than allow
        # config.py's fallback parser to read the operator's .env.
        stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
        stack.enter_context(patch.object(sys, "path", [str(ROOT_DIR), *sys.path]))
        safe_values = runpy.run_path(str(ROOT_DIR / "config.py"))
        existing_config = importlib.import_module("config")
        # Controllers may already have imported config in a pytest process.
        for key, value in safe_values.items():
            if key.isupper():
                stack.enter_context(patch.object(existing_config, key, value, create=True))

        from src.web import api_router
        from src.web.map_tile_service import MapTileService

        stack.enter_context(patch.object(api_router, "MapTileService", lambda: MapTileService(data_dir=data_dir)))
        yield data_dir


class MockBridge:
    """Minimal in-memory bridge with explicitly fake serial/MQTT/TX operations."""

    def __init__(self) -> None:
        from src.contact_manager import NodeRegistry
        from src.deduplicator import PacketDeduplicator
        from src.rate_limiter import TxRateLimiter

        self.running = True
        self.start_time = 1000.0
        self.node_registry = NodeRegistry()
        self.deduplicator = PacketDeduplicator()
        self.rate_limiter = TxRateLimiter()
        # Resolve a fake queue completion immediately; never start an RF worker.
        self.rate_limiter.submit = AsyncMock(side_effect=self._submit_tx)
        self.channels: dict[int, dict[str, str]] = {0: {"name": "Public", "psk": ""}}
        self.serial_adapter = SimpleNamespace(
            is_connected=True,
            port="FAKE",
            is_hardware_alive=lambda: True,
            add_contact=AsyncMock(return_value={"status": "ok"}),
        )
        self.mqtt = SimpleNamespace(is_connected=True)
        self.serial_port = "FAKE"

    async def _submit_tx(self, **kwargs: Any) -> asyncio.Future[dict[str, Any]]:
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        future.set_result({"status": "sent", "request_id": kwargs.get("request_id")})
        return future

    async def _execute_tx(self, tx_item: Any) -> dict[str, Any]:
        return {"status": "sent", "request_id": tx_item.get("request_id")}

    async def handle_admin(self, cmd: Any) -> dict[str, Any]:
        return {"status": "ok", "action": cmd.get("action")}

    def get_health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "subsystems": {
                "serial_companion": {"connected": True, "port": "FAKE"},
                "mqtt_broker": {"connected": True},
            },
        }


async def run_api_tests() -> bool:
    print("[API-CONTRACT] Selected router responses; isolated storage and fake hardware.")
    with isolated_environment():
        from src.web.api_router import WebAPIRouter

        bridge = MockBridge()
        router = WebAPIRouter(bridge)
        key = "ab" * 32
        test_cases = [
            ("GET", "/api/status", {}, 200),
            ("GET", "/api/health", {}, 200),
            ("GET", "/api/diagnostics", {}, 200),
            ("GET", "/api/diagnostics/report.md", {}, 200),
            ("GET", "/api/nodes", {}, 200),
            ("GET", "/api/contacts", {}, 200),
            ("GET", "/api/channels", {}, 200),
            ("GET", "/api/analytics", {}, 200),
            ("GET", "/api/system/logs", {}, 200),
            ("GET", "/api/config", {}, 200),
            ("GET", "/api/node/config", {}, 200),
            ("POST", "/api/config/radio", {"frequency": 915.0}, 200),
            ("POST", "/api/config/identity", {"name": "Base Node"}, 200),
            ("POST", "/api/contacts", {"name": "Nodo Alpha", "public_key": key}, 201),
            ("POST", "/api/contacts", {"name": "Nodo Updated", "public_key": key}, 200),
            ("POST", "/api/contacts", {}, 400),
            ("POST", "/api/tx", {"text": "Hola Malla", "channel_idx": 0, "to": "broadcast"}, 200),
            ("POST", "/api/tx", {"text": "Hola Malla", "channel_idx": 0}, 400),
            ("POST", "/api/tx", {}, 400),
            ("GET", "/api/ruta_inexistente", {}, 404),
        ]
        all_ok = True
        try:
            for method, path, body, expected_status in test_cases:
                status, response = await router.handle_request(method, path, body)
                valid = status == expected_status and isinstance(response, dict)
                if path == "/api/diagnostics":
                    valid = valid and response.get("data", {}).get("subsystems", {}).get("serial_companion", {}).get("connected") is True
                if path == "/api/tx" and expected_status == 200:
                    valid = valid and response.get("data", {}).get("status") == "sent"
                print(f"[{'PASS' if valid else 'FAIL'}] {method:<4} {path:<30} -> HTTP {status} (expected {expected_status})")
                all_ok = all_ok and valid
            print("[EXITOSO] Selected router cases passed." if all_ok else "[FALLO] Router response mismatch.")
            return all_ok
        finally:
            router.map_tile_service.close()
            await bridge.rate_limiter.stop()


def main() -> int:
    return 0 if asyncio.run(run_api_tests()) else 1


if __name__ == "__main__":
    sys.exit(main())
