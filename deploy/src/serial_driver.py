"""
Serial Communication Layer and Hybrid Adapters for MeshCore Bridge.
Fachada canónica para retrocompatibilidad hacia src/serial/.
"""

from src.serial import (
    BaseSerialAdapter,
    MeshcoreSDKAdapter,
    RawSerialFramingAdapter,
    SerialWatchdog,
    detect_serial_port,
)

__all__ = [
    "BaseSerialAdapter",
    "MeshcoreSDKAdapter",
    "RawSerialFramingAdapter",
    "SerialWatchdog",
    "detect_serial_port",
]
