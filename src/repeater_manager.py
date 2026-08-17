"""
Repeater Remote Management & Packet Sniffer for MeshCore Bridge.
Gestiona el enrutamiento de comandos administrativos remotos hacia repetidores
y el procesamiento de transmisiones de log en tiempo real (Packet Sniffer).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class RepeaterManager:
    """Administrador de comandos remotos a repetidores y decodificador de tramas de sniffer."""

    def __init__(self, transmit_callback: Callable[[str, str, int], Any] | None = None) -> None:
        self.transmit_callback = transmit_callback
        self._active_sniffers: set[str] = set()

    def build_repeater_command_payload(self, action: str, params: dict[str, Any]) -> str:
        """Construye la cadena de comando en texto para enviar al firmware del repetidor."""
        act = action.strip().lower()

        if act in ("stats-core", "stats-radio", "stats-packets", "clear stats", "neighbors", "discover.neighbors", "advert", "log start", "log stop", "ver", "board", "clock", "reboot"):
            return act

        if act.startswith("set "):
            return action

        if act == "set_tx_power":
            power = params.get("power", 20)
            return f"set tx {power}"

        if act == "set_name":
            name = params.get("name", "Repeater")
            return f"set name {name}"

        if act == "set_freq":
            freq = params.get("freq", 915.0)
            return f"set freq {freq}"

        return action

    def parse_log_packet(self, log_payload: bytes | str) -> dict[str, Any]:
        """
        Parsea un evento push 0x88 (LOG_DATA) emitido por un repetidor o sniffer.
        Extrae encabezados, tipo de ruta, saltos y calidad RF.
        """
        now = time.time()
        if isinstance(log_payload, str):
            return {
                "event_type": "rf_log",
                "raw_text": log_payload,
                "timestamp": now,
            }

        data_len = len(log_payload)
        parsed: dict[str, Any] = {
            "event_type": "rf_log",
            "byte_length": data_len,
            "raw_hex": log_payload.hex(),
            "timestamp": now,
        }

        if data_len >= 1:
            header_byte = log_payload[0]
            route_type = header_byte & 0x03
            payload_type = (header_byte >> 2) & 0x0F
            version = (header_byte >> 6) & 0x03

            parsed["route_type_id"] = route_type
            parsed["payload_type_id"] = payload_type
            parsed["version"] = version

        return parsed
