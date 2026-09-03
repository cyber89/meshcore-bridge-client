"""
LocalConfigExecutor: Gestión y parametrización del nodo local y módem LoRa conectado.
Descompone la lectura y escritura de configuración local:
- get_local_config: Consolidación de parámetros de hardware, telemetría y uptime.
- fetch_device_config: Consulta síncrona/asíncrona a la radio serial.
- set_local_config: Modificación atómica de potencia TX, frecuencia, posición GPS y alias.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import config
from src.contact_manager import NodeContactUpdate, is_valid_node_key
from src.shared_utils import clamp_tx_power, get_hardware_power_limits

if TYPE_CHECKING:
    from src.admin_handler import AdminContext


def _extract_payload_dict(data: Any) -> dict[str, Any]:
    """Extrae un diccionario de datos tanto de objetos Event como de dicts nativos."""
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if hasattr(data, "payload") and isinstance(data.payload, dict):
        return data.payload
    return {}


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
            "battery_pct": si.get("battery_pct", si.get("battery", cfg.get("battery_pct", 100))),
            "voltage": si.get("voltage", cfg.get("voltage", 5.0)),
            "battery_mv": si.get("battery_mv", cfg.get("battery_mv", 5000)),
            "telemetry_mode_base": si.get("telemetry_mode_base", cfg.get("telemetry_mode_base")),
            "telemetry_mode_loc": si.get("telemetry_mode_loc", cfg.get("telemetry_mode_loc")),
            "telemetry_mode_env": si.get("telemetry_mode_env", cfg.get("telemetry_mode_env")),
            "adv_loc_policy": si.get("adv_loc_policy", cfg.get("adv_loc_policy")),
            "multi_acks": si.get("multi_acks", cfg.get("multi_acks")),
            "manual_add_contacts": si.get("manual_add_contacts", cfg.get("manual_add_contacts")),
        })

    def _ensure_default_telemetry(self, cfg: dict[str, Any]) -> None:
        """Asegura campos por defecto para alimentación USB cuando no hay batería."""
        cfg.setdefault("battery_pct", 100)
        cfg.setdefault("voltage", 5.0)
        cfg.setdefault("battery_mv", 5000)
        cfg.setdefault("power_source", "USB 5V Directo")

    def _populate_uptime_and_airtime(self, cfg: dict[str, Any]) -> None:
        """Calcula métricas de uptime y ciclo de trabajo de radio."""
        uptime_sec = self._local_config.get("uptime", 0)
        if uptime_sec <= 0:
            bridge_start = getattr(self._ctx, "start_time", 0.0)
            if not bridge_start and hasattr(self._ctx, "counters"):
                bridge_start = getattr(self._ctx.counters, "start_time", 0.0)
            if not bridge_start:
                bridge_start = self._init_time
            if bridge_start > 0:
                uptime_sec = max(1, int(time.time() - bridge_start))

        days = uptime_sec // 86400
        hours = (uptime_sec % 86400) // 3600
        mins = (uptime_sec % 3600) // 60
        secs = uptime_sec % 60
        uptime_str = f"{days}d {hours}h {mins}m {secs}s" if days > 0 else (f"{hours}h {mins}m {secs}s" if hours > 0 else f"{mins}m {secs}s")

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

    async def fetch_device_config(self) -> dict[str, Any]:
        """Consulta directamente al hardware serial los parámetros de configuración."""
        mc = self._ctx.mc_provider()
        if mc and hasattr(mc, "commands"):
            await self._query_hardware_device_and_battery(mc)
            await self._query_hardware_stats_and_packets(mc)
        return self.get_local_config()

    async def _query_hardware_device_and_battery(self, mc: Any) -> None:
        """Consulta identidad, modo repetidor, parámetros avanzados y nivel de batería por serial."""
        if hasattr(mc.commands, "send_appstart"):
            try:
                res_app = await mc.commands.send_appstart()
                app_data = _extract_payload_dict(res_app)
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
            except Exception as e:
                logging.warning(f"Error consultando send_appstart de radio: {e}")

        if hasattr(mc.commands, "send_device_query"):
            try:
                dev_res = await mc.commands.send_device_query()
                dev_data = _extract_payload_dict(dev_res)
                if dev_data and isinstance(dev_data, dict):
                    if "repeat" in dev_data:
                        self._local_config["repeat"] = bool(dev_data["repeat"])
                    if "path_hash_mode" in dev_data:
                        self._local_config["path_hash_mode"] = dev_data["path_hash_mode"]
            except Exception as e:
                logging.warning(f"Error consultando send_device_query de radio: {e}")

        if hasattr(mc.commands, "get_bat"):
            try:
                bat_res = await mc.commands.get_bat()
                bat_data = _extract_payload_dict(bat_res)
                if bat_data and isinstance(bat_data, dict):
                    mv = bat_data.get("battery_mv", bat_data.get("mv", 5000))
                    pct = bat_data.get("battery_pct", bat_data.get("pct", 100))
                    self._local_config.update({
                        "battery_pct": pct,
                        "battery_mv": mv,
                        "voltage": round(mv / 1000.0, 2) if mv else 5.0,
                    })
            except Exception as e:
                logging.warning(f"Error consultando get_bat de radio: {e}")

        if hasattr(mc.commands, "get_tuning"):
            try:
                tun_res = await mc.commands.get_tuning()
                tun_data = _extract_payload_dict(tun_res)
                if tun_data and isinstance(tun_data, dict):
                    if "rx_delay" in tun_data:
                        self._local_config["rx_delay"] = tun_data["rx_delay"]
                    if "airtime_factor" in tun_data:
                        self._local_config["airtime_factor"] = tun_data["airtime_factor"]
            except Exception as e:
                logging.warning(f"Error consultando get_tuning de radio: {e}")

        if hasattr(mc.commands, "get_time"):
            try:
                t_res = await mc.commands.get_time()
                t_data = _extract_payload_dict(t_res)
                if t_data and isinstance(t_data, dict) and "time" in t_data:
                    self._local_config["device_epoch_time"] = t_data["time"]
            except Exception as e:
                logging.warning(f"Error consultando get_time de radio: {e}")

    async def _query_hardware_stats_and_packets(self, mc: Any) -> None:
        """Consulta estadísticas de núcleo, radio, sensores y paquetes por serial."""
        if hasattr(mc.commands, "get_stats_core"):
            try:
                c_res = await mc.commands.get_stats_core()
                c_data = _extract_payload_dict(c_res)
                if c_data and isinstance(c_data, dict):
                    self._local_config['stats_core'] = c_data
                    u_val = c_data.get("uptime_secs") or c_data.get("uptime")
                    if u_val is not None and int(u_val) > 0:
                        self._local_config["uptime"] = int(u_val)
                        self._local_config["uptime_secs"] = int(u_val)
                    if "battery_mv" in c_data:
                        self._local_config["battery_mv"] = c_data["battery_mv"]
                    if "errors" in c_data:
                        self._local_config["packet_errors"] = c_data["errors"]
            except Exception as e:
                logging.warning(f"Error consultando get_stats_core de radio: {e}")

        if hasattr(mc.commands, "get_stats_radio"):
            try:
                r_res = await mc.commands.get_stats_radio()
                r_data = _extract_payload_dict(r_res)
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
            except Exception as e:
                logging.warning(f"Error consultando get_stats_radio de radio: {e}")

        if hasattr(mc.commands, "get_stats_packets"):
            try:
                p_res = await mc.commands.get_stats_packets()
                p_data = _extract_payload_dict(p_res)
                if p_data and isinstance(p_data, dict):
                    self._local_config['stats_packets'] = p_data
                    if "sent" in p_data:
                        self._local_config["tx_count"] = p_data["sent"]
                    if "recv" in p_data:
                        self._local_config["rx_count"] = p_data["recv"]
                    if "recv_errors" in p_data:
                        self._local_config["packet_errors"] = p_data["recv_errors"]
            except Exception as e:
                logging.warning(f"Error consultando get_stats_packets de radio: {e}")

        if hasattr(mc.commands, "get_self_telemetry"):
            try:
                st_res = await mc.commands.get_self_telemetry()
                st_data = _extract_payload_dict(st_res)
                if st_data and isinstance(st_data, dict):
                    self._local_config["self_telemetry"] = st_data
                    if "temperature" in st_data or "temperature_c" in st_data:
                        self._local_config["temperature_c"] = st_data.get("temperature", st_data.get("temperature_c"))
                    if "humidity" in st_data or "humidity_pct" in st_data:
                        self._local_config["humidity_pct"] = st_data.get("humidity", st_data.get("humidity_pct"))
                    if "pressure" in st_data or "pressure_hpa" in st_data:
                        self._local_config["pressure_hpa"] = st_data.get("pressure", st_data.get("pressure_hpa"))
            except Exception as e:
                logging.warning(f"Error consultando get_self_telemetry de radio: {e}")

        if hasattr(mc.commands, "get_custom_vars"):
            try:
                cv_res = await mc.commands.get_custom_vars()
                cv_data = _extract_payload_dict(cv_res)
                if cv_data and isinstance(cv_data, dict):
                    self._local_config["custom_vars"] = cv_data
            except Exception as e:
                logging.warning(f"Error consultando get_custom_vars de radio: {e}")

        if hasattr(mc.commands, "get_allowed_repeat_freq"):
            try:
                arf_res = await mc.commands.get_allowed_repeat_freq()
                arf_data = _extract_payload_dict(arf_res)
                if arf_data and isinstance(arf_data, dict):
                    self._local_config["allowed_repeat_freq"] = arf_data.get("allowed_freqs", arf_data)
            except Exception as e:
                logging.warning(f"Error consultando get_allowed_repeat_freq de radio: {e}")

    async def set_local_config(self, admin_data: dict[str, Any], res: dict[str, Any], mc: Any) -> dict[str, Any]:
        """Aplica configuraciones locales sobre el nodo conectado."""
        params = admin_data.get("params", admin_data)
        applied: dict[str, Any] = {}

        await self._apply_identity_settings(params, applied, mc)
        await self._apply_radio_settings(params, applied, mc)
        self._apply_timing_settings(params, applied, mc)
        await self._apply_other_params_settings(params, applied, mc)

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
        res["applied"] = applied
        res["message"] = f"Configuración local aplicada exitosamente: {', '.join(applied.keys())}"
        res["config"] = self.get_local_config()
        self._publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), 1)
        return res

    async def _apply_identity_settings(self, params: dict[str, Any], applied: dict[str, Any], mc: Any) -> None:
        """Aplica nombre, propietario y coordenadas GPS."""
        if "name" in params:
            new_name = str(params["name"]).strip()
            self._local_config["name"] = new_name
            applied["name"] = new_name
            if mc:
                if hasattr(mc, "commands") and hasattr(mc.commands, "set_name"):
                    try:
                        res = mc.commands.set_name(new_name)
                        if asyncio.iscoroutine(res):
                            await asyncio.wait_for(res, timeout=2.0)
                    except Exception as e:
                        logging.warning(f"Aviso actualizando nombre de nodo: {e}")
                if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                    mc.self_info["name"] = new_name

        lat_val = params.get("latitude", params.get("lat"))
        lon_val = params.get("longitude", params.get("lon"))
        if lat_val is not None and lon_val is not None:
            try:
                lat_f, lon_f = float(lat_val), float(lon_val)
                self._local_config["latitude"] = lat_f
                self._local_config["longitude"] = lon_f
                applied["latitude"] = lat_f
                applied["longitude"] = lon_f
                if mc:
                    if hasattr(mc, "commands") and hasattr(mc.commands, "set_coords"):
                        try:
                            res = mc.commands.set_coords(lat=lat_f, lon=lon_f)
                            if asyncio.iscoroutine(res):
                                await asyncio.wait_for(res, timeout=2.0)
                        except Exception as e:
                            logging.warning(f"Aviso actualizando coordenadas: {e}")
                    if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                        mc.self_info["adv_lat"] = lat_f
                        mc.self_info["adv_lon"] = lon_f
            except (ValueError, TypeError):
                pass

        if "owner_info" in params or "owner" in params:
            owner = str(params.get("owner_info", params.get("owner", ""))).strip()
            self._local_config["owner_info"] = owner
            applied["owner_info"] = owner

    async def _apply_radio_settings(self, params: dict[str, Any], applied: dict[str, Any], mc: Any) -> None:
        """Aplica potencia TX, frecuencia y parámetros de modulación."""
        if "tx_power" in params or "power" in params:
            hw_board = self._local_config.get("hardware_board")
            raw_p = int(params.get("tx_power", params.get("power", 20)))
            new_p = clamp_tx_power(raw_p, hw_board, self._local_config.get("max_tx_power"))
            self._local_config["tx_power"] = new_p
            applied["tx_power"] = new_p
            if mc and hasattr(mc, "commands") and hasattr(mc.commands, "set_tx_power"):
                try:
                    res = mc.commands.set_tx_power(new_p)
                    if asyncio.iscoroutine(res):
                        await asyncio.wait_for(res, timeout=2.0)
                except Exception as e:
                    logging.warning(f"Aviso actualizando potencia TX: {e}")

        if "frequency" in params or "radio_freq" in params:
            try:
                new_f = float(params.get("frequency", params.get("radio_freq", 915.0)))
                self._local_config["frequency"] = new_f
                applied["frequency"] = new_f
            except (ValueError, TypeError):
                pass

        if "repeat" in params or "repeat_enabled" in params:
            rep = bool(params.get("repeat", params.get("repeat_enabled", False)))
            self._local_config["repeat"] = rep
            applied["repeat"] = rep

    def _apply_timing_settings(self, params: dict[str, Any], applied: dict[str, Any], mc: Any) -> None:
        """Aplica intervalos de baliza (advert) y telemetría."""
        if "beacon_interval" in params or "advert_interval" in params:
            try:
                adv_i = int(params.get("beacon_interval", params.get("advert_interval", 300)))
                self._local_config["beacon_interval"] = adv_i
                applied["beacon_interval"] = adv_i
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
        keys = ["telemetry_mode_base", "telemetry_mode_loc", "telemetry_mode_env", "multi_acks", "adv_loc_policy", "manual_add_contacts"]
        need_update = any(k in params for k in keys)

        if need_update:
            for k in keys:
                if k in params:
                    self._local_config[k] = params[k]
                    applied[k] = params[k]

            if mc and hasattr(mc, "commands") and hasattr(mc.commands, "set_other_params_from_infos"):
                infos = {}
                if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                    infos = mc.self_info.copy()
                else:
                    infos = {k: self._local_config.get(k, 0) for k in keys}

                for k in keys:
                    if k in params:
                        infos[k] = params[k]

                try:
                    res = mc.commands.set_other_params_from_infos(infos)
                    if asyncio.iscoroutine(res):
                        import asyncio
                        await asyncio.wait_for(res, timeout=2.0)
                except Exception as e:
                    import logging
                    logging.warning(f"Aviso actualizando other params: {e}")
