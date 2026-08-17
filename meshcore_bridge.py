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
    OpCode,
    TelemetryPayload,
    TextMessagePayload,
)
from src.rate_limiter import TxPriority, TxRateLimiter
from src.serial_driver import (
    BaseSerialAdapter,
    MeshcoreSDKAdapter,
    RawSerialFramingAdapter,
    SerialWatchdog,
)
from src.store_forward import PacketDeduplicator, SQLiteStoreAndForward

__all__ = [
    "MeshCoreBridge",
    "SQLiteStoreAndForward",
    "PacketDeduplicator",
    "TxRateLimiter",
    "TxPriority",
    "AsyncBridgeMQTTClient",
    "BaseSerialAdapter",
    "MeshcoreSDKAdapter",
    "RawSerialFramingAdapter",
    "SerialWatchdog",
    "OpCode",
    "HardwareModel",
    "FrameHeader",
    "TelemetryPayload",
    "TextMessagePayload",
    "NodeAdvertisement",
    "AckPayload",
    "MeshcoreFrame",
]


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    bridge = MeshCoreBridge()
    bridge.run_forever()


if __name__ == "__main__":
    main()
