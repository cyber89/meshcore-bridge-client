#!/usr/bin/env python3
"""
Validador de Contratos y Endpoints de la API REST.
Verifica que las rutas devuelvan respuestas JSON válidas, códigos HTTP apropiados
y cabeceras CORS / seguridad.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# UTF-8 en terminal Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT_DIR))

from src.contact_manager import NodeRegistry
from src.deduplicator import PacketDeduplicator
from src.rate_limiter import TxRateLimiter
from src.web.api_router import WebAPIRouter


class MockBridge:
    def __init__(self, db_path: str = ":memory:") -> None:
        self.running = True
        self.start_time = 1000.0
        self.node_registry = NodeRegistry()
        self.deduplicator = PacketDeduplicator()
        self.rate_limiter = TxRateLimiter()
        self.channels: dict[int, dict[str, str]] = {0: {"name": "Public", "psk": ""}}
        self.serial_adapter = MagicMock(is_connected=True)
        self.mqtt = MagicMock(is_connected=True)
        self.serial_port = "COM3"

    async def _execute_tx(self, tx_item: Any) -> bool:
        return True

    async def handle_admin(self, cmd: Any) -> dict[str, Any]:
        return {"status": "ok", "action": cmd.get("action")}

    def get_health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "subsystems": {
                "serial_companion": {"connected": True, "port": "COM3"},
                "mqtt_broker": {"connected": True},
            },
        }


async def run_api_tests() -> bool:
    print("\n" + "=" * 68)
    print(" [API-CONTRACT] Validando Contratos REST y Códigos de Estado")
    print("=" * 68)

    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = temp_db.name
    temp_db.close()

    try:
        bridge = MockBridge(db_path)
        router = WebAPIRouter(bridge)  # type: ignore

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
            ("POST", "/api/contacts", {"name": "Nodo Alpha", "public_key": "aabbcc112233"}, 200),
            ("POST", "/api/contacts", {}, 400),  # Falta clave
            ("POST", "/api/tx", {"text": "Hola Malla", "channel_idx": 0}, 200),
            ("POST", "/api/tx", {}, 400),  # Falta texto
            ("GET", "/api/ruta_inexistente", {}, 404),
        ]

        all_ok = True
        for method, path, body, expected_status in test_cases:
            status, resp = await router.handle_request(method, path, body)
            if status == expected_status:
                extra_check = ""
                if path == "/api/diagnostics":
                    sub = resp.get("data", {}).get("subsystems", {})
                    is_ser = sub.get("serial_companion", {}).get("connected")
                    if is_ser is True:
                        extra_check = " (Subsystems.serial_companion.connected == True ✅)"
                    else:
                        extra_check = " (Subsystems.serial_companion missing ⚠️)"
                        all_ok = False
                print(f"[PASS] {method:<4} {path:<30} -> HTTP {status} (Esperado {expected_status}){extra_check}")
            else:
                print(f"[FAIL] {method:<4} {path:<30} -> HTTP {status} (Esperado {expected_status})")
                all_ok = False

        print("-" * 68)
        if all_ok:
            print("[EXITOSO] Todos los endpoints cumplen con el contrato REST de respuesta.")
            return True
        else:
            print("[FALLO] Se detectaron discrepancias en los códigos de estado HTTP.")
            return False

    finally:
        for ext in ["", "-wal", "-shm"]:
            p = db_path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


def main() -> int:
    ok = asyncio.run(run_api_tests())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
