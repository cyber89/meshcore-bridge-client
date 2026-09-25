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
            if any(k in desc or k in hwid for k in ("heltec", "cp210", "ch340", "ch341", "ftdi", "uart", "acm", "usb serial", "usb-serial", "espressif", "t-beam", "rak", "com")):
                return str(p.device)
        if ports:
            return str(ports[0].device)
    except Exception as e:
        logging.warning(f"Error detecting serial port: {e}", exc_info=True)
    return "COM1" if os.name == "nt" else "/dev/ttyACM0"


class BaseSerialAdapter(abc.ABC):
    """Interfaz abstracta para adaptadores de comunicación serial con hardware MeshCore."""

    def __init__(self, port: str, baud_rate: int = 115200, timeout_sec: float = 30.0) -> None:
        port_clean = str(port or "").strip()
        if not port_clean.startswith("tcp://") and (
            port_clean.upper() in ("AUTO", "DETECT", "DEFAULT", "")
            or not port_clean
            or (os.name == "nt" and port_clean.startswith("/dev/"))
        ):
            self.port = detect_serial_port()
        else:
            self.port = port_clean
        self.baud_rate = baud_rate
        self.timeout_sec = timeout_sec
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

    @abc.abstractmethod
    async def send_admin_cmd(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        pass

    async def get_channels(self) -> list[dict[str, Any]]:
        """Devuelve la lista de canales configurados en el nodo (o lista vacía)."""
        return []

    async def set_channel(self, index: int, name: str, psk: str) -> dict[str, Any]:
        """Configura un canal en el firmware del transceptor serial."""
        return {"status": "OK", "index": index, "name": name}

    async def delete_channel(self, index: int) -> dict[str, Any]:
        """Elimina o vacía un canal en el firmware del transceptor serial."""
        return {"status": "OK", "index": index}

    async def add_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        """Añade o actualiza un contacto en la memoria del transceptor serial."""
        return {"status": "OK", "contact": contact_data}

    async def remove_contact(self, pubkey: str) -> dict[str, Any]:
        """Elimina un contacto de la memoria del transceptor serial."""
        return {"status": "OK", "public_key": pubkey}

    async def sync_all_contacts(self) -> list[dict[str, Any]]:
        """Descarga e importa todos los contactos almacenados en el hardware."""
        return []

    def is_hardware_alive(self) -> bool:
        """Verifica de forma síncrona si el hardware USB o socket TCP permanece conectado a nivel OS."""
        return bool(self.is_connected)

    async def ping_or_check_alive(self) -> bool:
        """Verifica si el transceptor local sigue vivo y respondiendo por serial."""
        return self.is_hardware_alive()

    async def get_channel(self, index: int) -> dict[str, Any] | None:
        """Obtiene la configuración de un canal específico."""
        return None

    async def get_stats(self) -> dict[str, Any] | None:
        """Obtiene las estadísticas de la radio."""
        return None

    async def device_query(self) -> dict[str, Any] | None:
        """Consulta el estado del dispositivo."""
        return None

    async def share_contact(self, contact_key: str) -> Any:
        """Comparte un contacto con la red."""
        return {"status": "NOT_SUPPORTED"}

    async def export_contact(self, contact_key: str | None = None) -> Any:
        """Exporta un contacto desde el transceptor."""
        return {"status": "NOT_SUPPORTED"}

    async def import_contact(self, contact_data: bytes) -> Any:
        """Importa un contacto hacia el transceptor."""
        return {"status": "NOT_SUPPORTED"}

    async def send_login(self, target_node: str, password: str) -> Any:
        """Envía credenciales de login a un repetidor remoto."""
        return {"status": "NOT_SUPPORTED"}

    async def logout(self, target_node: str) -> Any:
        """Cierra sesión administrativa en un repetidor remoto."""
        return {"status": "NOT_SUPPORTED"}

    def resolve_sender_name(self, prefix_or_key: str) -> str:
        return str(prefix_or_key)

    async def get_stats_core(self) -> Any:
        return None

    async def get_stats_radio(self) -> Any:
        return None

    async def get_stats_packets(self) -> Any:
        return None

    async def get_autoadd_config(self) -> Any:
        return None

    async def set_autoadd_config(self, flag: bool) -> Any:
        return None

    async def set_other_params_from_infos(self, infos: dict[str, Any]) -> Any:
        return None

    async def get_advert_path(self, key: str) -> Any:
        return None

    async def get_contact_by_key(self, pubkey: str) -> Any:
        return None

    async def send_path_discovery_sync(self, dst: str) -> Any:
        return None

    async def set_flood_scope(self, scope: int) -> Any:
        return None

    async def get_default_flood_scope(self) -> Any:
        return None

    async def set_devicepin(self, pin: int) -> Any:
        return None

    async def set_time(self, val: int) -> Any:
        return None

    async def has_connection(self) -> Any:
        return None

    async def set_path_hash_mode(self, mode: int) -> Any:
        return None
