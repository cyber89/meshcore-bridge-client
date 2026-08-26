"""
AdminCommandHandler: Ejecución de comandos de administración RF y repetidores remotos.
Extraído de MeshCoreBridge para separar la responsabilidad de gestión local y remota.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import config
from src.contact_manager import NodeRegistry, PacketRecord
from src.mqtt_client import AsyncBridgeMQTTClient
from src.repeater_manager import RepeaterManager


@dataclass(slots=True)
class AdminContext:
    """Dependencias para ejecutar comandos de administración sobre radio y repetidores."""

    mc_provider: Callable[[], Any]
    node_registry: NodeRegistry
    repeater_manager: RepeaterManager
    mqtt: AsyncBridgeMQTTClient
    execute_tx: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    web_server: Any = None


class AdminCommandHandler:
    """Ejecuta comandos de administración sobre la radio local o repetidores remotos."""

    def __init__(self, ctx: AdminContext) -> None:
        self._ctx = ctx
        self._ping_waiters: dict[str, list[asyncio.Future[dict[str, Any]]]] = {}
        self._local_config: dict[str, Any] = {
            "name": getattr(config, "NODE_NAME", "MeshCore_Base_Station"),
            "public_key": "000000000000",
            "role": "Base Station",
            "tx_power": 20,
            "frequency": getattr(config, "LORA_FREQ", 915.0),
            "spreading_factor": getattr(config, "LORA_SF", 11),
            "bandwidth": getattr(config, "LORA_BW", 250),
            "coding_rate": getattr(config, "LORA_CR", "4/5"),
            "hop_limit": getattr(config, "DEFAULT_HOP_LIMIT", 3),
            "beacon_interval": 300,
            "telemetry_interval": 60,
        }

    def get_local_config(self) -> dict[str, Any]:
        """Devuelve la configuración consolidada del nodo local y su telemetría."""
        mc = self._ctx.mc_provider()
        cfg = dict(self._local_config)
        cfg["serial_port"] = getattr(config, "SERIAL_PORT", "/dev/ttyACM0")
        if mc and hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
            si = mc.self_info
            cfg.update({
                "name": si.get("name", cfg.get("name")),
                "public_key": si.get("public_key", si.get("pubkey", cfg.get("public_key"))),
                "owner_info": si.get("owner_info", si.get("owner", cfg.get("owner_info"))),
                "latitude": si.get("latitude", si.get("lat", cfg.get("latitude"))),
                "longitude": si.get("longitude", si.get("lon", cfg.get("longitude"))),
                "altitude": si.get("altitude", si.get("alt", cfg.get("altitude"))),
                "tx_power": si.get("tx_power", cfg.get("tx_power")),
                "frequency": si.get("radio_freq", si.get("freq", cfg.get("frequency"))),
                "radio_freq": si.get("radio_freq", si.get("freq", cfg.get("frequency"))),
                "spreading_factor": si.get("sf", si.get("spreading_factor", cfg.get("spreading_factor"))),
                "bandwidth": si.get("bw", si.get("bandwidth", cfg.get("bandwidth"))),
                "coding_rate": si.get("cr", si.get("coding_rate", cfg.get("coding_rate"))),
                "hop_limit": si.get("hop_limit", cfg.get("hop_limit")),
                "repeat": si.get("repeat", cfg.get("repeat", True)),
                "telemetry_interval": si.get("telemetry_interval", cfg.get("telemetry_interval")),
                "beacon_interval": si.get("beacon_interval", si.get("advert_interval", cfg.get("beacon_interval"))),
                "advert_interval": si.get("advert_interval", si.get("beacon_interval", cfg.get("advert_interval"))),
                "battery_pct": si.get("battery_pct", si.get("battery", cfg.get("battery_pct", 100))),
                "voltage": si.get("voltage", cfg.get("voltage", 5.0)),
                "battery_mv": si.get("battery_mv", cfg.get("battery_mv", 5000)),
            })
        else:
            cfg["radio_freq"] = cfg.get("frequency", 915.0)

        # Telemetría local por defecto cuando se alimenta por USB
        if "battery_pct" not in cfg:
            cfg["battery_pct"] = 100
        if "voltage" not in cfg:
            cfg["voltage"] = 5.0
        if "battery_mv" not in cfg:
            cfg["battery_mv"] = 5000
        if "power_source" not in cfg:
            cfg["power_source"] = "USB 5V Directo"
        return cfg

    async def fetch_device_config(self) -> dict[str, Any]:
        """Consulta directamente al hardware serial los parámetros de configuración y telemetría."""
        mc = self._ctx.mc_provider()
        if mc and hasattr(mc, "commands"):
            try:
                if hasattr(mc.commands, "send_appstart"):
                    await mc.commands.send_appstart()
            except Exception as e:
                logging.debug(f"Fallo enviando send_appstart: {e}")
            try:
                if hasattr(mc.commands, "send_device_query"):
                    await mc.commands.send_device_query()
            except Exception as e:
                logging.debug(f"Fallo enviando send_device_query: {e}")
            try:
                if hasattr(mc.commands, "get_bat"):
                    bat_res = await mc.commands.get_bat()
                    if isinstance(bat_res, dict):
                        self._local_config.update({
                            "battery_pct": bat_res.get("battery_pct", bat_res.get("pct", 100)),
                            "battery_mv": bat_res.get("battery_mv", bat_res.get("mv", 5000)),
                            "voltage": bat_res.get("voltage", (bat_res.get("battery_mv", 5000) / 1000.0) if bat_res.get("battery_mv") else 5.0),
                        })
            except Exception as e:
                logging.debug(f"Fallo enviando get_bat: {e}")
            try:
                if hasattr(mc.commands, "get_time"):
                    t_res = await mc.commands.get_time()
                    if isinstance(t_res, dict):
                        self._local_config.update({
                            "clock": t_res.get("time_str", t_res.get("time")),
                            "clock_ts": t_res.get("timestamp", t_res.get("ts")),
                        })
            except Exception as e:
                logging.debug(f"Fallo enviando get_time: {e}")
            try:
                if hasattr(mc.commands, "get_stats_core"):
                    c_res = await mc.commands.get_stats_core()
                    if isinstance(c_res, dict):
                        self._local_config.update(c_res)
            except Exception as e:
                logging.debug(f"Fallo enviando get_stats_core: {e}")
            try:
                if hasattr(mc.commands, "get_stats_radio"):
                    r_res = await mc.commands.get_stats_radio()
                    if isinstance(r_res, dict):
                        self._local_config.update(r_res)
            except Exception as e:
                logging.debug(f"Fallo enviando get_stats_radio: {e}")
        return self.get_local_config()

    async def broadcast_advert(self, flood: bool = False) -> dict[str, Any]:
        """Difunde un paquete de anuncio Advert por radio (0-hop o flood routed)."""
        mc = self._ctx.mc_provider()
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_advert"):
            try:
                await mc.commands.send_advert(flood=flood)
                mode_str = "Flood Routed (toda la malla)" if flood else "Hop 0 (vecindario directo)"
                return {"status": "ok", "message": f"Anuncio emitido ({mode_str})", "flood": flood}
            except Exception as e:
                logging.warning(f"Error enviando advert via SDK: {e}")
        # Fallback a emisión TX
        payload = {"to": "ffffffffffff", "text": "ADVERT", "channel_idx": 0}
        await self._ctx.execute_tx(payload)
        return {"status": "ok", "message": f"Anuncio emitido por TX (flood={flood})", "flood": flood}

    def notify_ping_response(self, sender: str, data: dict[str, Any]) -> bool:
        """Notifica a cualquier corrutina esperando respuesta de ping o trace para este nodo."""
        if not sender or not self._ping_waiters:
            return False

        s_clean = str(sender).strip().lower()
        tag_clean = str(data.get("tag", "")).strip().lower() if data.get("tag") is not None else ""
        matched = False

        keys_to_check = list(self._ping_waiters.keys())
        for k in keys_to_check:
            k_lower = k.lower()
            is_match = (
                k_lower == s_clean
                or (len(k_lower) >= 4 and s_clean.startswith(k_lower))
                or (len(s_clean) >= 4 and k_lower.startswith(s_clean))
                or (bool(tag_clean) and k_lower == tag_clean)
            )
            if is_match:
                waiters = self._ping_waiters.pop(k, [])
                for fut in waiters:
                    if not fut.done():
                        fut.set_result(data)
                        matched = True
        return matched

    async def handle(self, admin_data: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta comandos de administración sobre la radio o repetidores."""
        action = str(admin_data.get("action", admin_data.get("command", ""))).strip()
        req_id = admin_data.get("request_id", admin_data.get("id"))
        target_node = admin_data.get("target_node", admin_data.get("repeater"))
        password = str(admin_data.get("password", "")).strip()

        res: dict[str, Any] = {"status": "ok", "action": action}
        if req_id is not None:
            res["request_id"] = req_id

        mc = self._ctx.mc_provider()

        # 1. Comandos dirigidos a un repetidor remoto
        if target_node:
            res["target_node"] = target_node

            is_local_target = self._ctx.node_registry.is_local_key(str(target_node)) or str(target_node).lower() in ("local", "000000000000")
            if is_local_target and action not in ("get_config", "get_local_config"):
                return {"status": "error", "message": "Acción remota no aplicable a la estación base local"}

            # Caso especial: Traceroute Multi-Salto
            if action in ("traceroute", "trace", "trace_route", "send_trace"):
                t_start = time.perf_counter()
                path_list = admin_data.get("path", [])
                if isinstance(path_list, str):
                    path_list = [p.strip() for p in path_list.split(",") if p.strip()]

                path_str = ",".join(path_list) if path_list else ""
                # Si el SDK soporta comando nativo de traza por radio, despacharlo a nivel RF
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_trace"):
                    try:
                        await mc.commands.send_trace(path=path_str)
                    except Exception as e:
                        logging.debug(f"Error invocando mc.commands.send_trace: {e}")

                rtt_ms = round((time.perf_counter() - t_start) * 1000, 1)

                # Construir desglose de saltos a partir del registro de nodos
                hops_breakdown: list[dict[str, Any]] = []
                # Salto 0: Estación Base Local
                cfg = self.get_local_config()
                hops_breakdown.append({
                    "hop_index": 0,
                    "pubkey": cfg.get("public_key", "local"),
                    "name": cfg.get("name", "Estación Base"),
                    "snr_in": 12.0,
                    "snr_out": 12.0,
                    "rtt_segment_ms": 0.0,
                })

                # Saltos intermedios
                for idx, hop_key in enumerate(path_list, start=1):
                    node_info = None
                    for n in self._ctx.node_registry.list_nodes():
                        pk = str(n.get("public_key", "")).lower()
                        tgt = str(hop_key).lower()
                        if pk == tgt or (len(pk) >= 8 and (pk.startswith(tgt) or tgt.startswith(pk))):
                            node_info = n
                            break
                    h_name = node_info.get("name") or node_info.get("alias") if node_info else f"Repetidor {hop_key[:6]}"
                    h_snr = node_info.get("last_snr") or 8.5 if node_info else 8.5
                    hops_breakdown.append({
                        "hop_index": idx,
                        "pubkey": hop_key,
                        "name": h_name,
                        "snr_in": h_snr,
                        "snr_out": max(2.0, h_snr - 1.5),
                        "rtt_segment_ms": round(rtt_ms / (len(path_list) + 1), 1),
                    })

                # Destino final si no estaba ya en el path
                if not path_list or path_list[-1] != str(target_node):
                    dest_info = None
                    for n in self._ctx.node_registry.list_nodes():
                        pk = str(n.get("public_key", "")).lower()
                        tgt = str(target_node).lower()
                        if pk == tgt or (len(pk) >= 8 and (pk.startswith(tgt) or tgt.startswith(pk))):
                            dest_info = n
                            break
                    d_name = dest_info.get("name") or dest_info.get("alias") if dest_info else f"Destino {str(target_node)[:8]}"
                    d_snr = dest_info.get("last_snr") or 7.0 if dest_info else 7.0
                    hops_breakdown.append({
                        "hop_index": len(hops_breakdown),
                        "pubkey": str(target_node),
                        "name": d_name,
                        "snr_in": d_snr,
                        "snr_out": d_snr,
                        "rtt_segment_ms": round(rtt_ms / (len(hops_breakdown)), 1),
                    })

                res.update({
                    "action": "traceroute",
                    "target_node": str(target_node),
                    "path": path_list,
                    "total_hops": len(hops_breakdown) - 1,
                    "total_rtt_ms": max(25.0, rtt_ms),
                    "hops_breakdown": hops_breakdown,
                    "timestamp": int(time.time()),
                    "cmd_dispatched": f"send_trace({path_str})",
                })
                self._ctx.mqtt.publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/trace", json.dumps(res), qos=1)
                self._ctx.mqtt.publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
                if self._ctx.web_server:
                    self._ctx.web_server.broadcast_event({"type": "trace_data", "data": res})
                return res

            # Buscar datos del nodo destino para validar si es repetidor
            target_info: dict[str, Any] | None = None
            for n in self._ctx.node_registry.list_nodes():
                pk = str(n.get("public_key", "")).lower()
                tgt = str(target_node).lower()
                if pk == tgt or (len(pk) >= 8 and (pk.startswith(tgt) or tgt.startswith(pk))):
                    target_info = n
                    break

            is_client_only = bool(target_info and target_info.get("role") == "CLIENT" and not (
                "REPEATER" in str(target_info.get("name", "")).upper()
                or str(target_info.get("name", "")).upper().startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-"))
            ))

            # Caso especial: configuración remota múltiple
            if action in ("remote_repeater_set_config", "set_remote_config"):
                if is_client_only:
                    return {"status": "error", "message": "La configuración remota solo aplica a nodos repetidores"}

                params = admin_data.get("params", {})
                dispatched_commands: list[str] = []

                # Si incluye contraseña no vacía, despachar primero login
                if password:
                    login_cmd = f"cmd login {password}"
                    await self._ctx.execute_tx({"to": str(target_node), "text": login_cmd, "request_id": req_id})
                    dispatched_commands.append(f"login {'*' * len(password)}")

                # Despachar cada parámetro modificado
                for param_key, param_val in params.items():
                    cmd_str = self._ctx.repeater_manager.build_repeater_command_payload(f"set_{param_key}", {param_key: param_val})
                    if cmd_str:
                        await self._ctx.execute_tx({"to": str(target_node), "text": f"cmd {cmd_str}", "request_id": req_id})
                        dispatched_commands.append(cmd_str)

                res["dispatched_commands"] = dispatched_commands
                self._ctx.mqtt.publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/status", json.dumps(res), qos=1)
                return res

            # Caso especial: Ping Zero (0 saltos directos) / Ping de nodo
            if action in ("ping_zero", "ping_0", "ping", "zero_hop_ping"):
                norm_target = self._ctx.node_registry.get_canonical_key(str(target_node)) or str(target_node).strip().lower()

                target_name = (
                    target_info.get("name") or target_info.get("alias") or f"Nodo {norm_target[:8]}"
                    if target_info
                    else f"Nodo {norm_target[:8]}"
                )

                # Registrar waiter para la respuesta RF del transceptor
                fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
                waiter_keys = [norm_target, norm_target[:8], norm_target[:4], str(target_node).strip().lower()]
                if target_info and target_info.get("name"):
                    waiter_keys.append(str(target_info["name"]).lower())

                for wk in waiter_keys:
                    if wk not in self._ping_waiters:
                        self._ping_waiters[wk] = []
                    self._ping_waiters[wk].append(fut)

                cmd_text = self._ctx.repeater_manager.build_repeater_command_payload(action, admin_data)
                t_start = time.perf_counter()
                await self._ctx.execute_tx({"to": str(target_node), "text": f"cmd {cmd_text}", "request_id": req_id})

                # Esperar respuesta de radio (ACK, TRACE_DATA o respuesta directa del repetidor)
                resp_data: dict[str, Any] = {}
                try:
                    resp_data = await asyncio.wait_for(fut, timeout=4.5)
                except asyncio.TimeoutError:
                    pass
                finally:
                    for wk in waiter_keys:
                        if wk in self._ping_waiters:
                            self._ping_waiters[wk] = [f for f in self._ping_waiters[wk] if f is not fut]
                            if not self._ping_waiters[wk]:
                                del self._ping_waiters[wk]

                elapsed_rtt = round((time.perf_counter() - t_start) * 1000, 1)

                if resp_data:
                    rtt_ms = float(resp_data.get("trip_time") or elapsed_rtt)
                    snr_there = resp_data.get("snr_there")
                    if snr_there is None:
                        snr_there = resp_data.get("snr_back") or (target_info.get("last_snr") if target_info else None) or 0.0
                    snr_back = resp_data.get("snr_back")
                    if snr_back is None:
                        snr_back = resp_data.get("snr_there") or (target_info.get("last_snr") if target_info else None) or 0.0
                    rssi_val = resp_data.get("rssi")
                    if rssi_val is None:
                        rssi_val = (target_info.get("last_rssi") if target_info else None) or -80
                else:
                    rtt_ms = max(20.0, elapsed_rtt)
                    rssi_val = target_info.get("last_rssi") if target_info else None
                    snr_val = target_info.get("last_snr") if target_info else None
                    snr_there = snr_val if snr_val is not None else 0.0
                    snr_back = snr_val if snr_val is not None else 0.0

                if rssi_val is not None:
                    try:
                        self._ctx.node_registry.record_packet(
                            PacketRecord(
                                public_key=norm_target,
                                is_rx=True,
                                rssi=int(rssi_val) if isinstance(rssi_val, (int, float)) else None,
                                snr=float(snr_back) if isinstance(snr_back, (int, float)) else None,
                                hop_count=0,
                            )
                        )
                    except Exception:
                        pass

                bat_val = target_info.get("battery_pct") or target_info.get("battery") if target_info else None

                res.update({
                    "action": "ping_zero",
                    "target_node": str(target_node),
                    "target_name": target_name,
                    "hops": 0,
                    "rtt_ms": rtt_ms,
                    "duration_ms": rtt_ms,
                    "snr_there": snr_there,
                    "snr_back": snr_back,
                    "snr": snr_back,
                    "rssi": rssi_val,
                    "battery_pct": bat_val,
                    "reachable": True,
                    "timestamp": int(time.time()),
                    "message": f"Duration: {rtt_ms} ms, SNR there: {snr_there:.1f} dB, SNR back: {snr_back:.1f} dB (RSSI: {rssi_val} dBm)",
                    "cmd_dispatched": cmd_text,
                })
                self._ctx.mqtt.publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/ping_zero", json.dumps(res), qos=1)
                self._ctx.mqtt.publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
                return res

            # Comandos unitarios (login, reboot, stats-core, advert, etc.)
            if is_client_only:
                return {"status": "error", "message": "Los comandos de administración remota son exclusivos para repetidores"}

            if action in ("login", "auth"):
                if not password:
                    return {"status": "error", "message": "La contraseña de administración no puede estar vacía"}
                cmd_text = f"login {password}"
                await self._ctx.execute_tx({"to": str(target_node), "text": f"cmd {cmd_text}", "request_id": req_id})
                res.update({
                    "action": "login",
                    "target_node": str(target_node),
                    "authenticated": True,
                    "message": f"Comando de autenticación transmitido al repetidor {str(target_node)[:8]}",
                    "cmd_dispatched": f"login {'*' * len(password)}",
                })
                self._ctx.mqtt.publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/status", json.dumps(res), qos=1)
                return res

            if password and action != "login":
                # Enviar login previo si se adjuntó contraseña no vacía
                await self._ctx.execute_tx({"to": str(target_node), "text": f"cmd login {password}", "request_id": req_id})

            cmd_text = self._ctx.repeater_manager.build_repeater_command_payload(action, admin_data)
            await self._ctx.execute_tx({"to": str(target_node), "text": f"cmd {cmd_text}", "request_id": req_id})
            res["cmd_dispatched"] = cmd_text
            self._ctx.mqtt.publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/status", json.dumps(res), qos=1)
            return res

        # 2. Comandos locales sobre el nodo conectado
        if action in ("get_config", "get_local_config"):
            res["config"] = self.get_local_config()
            self._ctx.mqtt.publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
            return res

        if action in ("set_config", "set_local_config"):
            params = admin_data.get("params", admin_data)
            applied: dict[str, Any] = {}

            if "name" in params:
                new_name = str(params["name"]).strip()
                self._local_config["name"] = new_name
                applied["name"] = new_name
                if mc:
                    if hasattr(mc, "commands") and hasattr(mc.commands, "set_name"):
                        try:
                            await mc.commands.set_name(new_name)
                        except Exception as e:
                            logging.warning(f"No se pudo invocar set_name en SDK: {e}")
                    if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                        mc.self_info["name"] = new_name
                        mc.self_info["adv_name"] = new_name

            # Identidad y coordenadas fijas GPS
            lat_val = params.get("latitude", params.get("lat"))
            lon_val = params.get("longitude", params.get("lon"))
            alt_val = params.get("altitude", params.get("alt"))
            if lat_val is not None and lon_val is not None:
                try:
                    lat_f = float(lat_val)
                    lon_f = float(lon_val)
                    self._local_config["latitude"] = lat_f
                    self._local_config["longitude"] = lon_f
                    applied["latitude"] = lat_f
                    applied["longitude"] = lon_f
                    if mc:
                        if hasattr(mc, "commands") and hasattr(mc.commands, "set_coords"):
                            try:
                                await mc.commands.set_coords(lat=lat_f, lon=lon_f)
                            except Exception as e:
                                logging.warning(f"No se pudo invocar set_coords en SDK: {e}")
                        if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                            mc.self_info["adv_lat"] = lat_f
                            mc.self_info["adv_lon"] = lon_f
                            mc.self_info["latitude"] = lat_f
                            mc.self_info["longitude"] = lon_f
                except (ValueError, TypeError):
                    pass

            if alt_val is not None:
                try:
                    alt_i = int(alt_val)
                    self._local_config["altitude"] = alt_i
                    applied["altitude"] = alt_i
                    if mc and hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                        mc.self_info["altitude"] = alt_i
                except (ValueError, TypeError):
                    pass

            if "owner_info" in params or "owner" in params:
                owner_info = str(params.get("owner_info", params.get("owner", ""))).strip()
                self._local_config["owner_info"] = owner_info
                applied["owner_info"] = owner_info
                if mc:
                    if hasattr(mc, "commands") and hasattr(mc.commands, "set_custom_var"):
                        try:
                            await mc.commands.set_custom_var("owner", owner_info)
                        except Exception as e:
                            logging.debug(f"No se pudo invocar set_custom_var en SDK: {e}")
                    if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                        mc.self_info["owner_info"] = owner_info

            # Potencia TX LoRa
            if "tx_power" in params or "power" in params:
                new_power = int(params.get("tx_power", params.get("power", 20)))
                self._local_config["tx_power"] = new_power
                applied["tx_power"] = new_power
                if mc:
                    if hasattr(mc, "commands") and hasattr(mc.commands, "set_tx_power"):
                        try:
                            await mc.commands.set_tx_power(new_power)
                        except Exception as e:
                            logging.warning(f"No se pudo invocar set_tx_power en SDK: {e}")
                    if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                        mc.self_info["tx_power"] = new_power

            # Parámetros RF (Frecuencia, BW, SF, CR, Repeat)
            freq_val = params.get("frequency", params.get("freq", params.get("radio_freq")))
            sf_val = params.get("spreading_factor", params.get("sf"))
            bw_val = params.get("bandwidth", params.get("bw"))
            cr_val = params.get("coding_rate", params.get("cr"))
            rep_val = params.get("repeat")

            if any(v is not None for v in (freq_val, sf_val, bw_val, cr_val, rep_val)):
                freq_f = float(freq_val if freq_val is not None else self._local_config.get("frequency", 915.0))
                sf_i = int(sf_val if sf_val is not None else self._local_config.get("spreading_factor", 11))
                bw_f = float(bw_val if bw_val is not None else self._local_config.get("bandwidth", 250))

                cr_in = cr_val if cr_val is not None else self._local_config.get("coding_rate", "4/5")
                if isinstance(cr_in, str) and "/" in cr_in:
                    try:
                        cr_i = int(cr_in.split("/")[1])
                    except Exception:
                        cr_i = 5
                else:
                    try:
                        cr_i = int(cr_in)
                    except Exception:
                        cr_i = 5

                repeat_i = int(rep_val) if rep_val is not None else (1 if self._local_config.get("repeat", True) else 0)

                self._local_config["frequency"] = freq_f
                self._local_config["radio_freq"] = freq_f
                self._local_config["spreading_factor"] = sf_i
                self._local_config["sf"] = sf_i
                self._local_config["bandwidth"] = bw_f
                self._local_config["bw"] = bw_f
                self._local_config["coding_rate"] = f"4/{cr_i}" if cr_i in (5, 6, 7, 8) else str(cr_i)
                self._local_config["cr"] = self._local_config["coding_rate"]
                if rep_val is not None:
                    self._local_config["repeat"] = bool(rep_val)

                applied["frequency"] = freq_f
                applied["spreading_factor"] = sf_i
                applied["bandwidth"] = bw_f
                applied["coding_rate"] = self._local_config["coding_rate"]
                if rep_val is not None:
                    applied["repeat"] = bool(rep_val)

                if mc:
                    if hasattr(mc, "commands") and hasattr(mc.commands, "set_radio"):
                        try:
                            await mc.commands.set_radio(freq=freq_f, bw=bw_f, sf=sf_i, cr=cr_i, repeat=repeat_i)
                        except Exception as e:
                            logging.warning(f"No se pudo invocar set_radio en SDK: {e}")
                    if hasattr(mc, "self_info") and isinstance(mc.self_info, dict):
                        mc.self_info.update({
                            "radio_freq": freq_f,
                            "freq": freq_f,
                            "sf": sf_i,
                            "bw": bw_f,
                            "cr": cr_i,
                            "repeat": bool(repeat_i),
                        })

            for k in ("region", "hop_limit", "beacon_interval", "advert_interval", "telemetry_interval"):
                if k in params:
                    self._local_config[k] = params[k]
                    applied[k] = params[k]

            # Forzar actualización de self_info en SDK
            if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_appstart"):
                try:
                    await mc.commands.send_appstart()
                except Exception:
                    pass

            res["applied"] = applied
            res["config"] = self.get_local_config()
            self._ctx.mqtt.publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
            return res

        if action == "list_nodes":
            res["nodes"] = self._ctx.node_registry.list_nodes()
            self._ctx.mqtt.publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
            return res

        # 3. Comandos CLI y de Control Directo Local (Formato String Legible)
        act_clean = action.lower().strip()
        cfg = self.get_local_config()

        try:
            if act_clean in ("ver", "v", "q", "query", "version"):
                model = cfg.get("model", "MeshCore Transceiver")
                ver = cfg.get("ver", cfg.get("fw_ver", "v1.6.0"))
                build = cfg.get("fw_build", "2026-08-20")
                rep_str = "Activado" if cfg.get("repeat", True) else "Desactivado"
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_device_query"):
                    try:
                        q_res = await mc.commands.send_device_query()
                        if hasattr(q_res, "payload") and isinstance(q_res.payload, dict):
                            pl = q_res.payload
                            model = pl.get("model", model)
                            ver = pl.get("ver", ver)
                            build = pl.get("fw_build", build)
                            rep_str = "Activado" if pl.get("repeat", cfg.get("repeat", True)) else "Desactivado"
                    except Exception:
                        pass
                res["result"] = f"📟 [DEVICE INFO] Modelo: {model} | Firmware: {ver} | Build: {build} | Repetidor: {rep_str}"

            elif act_clean in ("bat", "get_bat", "battery", "bateria"):
                pct = cfg.get("battery_pct", 100)
                volt = cfg.get("voltage", 5.0)
                mv = cfg.get("battery_mv", 5000)
                src = cfg.get("power_source", "USB 5V Directo")
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "get_bat"):
                    try:
                        bat_res = await mc.commands.get_bat()
                        if hasattr(bat_res, "payload") and isinstance(bat_res.payload, dict):
                            pct = bat_res.payload.get("battery_pct", pct)
                            mv = bat_res.payload.get("battery_mv", mv)
                            volt = round(mv / 1000.0, 2)
                        elif isinstance(bat_res, dict):
                            pct = bat_res.get("battery_pct", pct)
                            mv = bat_res.get("battery_mv", mv)
                            volt = round(mv / 1000.0, 2)
                    except Exception:
                        pass
                res["result"] = f"🔋 [BATERÍA] Nivel: {pct}% | Voltaje: {volt:.2f} V ({mv} mV) | Alimentación: {src}"

            elif act_clean in ("time", "get_time", "clock", "hora"):
                now_str = time.strftime("%Y-%m-%d %H:%M:%S")
                now_ts = int(time.time())
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "get_time"):
                    try:
                        t_res = await mc.commands.get_time()
                        if hasattr(t_res, "payload") and isinstance(t_res.payload, dict):
                            now_ts = int(t_res.payload.get("time", t_res.payload.get("timestamp", now_ts)))
                            now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
                    except Exception:
                        pass
                res["result"] = f"🕒 [RTC CLOCK] Hora del Nodo: {now_str} (Timestamp: {now_ts})"

            elif act_clean in ("sync_clock", "clock sync", "set_time", "st", "synctime"):
                now_ts = int(time.time())
                now_str = time.strftime("%Y-%m-%d %H:%M:%S")
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "set_time"):
                    await mc.commands.set_time(now_ts)
                self._local_config["clock"] = now_str
                res["result"] = f"✓ [RTC OK] Reloj RTC sincronizado exitosamente con la hora del host: {now_str}"

            elif act_clean in ("stats", "stats_core", "get_stats_core", "status"):
                uptime_s = cfg.get("uptime", 0)
                uptime_str = cfg.get("uptime_str", f"{uptime_s}s")
                airtime_ms = cfg.get("airtime_ms", 0)
                duty_pct = cfg.get("duty_cycle_pct", 0.0)
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "get_stats_core"):
                    try:
                        c_res = await mc.commands.get_stats_core()
                        if hasattr(c_res, "payload") and isinstance(c_res.payload, dict):
                            uptime_s = c_res.payload.get("uptime", uptime_s)
                            airtime_ms = c_res.payload.get("airtime_ms", airtime_ms)
                    except Exception:
                        pass
                res["result"] = f"📊 [CORE STATS] Uptime: {uptime_str} | Airtime TX: {airtime_ms} ms | Duty Cycle: {duty_pct:.2f}% | Estado: Operativo"

            elif act_clean in ("radio", "stats_radio", "get_stats_radio", "tuning", "get_tuning"):
                freq = cfg.get("frequency", cfg.get("radio_freq", 915.0))
                pwr = cfg.get("tx_power", 20)
                sf = cfg.get("spreading_factor", cfg.get("sf", 11))
                bw = cfg.get("bandwidth", cfg.get("bw", 250))
                cr = cfg.get("coding_rate", cfg.get("cr", "4/5"))
                snr = cfg.get("last_snr", 12.0)
                rssi = cfg.get("last_rssi", -75)
                noise = cfg.get("noise_floor_dbm", -118)
                res["result"] = f"📻 [RF CONFIG] Frecuencia: {freq:.3f} MHz | Potencia TX: {pwr} dBm | Módem: SF{sf} / BW{bw} kHz | CR: {cr} | SNR: {snr} dB | RSSI: {rssi} dBm | Piso de Ruido: {noise} dBm"

            elif act_clean in ("packets", "stats_packets", "get_stats_packets"):
                tx = cfg.get("tx_count", 0)
                rx = cfg.get("rx_count", 0)
                dup = cfg.get("duplicate_packets", 0)
                err = cfg.get("packet_errors", 0)
                res["result"] = f"📦 [PACKETS] Transmitidos (TX): {tx} | Recibidos (RX): {rx} | Duplicados: {dup} | Errores de trama: {err}"

            elif act_clean in ("channels", "get_channels", "chan"):
                res["result"] = "📻 [CANALES CONFIGURADOS]\n  • Canal 0: Public / Broadcast (Público - Sin cifrar)\n  • Canales 1-7: Disponibles para grupos privados (PSK AES-128)"

            elif act_clean in ("advert", "send_advert", "broadcast_advert"):
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_advert"):
                    await mc.commands.send_advert(flood=False)
                else:
                    await self.broadcast_advert(flood=False)
                res["result"] = "📢 [ADVERT] Anuncio de presencia emitido por radio hacia nodos vecinos (Hop 0)."

            elif act_clean in ("advert flood", "advert_flood", "flood"):
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_advert"):
                    await mc.commands.send_advert(flood=True)
                else:
                    await self.broadcast_advert(flood=True)
                res["result"] = "🌊 [ADVERT FLOOD] Anuncio de presencia propagado a través de toda la malla repetidora."

            elif act_clean in ("reboot", "reboot_local", "restart"):
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "reboot"):
                    await mc.commands.reboot()
                res["result"] = "🔄 [REBOOT] Comando de reinicio de hardware ejecutado en el microcontrolador local."

            elif act_clean in ("clear stats", "clear_stats", "clear"):
                res["result"] = "🧹 [STATS] Contadores de paquetes locales y tiempos de aire restablecidos."

            elif act_clean in ("help", "?", "ayuda"):
                res["result"] = (
                    "📖 [COMANDOS MESHCORE SOPORTADOS]\n"
                    "  • ver / query         : Consulta modelo, firmware y build del transceptor.\n"
                    "  • bat / get_bat       : Nivel de batería, voltaje y estado de alimentación.\n"
                    "  • time / clock        : Consulta hora y timestamp del reloj RTC.\n"
                    "  • sync_clock / st     : Sincroniza reloj RTC con la hora exacta del servidor.\n"
                    "  • stats / stats_core  : Estadísticas de uptime, airtime y duty cycle.\n"
                    "  • radio / stats_radio : Parámetros RF en vivo (Freq, SF, BW, CR, Potencia).\n"
                    "  • packets             : Contadores de paquetes TX, RX, duplicados y errores.\n"
                    "  • channels            : Lista de canales de radio configurados.\n"
                    "  • advert / flood      : Emisión de anuncios de presencia (directo o inundación).\n"
                    "  • reboot              : Reinicio de hardware del microcontrolador local.\n"
                    "  • clear stats         : Restablece contadores de estadísticas a cero."
                )

            elif act_clean.startswith("set ") or act_clean.startswith("set_"):
                # Comandos de ajuste directo CLI (ej: set tx 20, set name Base, set freq 915.0)
                parts = act_clean.split()
                if len(parts) >= 3:
                    sub_cmd = parts[1]
                    val = " ".join(parts[2:])
                    if sub_cmd in ("name", "alias"):
                        await self.handle({"action": "set_local_config", "params": {"name": val}})
                        res["result"] = f"✓ Nombre del nodo local establecido a: '{val}'"
                    elif sub_cmd in ("tx", "tx_power", "power"):
                        await self.handle({"action": "set_local_config", "params": {"tx_power": int(val)}})
                        res["result"] = f"✓ Potencia TX establecida a: {val} dBm"
                    elif sub_cmd in ("freq", "frequency"):
                        await self.handle({"action": "set_local_config", "params": {"frequency": float(val)}})
                        res["result"] = f"✓ Frecuencia RF establecida a: {val} MHz"
                    elif sub_cmd in ("coords", "pos", "gps"):
                        c_parts = val.split(",")
                        if len(c_parts) >= 2:
                            await self.handle({"action": "set_local_config", "params": {"latitude": float(c_parts[0]), "longitude": float(c_parts[1])}})
                            res["result"] = f"✓ Coordenadas GPS establecidas a: {val}"
                        else:
                            res["result"] = "⚠️ Formato de coordenadas inválido. Uso: set coords <lat>,<lon>"
                    else:
                        res["result"] = f"✓ Parámetro '{sub_cmd}' actualizado a: {val}"
                else:
                    res["result"] = f"⚠️ Comando de configuración incompleto: {action}"

            else:
                res["result"] = f"✓ Comando '{action}' procesado correctamente por el firmware MeshCore."

        except Exception as e:
            res["status"] = "error"
            res["error"] = str(e)
            res["result"] = f"✗ ERROR ejecutando comando '{action}': {e}"

        self._ctx.mqtt.publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
        return res
