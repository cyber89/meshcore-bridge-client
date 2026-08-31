"""
Repeater Remote Management for MeshCore Bridge.
Gestiona el enrutamiento de comandos administrativos remotos hacia repetidores
y el análisis integral de su telemetría.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any

from src.shared_utils import clamp_tx_power


class RepeaterManager:
    """Administrador de comandos remotos a repetidores y analizador de telemetría."""

    def __init__(self, transmit_callback: Callable[[str, str, int], Any] | None = None) -> None:
        self.transmit_callback = transmit_callback

    def build_repeater_command_payload(self, action: str, params: dict[str, Any]) -> str:
        """Construye la cadena de comando en texto para enviar al firmware del repetidor."""
        act = action.strip().lower()

        # Comandos sin argumentos adicionales
        if act in (
            "stats",
            "status",
            "stats-core",
            "stats_core",
            "stats-radio",
            "stats_radio",
            "stats-packets",
            "stats_packets",
            "clock",
            "get_clock",
            "get clock",
            "time",
            "get_time",
            "get time",
            "bat",
            "get_bat",
            "get bat",
            "battery",
            "uptime",
            "get_uptime",
            "get uptime",
            "ver",
            "version",
            "get_ver",
            "get version",
            "query",
            "q",
            "clear_stats",
            "clear stats",
            "clear",
            "neighbors",
            "vecinos",
            "discover_neighbors",
            "discover.neighbors",
            "pos",
            "get_pos",
            "get pos",
            "position",
            "owner",
            "get_owner",
            "get owner",
            "identity",
            "get_identity",
            "get identity",
            "acl",
            "get_acl",
            "get acl",
            "channels",
            "chan",
            "get_radio",
            "get radio",
            "radio",
            "reboot",
            "restart",
            "ping",
            "ping 0",
            "ping_zero",
            "pingzero",
            "advert",
            "flood",
            "advert flood",
            "advert_flood",
            "log start",
            "log stop",
            "board",
            "trace 0",
            "help",
            "?",
            "ayuda",
        ):
            if act in ("clear_stats", "clear stats", "clear"):
                return "clear stats"
            if act in ("neighbors", "vecinos", "discover_neighbors", "discover.neighbors"):
                return "neighbors"
            if act in ("pos", "get_pos", "get pos", "position", "lat", "get_lat", "get lat"):
                return "get lat"
            if act in ("lon", "get_lon", "get lon"):
                return "get lon"
            if act in ("owner", "get_owner", "get owner", "identity", "get_identity", "get identity", "get owner.info", "owner.info"):
                return "get owner.info"
            if act in ("acl", "get_acl", "get acl"):
                return "get allow.read.only"
            if act in ("get_radio", "get radio", "radio", "stats_radio", "stats-radio"):
                return "stats-radio" if "stats" in act else "get radio"
            if act in ("stats_core", "stats-core", "stats", "status"):
                return "stats-core"
            if act in ("stats_packets", "stats-packets"):
                return "stats-packets"
            if act in ("bat", "get_bat", "get bat", "battery"):
                return "get pwrmgt.bootmv"
            if act in ("clock", "get_clock", "get clock", "time", "get_time", "get time"):
                return "clock"
            if act in ("sync_clock", "clock_sync", "st", "clock sync"):
                return "clock sync"
            if act in ("ping_zero", "pingzero", "ping 0", "trace 0", "ping"):
                return "ping 0"
            if act in ("advert.zerohop", "advert_zerohop", "zerohop"):
                return "advert.zerohop"
            if act in ("flood", "advert flood", "advert_flood", "advert"):
                return "advert"
            if act in ("ver", "version", "query"):
                return "ver"
            if act in ("board", "hardware"):
                return "board"
            if act in ("help", "?", "ayuda"):
                return "help"
            return act

        # Si ya viene formateado como comando directo "set ...", "cmd ...", "login ..."
        if act.startswith("set ") or act.startswith("login ") or act.startswith("acl ") or act.startswith("cmd "):
            return action

        # 1. Autenticación
        if act in ("login", "auth"):
            password = params.get("password", "")
            return f"login {password}"

        # 2. Node Name & Owner Info
        if act in ("set_name", "name", "rename"):
            name = params.get("name", params.get("new_name", "Repeater"))
            return f"set name {name}"

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

        # 5. Radio Frequency & Power
        if act in ("set_frequency", "set_freq", "frequency", "freq"):
            freq = params.get("frequency", params.get("freq", 915.0))
            return f"set freq {freq}"

        if act in ("set_tx_power", "set_power", "tx_power", "power", "set_tx", "tx"):
            pwr = params.get("tx_power", params.get("power", params.get("tx", 20)))
            hw_board = params.get("hardware_board", params.get("board", params.get("hw_model")))
            max_p_hint = params.get("max_tx_power", params.get("max_power"))
            pwr_clamped = clamp_tx_power(int(pwr), hw_board, max_p_hint)
            return f"set tx {pwr_clamped}"


        # 6. LoRa Modem Parameters
        if act in ("set_sf", "set_spreading_factor", "sf"):
            sf = params.get("spreading_factor", params.get("sf", 11))
            return f"set sf {sf}"

        if act in ("set_bw", "set_bandwidth", "bandwidth", "bw"):
            bw = params.get("bandwidth", params.get("bw", 250.0))
            return f"set bw {bw}"

        if act in ("set_cr", "set_coding_rate", "coding_rate", "cr"):
            cr = params.get("coding_rate", params.get("cr", 5))
            return f"set cr {cr}"

        # 7. Access Control Lists (ACL)
        if act in ("acl_add", "add_acl", "acl.add"):
            pk = params.get("public_key", params.get("pk", ""))
            perm = params.get("permission", params.get("perm", "admin"))
            return f"acl add {pk} {perm}"

        if act in ("acl_remove", "remove_acl", "acl.remove", "acl_del"):
            pk = params.get("public_key", params.get("pk", ""))
            return f"acl remove {pk}"

        if act in ("acl_list", "get_acl_list", "acl.list"):
            return "acl list"

        # 8. Password & Security
        if act in ("set_admin_password", "set_password", "change_password", "password"):
            new_pwd = params.get("new_password", params.get("password", ""))
            return f"set admin.password {new_pwd}"

        if act in ("set_guest_password", "guest_password"):
            new_pwd = params.get("guest_password", params.get("password", ""))
            return f"set guest.password {new_pwd}"

        # 9. Clock & Time
        if act in ("set_clock", "set_time", "sync_time", "clock_sync"):
            ts = params.get("timestamp", params.get("time", int(time.time())))
            return f"set clock {ts}"

        # 10. Repeat Settings
        if act in ("set_repeat", "repeat_settings", "repeat"):
            enabled = params.get("repeat", params.get("enabled", True))
            val = "on" if enabled is True or str(enabled).lower() in ("true", "1", "on") else "off"
            return f"set repeat {val}"

        if act in ("set_hop_limit", "hop_limit"):
            hl = params.get("hop_limit", params.get("hops", 3))
            return f"set hop_limit {hl}"

        return action

    def extract_all_repeater_params_from_text(self, raw_text: str) -> dict[str, Any]:
        """Alias para extracción completa de parámetros de repetidor a partir de texto CLI/telemetría."""
        return self.parse_repeater_telemetry_or_response(raw_text)

    def parse_repeater_telemetry_or_response(self, raw_text: str) -> dict[str, Any]:
        """
        Analiza cadenas de texto provenientes de respuestas de repetidores MeshCore
        (stats-core, stats-radio, telemetry, status, clock, pos, ver) y extrae métricas estructuradas.
        """
        extracted: dict[str, Any] = {}
        text = raw_text.strip()
        if not text:
            return extracted

        lower_text = text.lower()
        if any(p in lower_text for p in ("invalid password", "access denied", "bad pin", "login failed", "wrong password", "incorrect password", "not authorized", "unauthorized", "permission denied", "not logged in")):
            extracted["auth_status"] = "failed"
            extracted["auth_error"] = text.strip()
        elif any(p in lower_text for p in ("login ok", "logged in", "auth ok", "welcome admin", "access granted", "login success")):
            extracted["auth_status"] = "success"

        # 0. Parsing directo si la respuesta viene en formato JSON (firmware oficial MeshCore C++ StatsFormatHelper)
        if text.startswith("{") and text.endswith("}"):
            try:
                data_json = json.loads(text)
                if isinstance(data_json, dict):
                    # Batería / Voltaje: {"battery_mv": 4120} o {"batt_mv": 4120} o {"battery": 92}
                    if "battery_mv" in data_json or "batt_mv" in data_json or "battery" in data_json:
                        raw_bat = data_json.get("battery_mv", data_json.get("batt_mv", data_json.get("battery")))
                        if isinstance(raw_bat, (int, float)):
                            if raw_bat > 100:
                                extracted["voltage_v"] = round(raw_bat / 1000.0, 2)
                                extracted["battery_pct"] = max(0, min(100, int((raw_bat - 3300) / (4200 - 3300) * 100)))
                            else:
                                extracted["battery_pct"] = int(raw_bat)
                    if "voltage_v" in data_json or "voltage" in data_json:
                        raw_v = data_json.get("voltage_v", data_json.get("voltage"))
                        if isinstance(raw_v, (int, float)):
                            extracted["voltage_v"] = round(float(raw_v), 2)
                    if "solar_mv" in data_json or "solar_v" in data_json or "solar" in data_json:
                        raw_sol = data_json.get("solar_mv", data_json.get("solar_v", data_json.get("solar")))
                        if isinstance(raw_sol, (int, float)):
                            extracted["solar_v"] = round(raw_sol / 1000.0, 2) if raw_sol > 100 else round(float(raw_sol), 2)
                    if "uptime_secs" in data_json or "uptime" in data_json:
                        raw_up = data_json.get("uptime_secs", data_json.get("uptime"))
                        if isinstance(raw_up, (int, float)):
                            secs = int(raw_up)
                            days, rem = divmod(secs, 86400)
                            hours, rem = divmod(rem, 3600)
                            mins, s = divmod(rem, 60)
                            extracted["uptime"] = f"{days}d {hours}h {mins}m" if days > 0 else f"{hours}h {mins}m {s}s"
                        else:
                            extracted["uptime"] = str(raw_up)
                    if "errors" in data_json:
                        extracted["packet_errors"] = int(data_json["errors"])
                    if "queue_len" in data_json:
                        extracted["queue_len"] = int(data_json["queue_len"])
                    if "noise_floor" in data_json:
                        extracted["noise_floor_dbm"] = int(data_json["noise_floor"])
                    if "last_rssi" in data_json:
                        extracted["last_rssi"] = int(data_json["last_rssi"])
                    if "last_snr" in data_json:
                        extracted["last_snr"] = round(float(data_json["last_snr"]), 1)
                    if "tx_air_secs" in data_json:
                        extracted["airtime_ms"] = int(float(data_json["tx_air_secs"]) * 1000)
                    if "sent" in data_json:
                        extracted["packets_sent"] = int(data_json["sent"])
                    if "recv" in data_json:
                        extracted["packets_recv"] = int(data_json["recv"])
                    if "recv_errors" in data_json:
                        extracted["packet_errors"] = int(data_json["recv_errors"])
                    if "repeat" in data_json or "repeat_enabled" in data_json or "repeating" in data_json:
                        raw_rep = data_json.get("repeat", data_json.get("repeat_enabled", data_json.get("repeating")))
                        extracted["repeat_enabled"] = bool(raw_rep) if not isinstance(raw_rep, str) else raw_rep.lower() in ("1", "true", "on", "enabled", "activado")
                    if "hop_limit" in data_json or "hops" in data_json or "max_hops" in data_json:
                        raw_hl = data_json.get("hop_limit", data_json.get("max_hops", data_json.get("hops")))
                        if isinstance(raw_hl, (int, float)):
                            extracted["hop_limit"] = int(raw_hl)
                    if "tx_power" in data_json or "power" in data_json:
                        raw_pwr = data_json.get("tx_power", data_json.get("power"))
                        if raw_pwr is not None:
                            extracted["tx_power"] = int(raw_pwr)
                    if "max_tx_power" in data_json or "max_power" in data_json:
                        raw_mp = data_json.get("max_tx_power", data_json.get("max_power"))
                        if raw_mp is not None:
                            extracted["max_tx_power"] = int(raw_mp)
                    if "freq" in data_json or "frequency" in data_json:
                        raw_fr = data_json.get("freq", data_json.get("frequency"))
                        if raw_fr is not None:
                            extracted["frequency"] = round(float(raw_fr), 3)
                    if "sf" in data_json or "spreading_factor" in data_json:
                        raw_sf = data_json.get("sf", data_json.get("spreading_factor"))
                        if raw_sf is not None:
                            extracted["spreading_factor"] = int(raw_sf)
                    if "bw" in data_json or "bandwidth" in data_json:
                        raw_bw = data_json.get("bw", data_json.get("bandwidth"))
                        if raw_bw is not None:
                            extracted["bandwidth"] = float(raw_bw)
                    if "cr" in data_json or "coding_rate" in data_json:
                        raw_cr = data_json.get("cr", data_json.get("coding_rate"))
                        if raw_cr is not None:
                            extracted["coding_rate"] = str(raw_cr).strip()
                    if "beacon_interval" in data_json or "advert_interval" in data_json:
                        raw_bi = data_json.get("beacon_interval", data_json.get("advert_interval"))
                        if raw_bi is not None:
                            extracted["advert_interval"] = int(raw_bi)
                    if "owner" in data_json or "owner_name" in data_json:
                        raw_ow = data_json.get("owner_name", data_json.get("owner"))
                        if raw_ow is not None:
                            extracted["owner_name"] = str(raw_ow)
                    if "owner_info" in data_json:
                        raw_oi = data_json.get("owner_info")
                        if raw_oi is not None:
                            extracted["owner_info"] = str(raw_oi)
                    if "lat" in data_json or "latitude" in data_json:
                        raw_la = data_json.get("lat", data_json.get("latitude"))
                        if raw_la is not None:
                            extracted["latitude"] = round(float(raw_la), 5)
                    if "lon" in data_json or "longitude" in data_json:
                        raw_lo = data_json.get("lon", data_json.get("longitude"))
                        if raw_lo is not None:
                            extracted["longitude"] = round(float(raw_lo), 5)
                    if "alt" in data_json or "altitude" in data_json:
                        raw_al = data_json.get("alt", data_json.get("altitude"))
                        if raw_al is not None:
                            extracted["altitude_m"] = round(float(raw_al), 1)
            except Exception:
                pass

        # Batería & Voltaje de Alimentación:
        # Formatos: "Battery: 4120mV (92%)", "Batt: 4.12V, 95%", "Battery: 92%", "Bat: 92%", "> 4120 mV", "Boot voltage = 4120 mV", "> 4.12 V", "> 95%"
        bat_m = re.search(r'(?:battery|batt|bat|pwrmgt\.bootmv|boot\s+voltage|bootmv)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mv|v|%)?(?:\s*\((?:(\d+)\s*%)?\))?', text, re.IGNORECASE)
        if not bat_m:
            bat_m = re.search(r'(?:^|>)\s*(\d{3,4})\s*(?:mv)?(?:\s*\((?:(\d+)\s*%)?\))?$', text, re.IGNORECASE)
        if not bat_m:
            bat_m = re.search(r'(?:^|>)\s*([34]\.\d{1,3})\s*(?:v)?$', text, re.IGNORECASE)
        if not bat_m:
            bat_m = re.search(r'(?:^|>)\s*(\d{1,2}|100)\s*%$', text, re.IGNORECASE)

        if bat_m:
            raw_val_str = bat_m.group(1)
            pct_in_paren = bat_m.group(2) if bat_m.lastindex and bat_m.lastindex >= 2 else None
            try:
                val_num = float(raw_val_str)
                if "%" in bat_m.group(0) or (val_num <= 100.0 and val_num > 4.5):
                    extracted["battery_pct"] = int(val_num)
                elif val_num > 100.0:  # mV (ej 4120)
                    extracted["voltage_v"] = round(val_num / 1000.0, 2)
                    if pct_in_paren:
                        extracted["battery_pct"] = int(pct_in_paren)
                    else:
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

        # Formato de respuesta de radio directa: "> 915.000,250,11,5" (freq, bw, sf, cr)
        radio_line_m = re.search(r'(?:^|>)\s*(\d{3}(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+)\s*,\s*(\d+)', text)
        if radio_line_m:
            try:
                extracted["frequency"] = round(float(radio_line_m.group(1)), 3)
                extracted["bandwidth"] = float(radio_line_m.group(2))
                extracted["spreading_factor"] = int(radio_line_m.group(3))
                cr_raw = radio_line_m.group(4).strip()
                extracted["coding_rate"] = f"4/{cr_raw}" if cr_raw in ("5", "6", "7", "8") else cr_raw
            except Exception:
                pass

        # Voltaje explícito si no vino en batería: "Voltage: 4.12V" o "VBat: 4.12" o "V: 4.12V"
        if "voltage_v" not in extracted:
            volt_m = re.search(r'(?:voltage|volt|vbat|v_bat)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mv|v)?', text, re.IGNORECASE)
            if volt_m:
                try:
                    v_num = float(volt_m.group(1))
                    extracted["voltage_v"] = round(v_num / 1000.0, 2) if v_num > 100.0 else round(v_num, 2)
                    if "battery_pct" not in extracted:
                        extracted["battery_pct"] = max(0, min(100, int((extracted["voltage_v"] - 3.3) / (4.2 - 3.3) * 100)))
                except Exception:
                    pass

        # Solar / Voltaje de entrada: "Solar: 5.12V" o "VIn: 5.12V" o "Solar Volt: 5.12"
        solar_m = re.search(r'(?:solar(?:_v)?|vin|v_in|vsolar|input(?:_v)?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*v?', text, re.IGNORECASE)
        if solar_m:
            try:
                extracted["solar_v"] = round(float(solar_m.group(1)), 2)
            except Exception:
                pass

        # Clock / RTC: "Clock: 2026-08-18 22:15:00" o "RTC: 18:52:39" o "Time: 18:52:39"
        clock_m = re.search(r'(?:clock|rtc|time)\s*[:=]?\s*([0-9\-:\s]+(?:[ap]m)?)', text, re.IGNORECASE)
        if clock_m:
            extracted["clock"] = clock_m.group(1).strip()

        # Uptime: "Uptime: 3d 14h 22m" o "Uptime: 310920s" o "Up: 142h 30m"
        uptime_m = re.search(r'(?:uptime|up)\s*[:=]?\s*([0-9a-zA-Z\s]+?)(?:,|$|\n)', text, re.IGNORECASE)
        if uptime_m:
            extracted["uptime"] = uptime_m.group(1).strip()

        # Total Airtime: "Total Airtime: 1420ms (0.24%)" o "Airtime: 1420ms" o "Airtime: 1.42s"
        airtime_m = re.search(r'(?:total\s+)?airtime\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(ms|s)?', text, re.IGNORECASE)
        if airtime_m:
            try:
                raw_at = float(airtime_m.group(1))
                unit = (airtime_m.group(2) or "ms").lower()
                extracted["airtime_ms"] = int(raw_at * 1000) if unit == "s" else int(raw_at)
            except Exception:
                pass

        # Noise Floor: "Noise Floor: -118 dBm" o "Noise: -118dBm" o "Floor: -118 dBm"
        noise_m = re.search(r'(?:noise(?:\s*floor)?|noisefloor|floor)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(?:dbm)?', text, re.IGNORECASE)
        if noise_m:
            try:
                extracted["noise_floor_dbm"] = int(float(noise_m.group(1)))
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

        # Packets Sent / Received / Duplicates / Errors / Queue:
        pkt_block = re.search(r'packets:\s*rx=(\d+),\s*tx=(\d+)(?:,\s*routed=(\d+))?(?:,\s*(?:drop|err|errors?)=(\d+))?', text, re.IGNORECASE)
        if pkt_block:
            try:
                extracted["packets_recv"] = int(pkt_block.group(1))
                extracted["packets_sent"] = int(pkt_block.group(2))
                if pkt_block.group(4):
                    extracted["packet_errors"] = int(pkt_block.group(4))
            except Exception:
                pass

        if "packets_sent" not in extracted:
            sent_m = re.search(r'(?:packets?\s+sent|tx\s+packets?|sent\s+packets?|nb_sent)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
            if sent_m:
                try:
                    extracted["packets_sent"] = int(sent_m.group(1))
                except Exception:
                    pass

        if "packets_recv" not in extracted:
            recv_m = re.search(r'(?:packets?\s+rec(?:ei)?ved|rx\s+packets?|rec(?:ei)?ved\s+packets?|nb_recv)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
            if recv_m:
                try:
                    extracted["packets_recv"] = int(recv_m.group(1))
                except Exception:
                    pass

        dup_m = re.search(r'(?:duplicate\s+packets?(?:\s+seen)?|duplicates?|direct_dups|flood_dups)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
        if dup_m:
            try:
                extracted["duplicate_packets"] = int(dup_m.group(1))
            except Exception:
                pass

        err_m = re.search(r'(?:rec(?:ei)?ved\s+packet\s+errors?|rx\s+errors?|packet\s+errors?|errors?)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
        if err_m and "packet_errors" not in extracted:
            try:
                extracted["packet_errors"] = int(err_m.group(1))
            except Exception:
                pass

        queue_m = re.search(r'(?:queue(?:\s+length)?|tx_queue_len)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
        if queue_m:
            try:
                extracted["queue_len"] = int(queue_m.group(1))
            except Exception:
                pass

        # Radio RF Parameters: Freq, Power, SF, BW, CR, Repeat, Hops, Beacon/Advert
        freq_m = re.search(r'(?:freq(?:uency)?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mhz)?', text, re.IGNORECASE)
        if freq_m:
            try:
                extracted["frequency"] = round(float(freq_m.group(1)), 3)
            except Exception:
                pass

        power_m = re.search(r'(?:tx_?power|power)\s*[:=]?\s*(\d+)\s*(?:dbm)?', text, re.IGNORECASE)
        if not power_m:
            power_m = re.search(r'(?:^|[\s,;])tx\s*[:=]?\s*(\d+)\s*dbm', text, re.IGNORECASE)
        if not power_m:
            power_m = re.search(r'(?:params|radio|config)?:.*?\btx\s*[:=]?\s*(\d{1,2})\b', text, re.IGNORECASE)
        if power_m:
            try:
                p_val = int(power_m.group(1))
                if p_val <= 33:  # Potencia LoRa válida en dBm (1 a 33 dBm)
                    extracted["tx_power"] = p_val
            except Exception:
                pass

        sf_m = re.search(r'(?:spreading_?factor|sf)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
        if sf_m:
            try:
                extracted["spreading_factor"] = int(sf_m.group(1))
            except Exception:
                pass

        bw_m = re.search(r'(?:bandwidth|bw)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:khz)?', text, re.IGNORECASE)
        if bw_m:
            try:
                extracted["bandwidth"] = float(bw_m.group(1))
            except Exception:
                pass

        cr_m = re.search(r'(?:coding_?rate|cr)\s*[:=]?\s*([0-9/]+)', text, re.IGNORECASE)
        if cr_m:
            extracted["coding_rate"] = cr_m.group(1).strip()

        repeat_m = re.search(r'(?:repeat(?:er)?|repeating|mode|routing)\s*[:=]?\s*(on|off|true|false|1|0|enabled|disabled|activa(?:do)?|desactiva(?:do)?)', text, re.IGNORECASE)
        if repeat_m:
            extracted["repeat_enabled"] = repeat_m.group(1).lower() in ("on", "true", "1", "enabled", "activado", "active")

        hops_m = re.search(r'(?:hop_?limit|max_?hops|default_?hops?)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
        if hops_m:
            try:
                extracted["hop_limit"] = int(hops_m.group(1))
            except Exception:
                pass

        hop_cnt_m = re.search(r'(?:hop\s+count|hops?|saltos?)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
        if hop_cnt_m:
            try:
                extracted["hops"] = int(hop_cnt_m.group(1))
                if "hop_limit" not in extracted:
                    extracted["hop_limit"] = int(hop_cnt_m.group(1))
            except Exception:
                pass

        advert_m = re.search(r'(?:advert(?:_?interval)?|beacon(?:_?interval)?)\s*[:=]?\s*(\d+)\s*s?', text, re.IGNORECASE)
        if advert_m:
            try:
                extracted["advert_interval"] = int(advert_m.group(1))
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

        fixed_m = re.search(r'fixed(?:\s*pos(?:ition)?)?\s*[:=]?\s*(on|off|1|0|true|false)', text, re.IGNORECASE)
        if fixed_m:
            extracted["fixed_position"] = fixed_m.group(1).lower() in ("on", "1", "true")

        # Owner: "Owner: Repetidor Pico Cristal" o "Owner.name: R1-Lee"
        owner_m = re.search(r'owner(?:\.name)?\s*[:=]?\s*([^\n\r,]+)', text, re.IGNORECASE)
        if owner_m:
            extracted["owner_name"] = owner_m.group(1).strip()

        owner_info_m = re.search(r'owner(?:\.info)?\s*[:=]?\s*([^\n\r]+)', text, re.IGNORECASE)
        if owner_info_m and not owner_info_m.group(0).lower().startswith("owner.name") and not owner_info_m.group(0).lower().startswith("owner:"):
            extracted["owner_info"] = owner_info_m.group(1).strip()

        # Version / Hardware: "Ver: v1.3.4 (Heltec V3 ESP32-S3)"
        ver_m = re.search(r'(?:ver|version|firmware)\s*[:=]?\s*([^\n\r]+)', text, re.IGNORECASE)
        if ver_m:
            extracted["firmware_version"] = ver_m.group(1).strip()

        board_m = re.search(r'board\s*[:=]?\s*([^\n\r]+)', text, re.IGNORECASE)
        if board_m:
            extracted["hardware_board"] = board_m.group(1).strip()

        return extracted

