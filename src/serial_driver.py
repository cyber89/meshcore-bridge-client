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
from src.serial.sdk_adapter import MeshCore

__all__ = [
    "BaseSerialAdapter",
    "MeshcoreSDKAdapter",
    "RawSerialFramingAdapter",
    "SerialWatchdog",
    "detect_serial_port",
    "MeshCore",
]
