"""
LocalConfigExecutor: Gestión y parametrización del nodo local y módem LoRa conectado.
Descompone la lectura y escritura de configuración local:
- get_local_config: Consolidación de parámetros de hardware, telemetría y uptime.
- fetch_device_config: Consulta síncrona/asíncrona a la radio serial.
- set_local_config: Modificación confirmada de potencia TX, frecuencia, posición GPS y alias.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import logging
import math
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from meshcore.events import EventType
from meshcore.packets import CommandType

import config
from src.admin.sdk_commands import require_success, run_sdk_command
from src.contact_manager import NodeContactUpdate, is_valid_node_key
from src.protocol_types import (
    LORA_MAX_FREQ_MHZ,
    LORA_MIN_FREQ_MHZ,
    normalize_tx_power,
    redact_sensitive_dict,
)
from src.shared_utils import (
    clamp_tx_power,
    extract_payload_dict,
    get_hardware_power_limits,
    normalize_battery,
    to_bool,
)

# Companion exposes no write command or bridge scheduler for these historical UI fields.
UNSUPPORTED_LOCAL_FIELDS = frozenset({
    "telemetry_interval", "beacon_interval", "advert_interval", "hop_limit", "hops",
    "owner_info", "owner", "altitude", "alt", "altitude_m",
    "fixed_position", "pos_fixed",
})

OTHER_PARAM_FIELDS = (
    "telemetry_mode_base", "telemetry_mode_loc", "telemetry_mode_env",
    "multi_acks", "adv_loc_policy", "manual_add_contacts",
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
        for si in (self._read_self_info(mc), getattr(mc, "_self_info", None)):
            if isinstance(si, dict):
                for a in (field, *aliases):
                    if a in si and si[a] is not None:
                        return si[a]
        for a in (field, *aliases):
            if a in self._local_config and self._local_config[a] is not None:
                return self._local_config[a]
        return None

    def _sync_confirmed_self_info(self, mc: Any, fields: dict[str, Any]) -> None:
        """Synchronize SDK and adapter snapshots after a confirmed write or read."""
        snapshots = [self._read_self_info(mc), getattr(mc, "_self_info", None)]
        adapter = getattr(self._ctx, "serial_adapter", None)
        if adapter is not None:
            snapshots.append(getattr(adapter, "self_info", None))
        for snapshot in snapshots:
            if isinstance(snapshot, dict):
                snapshot.update(fields)

    def _other_params_baseline(self, params: dict[str, Any], mc: Any) -> dict[str, Any]:
        """Require each untouched packed setting to have an observed device value."""
        current_info = self._read_self_info(mc)
        infos = dict(current_info) if current_info is not None else {}
        for key in OTHER_PARAM_FIELDS:
            if key in params:
                continue
            value = self._get_device_baseline(key, ())
            if value is None:
                raise ValueError(f"Baseline del dispositivo no disponible para {key}; actualice desde el dispositivo antes de guardar")
            infos[key] = value
        return infos

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
        cfg["capabilities"] = {
            "telemetry_interval": False, "beacon_interval": False, "advert_interval": False,
            "hop_limit": False, "owner_info": False, "altitude": False,
            "fixed_position": False,
        }
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
        raw_power = si.get("tx_power", cfg.get("tx_power"))
        power = normalize_tx_power(raw_power)
        if power is None and raw_power is not None:
            power = normalize_tx_power(cfg.get("tx_power"))
        cfg.update({
            "name": si.get("name", cfg.get("name")),
            "owner_info": si.get("owner_info", si.get("owner", cfg.get("owner_info"))),
            "latitude": si.get("adv_lat", si.get("latitude", si.get("lat", cfg.get("latitude")))),
            "longitude": si.get("adv_lon", si.get("longitude", si.get("lon", cfg.get("longitude")))),
            "altitude": si.get("altitude", si.get("alt", cfg.get("altitude"))),
            "tx_power": power,
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
            self._sync_confirmed_self_info(mc, app_data)
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
            if "ble_pin" in dev_data:
                self._local_config["pin"] = dev_data["ble_pin"]
            self._sync_confirmed_self_info(mc, {
                key: self._local_config[key] for key in ("repeat", "path_hash_mode", "pin")
                if key in self._local_config
            })

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
        if cv_res is not None and isinstance(cv_data, dict):
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
        integer_keys = {"tx_power", "power", "spreading_factor", "sf", "path_hash_mode",
                        "pin", "devicepin", "telemetry_mode_base", "telemetry_mode_loc",
                        "telemetry_mode_env"}
        for key in integer_keys.intersection(params):
            value = params[key]
            if isinstance(value, bool) or (isinstance(value, float) and
                                          (not math.isfinite(value) or not value.is_integer())):
                raise ValueError(f"El parámetro '{key}' debe ser un entero")
        if "name" in params and not isinstance(params["name"], str):
            raise ValueError("name debe ser texto")
        for key in {"repeat", "repeat_enabled", "manual_add_contacts", "adv_loc_policy", "multi_acks"}.intersection(params):
            value = params[key]
            if not (isinstance(value, bool) or
                    (isinstance(value, int) and value in (0, 1)) or
                    (isinstance(value, str) and value.lower().strip() in {"true", "false", "1", "0", "yes", "no", "on", "off"})):
                raise ValueError(f"El parámetro '{key}' debe ser booleano")
        for canonical, alias, convert in (
            ("frequency", "radio_freq", float), ("bandwidth", "bw", float),
            ("spreading_factor", "sf", int), ("coding_rate", "cr", normalize_coding_rate),
            ("tx_power", "power", int), ("latitude", "lat", float),
            ("longitude", "lon", float), ("repeat", "repeat_enabled", to_bool),
            ("rx_delay", "rx_dly", float), ("airtime_factor", "af", float),
        ):
            if canonical in params and alias in params and convert(params[canonical]) != convert(params[alias]):
                raise ValueError(f"Alias contradictorios: '{canonical}' y '{alias}'")
        for key in {"latitude", "lat", "longitude", "lon"}.intersection(params):
            if isinstance(params[key], bool):
                raise ValueError(f"El parámetro '{key}' no puede ser booleano")
        if "custom_vars" in params:
            if not isinstance(params["custom_vars"], dict):
                raise ValueError("custom_vars debe ser un objeto")
            for key, value in params["custom_vars"].items():
                self._validate_custom_var(str(key), str(value))

        unsupported = sorted(UNSUPPORTED_LOCAL_FIELDS.intersection(params))
        if unsupported:
            raise ValueError(
                "Parámetros no soportados por el nodo local: " + ", ".join(unsupported)
                + ". El firmware Companion no expone estos ajustes; no se aplicó ningún cambio."
            )

        allowed_local_keys = frozenset({
            # Identidad y ubicación
            "name", "latitude", "lat", "longitude", "lon",
            # Radio
            "frequency", "radio_freq", "bandwidth", "bw", "spreading_factor", "sf", "coding_rate", "cr",
            "tx_power", "power", "repeat", "repeat_enabled",
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

        if any(key in params for key in OTHER_PARAM_FIELDS):
            self._other_params_baseline(params, self._ctx.mc_provider())

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
                if raw_pin is None:
                    raise ValueError("El PIN del dispositivo no puede ser nulo")
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
                if raw_pwr is None:
                    raise ValueError("Potencia TX no puede ser nula")
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
                    # Companion loadPrefs constrains these factors after restart.
                    maximum = 20.0 if tk in ("rx_delay", "rx_dly") else 9.0
                    if f_val > maximum:
                        raise ValueError(f"El parámetro '{tk}' debe estar entre 0 y {maximum}")
                except (ValueError, TypeError) as err:
                    raise ValueError(f"Parámetro '{tk}' inválido: {t_val}") from err

        if any(key in params for key in ("rx_delay", "rx_dly", "airtime_factor", "af")):
            for field, alias in (("rx_delay", "rx_dly"), ("airtime_factor", "af")):
                if field not in params and alias not in params and self._get_device_baseline(field, (alias,)) is None:
                    raise ValueError(f"Baseline de tuning no disponible para {field}; actualice desde el dispositivo o especifique ambos ajustes")

        # Prevalidación de custom_vars
        if "custom_vars" in params and not isinstance(params["custom_vars"], dict):
            raise ValueError("custom_vars debe ser un objeto/diccionario")

    async def set_local_config(self, admin_data: dict[str, Any], res: dict[str, Any], mc: Any) -> dict[str, Any]:
        """Aplica configuraciones locales sobre el nodo conectado."""
        # A refresh must not restore an older SDK snapshot during a confirmed write.
        async with self._fetch_lock:
            return await self._set_local_config_locked(admin_data, res, mc)

    async def _set_local_config_locked(self, admin_data: dict[str, Any], res: dict[str, Any], mc: Any) -> dict[str, Any]:
        """Apply one save while hardware refreshes and other saves are excluded."""
        params = admin_data.get("params", admin_data)
        applied: dict[str, Any] = {}

        try:
            if not isinstance(params, dict):
                raise ValueError("params debe ser un objeto")
            self._prevalidate_local_params(params)
            await self._apply_identity_settings(params, applied, mc)
            await self._apply_radio_settings(params, applied, mc)
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
            self._sync_confirmed_self_info(mc, {"name": new_name})

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
                # SDK and firmware encode signed microdegrees, truncating toward zero.
                lat_f = int(lat_f * 1_000_000) / 1_000_000
                lon_f = int(lon_f * 1_000_000) / 1_000_000
                await self._write_device(mc, "set_coords", lat=lat_f, lon=lon_f, timeout=2.0)
                self._local_config["latitude"] = lat_f
                self._local_config["longitude"] = lon_f
                applied["latitude"] = lat_f
                applied["longitude"] = lon_f
                self._sync_confirmed_self_info(mc, {
                    "adv_lat": lat_f, "latitude": lat_f, "lat": lat_f,
                    "adv_lon": lon_f, "longitude": lon_f, "lon": lon_f,
                })
            except (ValueError, TypeError) as error:
                raise ValueError("Coordenadas inválidas") from error

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
            self._sync_confirmed_self_info(mc, {"tx_power": new_p})

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

            rep_val = params.get("repeat", params.get("repeat_enabled", self._get_device_baseline("repeat", ("repeat_enabled",))))
            new_rep = to_bool(rep_val)

            await self._write_device(mc, "set_radio", new_f, new_bw, new_sf, new_cr, int(new_rep), timeout=3.0)
            # Report exactly the single conversion performed by the SDK.
            # Re-serializing a rounded float could lose another unit at a boundary.
            new_f = int(new_f * 1000) / 1000
            new_bw = int(new_bw * 1000) / 1000

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
                "frequency": new_f,
                "freq": new_f,
                "radio_freq": new_f,
                "bandwidth": new_bw,
                "bw": new_bw,
                "radio_bw": new_bw,
                "spreading_factor": new_sf,
                "sf": new_sf,
                "radio_sf": new_sf,
                "coding_rate": new_cr,
                "cr": new_cr,
                "radio_cr": new_cr,
                "repeat": new_rep,
            }
            self._sync_confirmed_self_info(mc, update_fields)

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

    async def _apply_other_params_settings(self, params: dict[str, Any], applied: dict[str, Any], mc: Any) -> None:
        """Aplica modos de telemetría, políticas de anuncios y multi-acks."""
        keys = OTHER_PARAM_FIELDS
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
                infos = self._other_params_baseline(params, mc)

                for k in keys:
                    if k in params:
                        infos[k] = pending[k]

                await self._write_device(mc, "set_other_params_from_infos", infos, timeout=2.0)
            else:
                raise ConnectionError("Radio no conectada")
            self._local_config.update(pending)
            self._sync_confirmed_self_info(mc, pending)
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
            self._sync_confirmed_self_info(mc, {"pin": pin_val})
            applied["pin"] = pin_val

        # 2. Tuning de Radio (rx_delay y airtime_factor / af)
        tuning_keys = ("rx_delay", "airtime_factor", "af", "rx_dly")
        if any(k in params for k in tuning_keys):
            try:
                raw_rx = params.get("rx_delay", params.get("rx_dly", self._get_device_baseline("rx_delay", ("rx_dly",))))
                raw_af = params.get("airtime_factor", params.get("af", self._get_device_baseline("airtime_factor", ("af",))))

                rx_flt = float(raw_rx)
                af_flt = float(raw_af)
            except (ValueError, TypeError) as err:
                raise ValueError(f"Parámetros de tuning inválidos: {err}") from err

            # Conversión canónica dominio -> wire (wire = int(round(val * 1000)))
            wire_rx = int(round(rx_flt * 1000.0))
            wire_af = int(round(af_flt * 1000.0))
            rx_flt, af_flt = wire_rx / 1000.0, wire_af / 1000.0

            await self._write_device(mc, "set_tuning", wire_rx, wire_af, timeout=2.0)

            self._local_config["rx_delay"] = rx_flt
            self._local_config["airtime_factor"] = af_flt
            self._sync_confirmed_self_info(mc, {"rx_delay": rx_flt, "airtime_factor": af_flt})
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
            self._sync_confirmed_self_info(mc, {"path_hash_mode": phm})
            applied["path_hash_mode"] = phm

        # 4. Variables personalizadas (custom_vars)
        if "custom_vars" in params and isinstance(params["custom_vars"], dict):
            if "custom_vars" not in self._local_config or not isinstance(self._local_config["custom_vars"], dict):
                self._local_config["custom_vars"] = {}
            for k, v in params["custom_vars"].items():
                await self._write_device(mc, "set_custom_var", str(k), str(v), timeout=2.0)
                self._local_config["custom_vars"][str(k)] = str(v)
                applied["custom_vars"] = dict(self._local_config["custom_vars"])
                self._sync_confirmed_self_info(mc, {"custom_vars": dict(self._local_config["custom_vars"])})
            applied["custom_vars"] = self._local_config["custom_vars"]

    async def get_custom_vars(self) -> dict[str, Any]:
        """Obtiene las variables personalizadas almacenadas en el nodo local o en la flash."""
        mc = self._ctx.mc_provider()
        cv_res = await self._query_device(mc, "get_custom_vars", timeout=3.0)
        cv_data = extract_payload_dict(cv_res)
        if cv_res is not None and isinstance(cv_data, dict):
            self._local_config["custom_vars"] = cv_data
            self._sync_confirmed_self_info(mc, {"custom_vars": dict(cv_data)})
        cv = self._local_config.get("custom_vars", {})
        return cv if isinstance(cv, dict) else {}

    async def set_custom_var(self, key: str, val: str) -> dict[str, Any]:
        """Asigna o actualiza una variable personalizada en el transceptor."""
        self._validate_custom_var(key, val)
        mc = self._ctx.mc_provider()
        await self._write_device(mc, "set_custom_var", str(key), str(val), timeout=3.0)
        if "custom_vars" not in self._local_config or not isinstance(self._local_config["custom_vars"], dict):
            self._local_config["custom_vars"] = {}
        self._local_config["custom_vars"][str(key)] = str(val)
        self._sync_confirmed_self_info(mc, {"custom_vars": dict(self._local_config["custom_vars"])})
        return {"status": "ok", "custom_vars": self._local_config["custom_vars"]}

    async def delete_custom_var(self, key: str) -> dict[str, Any]:
        """Firmware custom variables are predefined settings, not deletable keys."""
        self._validate_custom_var(key, "")
        return {"status": "not_supported", "code": 422,
                "message": "Companion permite modificar ajustes custom definidos por el firmware, no eliminarlos"}

    async def get_path_hash_mode(self) -> int:
        """Obtiene el modo de compresión path hash configurado."""
        mc = self._ctx.mc_provider()
        response = await self._query_device(mc, "send_device_query", timeout=3.0)
        info = extract_payload_dict(response)
        mode = info.get("path_hash_mode")
        if mode not in (0, 1, 2) or isinstance(mode, bool):
            raise ConnectionError("El dispositivo no confirmó path_hash_mode")
        self._local_config["path_hash_mode"] = int(mode)
        self._sync_confirmed_self_info(mc, {"path_hash_mode": int(mode)})
        return int(mode)

    async def set_path_hash_mode(self, mode: int) -> dict[str, Any]:
        """Configura el modo de path hash (0, 1, 2)."""
        if isinstance(mode, bool) or not isinstance(mode, int) or mode not in (0, 1, 2):
            raise ValueError("path_hash_mode debe ser 0, 1 o 2")
        mc = self._ctx.mc_provider()
        await self._write_device(mc, "set_path_hash_mode", mode, timeout=3.0)
        self._local_config["path_hash_mode"] = mode
        self._sync_confirmed_self_info(mc, {"path_hash_mode": mode})
        return {"status": "ok", "path_hash_mode": mode}

    async def get_autoadd_config(self) -> dict[str, Any]:
        """Obtiene la configuración de auto-adición de contactos."""
        mc = self._ctx.mc_provider()
        res = await self._query_device(mc, "get_autoadd_config", timeout=3.0)
        res_dict = extract_payload_dict(res)
        if res is not None and "config" in res_dict:
            res_dict = dict(res_dict)
            res_dict["max_hops_supported"] = "max_hops" in res_dict
            self._local_config["autoadd_config"] = res_dict
            self._sync_confirmed_self_info(mc, {"autoadd_config": dict(res_dict)})
        cfg = self._local_config.get("autoadd_config", {})
        if not isinstance(cfg, dict):
            cfg = {}
        return cfg

    async def set_autoadd_config(self, flags: int, max_hops: int | None = None) -> dict[str, Any]:
        """Aplica la máscara de auto-adición de contactos."""
        mc = self._ctx.mc_provider()
        if isinstance(flags, bool) or not isinstance(flags, int) or not 0 <= flags <= 255:
            raise ValueError("flags debe ser un entero 0..255")
        observed = self._local_config.get("autoadd_config", {})
        if max_hops is not None and (isinstance(max_hops, bool) or
                                    not isinstance(max_hops, int) or not 0 <= max_hops <= 64):
            raise ValueError("max_hops debe ser un entero 0..64")
        if max_hops is not None and not observed.get("max_hops_supported", False):
            return {
                "status": "error",
                "code": 422,
                "message": "El dispositivo no confirmó soporte de max_hops; consulte primero autoadd",
            }
        if max_hops is None:
            await self._write_device(mc, "set_autoadd_config", flags, timeout=3.0)
        else:
            frame = bytes([CommandType.SET_AUTOADD_CONFIG.value, flags, max_hops])
            await self._write_device(mc, "send", frame, [EventType.OK, EventType.ERROR], timeout=3.0)
        confirmed = {**observed, "config": flags}
        if max_hops is not None:
            confirmed["max_hops"] = max_hops
        self._local_config["autoadd_config"] = confirmed
        self._sync_confirmed_self_info(mc, {"autoadd_config": dict(confirmed)})
        return {"status": "ok", "autoadd_config": self._local_config["autoadd_config"]}

    async def get_flood_scope(self) -> dict[str, Any]:
        """Obtiene el ámbito de inundación configurado."""
        mc = self._ctx.mc_provider()
        res = await self._query_device(mc, "get_default_flood_scope", timeout=3.0)
        res_dict = extract_payload_dict(res)
        if res is not None:
            self._local_config["flood_scope"] = res_dict or {"scope_name": "", "scope_key": ""}
            self._sync_confirmed_self_info(mc, {"flood_scope": dict(self._local_config["flood_scope"])})
        fs = self._local_config.get("flood_scope", {})
        return fs if isinstance(fs, dict) else {}

    async def set_flood_scope(self, scope: str | None) -> dict[str, Any]:
        """Asigna o reinicia el ámbito de inundación por defecto."""
        mc = self._ctx.mc_provider()
        if not scope or scope in ("*", "0", "global", "none"):
            await self._write_device(mc, "send", bytes([CommandType.SET_DEFAULT_FLOOD_SCOPE.value]),
                                     [EventType.OK, EventType.ERROR], timeout=3.0)
            self._local_config["flood_scope"] = {"scope_name": "", "scope_key": ""}
            self._sync_confirmed_self_info(mc, {"flood_scope": dict(self._local_config["flood_scope"])})
            return {"status": "ok", "flood_scope": self._local_config["flood_scope"]}

        canonical = scope if scope.startswith("#") else "#" + scope
        name = canonical.encode("utf-8")
        if not 1 <= len(name) <= 30 or any(ord(char) < 32 for char in canonical):
            raise ValueError("El ámbito debe ocupar 1..30 bytes UTF-8 sin caracteres de control")
        key = hashlib.sha256(name).digest()[:16]
        frame = bytes([CommandType.SET_DEFAULT_FLOOD_SCOPE.value]) + name.ljust(31, b"\0") + key
        await self._write_device(mc, "send", frame, [EventType.OK, EventType.ERROR], timeout=3.0)
        self._local_config["flood_scope"] = {"scope_name": canonical, "scope_key": key.hex()}
        self._sync_confirmed_self_info(mc, {"flood_scope": dict(self._local_config["flood_scope"])})
        return {"status": "ok", "flood_scope": self._local_config["flood_scope"]}

    @staticmethod
    def _validate_custom_var(key: str, val: str) -> None:
        """Keep the official key:value / comma-delimited readback unambiguous."""
        if not key or any(char in key + val for char in (":", ",", "\0", "\r", "\n")):
            raise ValueError("Variable custom inválida: clave vacía o separadores reservados")


