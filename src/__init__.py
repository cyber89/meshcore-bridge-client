"""
MeshCore Bridge Package.
Puente determinista y asíncrono entre hardware LoRa MeshCore, MQTT/n8n y Servidor Web SPA.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from runtime_requirements import require_stable_python

require_stable_python()

# Type hints for static analysis, IDEs, and linters without eager runtime imports
if TYPE_CHECKING:
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
    from src.web.asgi_server import AsgiWebServer

# PEP 562 module mapping for lazy attribute resolution on supported Python versions.
# Keeps pure domain imports independent of application configuration and network stacks.
_MODULE_LOOKUP: dict[str, str] = {
    "MeshCoreBridge": "src.bridge_core",
    "NodeContactInfo": "src.contact_manager",
    "NodeIdentity": "src.contact_manager",
    "NodeRegistry": "src.contact_manager",
    "NodeRfMetrics": "src.contact_manager",
    "NodeTelemetry": "src.contact_manager",
    "PacketDeduplicator": "src.deduplicator",
    "AsyncBridgeMQTTClient": "src.mqtt_client",
    "AckPayload": "src.protocol_types",
    "FrameHeader": "src.protocol_types",
    "HardwareModel": "src.protocol_types",
    "MeshcoreFrame": "src.protocol_types",
    "NodeAdvertisement": "src.protocol_types",
    "PacketType": "src.protocol_types",
    "TextMessagePayload": "src.protocol_types",
    "TxPriority": "src.rate_limiter",
    "TxRateLimiter": "src.rate_limiter",
    "RepeaterManager": "src.repeater_manager",
    "CayenneLPPDecoder": "src.sensor_decoder",
    "LppDataType": "src.sensor_decoder",
    "SensorReading": "src.sensor_decoder",
    "extract_telemetry_fields": "src.sensor_decoder",
    "format_telemetry_summary": "src.sensor_decoder",
    "BaseSerialAdapter": "src.serial_driver",
    "MeshcoreSDKAdapter": "src.serial_driver",
    "RawSerialFramingAdapter": "src.serial_driver",
    "SerialWatchdog": "src.serial_driver",
    "MeshCoreCompanionServer": "src.tcp_companion_server",
    "VirtualMeshAdapter": "src.virtual_mesh_adapter",
    "WebAPIRouter": "src.web.api_router",
    "AsgiWebServer": "src.web.asgi_server",
}

__version__ = "3.0.0"


def __getattr__(name: str) -> Any:
    """PEP 562 dynamic lazy export loader.

    Resolving an export imports only its module, keeping pure domain imports
    independent of heavy application dependencies or configuration loading.
    """
    module_path = _MODULE_LOOKUP.get(name)
    if module_path is not None:
        mod = import_module(module_path)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(_MODULE_LOOKUP.keys()))


__all__ = [
    "MeshCoreBridge",
    "AsgiWebServer",
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
