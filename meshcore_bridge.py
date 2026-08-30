#!/usr/bin/env python3
"""
MeshCore Universal Bridge: Companion USB (Heltec / LilyGO / RAKwireless / Seeed / RP2040) <-> Mosquitto MQTT <-> n8n
Puente bidireccional asíncrono, resiliente y de grado industrial para redes Mesh LoRa.

Entrypoint raíz compatible con systemd, Docker y scripts de despliegue.
Delega transparentemente en la arquitectura modular de /src/.
"""

import logging
import sys

from src.bridge_core import MeshCoreBridge
from src.mqtt_client import AsyncBridgeMQTTClient
from src.protocol_types import (
    AckPayload,
    FrameHeader,
    HardwareModel,
    MeshcoreFrame,
    NodeAdvertisement,
    PacketType,
    TelemetryPayload,
    TextMessagePayload,
)
from src.deduplicator import PacketDeduplicator
from src.rate_limiter import TxPriority, TxRateLimiter
from src.serial_driver import (
    BaseSerialAdapter,
    MeshcoreSDKAdapter,
    RawSerialFramingAdapter,
    SerialWatchdog,
)

__all__ = [
    "MeshCoreBridge",
    "PacketDeduplicator",
    "TxRateLimiter",
    "TxPriority",
    "AsyncBridgeMQTTClient",
    "BaseSerialAdapter",
    "MeshcoreSDKAdapter",
    "RawSerialFramingAdapter",
    "SerialWatchdog",
    "PacketType",
    "HardwareModel",
    "FrameHeader",
    "TelemetryPayload",
    "TextMessagePayload",
    "NodeAdvertisement",
    "AckPayload",
    "MeshcoreFrame",
]


def main() -> None:
    import config
    from src.diagnostics import setup_file_logging

    # 1. Configurar logging a consola estándar
    logging.basicConfig(
        level=getattr(logging, getattr(config, "LOG_LEVEL", "INFO"), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # 2. Configurar logging persistente a archivos rotativos
    setup_file_logging(
        log_file_path=getattr(config, "LOG_FILE_PATH", "logs/meshcore-bridge.log"),
        error_file_path=getattr(config, "LOG_ERROR_FILE_PATH", "logs/meshcore-bridge.error.log"),
        max_bytes=getattr(config, "LOG_MAX_BYTES", 5 * 1024 * 1024),
        backup_count=getattr(config, "LOG_BACKUP_COUNT", 3),
        level=getattr(config, "LOG_LEVEL", "INFO"),
    )

    # 3. Soporte para banderas CLI rápidas
    args = sys.argv[1:]
    if "--markdown" in args or "--diagnostics" in args or "--report" in args:
        bridge = MeshCoreBridge()
        diag = getattr(bridge, "diagnostics", None)
        if diag and hasattr(diag, "generate_markdown_report"):
            print(diag.generate_markdown_report())
        else:
            print("No se pudo generar el reporte de diagnóstico.")
        return

    if "--version" in args or "-v" in args:
        print("MeshCore Universal Bridge v3.0.0")
        return

    bridge = MeshCoreBridge()
    bridge.run_forever()


if __name__ == "__main__":
    main()
