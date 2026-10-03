"""
LocalConfigExecutor: Gestión y parametrización del nodo local y módem LoRa conectado.
Descompone la lectura y escritura de configuración local:
- get_local_config: Consolidación de parámetros de hardware, telemetría y uptime.
- fetch_device_config: Consulta síncrona/asíncrona a la radio serial.
- set_local_config: Modificación atómica de potencia TX, frecuencia, posición GPS y alias.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import math
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import config
from src.admin.sdk_commands import require_success, run_sdk_command
from src.contact_manager import NodeContactUpdate, is_valid_node_key
from src.protocol_types import (
    LORA_MAX_FREQ_MHZ,
    LORA_MIN_FREQ_MHZ,
    redact_sensitive_dict,
)
from src.shared_utils import (
    clamp_tx_power,
    extract_payload_dict,
    get_hardware_power_limits,
    normalize_battery,
    to_bool,
)

if TYPE_CHECKING:
    from src.admin_handler import AdminContext


def normalize_coding_rate(cr_val: Any) -> int | None:
    """Normaliza y valida un coding rate LoRa (5..8 o 4/5..4/8), devolviendo 5..8 o None si es inválido."""
    if cr_val is None:
        return None
    s = str(cr_val).strip()
    if s in ("5", "6", "7", "8"):
        return int(s)
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 2 and parts[0].strip() == "4" and parts[1].strip() in ("5", "6", "7", "8"):
            return int(parts[1].strip())
    return None


class LocalConfigExecutor:
    """Ejecutor de lectura y actualización de configuración del nodo local."""

    def __init__(
        self,
        ctx: AdminContext,
        local_config: dict[str, Any],
        init_time: float,
        publish_safe: Callable[[str, str, int], None],
    ) -> None:
        self._ctx = ctx
        self._local_config = local_config
        self._init_time = init_time
        self._publish_safe = publish_safe
        self._last_fetch_time: float = 0.0
        self._fetch_lock = asyncio.Lock()

    async def _write_device(self, mc: Any, command: str, *args: Any, timeout: float = 3.0, **kwargs: Any) -> Any:
        response = await asyncio.wait_for(run_sdk_command(self._ctx, mc, command, *args, **kwargs), timeout=timeout)
        return require_success(response, command)

    async def _query_device(self, mc: Any, command: str, *args: Any, timeout: float = 3.0, **kwargs: Any) -> Any:
        try:
            return await self._write_device(mc, command, *args, timeout=timeout, **kwargs)
        except Exception:
            logging.debug("Consulta SDK sin respuesta válida: %s", command)
            return None

    def _get_device_baseline(self, field: str, aliases: tuple[str, ...]) -> Any:
        """Obtiene el baseline del dispositivo físico conectado (self_info) antes de recurrir al host."""
        mc = self._ctx.mc_provider()
        for attr in ("self_info", "_self_info"):
            si = getattr(mc, attr, None)
            if isinstance(si, dict):
                for a in (field, *aliases):
                    if a in si and si[a] is not None:
                        return si[a]
        for a in (field, *aliases):
            if a in self._local_config and self._local_config[a] is not None:
                return self._local_config[a]
        return None

    def get_local_config(self) -> dict[str, Any]:
        """Devuelve la configuración consolidada del nodo local y su telemetría."""
        mc = self._ctx.mc_provider()
        cfg = dict(self._local_config)
        cfg["serial_port"] = getattr(config, "SERIAL_PORT", "/dev/ttyACM0")

        si = self._read_self_info(mc)
        if isinstance(si, dict) and si:
            self._apply_self_info_to_cfg(cfg, si)
        else:
            cfg["radio_freq"] = cfg.get("frequency", 915.0)

        # Flag has_pin para informar si el dispositivo tiene un PIN BLE configurado sin exponer el secreto
        raw_pin = cfg.get("pin", 0)
        cfg["has_pin"] = bool(raw_pin and raw_pin != 0 and raw_pin != "0")

        self._ensure_default_telemetry(cfg)
        self._populate_uptime_and_airtime(cfg)
        self._populate_last_rf_metrics(cfg)
        self._populate_radio_limits(cfg, si)
        return cfg

    def _read_self_info(self, mc: Any) -> dict[str, Any] | None:
        """Lee el objeto self_info del SDK oficial si está disponible."""
        if not mc:
            return None
        raw_si = getattr(mc, "self_info", None)
        if callable(raw_si):
            try:
                res_si = raw_si()
                if isinstance(res_si, dict):
                    return cast(dict[str, Any], res_si)
                return None
            except Exception:
                si_fallback = getattr(mc, "_self_info", None)
                return cast(dict[str, Any], si_fallback) if isinstance(si_fallback, dict) else None
        if isinstance(raw_si, dict):
            return raw_si
        if hasattr(mc, "_self_info") and isinstance(mc._self_info, dict):
            return mc._self_info
        return None

    def _apply_self_info_to_cfg(self, cfg: dict[str, Any], si: dict[str, Any]) -> None:
        """Fusiona los campos de self_info en el diccionario de configuración."""
        pk = si.get("public_key") or si.get("pubkey")
        if pk:
            cfg["public_key"] = str(pk).lower().strip()
        cfg.update({
            "name": si.get("name", cfg.get("name")),
            "owner_info": si.get("owner_info", si.get("owner", cfg.get("owner_info"))),
            "latitude": si.get("adv_lat", si.get("latitude", si.get("lat", cfg.get("latitude")))),
            "longitude": si.get("adv_lon", si.get("longitude", si.get("lon", cfg.get("longitude")))),
            "altitude": si.get("altitude", si.get("alt", cfg.get("altitude"))),
            "tx_power": si.get("tx_power", cfg.get("tx_power")),
            "frequency": si.get("radio_freq", si.get("freq", cfg.get("frequency"))),
            "radio_freq": si.get("radio_freq", si.get("freq", cfg.get("frequency"))),
            "spreading_factor": si.get("sf", si.get("radio_sf", si.get("spreading_factor", cfg.get("spreading_factor")))),
            "bandwidth": si.get("bw", si.get("radio_bw", si.get("bandwidth", cfg.get("bandwidth")))),
            "coding_rate": si.get("cr", si.get("radio_cr", si.get("coding_rate", cfg.get("coding_rate")))),
            "hop_limit": si.get("hop_limit", cfg.get("hop_limit")),
            "repeat": si.get("repeat", cfg.get("repeat", False)),
            "telemetry_interval": si.get("telemetry_interval", cfg.get("telemetry_interval")),
            "beacon_interval": si.get("beacon_interval", si.get("advert_interval", cfg.get("beacon_interval"))),
            "advert_interval": si.get("advert_interval", si.get("beacon_interval", cfg.get("advert_interval"))),
            "battery_pct": si.get("battery_pct", si.get("battery", cfg.get("battery_pct"))),
            "voltage": si.get("voltage", cfg.get("voltage")),
            "battery_mv": si.get("battery_mv", cfg.get("battery_mv")),
            "telemetry_mode_base": si.get("telemetry_mode_base", cfg.get("telemetry_mode_base")),
            "telemetry_mode_loc": si.get("telemetry_mode_loc", cfg.get("telemetry_mode_loc")),
            "telemetry_mode_env": si.get("telemetry_mode_env", cfg.get("telemetry_mode_env")),
            "adv_loc_policy": si.get("adv_loc_policy", cfg.get("adv_loc_policy")),
            "multi_acks": si.get("multi_acks", cfg.get("multi_acks")),
            "manual_add_contacts": si.get("manual_add_contacts", cfg.get("manual_add_contacts")),
            "pin": si.get("pin", cfg.get("pin", 0)),
            "rx_delay": si.get("rx_delay", cfg.get("rx_delay", 0)),
            "airtime_factor": si.get("airtime_factor", cfg.get("airtime_factor", 0)),
            "path_hash_mode": si.get("path_hash_mode", cfg.get("path_hash_mode", 0)),
            "custom_vars": si.get("custom_vars", cfg.get("custom_vars", {})),
        })

    def _ensure_default_telemetry(self, cfg: dict[str, Any]) -> None:
        """Asegura campos por defecto para alimentación USB cuando no hay batería."""
        cfg.setdefault("battery_pct", None)
        cfg.setdefault("voltage", None)
        cfg.setdefault("battery_mv", None)
        cfg.setdefault("power_source", "desconocida")
        cfg.setdefault("pin", self._local_config.get("pin", 0))
        cfg.setdefault("rx_delay", self._local_config.get("rx_delay", 0))
        cfg.setdefault("airtime_factor", self._local_config.get("airtime_factor", 0))
        cfg.setdefault("path_hash_mode", self._local_config.get("path_hash_mode", 0))
        cfg.setdefault("telemetry_mode_base", self._local_config.get("telemetry_mode_base", 1))
        cfg.setdefault("telemetry_mode_loc", self._local_config.get("telemetry_mode_loc", 1))
        cfg.setdefault("telemetry_mode_env", self._local_config.get("telemetry_mode_env", 1))
        cfg.setdefault("adv_loc_policy", self._local_config.get("adv_loc_policy", 0))
        cfg.setdefault("multi_acks", self._local_config.get("multi_acks", 0))
        cfg.setdefault("manual_add_contacts", self._local_config.get("manual_add_contacts", 0))
        cfg.setdefault("custom_vars", self._local_config.get("custom_vars", {}))
        cfg.setdefault("temperature_c", self._local_config.get("temperature_c"))
        cfg.setdefault("humidity_pct", self._local_config.get("humidity_pct"))
        cfg.setdefault("pressure_hpa", self._local_config.get("pressure_hpa"))
        cfg.setdefault("satellites", self._local_config.get("satellites", 0))

    def _populate_uptime_and_airtime(self, cfg: dict[str, Any]) -> None:
        """Calcula métricas de uptime y ciclo de trabajo de radio."""
        uptime_sec = self._local_config.get("uptime", 0)
        if uptime_sec <= 0:
            bridge_start = getattr(self._ctx, "start_time", 0.0)
            if not bridge_start and hasattr(self._ctx, "counters"):
                bridge_start = getattr(self._ctx.counters, "start_time", 0.0)
            if not bridge_start:
                bridge_start = self._init_time
            if isinstance(bridge_start, (int, float)) and bridge_start > 0:
                uptime_sec = max(1, int(time.time() - bridge_start))

        days = uptime_sec // 86400
        hours = (uptime_sec % 86400) // 3600
        mins = (uptime_sec % 3600) // 60
        uptime_str = f"{days}d {hours}h {mins}m" if days > 0 else (f"{hours}h {mins}m" if hours > 0 else f"{mins}m")

        airtime_ms = self._local_config.get("airtime_ms", 0)
        duty_pct = self._local_config.get("duty_cycle_pct", 0.0)
        if self._ctx.rate_limiter and hasattr(self._ctx.rate_limiter, "airtime_tracker"):
            try:
                air_stats = self._ctx.rate_limiter.airtime_tracker.get_stats()
                if airtime_ms == 0:
                    airtime_ms = int(air_stats.get("total_airtime_ms", 0))
                if duty_pct == 0.0:
                    duty_pct = air_stats.get("hourly_duty_cycle_pct") or air_stats.get("daily_duty_cycle_pct") or 0.0
            except Exception:
                pass

        if duty_pct == 0.0 and airtime_ms > 0 and uptime_sec > 0:
            duty_pct = round((airtime_ms / (uptime_sec * 1000.0)) * 100.0, 3)

        tx_val = getattr(self._ctx.counters, "tx_count", self._local_config.get("tx_count", 0)) if hasattr(self._ctx, "counters") and self._ctx.counters else self._local_config.get("tx_count", 0)
        rx_val = getattr(self._ctx.counters, "rx_count", self._local_config.get("rx_count", 0)) if hasattr(self._ctx, "counters") and self._ctx.counters else self._local_config.get("rx_count", 0)

        cfg["uptime"] = uptime_sec
        cfg["uptime_secs"] = uptime_sec
        cfg["uptime_str"] = uptime_str
        cfg["airtime_ms"] = airtime_ms
        cfg["duty_cycle_pct"] = duty_pct
        cfg["tx_count"] = tx_val
        cfg["rx_count"] = rx_val

    def _populate_last_rf_metrics(self, cfg: dict[str, Any]) -> None:
        """Pobla las últimas métricas de SNR y RSSI."""
        last_snr = getattr(self._ctx, "last_rx_snr", None)
        last_rssi = getattr(self._ctx, "last_rx_rssi", None)
        if (last_snr is None or last_rssi is None) and self._ctx.node_registry:
            nodes = [
                n for n in self._ctx.node_registry.list_nodes()
                if not n.get("is_local") and str(n.get("role")).upper() != "LOCAL" and (n.get("last_snr") is not None or n.get("last_rssi") is not None)
            ]
            if nodes:
                nodes.sort(key=lambda x: float(x.get("last_seen") or 0.0), reverse=True)
                if last_snr is None:
                    last_snr = nodes[0].get("last_snr")
                if last_rssi is None:
                    last_rssi = nodes[0].get("last_rssi")
        cfg["last_snr"] = last_snr
        cfg["last_rssi"] = last_rssi

    def _populate_radio_limits(self, cfg: dict[str, Any], si: dict[str, Any] | None) -> None:
        """Calcula límites dinámicos de potencia TX según placa."""
        hw_board = cfg.get("hardware_board") or (si.get("hardware_board") if isinstance(si, dict) else None)
        max_hint = cfg.get("max_tx_power") or (si.get("max_tx_power") if isinstance(si, dict) else None)
        min_p, max_p, def_p = get_hardware_power_limits(hw_board, max_hint)
        cfg["min_tx_power"] = min_p
        cfg["max_tx_power"] = max_p
        cfg["default_tx_power"] = def_p

    async def fetch_device_config(self, force: bool = False) -> dict[str, Any]:
        """Consulta directamente al hardware serial los parámetros de configuración respetando cooldown de seguridad."""
        now = time.time()
        if not force and (now - self._last_fetch_time) < 30.0:
            cfg = self.get_local_config()
            cfg.setdefault("cached", True)
            cfg.setdefault("observed_at", self._last_fetch_time or self._init_time)
            return cfg

        async with self._fetch_lock:
            now = time.time()
            if not force and (now - self._last_fetch_time) < 30.0:
                cfg = self.get_local_config()
                cfg.setdefault("cached", True)
                cfg.setdefault("observed_at", self._last_fetch_time or self._init_time)
                return cfg

            mc = self._ctx.mc_provider()
            if not mc or not hasattr(mc, "commands"):
                cfg = self.get_local_config()
                cfg["cached"] = True
                cfg["stale"] = True
                cfg["refresh_error"] = "Dispositivo no conectado"
                cfg["observed_at"] = self._last_fetch_time or self._init_time
                return cfg

            self._last_fetch_time = now
            await self._query_hardware_device_and_battery(mc)
            await self._query_hardware_stats_and_packets(mc)
            cfg = self.get_local_config()
            cfg["cached"] = False
            cfg["stale"] = False
            cfg["observed_at"] = self._last_fetch_time
            return cfg

    async def _query_hardware_device_and_battery(self, mc: Any) -> None:
        """Consulta identidad, modo repetidor, parámetros avanzados y nivel de batería por serial."""
        res_app = await self._query_device(mc, "send_appstart")
        app_data = extract_payload_dict(res_app)
        if app_data and isinstance(app_data, dict):
            self._apply_self_info_to_cfg(self._local_config, app_data)
            pk = app_data.get("public_key") or app_data.get("pubkey")
            if pk and self._ctx.node_registry:
                pk_clean = str(pk).lower().strip()
                self._ctx.node_registry.set_local_pubkey(pk_clean)
                self._ctx.node_registry.add_or_update(
                    pk_clean,
                    NodeContactUpdate(
                        name=app_data.get("name", self._local_config.get("name")),
                        alias=app_data.get("name", self._local_config.get("name")),
                        role="LOCAL",
                        is_local=True,
                        hops=0,
                        fixed_position=True,
                    ),
                )

        dev_res = await self._query_device(mc, "send_device_query")
        dev_data = extract_payload_dict(dev_res)
        if dev_data and isinstance(dev_data, dict):
            if "model" in dev_data:
                self._local_config["model"] = dev_data["model"]
            if "ver" in dev_data or "fw_ver" in dev_data:
                fw_v = dev_data.get("ver", dev_data.get("fw_ver"))
                self._local_config["ver"] = fw_v
                self._local_config["fw_ver"] = fw_v
            if "fw_build" in dev_data or "build" in dev_data:
                self._local_config["fw_build"] = dev_data.get("fw_build", dev_data.get("build"))
            if "hardware_board" in dev_data or "board" in dev_data:
                self._local_config["hardware_board"] = dev_data.get("hardware_board", dev_data.get("board"))
            if "repeat" in dev_data:
                self._local_config["repeat"] = bool(dev_data["repeat"])
            if "path_hash_mode" in dev_data:
                self._local_config["path_hash_mode"] = dev_data["path_hash_mode"]

        bat_res = await self._query_device(mc, "get_bat")
        bat_data = extract_payload_dict(bat_res)
        if bat_data and isinstance(bat_data, dict):
            mv = bat_data.get("level", bat_data.get("battery_mv", bat_data.get("mv")))
            if mv is not None:
                pct, voltage = normalize_battery(mv)
                self._local_config.update({
                    "battery_pct": bat_data.get("battery_pct", bat_data.get("pct", pct)),
                    "battery_mv": mv,
                    "voltage": voltage,
                })

        tun_res = await self._query_device(mc, "get_tuning")
        tun_data = extract_payload_dict(tun_res)
        if tun_data and isinstance(tun_data, dict):
            if "rx_delay" in tun_data:
                rx_val = float(tun_data["rx_delay"])
                self._local_config["rx_delay"] = round(rx_val / 1000.0, 3)
            if "airtime_factor" in tun_data:
                af_val = float(tun_data["airtime_factor"])
                self._local_config["airtime_factor"] = round(af_val / 1000.0, 3)

        t_res = await self._query_device(mc, "get_time")
        t_data = extract_payload_dict(t_res)
        if t_data and isinstance(t_data, dict) and "time" in t_data:
            now_ts = time.time()
            dev_time = int(t_data["time"])
            self._local_config["device_epoch_time"] = dev_time
            self._local_config["device_time_sampled_at"] = now_ts
            self._local_config["device_time_drift"] = int(dev_time - now_ts)

    async def _query_hardware_stats_and_packets(self, mc: Any) -> None:
        """Consulta estadísticas de núcleo, radio, sensores y paquetes por serial."""
        c_res = await self._query_device(mc, "get_stats_core")
        c_data = extract_payload_dict(c_res)
        if c_data and isinstance(c_data, dict):
            self._local_config['stats_core'] = c_data
            u_val = c_data.get("uptime_secs") or c_data.get("uptime")
            if u_val is not None and int(u_val) > 0:
                self._local_config["uptime"] = int(u_val)
                self._local_config["uptime_secs"] = int(u_val)
                self._local_config["device_uptime"] = int(u_val)
                self._local_config["device_uptime_secs"] = int(u_val)
                self._local_config["device_uptime_sampled_at"] = time.time()
            if "battery_mv" in c_data:
                self._local_config["battery_mv"] = c_data["battery_mv"]
            if "errors" in c_data:
                self._local_config["packet_errors"] = c_data["errors"]

        r_res = await self._query_device(mc, "get_stats_radio")
        r_data = extract_payload_dict(r_res)
        if r_data and isinstance(r_data, dict):
            self._local_config['stats_radio'] = r_data
            if "noise_floor" in r_data:
                self._local_config["noise_floor_dbm"] = r_data["noise_floor"]
            if "last_snr" in r_data:
                self._local_config["last_snr"] = r_data["last_snr"]
            if "last_rssi" in r_data:
                self._local_config["last_rssi"] = r_data["last_rssi"]
            if "tx_air_secs" in r_data:
                self._local_config["airtime_ms"] = int(float(r_data["tx_air_secs"]) * 1000)

        p_res = await self._query_device(mc, "get_stats_packets")
        p_data = extract_payload_dict(p_res)
        if p_data and isinstance(p_data, dict):
            self._local_config['stats_packets'] = p_data
            if "sent" in p_data:
                self._local_config["tx_count"] = p_data["sent"]
            if "recv" in p_data:
                self._local_config["rx_count"] = p_data["recv"]
            if "recv_errors" in p_data:
                self._local_config["packet_errors"] = p_data["recv_errors"]

        st_res = await self._query_device(mc, "get_self_telemetry")
        st_data = extract_payload_dict(st_res)
        if st_data and isinstance(st_data, dict):
            self._local_config["self_telemetry"] = st_data
            if "temperature" in st_data or "temperature_c" in st_data:
                self._local_config["temperature_c"] = st_data.get("temperature", st_data.get("temperature_c"))
            if "humidity" in st_data or "humidity_pct" in st_data:
                self._local_config["humidity_pct"] = st_data.get("humidity", st_data.get("humidity_pct"))
            if "pressure" in st_data or "pressure_hpa" in st_data:
                self._local_config["pressure_hpa"] = st_data.get("pressure", st_data.get("pressure_hpa"))

        cv_res = await self._query_device(mc, "get_custom_vars")
        cv_data = extract_payload_dict(cv_res)
        if cv_data and isinstance(cv_data, dict):
            self._local_config["custom_vars"] = cv_data

        arf_res = await self._query_device(mc, "get_allowed_repeat_freq")
        arf_data = extract_payload_dict(arf_res)
        if arf_data and isinstance(arf_data, dict):
            self._local_config["allowed_repeat_freq"] = arf_data.get("allowed_freqs", arf_data)

    async def sync_device_clock(self, epoch_ts: int | None = None) -> dict[str, Any]:
        """Sincroniza el reloj de tiempo real RTC del hardware con la hora exacta del host."""
        ts = int(epoch_ts if epoch_ts is not None else time.time())
        now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        mc = self._ctx.mc_provider()
        try:
            await self._write_device(mc, "set_time", ts, timeout=3.0)
        except (RuntimeError, NotImplementedError, ConnectionError, asyncio.TimeoutError) as error:
            return {"status": "error", "message": str(error)}

        self._local_config["clock"] = time.strftime("%I:%M:%S %p", time.localtime(ts))
        self._local_config["device_epoch_time"] = ts
        self._local_config["device_time_sampled_at"] = time.time()
        self._local_config["device_time_drift"] = 0
        return {
            "status": "ok",
            "clock": now_str,
            "epoch": ts,
            "message": f"Reloj RTC sincronizado exitosamente con la hora del host: {now_str}",
        }

    async def clear_device_stats(self) -> dict[str, Any]:
        """Restablece los contadores de estadísticas y airtime en el nodo local."""
        self._local_config["tx_count"] = 0
        self._local_config["rx_count"] = 0
        self._local_config["packet_errors"] = 0
        self._local_config["airtime_ms"] = 0
        self._local_config["duplicate_packets"] = 0
        if hasattr(self._ctx, "counters") and self._ctx.counters:
            try:
                self._ctx.counters.tx_count = 0
                self._ctx.counters.rx_count = 0
            except Exception:
                pass
        return {
            "status": "ok",
            "message": "Contadores de paquetes y tiempos de aire restablecidos correctamente a cero",
        }

    def _prevalidate_local_params(self, params: dict[str, Any]) -> None:
        """Prevalida el lote completo de configuración local antes de mutar el hardware."""
        if not isinstance(params, dict):
            raise ValueError("params debe ser un objeto")

        allowed_local_keys = frozenset({
            # Identidad y ubicación
            "name", "latitude", "lat", "longitude", "lon", "altitude", "alt", "altitude_m", "owner_info", "owner",
            # Radio
            "frequency", "radio_freq", "bandwidth", "bw", "spreading_factor", "sf", "coding_rate", "cr",
            "tx_power", "power", "repeat", "repeat_enabled",
            # Tiempos e intervalos
            "beacon_interval", "advert_interval", "telemetry_interval", "hop_limit", "hops",
            # Parámetros de telemetría y políticas
            "telemetry_mode_base", "telemetry_mode_loc", "telemetry_mode_env",
            "multi_acks", "adv_loc_policy", "manual_add_contacts",
            # Ajustes avanzados y tuning
            "pin", "devicepin", "rx_delay", "rx_dly", "airtime_factor", "af",
            "path_hash_mode", "custom_vars",
            # Políticas de host / airtime
            "duty_cycle_limit_pct", "warn_threshold_pct",
            "airtime_cutoff_enabled", "airtime_cutoff_threshold_pct", "airtime_cutoff_resume_pct",
            "repeater_pre_send_delay_enabled", "repeater_pre_send_delay_s",
        })

        for k in params:
            if k not in allowed_local_keys:
                raise ValueError(f"Parámetro de configuración local desconocido: '{k}'")

        if "name" in params:
            name_val = str(params["name"]).strip()
            if len(name_val.encode("utf-8")) > 31 or any(ord(c) < 0x20 for c in name_val):
                raise ValueError("Nombre de nodo inválido: máximo 31 bytes UTF-8 sin caracteres de control")

        lat_val = params.get("latitude", params.get("lat"))
        lon_val = params.get("longitude", params.get("lon"))
        if lat_val is not None or lon_val is not None:
            if lat_val is None:
                lat_val = self._get_device_baseline("latitude", ("lat", "adv_lat"))
            if lon_val is None:
                lon_val = self._get_device_baseline("longitude", ("lon", "adv_lon"))
            if lat_val is None or lon_val is None:
                raise ValueError("Coordenadas incompletas: se requieren tanto latitud como longitud")
            try:
                lat_f, lon_f = float(lat_val), float(lon_val)
                if math.isnan(lat_f) or math.isnan(lon_f) or math.isinf(lat_f) or math.isinf(lon_f):
                    raise ValueError("Coordenadas no pueden ser NaN o infinitas")
                if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
                    raise ValueError("Coordenadas fuera de rango (-90..90, -180..180)")
            except (ValueError, TypeError) as err:
                raise ValueError("Coordenadas inválidas") from err

        if "altitude" in params or "alt" in params or "altitude_m" in params:
            alt_raw = params.get("altitude", params.get("alt", params.get("altitude_m")))
            if alt_raw is not None:
                try:
                    alt_f = float(alt_raw)
                    if math.isnan(alt_f) or math.isinf(alt_f):
                        raise ValueError("Altitud inválida")
                except (ValueError, TypeError) as err:
                    raise ValueError(f"Altitud inválida: {alt_raw}") from err

        if "path_hash_mode" in params:
            try:
                phm = int(params["path_hash_mode"])
                if phm not in (0, 1, 2):
                    raise ValueError(f"path_hash_mode debe ser 0, 1 o 2 (recibido: {phm})")
            except (ValueError, TypeError) as err:
                raise ValueError(f"Path hash mode inválido: {err}") from err

        if "pin" in params or "devicepin" in params:
            raw_pin = params.get("pin", params.get("devicepin"))
            try:
                p_int = int(raw_pin)
                if p_int != 0 and not (100000 <= p_int <= 999999):
                    raise ValueError("El PIN del dispositivo debe ser 0 (desactivado) o de 6 dígitos (100000-999999)")
            except (ValueError, TypeError) as err:
                raise ValueError(f"PIN inválido: {raw_pin}") from err

        # Prevalidación de potencia TX (BV06)
        if "tx_power" in params or "power" in params:
            raw_pwr = params.get("tx_power", params.get("power"))
            if isinstance(raw_pwr, bool):
                raise ValueError("Potencia TX no puede ser un booleano")
            try:
                p_int = int(raw_pwr)
                if not (-9 <= p_int <= 30):
                    raise ValueError(f"Potencia TX fuera de rango (-9..30 dBm): {raw_pwr}")
            except (ValueError, TypeError) as err:
                raise ValueError(f"Potencia TX inválida: {raw_pwr}") from err

        # Prevalidación de parámetros de radio (BV02, BV03, BV10)
        radio_keys = ("frequency", "radio_freq", "bandwidth", "bw", "spreading_factor", "sf", "coding_rate", "cr", "repeat", "repeat_enabled")
        if any(k in params for k in radio_keys):
            b_freq = params.get("frequency", params.get("radio_freq", self._get_device_baseline("frequency", ("freq", "radio_freq"))))
            b_bw = params.get("bandwidth", params.get("bw", self._get_device_baseline("bandwidth", ("bw", "radio_bw"))))
            b_sf = params.get("spreading_factor", params.get("sf", self._get_device_baseline("spreading_factor", ("sf", "radio_sf"))))
            b_cr = params.get("coding_rate", params.get("cr", self._get_device_baseline("coding_rate", ("cr", "radio_cr"))))
            if b_freq is None or b_bw is None or b_sf is None or b_cr is None:
                raise ValueError("Baseline de parámetros de radio no disponible; se requiere especificar frequency, bandwidth, spreading_factor y coding_rate completos.")
            try:
                f_flt = float(b_freq)
                if not (LORA_MIN_FREQ_MHZ <= f_flt <= LORA_MAX_FREQ_MHZ):
                    raise ValueError(f"Frecuencia {f_flt} MHz fuera del rango permitido ({LORA_MIN_FREQ_MHZ}-{LORA_MAX_FREQ_MHZ} MHz)")
                bw_flt = float(b_bw)
                if not (7.0 <= bw_flt <= 500.0):
                    raise ValueError(f"Ancho de banda {bw_flt} kHz inválido")
                sf_int = int(b_sf)
                if sf_int not in range(5, 13):
                    raise ValueError(f"Spreading factor SF{sf_int} inválido (5..12)")
                cr_parsed = normalize_coding_rate(b_cr)
                if cr_parsed is None:
                    raise ValueError(f"Coding rate CR '{b_cr}' inválido (debe ser 5..8 o 4/5..4/8)")
            except (ValueError, TypeError) as err:
                raise ValueError(f"Parámetros de radio inválidos: {err}") from err

        # Prevalidación de tiempos e intervalos
        for int_key in ("beacon_interval", "advert_interval", "telemetry_interval", "hop_limit", "hops"):
            if int_key in params:
                val = params[int_key]
                if isinstance(val, bool):
                    raise ValueError(f"El parámetro '{int_key}' no puede ser booleano")
                try:
                    i_val = int(val)
                    if i_val < 0:
                        raise ValueError(f"El parámetro '{int_key}' debe ser no negativo")
                except (ValueError, TypeError) as err:
                    raise ValueError(f"Parámetro '{int_key}' inválido: {val}") from err

        # Prevalidación de modos de telemetría
        for ok in ("telemetry_mode_base", "telemetry_mode_loc", "telemetry_mode_env"):
            if ok in params:
                o_val = params[ok]
                if isinstance(o_val, bool):
                    raise ValueError(f"El parámetro '{ok}' no puede ser booleano")
                try:
                    oi = int(o_val)
                    if oi not in (0, 1, 2):
                        raise ValueError(f"El parámetro '{ok}' debe ser 0, 1 o 2 (recibido: {oi})")
                except (ValueError, TypeError) as err:
                    raise ValueError(f"Parámetro '{ok}' inválido: {o_val}") from err

        # Prevalidación de tuning
        for tk in ("rx_delay", "airtime_factor", "af", "rx_dly"):
            if tk in params:
                t_val = params[tk]
                if isinstance(t_val, bool):
                    raise ValueError(f"El parámetro '{tk}' no puede ser booleano")
                try:
                    f_val = float(t_val)
                    if not math.isfinite(f_val) or f_val < 0.0:
                        raise ValueError(f"El parámetro '{tk}' debe ser un número finito no negativo")
                except (ValueError, TypeError) as err:
                    raise ValueError(f"Parámetro '{tk}' inválido: {t_val}") from err

        # Prevalidación de custom_vars
        if "custom_vars" in params and not isinstance(params["custom_vars"], dict):
            raise ValueError("custom_vars debe ser un objeto/diccionario")

    async def set_local_config(self, admin_data: dict[str, Any], res: dict[str, Any], mc: Any) -> dict[str, Any]:
        """Aplica configuraciones locales sobre el nodo conectado."""
        params = admin_data.get("params", admin_data)
        applied: dict[str, Any] = {}

        try:
            if not isinstance(params, dict):
                raise ValueError("params debe ser un objeto")
            self._prevalidate_local_params(params)
            await self._apply_identity_settings(params, applied, mc)
            await self._apply_radio_settings(params, applied, mc)
            self._apply_timing_settings(params, applied, mc)
            await self._apply_other_params_settings(params, applied, mc)
            await self._apply_advanced_meshcore_settings(params, applied, mc)
        except Exception as error:
            res.update({
                "status": "partial" if applied else "error",
                "code": 422 if not applied and isinstance(error, ValueError) else (400 if applied else 422),
                "action": "set_local_config",
                "applied": redact_sensitive_dict(applied),
                "message": str(error),
                "config": redact_sensitive_dict(self.get_local_config()),
            })
            pub_res = redact_sensitive_dict(dict(res))
            self._publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(pub_res), 1)
            return res

        # Actualizar en el NodeRegistry local
        cfg_now = self.get_local_config()
        local_pk = cfg_now.get("public_key")
        if local_pk and is_valid_node_key(local_pk) and self._ctx.node_registry:
            self._ctx.node_registry.add_or_update(
                local_pk,
                NodeContactUpdate(
                    name=self._local_config.get("name"),
                    alias=self._local_config.get("name"),
                    role="LOCAL",
                    latitude=self._local_config.get("latitude"),
                    longitude=self._local_config.get("longitude"),
                    altitude_m=self._local_config.get("altitude"),
                    owner_name=self._local_config.get("name"),
                    owner_info=self._local_config.get("owner_info"),
                    fixed_position=True,
                ),
            )

        res["status"] = "ok"
        res["action"] = "set_local_config"
        res["applied"] = redact_sensitive_dict(applied)
        res["message"] = f"Configuración local aplicada exitosamente: {', '.join(applied.keys())}"
        res["config"] = redact_sensitive_dict(self.get_local_config())
        pub_res = redact_sensitive_dict(dict(res))
        self._publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(pub_res), 1)
        return res

    async def _apply_identity_settings(self, params: dict[str, Any], applied: dict[str, Any], mc: Any) -> None:
        """Aplica nombre, propietario y coordenadas GPS."""
        if "name" in params:
            new_name = str(params["name"]).strip()
            if len(new_name.encode("utf-8")) > 31 or any(ord(char) < 0x20 for char in new_name):
                raise ValueError("Nombre de nodo inválido: máximo 31 bytes UTF-8")
            await self._write_device(mc, "set_name", new_name, timeout=2.0)
            self._local_config["name"] = new_name
            applied["name"] = new_name
            if mc:
                if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                    mc.self_info["name"] = new_name
                if hasattr(mc, "_self_info") and isinstance(mc._self_info, dict):
                    mc._self_info["name"] = new_name

        lat_val = params.get("latitude", params.get("lat"))
        lon_val = params.get("longitude", params.get("lon"))
        if lat_val is not None or lon_val is not None:
            if lat_val is None:
                lat_val = self._get_device_baseline("latitude", ("lat", "adv_lat"))
            if lon_val is None:
                lon_val = self._get_device_baseline("longitude", ("lon", "adv_lon"))
            if lat_val is None or lon_val is None:
                raise ValueError("Coordenadas incompletas: se requieren tanto latitud como longitud")
            try:
                lat_f, lon_f = float(lat_val), float(lon_val)
                if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
                    raise ValueError("Coordenadas fuera de rango (-90..90, -180..180)")
                await self._write_device(mc, "set_coords", lat=lat_f, lon=lon_f, timeout=2.0)
                self._local_config["latitude"] = lat_f
                self._local_config["longitude"] = lon_f
                applied["latitude"] = lat_f
                applied["longitude"] = lon_f
                if mc:
                    if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                        mc.self_info["adv_lat"] = lat_f
                        mc.self_info["adv_lon"] = lon_f
                    if hasattr(mc, "_self_info") and isinstance(mc._self_info, dict):
                        mc._self_info["adv_lat"] = lat_f
                        mc._self_info["adv_lon"] = lon_f
            except (ValueError, TypeError) as error:
                raise ValueError("Coordenadas inválidas") from error

        alt_val = params.get("altitude", params.get("alt", params.get("altitude_m")))
        if alt_val is not None:
            try:
                alt_f = float(alt_val)
                self._local_config["altitude"] = alt_f
                applied["altitude"] = alt_f
                if mc and hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                    mc.self_info["altitude"] = alt_f
                if mc and hasattr(mc, "_self_info") and isinstance(mc._self_info, dict):
                    mc._self_info["altitude"] = alt_f
            except (ValueError, TypeError):
                pass

        if "owner_info" in params or "owner" in params:
            owner = str(params.get("owner_info", params.get("owner", ""))).strip()
            self._local_config["owner_info"] = owner
            applied["owner_info"] = owner

    async def _apply_radio_settings(self, params: dict[str, Any], applied: dict[str, Any], mc: Any) -> None:
        """
        Aplica potencia TX, frecuencia y parámetros de modulación en el hardware y la memoria local.
        """
        if "tx_power" in params or "power" in params:
            raw_p_val = params.get("tx_power", params.get("power", 20))
            try:
                raw_p = int(raw_p_val)
            except (ValueError, TypeError) as err:
                raise ValueError(f"Potencia TX inválida: {raw_p_val}") from err
            hw_board = self._local_config.get("hardware_board")
            new_p = clamp_tx_power(raw_p, hw_board, self._local_config.get("max_tx_power"))
            await self._write_device(mc, "set_tx_power", new_p, timeout=2.0)
            self._local_config["tx_power"] = new_p
            applied["tx_power"] = new_p
            if mc:
                if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                    mc.self_info["tx_power"] = new_p
                if hasattr(mc, "_self_info") and isinstance(mc._self_info, dict):
                    mc._self_info["tx_power"] = new_p

        radio_keys = ("frequency", "radio_freq", "bandwidth", "bw", "spreading_factor", "sf", "coding_rate", "cr", "repeat", "repeat_enabled")
        if any(k in params for k in radio_keys):
            if "frequency" in params or "radio_freq" in params:
                freq_raw = params.get("frequency") if "frequency" in params else params.get("radio_freq")
                if freq_raw is None:
                    raise ValueError("Frecuencia no especificada")
                try:
                    new_f = float(freq_raw)
                except (ValueError, TypeError) as err:
                    raise ValueError(f"Frecuencia inválida: {freq_raw}") from err
            else:
                baseline_f = self._get_device_baseline("frequency", ("freq", "radio_freq"))
                if baseline_f is None:
                    raise ValueError("Baseline de parámetros de radio no disponible; se requiere especificar frequency completa.")
                new_f = float(baseline_f)

            if "bandwidth" in params or "bw" in params:
                bw_raw = params.get("bandwidth") if "bandwidth" in params else params.get("bw")
                if bw_raw is None:
                    raise ValueError("Ancho de banda no especificado")
                try:
                    new_bw = float(bw_raw)
                except (ValueError, TypeError) as err:
                    raise ValueError(f"Ancho de banda inválido: {bw_raw}") from err
            else:
                baseline_bw = self._get_device_baseline("bandwidth", ("bw", "radio_bw"))
                if baseline_bw is None:
                    raise ValueError("Baseline de parámetros de radio no disponible; se requiere especificar bandwidth completo.")
                new_bw = float(baseline_bw)

            if "spreading_factor" in params or "sf" in params:
                sf_raw = params.get("spreading_factor") if "spreading_factor" in params else params.get("sf")
                if sf_raw is None:
                    raise ValueError("Spreading factor no especificado")
                try:
                    new_sf = int(sf_raw)
                except (ValueError, TypeError) as err:
                    raise ValueError(f"Spreading factor inválido: {sf_raw}") from err
            else:
                baseline_sf = self._get_device_baseline("spreading_factor", ("sf", "radio_sf"))
                if baseline_sf is None:
                    raise ValueError("Baseline de parámetros de radio no disponible; se requiere especificar spreading_factor completo.")
                new_sf = int(baseline_sf)

            if "coding_rate" in params or "cr" in params:
                cr_raw = params.get("coding_rate") if "coding_rate" in params else params.get("cr")
                new_cr = normalize_coding_rate(cr_raw)
                if new_cr is None:
                    raise ValueError(f"Coding rate inválido: {cr_raw}")
            else:
                baseline_cr = self._get_device_baseline("coding_rate", ("cr", "radio_cr"))
                new_cr = normalize_coding_rate(baseline_cr)
                if new_cr is None:
                    raise ValueError(f"Baseline de coding rate inválido: {baseline_cr}")

            rep_val = params.get("repeat", params.get("repeat_enabled", self._local_config.get("repeat", False)))
            new_rep = to_bool(rep_val)

            await self._write_device(mc, "set_radio", new_f, new_bw, new_sf, new_cr, int(new_rep), timeout=3.0)

            self._local_config["frequency"] = new_f
            self._local_config["radio_freq"] = new_f
            self._local_config["bandwidth"] = new_bw
            self._local_config["radio_bw"] = new_bw
            self._local_config["spreading_factor"] = new_sf
            self._local_config["sf"] = new_sf
            self._local_config["coding_rate"] = new_cr
            self._local_config["cr"] = new_cr
            self._local_config["repeat"] = new_rep

            if "frequency" in params or "radio_freq" in params:
                applied["frequency"] = new_f
            if "bandwidth" in params or "bw" in params:
                applied["bandwidth"] = new_bw
            if "spreading_factor" in params or "sf" in params:
                applied["spreading_factor"] = new_sf
            if "coding_rate" in params or "cr" in params:
                applied["coding_rate"] = new_cr
            if "repeat" in params or "repeat_enabled" in params:
                applied["repeat"] = new_rep


            update_fields = {
                "freq": new_f,
                "radio_freq": new_f,
                "bw": new_bw,
                "radio_bw": new_bw,
                "sf": new_sf,
                "radio_sf": new_sf,
                "cr": new_cr,
                "radio_cr": new_cr,
                "repeat": new_rep,
            }
            if mc:
                raw_si = getattr(mc, "self_info", None)
                if isinstance(raw_si, dict):
                    raw_si.update(update_fields)
                if hasattr(mc, "_self_info") and isinstance(mc._self_info, dict):
                    mc._self_info.update(update_fields)

            ser = getattr(self._ctx, "serial_adapter", None)
            if ser and hasattr(ser, "self_info") and isinstance(ser.self_info, dict):
                ser.self_info.update(update_fields)

            rl = getattr(self._ctx, "rate_limiter", None)
            if rl and hasattr(rl, "radio_config") and rl.radio_config:
                if dataclasses.is_dataclass(rl.radio_config):
                    rl.radio_config = dataclasses.replace(
                        cast(Any, rl.radio_config),
                        sf=new_sf,
                        bw_khz=new_bw,
                        cr=new_cr,
                    )
                else:
                    rl.radio_config.sf = new_sf
                    rl.radio_config.bw_khz = new_bw
                    rl.radio_config.cr = new_cr
                logging.info("TxRateLimiter: Parámetros LoRa actualizados a SF%d, BW%.1f kHz, CR%d", new_sf, new_bw, new_cr)

    def _apply_timing_settings(self, params: dict[str, Any], applied: dict[str, Any], mc: Any) -> None:
        """Aplica intervalos de baliza (advert) y telemetría."""
        if "beacon_interval" in params or "advert_interval" in params:
            try:
                adv_i = int(params.get("beacon_interval", params.get("advert_interval", 300)))
                self._local_config["beacon_interval"] = adv_i
                self._local_config["advert_interval"] = adv_i
                applied["beacon_interval"] = adv_i
                applied["advert_interval"] = adv_i
            except (ValueError, TypeError):
                pass

        if "telemetry_interval" in params:
            try:
                tel_i = int(params["telemetry_interval"])
                self._local_config["telemetry_interval"] = tel_i
                applied["telemetry_interval"] = tel_i
            except (ValueError, TypeError):
                pass

        if "hop_limit" in params or "hops" in params:
            try:
                hl = int(params.get("hop_limit", params.get("hops", 3)))
                self._local_config["hop_limit"] = hl
                applied["hop_limit"] = hl
            except (ValueError, TypeError):
                pass

    async def _apply_other_params_settings(self, params: dict[str, Any], applied: dict[str, Any], mc: Any) -> None:
        """Aplica modos de telemetría, políticas de anuncios y multi-acks."""
        keys = ["telemetry_mode_base", "telemetry_mode_loc", "telemetry_mode_env", "multi_acks", "adv_loc_policy", "manual_add_contacts"]
        need_update = any(k in params for k in keys)

        if need_update:
            pending: dict[str, int] = {}
            for k in keys:
                if k in params:
                    val = params[k]
                    try:
                        if k in ("multi_acks", "manual_add_contacts", "adv_loc_policy"):
                            int_val = int(to_bool(val))
                        else:
                            int_val = int(val)
                    except (ValueError, TypeError) as err:
                        raise ValueError(f"Valor inválido para {k}: {val}") from err
                    pending[k] = int_val

            if mc:
                infos: dict[str, Any] = {}
                if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                    infos = mc.self_info.copy()
                else:
                    infos = {k: int(self._local_config.get(k, 0)) for k in keys}

                for k in keys:
                    if k in params:
                        infos[k] = pending[k]
                    else:
                        infos.setdefault(k, int(self._local_config.get(k, 0)))

                await self._write_device(mc, "set_other_params_from_infos", infos, timeout=2.0)
            else:
                raise ConnectionError("Radio no conectada")
            self._local_config.update(pending)
            applied.update(pending)

    async def _apply_advanced_meshcore_settings(self, params: dict[str, Any], applied: dict[str, Any], mc: Any) -> None:
        """Aplica PIN del dispositivo, tuning de radio, path hash mode y custom variables."""
        # 1. PIN del dispositivo / BLE PIN
        if "pin" in params or "devicepin" in params:
            raw_pin = params.get("pin", params.get("devicepin", 0))
            try:
                pin_val = int(raw_pin)
            except (ValueError, TypeError) as err:
                raise ValueError(f"PIN inválido proporcionado: {raw_pin}") from err
            await self._write_device(mc, "set_devicepin", pin_val, timeout=2.0)
            self._local_config["pin"] = pin_val
            applied["pin"] = pin_val

        # 2. Tuning de Radio (rx_delay y airtime_factor / af)
        tuning_keys = ("rx_delay", "airtime_factor", "af", "rx_dly")
        if any(k in params for k in tuning_keys):
            try:
                raw_rx = params.get("rx_delay", params.get("rx_dly", self._local_config.get("rx_delay", 0.0)))
                raw_af = params.get("airtime_factor", params.get("af", self._local_config.get("airtime_factor", 1.0)))

                rx_flt = float(raw_rx)
                af_flt = float(raw_af)
            except (ValueError, TypeError) as err:
                raise ValueError(f"Parámetros de tuning inválidos: {err}") from err

            # Conversión canónica dominio -> wire (wire = int(round(val * 1000)))
            wire_rx = int(round(rx_flt * 1000.0))
            wire_af = int(round(af_flt * 1000.0))

            await self._write_device(mc, "set_tuning", wire_rx, wire_af, timeout=2.0)

            self._local_config["rx_delay"] = rx_flt
            self._local_config["airtime_factor"] = af_flt
            if "rx_delay" in params or "rx_dly" in params:
                applied["rx_delay"] = rx_flt
            if "airtime_factor" in params or "af" in params:
                applied["airtime_factor"] = af_flt

        # 3. Path Hash Mode
        if "path_hash_mode" in params:
            try:
                phm = int(params["path_hash_mode"])
                if phm not in (0, 1, 2):
                    raise ValueError(f"path_hash_mode debe ser 0, 1 o 2 (recibido: {phm})")
            except (ValueError, TypeError) as err:
                raise ValueError(f"Path hash mode inválido: {err}") from err
            await self._write_device(mc, "set_path_hash_mode", phm, timeout=2.0)
            self._local_config["path_hash_mode"] = phm
            applied["path_hash_mode"] = phm

        # 4. Variables personalizadas (custom_vars)
        if "custom_vars" in params and isinstance(params["custom_vars"], dict):
            if "custom_vars" not in self._local_config or not isinstance(self._local_config["custom_vars"], dict):
                self._local_config["custom_vars"] = {}
            for k, v in params["custom_vars"].items():
                await self._write_device(mc, "set_custom_var", str(k), str(v), timeout=2.0)
                self._local_config["custom_vars"][str(k)] = str(v)
            applied["custom_vars"] = self._local_config["custom_vars"]

    async def get_custom_vars(self) -> dict[str, Any]:
        """Obtiene las variables personalizadas almacenadas en el nodo local o en la flash."""
        mc = self._ctx.mc_provider()
        cv_res = await self._query_device(mc, "get_custom_vars", timeout=3.0)
        cv_data = extract_payload_dict(cv_res)
        if cv_data and isinstance(cv_data, dict):
            self._local_config["custom_vars"] = cv_data
        cv = self._local_config.get("custom_vars", {})
        return cv if isinstance(cv, dict) else {}

    async def set_custom_var(self, key: str, val: str) -> dict[str, Any]:
        """Asigna o actualiza una variable personalizada en el transceptor."""
        mc = self._ctx.mc_provider()
        await self._write_device(mc, "set_custom_var", str(key), str(val), timeout=3.0)
        if "custom_vars" not in self._local_config or not isinstance(self._local_config["custom_vars"], dict):
            self._local_config["custom_vars"] = {}
        self._local_config["custom_vars"][str(key)] = str(val)
        return {"status": "ok", "custom_vars": self._local_config["custom_vars"]}

    async def delete_custom_var(self, key: str) -> dict[str, Any]:
        """Elimina una variable personalizada asignando cadena vacía al firmware."""
        mc = self._ctx.mc_provider()
        await self._write_device(mc, "set_custom_var", str(key), "", timeout=3.0)
        if "custom_vars" in self._local_config and isinstance(self._local_config["custom_vars"], dict):
            self._local_config["custom_vars"].pop(str(key), None)
        return {"status": "ok", "custom_vars": self._local_config.get("custom_vars", {})}

    async def get_path_hash_mode(self) -> int:
        """Obtiene el modo de compresión path hash configurado."""
        return int(self._local_config.get("path_hash_mode", 0))

    async def set_path_hash_mode(self, mode: int) -> dict[str, Any]:
        """Configura el modo de path hash (0, 1, 2)."""
        mode = int(mode)
        if mode not in (0, 1, 2):
            raise ValueError("path_hash_mode debe ser 0, 1 o 2")
        mc = self._ctx.mc_provider()
        await self._write_device(mc, "set_path_hash_mode", mode, timeout=3.0)
        self._local_config["path_hash_mode"] = mode
        return {"status": "ok", "path_hash_mode": mode}

    async def get_autoadd_config(self) -> dict[str, Any]:
        """Obtiene la configuración de auto-adición de contactos."""
        mc = self._ctx.mc_provider()
        res = await self._query_device(mc, "get_autoadd_config", timeout=3.0)
        res_dict = extract_payload_dict(res)
        if res_dict and isinstance(res_dict, dict):
            if "max_hops" not in res_dict and isinstance(self._local_config.get("autoadd_config"), dict):
                res_dict["max_hops"] = self._local_config["autoadd_config"].get("max_hops", 0)
            self._local_config["autoadd_config"] = res_dict
        cfg = self._local_config.get("autoadd_config", {})
        if not isinstance(cfg, dict):
            cfg = {"config": int(self._local_config.get("manual_add_contacts", 0)), "max_hops": 0}
        return cfg

    async def set_autoadd_config(self, flags: int, max_hops: int | None = None) -> dict[str, Any]:
        """Aplica la máscara de auto-adición de contactos."""
        mc = self._ctx.mc_provider()
        if max_hops is not None and max_hops != 0:
            return {
                "status": "error",
                "code": 422,
                "message": "El SDK oficial de MeshCore no admite 'max_hops' en set_autoadd_config (parámetro no soportado)",
            }
        await self._write_device(mc, "set_autoadd_config", int(flags), timeout=3.0)
        self._local_config["autoadd_config"] = {"config": int(flags), "max_hops": 0}
        return {"status": "ok", "autoadd_config": self._local_config["autoadd_config"]}

    async def get_flood_scope(self) -> dict[str, Any]:
        """Obtiene el ámbito de inundación configurado."""
        mc = self._ctx.mc_provider()
        res = await self._query_device(mc, "get_default_flood_scope", timeout=3.0)
        res_dict = extract_payload_dict(res)
        if res_dict and isinstance(res_dict, dict):
            self._local_config["flood_scope"] = res_dict
        fs = self._local_config.get("flood_scope", {})
        return fs if isinstance(fs, dict) else {}

    async def set_flood_scope(self, scope: str | None) -> dict[str, Any]:
        """Asigna o reinicia el ámbito de inundación por defecto."""
        mc = self._ctx.mc_provider()
        if not scope or scope in ("*", "0", "global", "none"):
            await self._write_device(mc, "reset_default_flood_scope", timeout=3.0)
            self._local_config["flood_scope"] = {"scope_name": "", "scope_key": ""}
            return {"status": "ok", "flood_scope": self._local_config["flood_scope"]}

        await self._write_device(mc, "set_default_flood_scope", scope, timeout=3.0)
        self._local_config["flood_scope"] = {"scope_name": str(scope)}
        return {"status": "ok", "flood_scope": self._local_config["flood_scope"]}


