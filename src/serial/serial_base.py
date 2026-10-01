"""
Base Serial Adapter and Hardware Detection for MeshCore Bridge.
"""

from __future__ import annotations

import abc
import logging
import os
import time
from collections.abc import Callable
from typing import Any


def detect_serial_port() -> str:
    """Detecta automáticamente el puerto serial de un nodo LoRa conectado."""
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in hwid for k in (
                "heltec", "cp210", "ch340", "ch341", "ftdi", "uart", "acm",
                "usb serial", "usb-serial", "espressif", "t-beam", "rak",
                "silicon labs", "wch"
            )):
                return str(p.device)
        # Fallback: preferir puertos explícitamente USB antes que COM de placa madre
        usb_ports = [p for p in ports if "usb" in (p.hwid or "").lower() or "usb" in (p.description or "").lower()]
        if usb_ports:
            return str(usb_ports[0].device)
        if ports:
            non_com1 = [p for p in ports if str(p.device).upper() != "COM1"]
            if non_com1:
                return str(non_com1[0].device)
            return str(ports[0].device)
    except Exception as e:
        logging.warning(f"Error detecting serial port: {e}", exc_info=True)
    return "COM1" if os.name == "nt" else "/dev/ttyACM0"


class BaseSerialAdapter(abc.ABC):
    """Interfaz abstracta para adaptadores de comunicación serial con hardware MeshCore."""

    @classmethod
    def resolve_port(cls, port: str) -> str:
        """Resuelve el puerto serial canónico aplicando auto-detección segura si se solicita."""
        port_clean = str(port or "").strip()
        if not port_clean.startswith("tcp://") and (
            port_clean.upper() in ("AUTO", "DETECT", "DEFAULT", "")
            or not port_clean
            or (os.name == "nt" and port_clean.startswith("/dev/"))
        ):
            return detect_serial_port()
        return port_clean

    def __init__(
        self,
        port: str,
        baud_rate: int = 115200,
        timeout_sec: float = 30.0,
        node_registry: Any = None,
    ) -> None:
        self.port = self.resolve_port(port)
        self.baud_rate = baud_rate
        self.timeout_sec = timeout_sec
        self.node_registry = node_registry
        self.is_connected = False
        self.rx_callback: Callable[[Any], None] | None = None
        self.companion_rx_callback: Callable[[bytes], Any] | None = None
        self.last_heartbeat_time = time.time()

    def set_rx_callback(self, callback: Callable[[Any], None]) -> None:
        self.rx_callback = callback

    def set_companion_rx_callback(self, callback: Callable[[bytes], Any] | None) -> None:
        self.companion_rx_callback = callback

    def heartbeat(self) -> None:
        self.last_heartbeat_time = time.time()

    async def send_raw_companion_frame(self, data: bytes) -> bool:
        """Envía una trama cruda de comando companion hacia el hardware transceptor."""
        return False

    @abc.abstractmethod
    async def connect(self) -> bool:
        pass

    @abc.abstractmethod
    async def disconnect(self) -> None:
        pass

    @abc.abstractmethod
    async def send_message(
        self,
        text: str,
        target: str | None = None,
        channel_idx: int = 0,
    ) -> dict[str, Any]:
        pass

    async def get_channels(self) -> list[dict[str, Any]]:
        """Devuelve la lista de canales configurados en el nodo (o lista vacía)."""
        return []

    async def set_channel(self, index: int, name: str, psk: str) -> dict[str, Any]:
        """Configura un canal en el firmware del transceptor serial."""
        return {"status": "NOT_SUPPORTED", "index": index}

    async def delete_channel(self, index: int) -> dict[str, Any]:
        """Elimina o vacía un canal en el firmware del transceptor serial."""
        return {"status": "NOT_SUPPORTED", "index": index}

    async def add_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        """Añade o actualiza un contacto en la memoria del transceptor serial."""
        return {"status": "NOT_SUPPORTED"}

    async def remove_contact(self, pubkey: str) -> dict[str, Any]:
        """Elimina un contacto de la memoria del transceptor serial."""
        return {"status": "NOT_SUPPORTED", "public_key": pubkey}

    async def sync_all_contacts(self) -> list[dict[str, Any]]:
        """Descarga e importa todos los contactos almacenados en el hardware."""
        return []

    def is_hardware_alive(self) -> bool:
        """Verifica de forma síncrona si el hardware USB o socket TCP permanece conectado a nivel OS."""
        return bool(self.is_connected)

    async def ping_or_check_alive(self) -> bool:
        """Verifica si el transceptor local sigue vivo y respondiendo por serial."""
        return self.is_hardware_alive()

    async def share_contact(self, contact_key: str) -> Any:
        """Comparte un contacto con la red."""
        return {"status": "NOT_SUPPORTED"}

    async def export_contact(self, contact_key: str | None = None) -> Any:
        """Exporta un contacto desde el transceptor."""
        return {"status": "NOT_SUPPORTED"}

    async def import_contact(self, contact_data: bytes) -> Any:
        """Importa un contacto hacia el transceptor."""
        return {"status": "NOT_SUPPORTED"}

    def resolve_sender_name(self, prefix_or_key: str) -> str:
        return str(prefix_or_key)
