#!/usr/bin/env python3
"""Interactive virtual station isolated in a disposable subprocess.

The launcher never imports production configuration. Its child receives dedicated
storage paths, no operator credentials, virtual radio and memory-only MQTT.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

from runtime_requirements import require_stable_python

require_stable_python()

ROOT_DIR = Path(__file__).resolve().parent


class InMemoryMQTT:
    """Consume simulated publications without contacting an external broker."""

    def __init__(self) -> None:
        self.is_connected = True
        self.reconnect_count = 0
        self.total_published = 0
        self.total_received = 0
        self.client: Any = None

    def publish_safe(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> bool:
        self.total_published += 1
        return True

    def stop(self) -> None:
        self.is_connected = False


def isolated_environment(data_dir: Path) -> dict[str, str]:
    """Forward OS runtime necessities, excluding operator app configuration."""
    names = ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA")
    env = {key: os.environ[key] for key in names if key in os.environ}
    env.update({
        "PYTHONUTF8": "1", "MESHCORE_DEMO_DATA_DIR": str(data_dir),
        "DATA_DIR": str(data_dir),
        "NODE_REGISTRY_STORAGE_PATH": str(data_dir / "nodes.json"),
        "AIRTIME_HISTORY_FILE": str(data_dir / "airtime.json"),
        "CHANNELS_JSON_PATH": str(data_dir / "channels.json"),
        "CHANNELS_STORAGE_PATH": str(data_dir / "channels.json"),
        "LOG_DIR": str(data_dir / "logs"),
        "LOG_FILE_PATH": str(data_dir / "logs" / "bridge.log"),
        "LOG_ERROR_FILE_PATH": str(data_dir / "logs" / "error.log"),
        "WEB_HOST": "127.0.0.1", "WEB_PORT": "0", "WEB_ENABLED": "true",
        "TCP_SERVER_ENABLED": "false", "SERIAL_PORT": "VIRTUAL_COM",
        "MQTT_USER": "", "MQTT_PASSWORD": "", "BRIDGE_API_KEY": "",
        "COMPANION_TOKEN": "", "BRIDGE_ALLOWED_ORIGINS": "",
    })
    return env


def create_demo_bridge(data_dir: Path) -> Any:
    """Construct only after verifying every effective path belongs to the demo."""
    import config
    from src.bridge_core import MeshCoreBridge
    from src.virtual_mesh_adapter import VirtualMeshAdapter

    for name in ("DATA_DIR", "NODE_REGISTRY_STORAGE_PATH", "AIRTIME_HISTORY_FILE",
                 "CHANNELS_JSON_PATH", "LOG_FILE_PATH", "LOG_ERROR_FILE_PATH"):
        if not Path(getattr(config, name)).resolve().is_relative_to(data_dir.resolve()):
            raise ValueError(f"Ruta de demo fuera del directorio aislado: {name}")

    class DemoBridge(MeshCoreBridge):
        def _init_storage_and_network(self) -> None:
            super()._init_storage_and_network()
            self.mqtt = InMemoryMQTT()  # type: ignore[assignment]

        def _create_serial_adapter(self) -> VirtualMeshAdapter:
            return VirtualMeshAdapter()

        def _create_tcp_server(self) -> None:
            return None

        async def _start_subsystems(self) -> None:
            # No production preflight, broker, TCP Companion or physical watchdog.
            self.rate_limiter.start()
            await self.serial_adapter.connect()
            if self.web_server:
                await self.web_server.start()
            await self._auto_bootstrap_heltec_state()

    bridge = DemoBridge(loop=asyncio.get_running_loop())
    if bridge.web_server:
        bridge.web_server.host = "127.0.0.1"
        bridge.web_server.port = 0
    return bridge


def print_simulation_banner(port: int, data_dir: Path) -> None:
    print(f"MeshCore Bridge: estación virtual en http://127.0.0.1:{port}")
    print(f"Datos temporales: {data_dir}; MQTT en memoria; cierre con Ctrl+C.")


async def main(data_dir: Path, stop_event: asyncio.Event | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    bridge = create_demo_bridge(data_dir)
    stopping = stop_event or asyncio.Event()
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    try:
        if sys.platform != "win32":
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stopping.set)
                installed.append(sig)
        await bridge.start()
        server = bridge.web_server.server if bridge.web_server else None
        port = int(server.sockets[0].getsockname()[1]) if server and server.sockets else 0
        print_simulation_banner(port, data_dir)
        await stopping.wait()
    finally:
        await bridge.stop()
        for sig in installed:
            loop.remove_signal_handler(sig)


def launch() -> int:
    with tempfile.TemporaryDirectory(prefix="meshcore-demo-") as directory:
        # The directory remains alive until the child has stopped all subsystems.
        child = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--isolated-child"],
            cwd=directory, env=isolated_environment(Path(directory)),
        )
        try:
            return child.wait()
        except KeyboardInterrupt:
            # Console interrupt also reaches the child. Wait for its finally block.
            return child.wait()


def child_main() -> int:
    directory = Path(os.environ["MESHCORE_DEMO_DATA_DIR"])
    # Block .env loading before the first production import, including its fallback.
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: False  # type: ignore[attr-defined]
    sys.modules["dotenv"] = dotenv
    sys.path.insert(0, str(ROOT_DIR))
    try:
        asyncio.run(main(directory))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(child_main() if sys.argv[1:] == ["--isolated-child"] else launch())
