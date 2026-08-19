"""
Repeater Remote Management & Packet Sniffer for MeshCore Bridge.
Gestiona el enrutamiento de comandos administrativos remotos hacia repetidores,
el análisis integral de telemetría y el procesamiento de tramas de sniffer.
"""

from __future__ import annotations

import re
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

        # Comandos directos sin argumentos
        if act in (
            "stats-core",
            "stats-radio",
            "stats-packets",
            "stats",
            "telemetry",
            "clear stats",
            "clear_stats",
            "neighbors",
            "discover.neighbors",
            "discover_neighbors",
            "advert",
            "log start",
            "log stop",
            "ver",
            "version",
            "board",
            "clock",
            "pos",
            "get pos",
            "get_pos",
            "owner",
            "get owner",
            "get_owner",
            "acl",
            "get acl",
            "get_acl",
            "identity",
            "get identity",
            "get_identity",
            "radio",
            "get radio",
            "get_radio",
            "reboot",
        ):
            if act in ("clear_stats", "clear stats"):
                return "clear stats"
            if act in ("discover_neighbors", "discover.neighbors"):
                return "discover.neighbors"
            if act in ("get_pos", "get pos"):
                return "get pos"
            if act in ("get_owner", "get owner"):
                return "get owner"
            if act in ("get_acl", "get acl"):
                return "get acl"
            if act in ("get_identity", "get identity"):
                return "get identity"
            if act in ("get_radio", "get radio"):
                return "get radio"
            return act

        # Si ya viene formateado como comando directo "set ...", "cmd ...", "login ..."
        if act.startswith("set ") or act.startswith("login ") or act.startswith("acl ") or act.startswith("cmd "):
            return action

        # 1. Autenticación
        if act in ("login", "auth"):
            password = params.get("password", "")
            return f"login {password}"

        # 2. Owner Info
        if act in ("set_owner", "set_owner_name", "owner_info"):
            name = params.get("owner_name", params.get("name", params.get("owner", "Repeater")))
            info = params.get("owner_info", params.get("info", ""))
            if info:
                return f"set owner.name \"{name}\" \"{info}\""
            return f"set owner.name \"{name}\""

        if act == "set_owner_info":
            info = params.get("owner_info", params.get("info", ""))
            return f"set owner.info \"{info}\""

        # 3. Advert & Beacon Intervals
        if act == "advert":
            return "advert"

        if act in ("set_advert_interval", "set_beacon", "advert_intervals", "beacon"):
            interval = params.get("advert_interval", params.get("beacon_interval", params.get("interval", params.get("beacon", 300))))
            return f"set advert.interval {interval}"

        # 4. Position & GPS
        if act in ("set_position", "set_pos", "position"):
            lat = params.get("lat", params.get("latitude", 0.0))
            lon = params.get("lon", params.get("longitude", 0.0))
            alt = params.get("alt", params.get("altitude", 0.0))
            fixed = params.get("fixed", True)
            fixed_val = "1" if fixed is True or str(fixed).lower() in ("true", "1", "on") else "0"
            return f"set pos {lat} {lon} {alt} {fixed_val}"

        if act == "set_pos_lat":
            lat = params.get("lat", params.get("latitude", 0.0))
            return f"set pos.lat {lat}"

        if act == "set_pos_lon":
            lon = params.get("lon", params.get("longitude", 0.0))
            return f"set pos.lon {lon}"

        if act == "set_pos_alt":
            alt = params.get("alt", params.get("altitude", 0.0))
            return f"set pos.alt {alt}"

        if act == "set_pos_fixed":
            fixed = params.get("fixed", True)
            val = "on" if fixed is True or str(fixed).lower() in ("true", "1", "on") else "off"
            return f"set pos.fixed {val}"

        # 5. Sync Clock
        if act in ("sync_clock", "set_clock"):
            epoch_val = params.get("timestamp", params.get("epoch", int(time.time())))
            return f"set clock {epoch_val}"

        # 6. Access Control (ACL)
        if act in ("set_acl_mode", "access_control"):
            mode = params.get("acl_mode", params.get("mode", "public"))
            return f"set acl.mode {mode}"

        if act in ("acl_add", "add_acl_key"):
            key = params.get("public_key", params.get("key", ""))
            return f"acl add {key}"

        if act in ("acl_remove", "remove_acl_key"):
            key = params.get("public_key", params.get("key", ""))
            return f"acl remove {key}"

        # 7. Passwords
        if act in ("set_admin_password", "set_admin_pwd", "admin_password"):
            pwd = params.get("admin_password", params.get("password", ""))
            return f"set admin.password {pwd}"

        if act in ("set_guest_password", "set_guest_pwd", "guest_password"):
            pwd = params.get("guest_password", params.get("password", ""))
            return f"set guest.password {pwd}"

        # 8. Identity Key
        if act in ("set_identity_key", "change_identity_key", "identity_key"):
            key = params.get("identity_key", params.get("key", ""))
            return f"set identity.key {key}"

        # 9. Radio & Regions
        if act in ("set_region", "manage_regions", "region"):
            region = params.get("region", "US915")
            return f"set region {region}"

        if act in ("set_tx_power", "set_tx", "tx_power"):
            power = params.get("power", params.get("tx_power", 20))
            return f"set tx {power}"

        if act == "set_name":
            name = params.get("name", "Repeater")
            return f'set name "{name}"' if " " in str(name) else f"set name {name}"

        if act in ("set_freq", "frequency"):
            freq = params.get("freq", params.get("frequency", 915.0))
            return f"set freq {freq}"

        if act in ("set_sf", "spreading_factor"):
            sf = params.get("sf", params.get("spreading_factor", 11))
            return f"set sf {sf}"

        if act in ("set_bw", "bandwidth"):
            bw = params.get("bw", params.get("bandwidth", 250))
            return f"set bw {bw}"

        if act in ("set_cr", "coding_rate"):
            cr = params.get("cr", params.get("coding_rate", "4/5"))
            return f"set cr {cr}"

        # 10. Repeat Settings
        if act in ("set_repeat", "repeat_settings", "repeat"):
            enabled = params.get("repeat", params.get("enabled", True))
            val = "on" if enabled is True or str(enabled).lower() in ("true", "1", "on") else "off"
            return f"set repeat {val}"

        if act in ("set_hop_limit", "hop_limit"):
            hl = params.get("hop_limit", params.get("hops", 3))
            return f"set hop_limit {hl}"

        return action

    def parse_repeater_telemetry_or_response(self, raw_text: str) -> dict[str, Any]:
        """
        Analiza cadenas de texto provenientes de respuestas de repetidores MeshCore
        (stats-core, stats-radio, telemetry, status, clock, pos, ver) y extrae métricas estructuradas.
        """
        extracted: dict[str, Any] = {}
        text = raw_text.strip()
        if not text:
            return extracted

        # Batería: "Battery: 4120mV (92%)" o "Batt: 4.12V, 95%" o "Battery: 92%"
        bat_m = re.search(r'(?:battery|batt|bat)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mv|v|%)?(?:\s*\((?:(\d+)\s*%)?\))?', text, re.IGNORECASE)
        if bat_m:
            raw_val_str = bat_m.group(1)
            pct_in_paren = bat_m.group(2)
            try:
                val_num = float(raw_val_str)
                if "%" in bat_m.group(0) or val_num <= 100.0 and val_num > 4.5:
                    extracted["battery_pct"] = int(val_num)
                elif val_num > 100.0:  # mV (ej 4120)
                    extracted["voltage_v"] = round(val_num / 1000.0, 2)
                    if pct_in_paren:
                        extracted["battery_pct"] = int(pct_in_paren)
                    else:
                        # Estimar % para LiPo 3.0V - 4.2V
                        pct = max(0, min(100, int((val_num - 3300) / (4200 - 3300) * 100)))
                        extracted["battery_pct"] = pct
                else:  # V (ej 4.12)
                    extracted["voltage_v"] = round(val_num, 2)
                    if pct_in_paren:
                        extracted["battery_pct"] = int(pct_in_paren)
                    else:
                        pct = max(0, min(100, int((val_num - 3.3) / (4.2 - 3.3) * 100)))
                        extracted["battery_pct"] = pct
            except Exception:
                pass

        # Solar / Voltaje de entrada: "Solar: 5.12V"
        solar_m = re.search(r'solar(?:_v)?\s*[:=]?\s*(\d+(?:\.\d+)?)\s*v?', text, re.IGNORECASE)
        if solar_m:
            try:
                extracted["solar_v"] = round(float(solar_m.group(1)), 2)
            except Exception:
                pass

        # Clock: "Clock: 2026-08-18 22:15:00" o "Clock: 1787105384"
        clock_m = re.search(r'clock\s*[:=]?\s*([0-9\-:\s]+)', text, re.IGNORECASE)
        if clock_m:
            extracted["clock"] = clock_m.group(1).strip()

        # Uptime: "Uptime: 3d 14h 22m" o "Uptime: 310920s"
        uptime_m = re.search(r'uptime\s*[:=]?\s*([0-9a-zA-Z\s]+?)(?:,|$|\n)', text, re.IGNORECASE)
        if uptime_m:
            extracted["uptime"] = uptime_m.group(1).strip()

        # Total Airtime: "Total Airtime: 1420ms (0.24%)"
        airtime_m = re.search(r'(?:total\s+)?airtime\s*[:=]?\s*(\d+)\s*ms', text, re.IGNORECASE)
        if airtime_m:
            try:
                extracted["airtime_ms"] = int(airtime_m.group(1))
            except Exception:
                pass

        # Noise Floor: "Noise Floor: -118 dBm"
        noise_m = re.search(r'noise(?:\s*floor)?\s*[:=]?\s*(-?\d+)\s*(?:dbm)?', text, re.IGNORECASE)
        if noise_m:
            try:
                extracted["noise_floor_dbm"] = int(noise_m.group(1))
            except Exception:
                pass

        # Signal (Last RSSI / SNR): "Last RSSI: -72 dBm, Last SNR: 9.5 dB"
        rssi_m = re.search(r'(?:last\s+)?rssi\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(?:dbm)?', text, re.IGNORECASE)
        if rssi_m:
            try:
                extracted["last_rssi"] = int(float(rssi_m.group(1)))
            except Exception:
                pass

        snr_m = re.search(r'(?:last\s+)?snr\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(?:db)?', text, re.IGNORECASE)
        if snr_m:
            try:
                extracted["last_snr"] = round(float(snr_m.group(1)), 1)
            except Exception:
                pass

        # Packets Sent / Received / Duplicates / Errors:
        # "Packets Sent: 1420, Received: 3120, Duplicates: 45, Errors: 2"
        sent_m = re.search(r'(?:packets?\s+sent|tx\s+packets?)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
        if sent_m:
            try:
                extracted["packets_sent"] = int(sent_m.group(1))
            except Exception:
                pass

        recv_m = re.search(r'(?:packets?\s+rec(?:ei)?ved|rx\s+packets?)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
        if recv_m:
            try:
                extracted["packets_recv"] = int(recv_m.group(1))
            except Exception:
                pass

        dup_m = re.search(r'(?:duplicate\s+packets?(?:\s+seen)?|duplicates?)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
        if dup_m:
            try:
                extracted["duplicate_packets"] = int(dup_m.group(1))
            except Exception:
                pass

        err_m = re.search(r'(?:rec(?:ei)?ved\s+packet\s+errors?|rx\s+errors?|packet\s+errors?)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
        if err_m:
            try:
                extracted["packet_errors"] = int(err_m.group(1))
            except Exception:
                pass

        queue_m = re.search(r'queue(?:\s+length)?\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
        if queue_m:
            try:
                extracted["queue_len"] = int(queue_m.group(1))
            except Exception:
                pass

        # Position: "Position: Lat: 20.1504, Lon: -75.2014, Alt: 45m" o "Lat: 20.1504, Lon: -75.2014"
        lat_m = re.search(r'lat(?:itude)?\s*[:=]?\s*(-?\d+\.\d+)', text, re.IGNORECASE)
        if lat_m:
            try:
                extracted["latitude"] = round(float(lat_m.group(1)), 5)
            except Exception:
                pass

        lon_m = re.search(r'lon(?:gitude)?\s*[:=]?\s*(-?\d+\.\d+)', text, re.IGNORECASE)
        if lon_m:
            try:
                extracted["longitude"] = round(float(lon_m.group(1)), 5)
            except Exception:
                pass

        alt_m = re.search(r'alt(?:itude)?\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*m?', text, re.IGNORECASE)
        if alt_m:
            try:
                extracted["altitude_m"] = round(float(alt_m.group(1)), 1)
            except Exception:
                pass

        # Owner: "Owner: Repetidor Pico Cristal"
        owner_m = re.search(r'owner(?:\.name)?\s*[:=]?\s*([^\n\r,]+)', text, re.IGNORECASE)
        if owner_m:
            extracted["owner_name"] = owner_m.group(1).strip()

        # Version / Hardware: "Ver: v1.3.4 (Heltec V3 ESP32-S3)"
        ver_m = re.search(r'(?:ver|version|firmware)\s*[:=]?\s*([^\n\r]+)', text, re.IGNORECASE)
        if ver_m:
            extracted["firmware_version"] = ver_m.group(1).strip()

        board_m = re.search(r'board\s*[:=]?\s*([^\n\r]+)', text, re.IGNORECASE)
        if board_m:
            extracted["hardware_board"] = board_m.group(1).strip()

        return extracted

    def parse_log_packet(self, log_payload: Any) -> dict[str, Any]:
        """
        Parsea un evento push 0x88 (LOG_DATA / RX_LOG_DATA) emitido por un repetidor o sniffer.
        Extrae encabezados, tipo de ruta, saltos y calidad RF de dicts, bytes o cadenas.
        """
        now = time.time()

        # 1. Si ya es un diccionario (MeshCore SDK o deserializado)
        if isinstance(log_payload, dict):
            parsed = dict(log_payload)
            parsed["event_type"] = "rf_log"
            if "timestamp" not in parsed:
                parsed["timestamp"] = now
            for k, v in list(parsed.items()):
                if isinstance(v, (bytes, bytearray, memoryview)):
                    parsed[k] = bytes(v).hex()
            if "raw_hex" not in parsed and "payload" in parsed:
                if isinstance(parsed["payload"], str):
                    parsed["raw_hex"] = parsed["payload"]
            return parsed

        # 2. Si es una cadena de texto
        if isinstance(log_payload, str):
            return {
                "event_type": "rf_log",
                "raw_text": log_payload,
                "timestamp": now,
            }

        # 3. Si son bytes / bytearray / memoryview o convertible
        try:
            if isinstance(log_payload, (bytes, bytearray, memoryview)):
                raw_bytes = bytes(log_payload)
            else:
                raw_bytes = bytes(str(log_payload), "utf-8", "ignore")
        except Exception:
            raw_bytes = b""

        data_len = len(raw_bytes)
        parsed_bytes: dict[str, Any] = {
            "event_type": "rf_log",
            "byte_length": data_len,
            "raw_hex": raw_bytes.hex(),
            "timestamp": now,
        }

        if data_len >= 1:
            header_byte = raw_bytes[0]
            route_type = header_byte & 0x03
            payload_type = (header_byte >> 2) & 0x0F
            version = (header_byte >> 6) & 0x03

            parsed_bytes["route_type_id"] = route_type
            parsed_bytes["payload_type_id"] = payload_type
            parsed_bytes["version"] = version

        return parsed_bytes

