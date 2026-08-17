#!/usr/bin/env python3
"""
MeshCore Bridge - Lanzador de Simulación Interactiva en Vivo (v3.0).
Inicia el puente en modo simulación con nodos LoRa virtuales, bot de auto-eco,
telemetría ambiental dinámica, analizador de paquetes RF y servidor web en http://localhost:8080.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# Configurar salida UTF-8 en terminal de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

import config
from src.bridge_core import MeshCoreBridge
from src.virtual_mesh_adapter import VirtualMeshAdapter


def print_simulation_banner(port: int = 8080) -> None:
    print("\n" + "=" * 74)
    print(" 🚀 MESHCORE BRIDGE v3.0 - SIMULACIÓN INTERACTIVA EN VIVO")
    print("=" * 74)
    print(f" 🌐 Interfaz Web SPA:          http://localhost:{port}")
    print(" 🔌 Adaptador LoRa Virtual:     CONECTADO (Emulación SX1262 / ESP32-S3)")
    print(" 👥 Nodos Clientes Activos:")
    print("    • 🛰️ Nodo Alpha (Field Unit):  Clave: a1b2c3d4e5f6 | [Auto-Eco en DMs]")
    print("    • 🚜 Nodo Bravo (Rover Scout): Clave: d7e8f9012345 | [Auto-Eco en DMs + GPS móvil]")
    print("-" * 74)
    print(" 💡 GUÍA RÁPIDA DE PRUEBAS:")
    print("    1. Abre tu navegador en: http://localhost:8080")
    print("    2. Pestaña '💬 Chat': Envía un mensaje privado a Alpha o Bravo y recibirás")
    print("       automáticamente una respuesta de eco con telemetría RF en tiempo real.")
    print("    3. Pestaña '🗺️ Mapa': Observa la posición GPS y movimiento del Rover Bravo.")
    print("    4. Pestaña '🕵️ Sniffer': Observa las tramas Wire LoRa 0x88 capturadas en el aire.")
    print("    5. Pestaña '📈 Métricas': Consulta el Top de tráfico, señal y estado de salud.")
    print("=" * 74 + "\n")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    port = getattr(config, "WEB_PORT", 8080)
    db_path = "meshcore_sim_buffer.db"

    # Instanciar el orquestador MeshCoreBridge
    bridge = MeshCoreBridge(db_path=db_path)

    # Conectar el adaptador de simulación virtual
    sim_adapter = VirtualMeshAdapter(
        event_callback=bridge.on_mesh_event,
        port="VIRTUAL_COM",
    )
    bridge.serial_adapter = sim_adapter

    # Iniciar el puente y servidor web
    await bridge.start()

    print_simulation_banner(port=port)

    stop_event = asyncio.Event()

    def _sig_handler() -> None:
        logging.info("Señal de parada recibida. Cerrando simulación...")
        stop_event.set()

    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _sig_handler)

    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await bridge.stop()
        if os.path.exists(db_path):
            for ext in ["", "-wal", "-shm"]:
                p = db_path + ext
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        logging.info("Simulación finalizada limpiamente.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
