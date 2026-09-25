"""
Serial Communication Layer and Modular Drivers for MeshCore Bridge.
"""

from src.serial.raw_framing import RawSerialFramingAdapter
from src.serial.sdk_adapter import MeshcoreSDKAdapter
from src.serial.serial_base import BaseSerialAdapter, detect_serial_port
from src.serial.watchdog import SerialWatchdog

__all__ = [
    "BaseSerialAdapter",
    "detect_serial_port",
    "MeshcoreSDKAdapter",
    "RawSerialFramingAdapter",
    "SerialWatchdog",
]
