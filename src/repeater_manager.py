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

from src.shared_utils import (
    clamp_tx_power,
    clean_battery_input,
    clean_numeric_value,
    normalize_battery,
)


class RepeaterManager:
    """Administrador de comandos remotos a repetidores y analizador de telemetría."""

    def __init__(
        self,
        transmit_callback: Callable[[str, str, int], Any] | None = None,
        min_cmd_interval_s: float = 5.0,
        min_telemetry_interval_s: float = 30.0,
        min_ping_interval_s: float = 15.0,
        min_traceroute_interval_s: float = 60.0,
        min_neighbours_interval_s: float = 30.0,
        is_cutoff_active_callback: Callable[[], bool] | None = None,
    ) -> None:
        self.transmit_callback = transmit_callback
        self.min_cmd_interval_s = min_cmd_interval_s
        self.min_telemetry_interval_s = min_telemetry_interval_s
        self.min_ping_interval_s = min_ping_interval_s
        self.min_traceroute_interval_s = min_traceroute_interval_s
        self.min_neighbours_interval_s = min_neighbours_interval_s
        self.is_cutoff_active_callback = is_cutoff_active_callback
        self._last_cmd_ts: dict[str, float] = {}
        self._last_full_telemetry_ts: dict[str, float] = {}
        self._last_ping_ts: dict[str, float] = {}
        self._last_traceroute_ts: dict[str, float] = {}
        self._last_neighbours_ts: dict[str, float] = {}

    def is_airtime_cutoff_active(self) -> bool:
        """Consulta si el Airtime Cutoff dinámico está activo en el sistema."""
        return self.is_cutoff_active_callback() if self.is_cutoff_active_callback else False

    def check_airtime_cooldown(
        self, repeater_pk: str, is_full_query: bool = False, is_automated: bool = False
    ) -> tuple[bool, float]:
        """
        Verifica si el repetidor ha cumplido su periodo de enfriamiento (cooldown) antes de transmitir.
        Si la consulta es automática y el Airtime Cutoff está activo, bloquea la transmisión.
        Retorna (puede_enviar: bool, segundos_restantes: float).
        """
        if is_automated and self.is_airtime_cutoff_active():
            return False, 999.0

        now = time.monotonic()
        clean_pk = repeater_pk.strip().lower()

        min_interval = self.min_telemetry_interval_s if is_full_query else self.min_cmd_interval_s
        last_ts = self._last_full_telemetry_ts.get(clean_pk, 0.0) if is_full_query else self._last_cmd_ts.get(clean_pk, 0.0)

        elapsed = now - last_ts
        if elapsed < min_interval:
            return False, round(min_interval - elapsed, 1)

        return True, 0.0

    def build_cooldown_error_response(self, remaining_cd: float) -> dict[str, Any]:
        """Construye la respuesta de error 429 estándar para protección de airtime LoRa."""
        if remaining_cd >= 900.0:
            msg = "Airtime Cutoff Dinámico activo: el canal LoRa supera el umbral de congestión. Consultas automáticas suspendidas temporalmente."
        else:
            msg = f"Protección de Airtime LoRa activa. Espere {remaining_cd}s."

        return {
            "status": "error",
            "code": 429,
            "message": msg,
            "cooldown_remaining": remaining_cd,
            "cutoff_active": remaining_cd >= 900.0,
        }

    def record_command_sent(self, repeater_pk: str, is_full_query: bool = False) -> None:
        """Registra el timestamp de transmisión hacia un repetidor para gobernar el airtime."""
        now = time.monotonic()
        clean_pk = repeater_pk.strip().lower()
        self._last_cmd_ts[clean_pk] = now
        if is_full_query:
            self._last_full_telemetry_ts[clean_pk] = now

    def check_ping_cooldown(self, target_pk: str, is_automated: bool = False) -> tuple[bool, float]:
        """Verifica si ha transcurrido el cooldown mínimo antes de enviar otro ping 0 a target_pk."""
        if is_automated and self.is_airtime_cutoff_active():
            return False, 999.0

        now = time.monotonic()
        clean_pk = target_pk.strip().lower()
        last_ts = self._last_ping_ts.get(clean_pk, 0.0)
        elapsed = now - last_ts
        if elapsed < self.min_ping_interval_s:
            return False, round(self.min_ping_interval_s - elapsed, 1)
        return True, 0.0

    def record_ping_sent(self, target_pk: str) -> None:
        """Registra la emisión de un ping 0 hacia target_pk."""
        self._last_ping_ts[target_pk.strip().lower()] = time.monotonic()

    def check_traceroute_cooldown(self, target_pk: str, is_automated: bool = False) -> tuple[bool, float]:
        """Verifica si ha transcurrido el cooldown mínimo antes de iniciar otro traceroute a target_pk."""
        if is_automated and self.is_airtime_cutoff_active():
            return False, 999.0

        now = time.monotonic()
        clean_pk = target_pk.strip().lower()
        last_ts = self._last_traceroute_ts.get(clean_pk, 0.0)
        elapsed = now - last_ts
        if elapsed < self.min_traceroute_interval_s:
            return False, round(self.min_traceroute_interval_s - elapsed, 1)
        return True, 0.0

    def record_traceroute_sent(self, target_pk: str) -> None:
        """Registra la emisión de un traceroute hacia target_pk."""
        self._last_traceroute_ts[target_pk.strip().lower()] = time.monotonic()

    def check_neighbours_cooldown(self, target_pk: str, is_automated: bool = False) -> tuple[bool, float]:
        """Verifica si ha transcurrido el cooldown antes de consultar vecinos de target_pk."""
        if is_automated and self.is_airtime_cutoff_active():
            return False, 999.0

        now = time.monotonic()
        clean_pk = target_pk.strip().lower()
        last_ts = self._last_neighbours_ts.get(clean_pk, 0.0)
        elapsed = now - last_ts
        if elapsed < self.min_neighbours_interval_s:
            return False, round(self.min_neighbours_interval_s - elapsed, 1)
        return True, 0.0

    def record_neighbours_sent(self, target_pk: str) -> None:
        """Registra la consulta de vecinos hacia target_pk."""
        self._last_neighbours_ts[target_pk.strip().lower()] = time.monotonic()


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
        if act in ("set_radio", "radio"):
            freq = params.get("frequency", params.get("freq", 915.0))
            bw = params.get("bandwidth", params.get("bw", 250.0))
            sf = params.get("spreading_factor", params.get("sf", 11))
            cr_raw = params.get("coding_rate", params.get("cr", 5))
            cr_num = 5
            if str(cr_raw).strip() in ("5", "6", "7", "8"):
                cr_num = int(str(cr_raw).strip())
            elif "/" in str(cr_raw):
                parts = str(cr_raw).split("/")
                if len(parts) > 1 and parts[1].strip() in ("5", "6", "7", "8"):
                    cr_num = int(parts[1].strip())
            return f"set radio {freq} {bw} {sf} {cr_num}"

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
        if act in ("set_lat", "set_pos_lat", "lat"):
            lat = params.get("lat", params.get("latitude"))
            if lat is not None:
                return f"set lat {float(lat):.6f}"
            return None

        if act in ("set_lon", "set_pos_lon", "lon"):
            lon = params.get("lon", params.get("longitude"))
            if lon is not None:
                return f"set lon {float(lon):.6f}"
            return None

        if act in ("set_name", "name", "rename", "set_owner_name", "set_owner"):
            name = params.get("name", params.get("owner_name", params.get("new_name", "Repeater")))
            return f"set name {name}"

        if act in ("set_owner_info", "owner_info"):
            info = params.get("owner_info", params.get("info", ""))
            return f"set owner.info \"{info}\""

        if act in ("set_advert_interval", "set_beacon", "advert_intervals", "beacon"):
            interval = params.get("advert_interval", params.get("beacon_interval", params.get("interval", params.get("beacon", 300))))
            try:
                inv = int(interval)
                if inv >= 60:
                    mins = max(2, min(240, int(round(inv / 60))))
                else:
                    mins = max(2, min(240, inv))
            except (ValueError, TypeError):
                mins = 5
            return f"set advert.interval {mins}"

        if act in ("set_fixed", "set_pos_fixed", "fixed", "pos_fixed"):
            return None

        if act in ("set_position", "set_pos", "position", "set_coords", "coords"):
            lat = params.get("lat", params.get("latitude", 0.0))
            lon = params.get("lon", params.get("longitude", 0.0))
            alt = params.get("alt", params.get("altitude", 0.0))
            fixed = params.get("fixed", True)
            fixed_val = "1" if fixed is True or str(fixed).lower() in ("true", "1", "on") else "0"
            return f"set pos {lat} {lon} {alt} {fixed_val}"

        if act == "set_pos_alt":
            alt = params.get("alt", params.get("altitude", 0.0))
            return f"set pos.alt {alt}"

        return None

    def _build_acl_and_security_cmd(self, act: str, params: dict[str, Any]) -> str | None:
        """Construye comandos de autenticación, ACL y sincronización horaria."""
        if act in ("login", "auth"):
            password = params.get("password", params.get("pin", ""))
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

        if act in ("set_admin_password", "admin_password", "admin.password"):
            new_pwd = params.get("new_password", params.get("password", params.get("admin_password", "")))
            return f"set admin.password {new_pwd}"

        if act in ("set_password", "change_password", "password"):
            new_pwd = params.get("new_password", params.get("password", params.get("admin_password", "")))
            return f"password {new_pwd}"

        if act in ("set_guest_password", "guest_password"):
            new_pwd = params.get("guest_password", params.get("password", ""))
            return f"set guest.password {new_pwd}"

        if act in ("set_identity_key", "set_prv_key", "prv_key", "prv.key"):
            key = params.get("identity_key", params.get("prv_key", params.get("key", "")))
            return f"set prv.key {key}"

        if act in ("set_clock", "set_time", "sync_time", "clock_sync"):
            ts = params.get("timestamp", params.get("time", int(time.time())))
            return f"time {ts}"

        return None

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

    @staticmethod
    def _extract_json_power(data_json: dict[str, Any], extracted: dict[str, Any]) -> None:
        raw_bat = data_json.get(
            "battery_pct",
            data_json.get("battery", data_json.get("batt", data_json.get("battery_mv", data_json.get("batt_mv", data_json.get("level"))))),
        )
        if raw_bat is not None:
            clean_b = clean_battery_input(raw_bat)
            if clean_b is not None:
                pct_norm, volt_norm = normalize_battery(clean_b)
                if pct_norm > 0 or clean_b in (0, 0.0):
                    extracted["battery_pct"] = int(round(pct_norm))
                if volt_norm > 0 and "voltage_v" not in extracted:
                    extracted["voltage_v"] = volt_norm

        raw_v = data_json.get("voltage_v", data_json.get("voltage", data_json.get("vbat", data_json.get("volt"))))
        if raw_v is not None:
            clean_v = clean_battery_input(raw_v)
            if clean_v is not None:
                pct_norm, volt_norm = normalize_battery(clean_v)
                extracted["voltage_v"] = volt_norm
                if "battery_pct" not in extracted:
                    extracted["battery_pct"] = int(round(pct_norm))

        raw_sol = data_json.get("solar_v", data_json.get("solar_mv", data_json.get("solar")))
        if raw_sol is not None:
            clean_s = clean_battery_input(raw_sol)
            if clean_s is not None:
                extracted["solar_v"] = round(clean_s / 1000.0, 2) if clean_s > 100.0 else round(clean_s, 2)

    @staticmethod
    def _extract_json_system(data_json: dict[str, Any], extracted: dict[str, Any]) -> None:
        if "uptime_secs" in data_json or "uptime" in data_json:
            raw_up = data_json.get("uptime_secs", data_json.get("uptime"))
            clean_up = clean_numeric_value(raw_up)
            if clean_up is not None and (
                isinstance(raw_up, (int, float)) or str(raw_up).strip().isdigit() or str(raw_up).strip().endswith("s")
            ):
                secs = int(clean_up)
                days, rem = divmod(secs, 86400)
                hours, rem = divmod(rem, 3600)
                mins, s = divmod(rem, 60)
                extracted["uptime"] = f"{days}d {hours}h {mins}m" if days > 0 else f"{hours}h {mins}m {s}s"
            else:
                extracted["uptime"] = str(raw_up)

        if "errors" in data_json:
            clean_err = clean_numeric_value(data_json["errors"])
            if clean_err is not None:
                extracted["packet_errors"] = int(clean_err)
        if "recv_errors" in data_json:
            clean_rerr = clean_numeric_value(data_json["recv_errors"])
            if clean_rerr is not None:
                extracted["packet_errors"] = int(clean_rerr)
        if "queue_len" in data_json or "queue" in data_json:
            clean_q = clean_numeric_value(data_json.get("queue_len", data_json.get("queue")))
            if clean_q is not None:
                extracted["queue_len"] = int(clean_q)
        if "noise_floor" in data_json or "noise_floor_dbm" in data_json:
            clean_nf = clean_numeric_value(data_json.get("noise_floor", data_json.get("noise_floor_dbm")))
            if clean_nf is not None:
                extracted["noise_floor_dbm"] = int(round(clean_nf))
        if "last_rssi" in data_json or "rssi" in data_json:
            clean_rssi = clean_numeric_value(data_json.get("last_rssi", data_json.get("rssi")))
            if clean_rssi is not None:
                extracted["last_rssi"] = int(round(clean_rssi))
        if "last_snr" in data_json or "snr" in data_json:
            clean_snr = clean_numeric_value(data_json.get("last_snr", data_json.get("snr")))
            if clean_snr is not None:
                extracted["last_snr"] = round(clean_snr, 1)
        if "tx_air_secs" in data_json or "airtime_ms" in data_json:
            raw_at = data_json.get("airtime_ms", data_json.get("tx_air_secs"))
            clean_at = clean_numeric_value(raw_at)
            if clean_at is not None:
                raw_s = str(raw_at).strip().lower()
                if "tx_air_secs" in data_json or (raw_s.endswith("s") and not raw_s.endswith("ms")):
                    extracted["airtime_ms"] = int(clean_at * 1000)
                else:
                    extracted["airtime_ms"] = int(clean_at)
        if "sent" in data_json or "packets_sent" in data_json:
            clean_s = clean_numeric_value(data_json.get("sent", data_json.get("packets_sent")))
            if clean_s is not None:
                extracted["packets_sent"] = int(clean_s)
        if "recv" in data_json or "packets_recv" in data_json:
            clean_r = clean_numeric_value(data_json.get("recv", data_json.get("packets_recv")))
            if clean_r is not None:
                extracted["packets_recv"] = int(clean_r)

        temp_val = data_json.get("temperature_c", data_json.get("temperature", data_json.get("temp", data_json.get("temp_c"))))
        if temp_val is not None:
            clean_t = clean_numeric_value(temp_val)
            if clean_t is not None:
                extracted["temperature_c"] = round(clean_t, 1)

        hum_val = data_json.get("humidity_pct", data_json.get("humidity", data_json.get("hum")))
        if hum_val is not None:
            clean_h = clean_numeric_value(hum_val)
            if clean_h is not None:
                extracted["humidity_pct"] = round(clean_h, 1)

        press_val = data_json.get("pressure_hpa", data_json.get("pressure", data_json.get("press", data_json.get("barometer"))))
        if press_val is not None:
            clean_p = clean_numeric_value(press_val)
            if clean_p is not None:
                extracted["pressure_hpa"] = round(clean_p, 1)

    @staticmethod
    def _extract_json_radio_and_coords(data_json: dict[str, Any], extracted: dict[str, Any]) -> None:
        if "repeat" in data_json or "repeat_enabled" in data_json or "repeating" in data_json:
            raw_rep = data_json.get("repeat", data_json.get("repeat_enabled", data_json.get("repeating")))
            extracted["repeat_enabled"] = bool(raw_rep) if not isinstance(raw_rep, str) else raw_rep.lower() in ("1", "true", "on", "enabled", "activado")

        if "hop_limit" in data_json or "hops" in data_json or "max_hops" in data_json:
            clean_hl = clean_numeric_value(data_json.get("hop_limit", data_json.get("max_hops", data_json.get("hops"))))
            if clean_hl is not None:
                extracted["hop_limit"] = int(clean_hl)

        if "tx_power" in data_json or "power" in data_json:
            clean_pwr = clean_numeric_value(data_json.get("tx_power", data_json.get("power")))
            if clean_pwr is not None:
                extracted["tx_power"] = int(clean_pwr)

        if "freq" in data_json or "frequency" in data_json:
            clean_fr = clean_numeric_value(data_json.get("freq", data_json.get("frequency")))
            if clean_fr is not None:
                extracted["frequency"] = round(clean_fr, 3)

        if "sf" in data_json or "spreading_factor" in data_json:
            clean_sf = clean_numeric_value(data_json.get("sf", data_json.get("spreading_factor")))
            if clean_sf is not None:
                extracted["spreading_factor"] = int(clean_sf)

        if "bw" in data_json or "bandwidth" in data_json:
            clean_bw = clean_numeric_value(data_json.get("bw", data_json.get("bandwidth")))
            if clean_bw is not None:
                extracted["bandwidth"] = clean_bw

        if "cr" in data_json or "coding_rate" in data_json:
            raw_cr = data_json.get("cr", data_json.get("coding_rate"))
            if raw_cr is not None:
                extracted["coding_rate"] = str(raw_cr).strip()

        if "owner" in data_json or "owner_name" in data_json:
            raw_ow = data_json.get("owner_name", data_json.get("owner"))
            if raw_ow is not None:
                extracted["owner_name"] = str(raw_ow)

        if "lat" in data_json or "latitude" in data_json:
            clean_la = clean_numeric_value(data_json.get("lat", data_json.get("latitude")))
            if clean_la is not None:
                extracted["latitude"] = round(clean_la, 5)

        if "lon" in data_json or "longitude" in data_json:
            clean_lo = clean_numeric_value(data_json.get("lon", data_json.get("longitude")))
            if clean_lo is not None:
                extracted["longitude"] = round(clean_lo, 5)

        if "alt" in data_json or "altitude" in data_json:
            clean_al = clean_numeric_value(data_json.get("alt", data_json.get("altitude")))
            if clean_al is not None:
                extracted["altitude_m"] = round(clean_al, 1)

    def _parse_json_telemetry(self, text: str, extracted: dict[str, Any]) -> bool:
        """Parsea telemetría si viene serializada en JSON oficial MeshCore."""
        if not (text.startswith("{") and text.endswith("}")):
            return False

        try:
            data_json = json.loads(text)
            if not isinstance(data_json, dict):
                return False

            self._extract_json_power(data_json, extracted)
            self._extract_json_system(data_json, extracted)
            self._extract_json_radio_and_coords(data_json, extracted)
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
                if "%" in bat_m.group(0) or ("v" not in bat_m.group(0).lower() and 5.0 < val_num <= 100.0 and "." not in raw_val_str):
                    extracted["battery_pct"] = int(val_num)
                elif val_num > 100.0:  # mV
                    extracted["voltage_v"] = round(val_num / 1000.0, 2)
                    if pct_in_paren:
                        extracted["battery_pct"] = int(pct_in_paren)
                    else:
                        pct, _ = normalize_battery(extracted["voltage_v"])
                        extracted["battery_pct"] = int(round(pct))
                elif 0.0 < val_num <= 5.5:  # Volts (ej. 3.7V, 4.2V, 4.7V)
                    extracted["voltage_v"] = round(val_num, 2)
                    if pct_in_paren:
                        extracted["battery_pct"] = int(pct_in_paren)
                    else:
                        pct, _ = normalize_battery(extracted["voltage_v"])
                        extracted["battery_pct"] = int(round(pct))
            except Exception:
                pass

        if "voltage_v" not in extracted:
            volt_m = re.search(r'(?:voltage|volt|vbat|v_bat)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mv|v)?', text, re.IGNORECASE)
            if volt_m:
                try:
                    v_num = float(volt_m.group(1))
                    extracted["voltage_v"] = round(v_num / 1000.0, 2) if v_num > 100.0 else round(v_num, 2)
                    if "battery_pct" not in extracted:
                        pct, _ = normalize_battery(extracted["voltage_v"])
                        extracted["battery_pct"] = int(round(pct))
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
        clock_m = re.search(r'(?:clock|rtc|time)(?:\s*set)?\s*[:=]?\s*([0-9\-:\s\/]+(?:[ap]m|utc)?)', text, re.IGNORECASE)
        if not clock_m or not clock_m.group(1).strip():
            clock_m = re.search(r'(?:^|>)\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*-\s*\d{1,2}\/\d{1,2}\/\d{2,4})?(?:\s*(?:UTC|[ap]m))?)', text, re.IGNORECASE)
        if not clock_m or not clock_m.group(1).strip():
            clock_m = re.search(r'(?:^|>)\s*([0-9\-:\s\/]+UTC)', text, re.IGNORECASE)
        if clock_m and clock_m.group(1).strip():
            extracted["clock"] = clock_m.group(1).strip()

        duty_m = re.search(r'(?:duty(?:cycle)?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%', text, re.IGNORECASE)
        if not duty_m:
            duty_m = re.search(r'(?:^|>)\s*(\d+(?:\.\d+)?)\s*%', text)
        if duty_m:
            clean_dc = clean_numeric_value(duty_m.group(1))
            if clean_dc is not None:
                extracted["duty_cycle_pct"] = float(clean_dc)

        uptime_m = re.search(r'\b(?:uptime\s*[:=]?\s*|up\s*[:=]\s*)(\d+[0-9a-zA-Z\s:]*?)(?:,|$|\n)', text, re.IGNORECASE)
        if uptime_m:
            extracted["uptime"] = uptime_m.group(1).strip()

        airtime_m = re.search(r'(?:total\s+)?airtime\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(ms|s)?', text, re.IGNORECASE)
        if airtime_m:
            clean_at = clean_numeric_value(airtime_m.group(1))
            if clean_at is not None:
                unit = (airtime_m.group(2) or "ms").lower()
                extracted["airtime_ms"] = int(clean_at * 1000) if unit == "s" else int(clean_at)

        noise_m = re.search(r'(?:noise(?:\s*floor)?|noisefloor|floor)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(?:dbm)?', text, re.IGNORECASE)
        if noise_m:
            clean_n = clean_numeric_value(noise_m.group(1))
            if clean_n is not None:
                extracted["noise_floor_dbm"] = int(round(clean_n))

        rssi_m = re.search(r'(?:last\s+)?rssi\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(?:dbm)?', text, re.IGNORECASE)
        if rssi_m:
            clean_rssi = clean_numeric_value(rssi_m.group(1))
            if clean_rssi is not None:
                extracted["last_rssi"] = int(round(clean_rssi))

        snr_m = re.search(r'(?:last\s+)?snr\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(?:db)?', text, re.IGNORECASE)
        if snr_m:
            clean_snr = clean_numeric_value(snr_m.group(1))
            if clean_snr is not None:
                extracted["last_snr"] = round(clean_snr, 1)

        temp_m = re.search(r'(?:temp(?:erature)?(?:_c)?)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(?:°?c)?', text, re.IGNORECASE)
        if temp_m:
            clean_t = clean_numeric_value(temp_m.group(1))
            if clean_t is not None:
                extracted["temperature_c"] = round(clean_t, 1)

        hum_m = re.search(r'(?:hum(?:idity)?(?:_pct)?)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(?:%)?', text, re.IGNORECASE)
        if hum_m:
            clean_h = clean_numeric_value(hum_m.group(1))
            if clean_h is not None:
                extracted["humidity_pct"] = round(clean_h, 1)

        press_m = re.search(r'(?:press(?:ure)?(?:_hpa)?|baro(?:meter)?)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(?:hpa)?', text, re.IGNORECASE)
        if press_m:
            clean_p = clean_numeric_value(press_m.group(1))
            if clean_p is not None:
                extracted["pressure_hpa"] = round(clean_p, 1)

        pkt_block = re.search(r'packets:\s*rx=(\d+),\s*tx=(\d+)(?:,\s*routed=(\d+))?(?:,\s*(?:drop|err|errors?)=(\d+))?', text, re.IGNORECASE)
        if pkt_block:
            clean_rx = clean_numeric_value(pkt_block.group(1))
            clean_tx = clean_numeric_value(pkt_block.group(2))
            if clean_rx is not None:
                extracted["packets_recv"] = int(clean_rx)
            if clean_tx is not None:
                extracted["packets_sent"] = int(clean_tx)
            if pkt_block.group(4):
                clean_err = clean_numeric_value(pkt_block.group(4))
                if clean_err is not None:
                    extracted["packet_errors"] = int(clean_err)

        if "packets_sent" not in extracted:
            sent_m = re.search(r'(?:packets?\s+sent|tx\s+packets?|sent\s+packets?|nb_sent)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
            if sent_m:
                clean_s = clean_numeric_value(sent_m.group(1))
                if clean_s is not None:
                    extracted["packets_sent"] = int(clean_s)

        if "packets_recv" not in extracted:
            recv_m = re.search(r'(?:packets?\s+rec(?:ei)?ved|rx\s+packets?|rec(?:ei)?ved\s+packets?|nb_recv)\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
            if recv_m:
                clean_r = clean_numeric_value(recv_m.group(1))
                if clean_r is not None:
                    extracted["packets_recv"] = int(clean_r)

    def _parse_owner_and_location(self, text: str, extracted: dict[str, Any]) -> None:
        """Extrae coordenadas GPS, propietario e información de versión del firmware."""
        lat_m = re.search(r'lat(?:itude)?\s*[:=]?\s*(-?\d+(?:\.\d+)?)', text, re.IGNORECASE)
        if lat_m:
            clean_lat = clean_numeric_value(lat_m.group(1))
            if clean_lat is not None:
                extracted["latitude"] = round(clean_lat, 5)

        lon_m = re.search(r'lon(?:gitude)?\s*[:=]?\s*(-?\d+(?:\.\d+)?)', text, re.IGNORECASE)
        if lon_m:
            clean_lon = clean_numeric_value(lon_m.group(1))
            if clean_lon is not None:
                extracted["longitude"] = round(clean_lon, 5)

        alt_m = re.search(r'alt(?:itude)?\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*m?', text, re.IGNORECASE)
        if alt_m:
            clean_alt = clean_numeric_value(alt_m.group(1))
            if clean_alt is not None:
                extracted["altitude_m"] = round(clean_alt, 1)

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
