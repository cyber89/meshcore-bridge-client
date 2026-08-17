"""
MeshCore Bridge Package.
Puente determinista y asíncrono entre hardware LoRa MeshCore y MQTT/n8n.
"""

from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactInfo, NodeRegistry
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
from src.repeater_manager import RepeaterManager
from src.sensor_decoder import CayenneLPPDecoder, LppDataType, SensorReading
from src.serial_driver import (
    BaseSerialAdapter,
    MeshcoreSDKAdapter,
    RawSerialFramingAdapter,
    SerialWatchdog,
)

__version__ = "2.1.0"

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
    "NodeRegistry",
    "NodeContactInfo",
    "RepeaterManager",
    "CayenneLPPDecoder",
    "LppDataType",
    "SensorReading",
    "OpCode",
    "HardwareModel",
    "FrameHeader",
    "TelemetryPayload",
    "TextMessagePayload",
    "NodeAdvertisement",
    "AckPayload",
    "MeshcoreFrame",
]
