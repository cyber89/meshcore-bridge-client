"""
MeshCore Bridge Package.
Puente determinista y asíncrono entre hardware LoRa MeshCore y MQTT/n8n.
"""

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

__version__ = "2.0.0"

__all__ = [
    "MeshCoreBridge",
    "AsyncBridgeMQTTClient",
    "SQLiteStoreAndForward",
    "PacketDeduplicator",
    "TxRateLimiter",
    "TxPriority",
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
