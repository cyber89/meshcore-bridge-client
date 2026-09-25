"""
MeshCore Bridge Package.
Puente determinista y asíncrono entre hardware LoRa MeshCore, MQTT/n8n y Servidor Web SPA.
"""

from src.bridge_core import MeshCoreBridge
from src.contact_manager import (
    NodeContactInfo,
    NodeIdentity,
    NodeRegistry,
    NodeRfMetrics,
    NodeTelemetry,
)
from src.deduplicator import PacketDeduplicator
from src.mqtt_client import AsyncBridgeMQTTClient
from src.protocol_types import (
    AckPayload,
    FrameHeader,
    HardwareModel,
    MeshcoreFrame,
    NodeAdvertisement,
    PacketType,
    TextMessagePayload,
)
from src.rate_limiter import TxPriority, TxRateLimiter
from src.repeater_manager import RepeaterManager
from src.sensor_decoder import (
    CayenneLPPDecoder,
    LppDataType,
    SensorReading,
    extract_telemetry_fields,
    format_telemetry_summary,
)
from src.serial_driver import (
    BaseSerialAdapter,
    MeshcoreSDKAdapter,
    RawSerialFramingAdapter,
    SerialWatchdog,
)
from src.tcp_companion_server import MeshCoreCompanionServer
from src.virtual_mesh_adapter import VirtualMeshAdapter
from src.web.api_router import WebAPIRouter
from src.web.http_server import MeshCoreWebServer

__version__ = "3.0.0"

__all__ = [
    "MeshCoreBridge",
    "MeshCoreWebServer",
    "MeshCoreCompanionServer",
    "WebAPIRouter",
    "VirtualMeshAdapter",
    "AsyncBridgeMQTTClient",
    "PacketDeduplicator",
    "TxRateLimiter",
    "TxPriority",
    "BaseSerialAdapter",
    "MeshcoreSDKAdapter",
    "RawSerialFramingAdapter",
    "SerialWatchdog",
    "NodeRegistry",
    "NodeContactInfo",
    "NodeIdentity",
    "NodeRfMetrics",
    "NodeTelemetry",
    "RepeaterManager",
    "CayenneLPPDecoder",
    "LppDataType",
    "SensorReading",
    "extract_telemetry_fields",
    "format_telemetry_summary",
    "PacketType",
    "HardwareModel",
    "FrameHeader",
    "TextMessagePayload",
    "NodeAdvertisement",
    "AckPayload",
    "MeshcoreFrame",
]
