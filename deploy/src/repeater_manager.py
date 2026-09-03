"""
Repeater Remote Management for MeshCore Bridge.
Gestiona el enrutamiento de comandos administrativos remotos hacia repetidores
y el análisis integral de su telemetría con control de Airtime LoRa.
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

    def __init__(
        self,
        transmit_callback: Callable[[str, str, int], Any] | None = None,
        min_cmd_interval_s: float = 5.0,
        min_telemetry_interval_s: float = 30.0,
    ) -> None:
        self.transmit_callback = transmit_callback
        self.min_cmd_interval_s = min_cmd_interval_s
        self.min_telemetry_interval_s = min_telemetry_interval_s
        self._last_cmd_ts: dict[str, float] = {}
        self._last_full_telemetry_ts: dict[str, float] = {}

    def check_airtime_cooldown(self, repeater_pk: str, is_full_query: bool = False) -> tuple[bool, float]:
        """
        Verifica si el repetidor ha cumplido su periodo de enfriamiento (cooldown) antes de transmitir.
        Retorna (puede_enviar: bool, segundos_restantes: float).
        """
        now = time.monotonic()
        clean_pk = repeater_pk.strip().lower()

        min_interval = self.min_telemetry_interval_s if is_full_query else self.min_cmd_interval_s
        last_ts = self._last_full_telemetry_ts.get(clean_pk, 0.0) if is_full_query else self._last_cmd_ts.get(clean_pk, 0.0)

        elapsed = now - last_ts
        if elapsed < min_interval:
            return False, round(min_interval - elapsed, 1)

        return True, 0.0

    def record_command_sent(self, repeater_pk: str, is_full_query: bool = False) -> None:
        """Registra el timestamp de transmisión hacia un repetidor para gobernar el airtime."""
        now = time.monotonic()
        clean_pk = repeater_pk.strip().lower()
        self._last_cmd_ts[clean_pk] = now
        if is_full_query:
            self._last_full_telemetry_ts[clean_pk] = now

    def build_repeater_command_payload(self, action: str, params: dict[str, Any]) -> str:
        """Construye la cadena de comando en texto para enviar al firmware del repetidor."""
        act = action.strip().lower()

        # 1. Comandos sin argumentos adicionales (consultas/queries)
        query_cmd = self._build_query_cmd(act)
        if query_cmd:
            return query_cmd

        # Comandos que ya vienen formateados directamente
        if act.startswith(("set ", "login ", "acl ", "cmd ")):
            return action

        # 2. Comandos de radio y parámetros RF
        radio_cmd = self._build_radio_cmd(act, params)
        if radio_cmd:
            return radio_cmd

        # 3. Comandos de posición, identidad y propietario
        owner_pos_cmd = self._build_owner_and_location_cmd(act, params)
        if owner_pos_cmd:
            return owner_pos_cmd

        # 4. Comandos de ACL, autenticación y seguridad
        acl_sec_cmd = self._build_acl_and_security_cmd(act, params)
        if acl_sec_cmd:
            return acl_sec_cmd

        return action

    def _build_query_cmd(self, act: str) -> str | None:
        """Construye comandos de lectura sin argumentos adicionales."""
        query_map: dict[str, str] = {
            "stats": "stats-core",
            "status": "stats-core",
            "stats-core": "stats-core",
            "stats_core": "stats-core",
            "stats-radio": "stats-radio",
            "stats_radio": "stats-radio",
            "stats-packets": "stats-packets",
            "stats_packets": "stats-packets",
            "clear": "clear stats",
            "clear_stats": "clear stats",
            "clear stats": "clear stats",
            "clock": "clock",
            "get_clock": "clock",
            "get clock": "clock",
            "time": "clock",
            "get_time": "clock",
            "get time": "clock",
            "sync_clock": "clock sync",
            "clock_sync": "clock sync",
            "st": "clock sync",
            "clock sync": "clock sync",
            "bat": "get pwrmgt.bootmv",
            "get_bat": "get pwrmgt.bootmv",
            "get bat": "get pwrmgt.bootmv",
            "battery": "get pwrmgt.bootmv",
            "uptime": "get uptime",
            "get_uptime": "get uptime",
            "get uptime": "get uptime",
            "ver": "ver",
            "version": "ver",
            "get_ver": "ver",
            "get version": "ver",
            "query": "ver",
            "q": "ver",
            "board": "board",
            "hardware": "board",
            "help": "help",
            "?": "help",
            "ayuda": "help",
            "neighbors": "neighbors",
            "vecinos": "neighbors",
            "discover_neighbors": "neighbors",
            "discover.neighbors": "neighbors",
            "pos": "get lat",
            "get_pos": "get lat",
            "get pos": "get lat",
            "position": "get lat",
            "lat": "get lat",
            "get_lat": "get lat",
            "get lat": "get lat",
            "lon": "get lon",
            "get_lon": "get lon",
            "get lon": "get lon",
            "owner": "get owner.info",
            "get_owner": "get owner.info",
            "get owner": "get owner.info",
            "identity": "get owner.info",
            "get_identity": "get owner.info",
            "get identity": "get owner.info",
            "get owner.info": "get owner.info",
            "owner.info": "get owner.info",
            "acl": "get allow.read.only",
            "get_acl": "get allow.read.only",
            "get acl": "get allow.read.only",
            "get_radio": "get radio",
            "get radio": "get radio",
            "radio": "get radio",
            "ping": "ping 0",
            "ping 0": "ping 0",
            "ping_zero": "ping 0",
            "pingzero": "ping 0",
            "trace 0": "ping 0",
            "advert": "advert",
            "flood": "advert",
            "advert flood": "advert",
            "advert_flood": "advert",
            "advert.zerohop": "advert.zerohop",
            "advert_zerohop": "advert.zerohop",
            "zerohop": "advert.zerohop",
            "log start": "log start",
            "log stop": "log stop",
            "reboot": "reboot",
            "restart": "reboot",
        }
        return query_map.get(act)

    def _build_radio_cmd(self, act: str, params: dict[str, Any]) -> str | None:
        """Construye comandos de parámetros de radio y modem LoRa."""
        if act in ("set_frequency", "set_freq", "frequency", "freq"):
            freq = params.get("frequency", params.get("freq", 915.0))
            return f"set freq {freq}"

        if act in ("set_tx_power", "set_power", "tx_power", "power", "set_tx", "tx"):
            pwr = params.get("tx_power", params.get("power", params.get("tx", 20)))
            hw_board = params.get("hardware_board", params.get("board", params.get("hw_model")))
            max_p_hint = params.get("max_tx_power", params.get("max_power"))
            pwr_clamped = clamp_tx_power(int(pwr), hw_board, max_p_hint)
            return f"set tx {pwr_clamped}"

        if act in ("set_sf", "set_spreading_factor", "sf"):
            sf = params.get("spreading_factor", params.get("sf", 11))
            return f"set sf {sf}"

        if act in ("set_bw", "set_bandwidth", "bandwidth", "bw"):
            bw = params.get("bandwidth", params.get("bw", 250.0))
            return f"set bw {bw}"

        if act in ("set_cr", "set_coding_rate", "coding_rate", "cr"):
            cr = params.get("coding_rate", params.get("cr", 5))
            return f"set cr {cr}"

        if act in ("set_repeat", "repeat_settings", "repeat"):
            enabled = params.get("repeat", params.get("enabled", True))
            val = "on" if enabled is True or str(enabled).lower() in ("true", "1", "on") else "off"
            return f"set repeat {val}"

        if act in ("set_hop_limit", "hop_limit"):
            hl = params.get("hop_limit", params.get("hops", 3))
            return f"set hop_limit {hl}"

        return None

    def _build_owner_and_location_cmd(self, act: str, params: dict[str, Any]) -> str | None:
        """Construye comandos de nombre de nodo, propietario y ubicación geográfica."""
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

        if act in ("set_advert_interval", "set_beacon", "advert_intervals", "beacon"):
            interval = params.get("advert_interval", params.get("beacon_interval", params.get("interval", params.get("beacon", 300))))
            return f"set advert.interval {interval}"

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

        return None

    def _build_acl_and_security_cmd(self, act: str, params: dict[str, Any]) -> str | None:
        """Construye comandos de autenticación, ACL y sincronización horaria."""
        if act in ("login", "auth"):
            password = params.get("password", "")
            return f"login {password}"

        if act in ("acl_add", "add_acl", "acl.add"):
            pk = params.get("public_key", params.get("pk", ""))
            perm = params.get("permission", params.get("perm", "admin"))
            return f"acl add {pk} {perm}"

        if act in ("acl_remove", "remove_acl", "acl.remove", "acl_del"):
            pk = params.get("public_key", params.get("pk", ""))
            return f"acl remove {pk}"

        if act in ("acl_list", "get_acl_list", "acl.list"):
            return "acl list"

        if act in ("set_admin_password", "set_password", "change_password", "password"):
            new_pwd = params.get("new_password", params.get("password", ""))
            return f"set admin.password {new_pwd}"

        if act in ("set_guest_password", "guest_password"):
            new_pwd = params.get("guest_password", params.get("password", ""))
            return f"set guest.password {new_pwd}"

        if act in ("set_clock", "set_time", "sync_time", "clock_sync"):
            ts = params.get("timestamp", params.get("time", int(time.time())))
            return f"set clock {ts}"

        return None

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
        self._parse_auth_status(lower_text, text, extracted)

        # 0. Parsing directo si la respuesta viene en formato JSON
        if self._parse_json_telemetry(text, extracted):
            return extracted

        # Parsing de campos en texto libre o CLI
        self._parse_battery_and_voltage(text, extracted)
        self._parse_radio_parameters(text, extracted)
        self._parse_system_metrics(text, extracted)
        self._parse_owner_and_location(text, extracted)

        return extracted

    def _parse_auth_status(self, lower_text: str, text: str, extracted: dict[str, Any]) -> None:
        """Identifica estados de éxito o fallo de autenticación remota."""
        fail_markers = (
            "invalid password",
            "access denied",
            "bad pin",
            "login failed",
            "wrong password",
            "incorrect password",
            "not authorized",
            "unauthorized",
            "permission denied",
            "not logged in",
        )
        if any(p in lower_text for p in fail_markers):
            extracted["auth_status"] = "failed"
            extracted["auth_error"] = text.strip()
        elif any(p in lower_text for p in ("login ok", "logged in", "auth ok", "welcome admin", "access granted", "login success")):
            extracted["auth_status"] = "success"

    def _parse_json_telemetry(self, text: str, extracted: dict[str, Any]) -> bool:
        """Parsea telemetría si viene serializada en JSON oficial MeshCore."""
        if not (text.startswith("{") and text.endswith("}")):
            return False

        try:
            data_json = json.loads(text)
            if not isinstance(data_json, dict):
                return False

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

            if "owner" in data_json or "owner_name" in data_json:
                raw_ow = data_json.get("owner_name", data_json.get("owner"))
                if raw_ow is not None:
                    extracted["owner_name"] = str(raw_ow)

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

            return True
        except Exception:
            return False

    def _parse_battery_and_voltage(self, text: str, extracted: dict[str, Any]) -> None:
        """Extrae porcentaje de batería, voltaje y lecturas solares de respuestas CLI."""
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
                elif val_num > 100.0:  # mV
                    extracted["voltage_v"] = round(val_num / 1000.0, 2)
                    if pct_in_paren:
                        extracted["battery_pct"] = int(pct_in_paren)
                    else:
                        extracted["battery_pct"] = max(0, min(100, int((val_num - 3300) / (4200 - 3300) * 100)))
                else:  # V
                    extracted["voltage_v"] = round(val_num, 2)
                    if pct_in_paren:
                        extracted["battery_pct"] = int(pct_in_paren)
                    else:
                        extracted["battery_pct"] = max(0, min(100, int((val_num - 3.3) / (4.2 - 3.3) * 100)))
            except Exception:
                pass

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

        solar_m = re.search(r'(?:solar(?:_v)?|vin|v_in|vsolar|input(?:_v)?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*v?', text, re.IGNORECASE)
        if solar_m:
            try:
                extracted["solar_v"] = round(float(solar_m.group(1)), 2)
            except Exception:
                pass

    def _parse_radio_parameters(self, text: str, extracted: dict[str, Any]) -> None:
        """Extrae parámetros de módem RF LoRa (frecuencia, potencia, SF, BW, CR)."""
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
                if p_val <= 33:
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

    def _parse_system_metrics(self, text: str, extracted: dict[str, Any]) -> None:
        """Extrae uptime, ruido base, airtime, paquetes transmitidos y métricas de enlace."""
        clock_m = re.search(r'(?:clock|rtc|time)\s*[:=]?\s*([0-9\-:\s]+(?:[ap]m)?)', text, re.IGNORECASE)
        if clock_m:
            extracted["clock"] = clock_m.group(1).strip()

        uptime_m = re.search(r'(?:uptime|up)\s*[:=]?\s*([0-9a-zA-Z\s]+?)(?:,|$|\n)', text, re.IGNORECASE)
        if uptime_m:
            extracted["uptime"] = uptime_m.group(1).strip()

        airtime_m = re.search(r'(?:total\s+)?airtime\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(ms|s)?', text, re.IGNORECASE)
        if airtime_m:
            try:
                raw_at = float(airtime_m.group(1))
                unit = (airtime_m.group(2) or "ms").lower()
                extracted["airtime_ms"] = int(raw_at * 1000) if unit == "s" else int(raw_at)
            except Exception:
                pass

        noise_m = re.search(r'(?:noise(?:\s*floor)?|noisefloor|floor)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(?:dbm)?', text, re.IGNORECASE)
        if noise_m:
            try:
                extracted["noise_floor_dbm"] = int(float(noise_m.group(1)))
            except Exception:
                pass

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

    def _parse_owner_and_location(self, text: str, extracted: dict[str, Any]) -> None:
        """Extrae coordenadas GPS, propietario e información de versión del firmware."""
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

        owner_m = re.search(r'owner(?:\.name)?\s*[:=]?\s*([^\n\r,]+)', text, re.IGNORECASE)
        if owner_m:
            extracted["owner_name"] = owner_m.group(1).strip()

        owner_info_m = re.search(r'owner(?:\.info)?\s*[:=]?\s*([^\n\r]+)', text, re.IGNORECASE)
        if owner_info_m and not owner_info_m.group(0).lower().startswith("owner.name") and not owner_info_m.group(0).lower().startswith("owner:"):
            extracted["owner_info"] = owner_info_m.group(1).strip()

        ver_m = re.search(r'(?:ver|version|firmware)\s*[:=]?\s*([^\n\r]+)', text, re.IGNORECASE)
        if ver_m:
            extracted["firmware_version"] = ver_m.group(1).strip()

        board_m = re.search(r'board\s*[:=]?\s*([^\n\r]+)', text, re.IGNORECASE)
        if board_m:
            extracted["hardware_board"] = board_m.group(1).strip()
