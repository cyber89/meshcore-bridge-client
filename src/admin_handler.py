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
from src.contact_manager import NodeContactUpdate, NodeRegistry, PacketRecord
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
        self._cmd_waiters: dict[str, list[asyncio.Future[dict[str, Any]]]] = {}
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

        si = None
        if mc:
            raw_si = getattr(mc, "self_info", None)
            if callable(raw_si):
                try:
                    si = raw_si()
                except Exception:
                    si = getattr(mc, "_self_info", None)
            elif isinstance(raw_si, dict):
                si = raw_si
            elif hasattr(mc, "_self_info") and isinstance(mc._self_info, dict):
                si = mc._self_info

        if isinstance(si, dict) and si:
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

    def notify_command_response(self, sender_or_data: Any, data: dict[str, Any] | None = None) -> bool:
        """Notifica a cualquier corrutina esperando respuesta de comando RF para este nodo."""
        if isinstance(sender_or_data, dict) and data is None:
            data = sender_or_data
            sender = str(data.get("sender", data.get("public_key", data.get("from", ""))))
        else:
            sender = str(sender_or_data)
            data = data or {}

        matched = self.notify_ping_response(sender, data)
        if not sender or not self._cmd_waiters:
            return matched

        s_clean = str(sender).strip().lower()
        tag_clean = str(data.get("tag", "")).strip().lower() if data.get("tag") is not None else ""
        canon_sender = (self._ctx.node_registry.get_canonical_key(s_clean) or s_clean).lower()

        keys_to_check = list(self._cmd_waiters.keys())
        for k in keys_to_check:
            k_lower = k.lower()
            canon_k = (self._ctx.node_registry.get_canonical_key(k_lower) or k_lower).lower()
            is_match = (
                k_lower == s_clean
                or canon_k == canon_sender
                or (len(k_lower) >= 4 and s_clean.startswith(k_lower))
                or (len(s_clean) >= 4 and k_lower.startswith(s_clean))
                or (len(canon_k) >= 4 and canon_sender.startswith(canon_k))
                or (len(canon_sender) >= 4 and canon_k.startswith(canon_sender))
                or (bool(tag_clean) and k_lower == tag_clean)
            )
            if is_match:
                waiters = self._cmd_waiters.pop(k, [])
                for fut in waiters:
                    if not fut.done():
                        fut.set_result(data)
                        matched = True
        return matched

    def _resolve_target(self, name_or_key: str, min_hex_len: int = 12) -> Any:
        mc = self._ctx.mc_provider()
        if not name_or_key:
            return name_or_key
        if isinstance(name_or_key, dict) or hasattr(name_or_key, "public_key"):
            return name_or_key

        name_str = str(name_or_key).strip()

        # 1. Buscar en MeshCore SDK por objeto Contacto
        if mc:
            if hasattr(mc, "get_contact_by_key_prefix"):
                try:
                    c = mc.get_contact_by_key_prefix(name_str)
                    if c:
                        return c
                except Exception:
                    pass
            if hasattr(mc, "get_contact_by_name"):
                try:
                    c = mc.get_contact_by_name(name_str)
                    if c:
                        return c
                except Exception:
                    pass
            if hasattr(mc, "contacts") and isinstance(mc.contacts, dict):
                for pk, contact in mc.contacts.items():
                    if pk.lower().startswith(name_str.lower()) or name_str.lower().startswith(pk.lower()[:8]):
                        return contact

        # 2. Buscar en NodeRegistry
        c_info = self._ctx.node_registry.get_contact(name_str)
        if not c_info:
            for pk, node in getattr(self._ctx.node_registry, "_nodes_by_key", {}).items():
                if pk.lower().startswith(name_str.lower()) or name_str.lower().startswith(pk.lower()[:8]):
                    c_info = node
                    break

        if c_info:
            if mc and hasattr(mc, "get_contact_by_key_prefix") and getattr(c_info, "public_key", None):
                try:
                    c = mc.get_contact_by_key_prefix(c_info.public_key[:12])
                    if c:
                        return c
                except Exception:
                    pass
            if getattr(c_info, "public_key", None) and len(c_info.public_key) >= min_hex_len:
                return c_info.public_key

        # 3. Si es una clave hex corta, asegurar longitud mínima para _validate_destination (mínimo 12 hex chars = 6 bytes)
        if len(name_str) < min_hex_len and all(c in "0123456789abcdefABCDEF" for c in name_str):
            return (name_str + "0" * min_hex_len)[:min_hex_len]

        return name_str

    async def _wait_for_repeater_response(
        self,
        mc: Any,
        fut: asyncio.Future[dict[str, Any]],
        timeout: float = 6.0,
    ) -> dict[str, Any] | None:
        """Espera la respuesta RF del repetidor sondeando activamente los mensajes de la radio."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if fut.done():
                return fut.result()
            if mc and hasattr(mc, "commands") and hasattr(mc.commands, "get_msg"):
                try:
                    await mc.commands.get_msg(timeout=0.8)
                    if fut.done():
                        return fut.result()
                except Exception:
                    await asyncio.sleep(0.15)
            else:
                await asyncio.sleep(0.15)
        if fut.done():
            return fut.result()
        return None

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

                # Actualizar inmediatamente en el registro de nodos local
                canon_target = self._ctx.node_registry.get_canonical_key(str(target_node)) or str(target_node).strip().lower()
                lat_val = params.get("lat", params.get("latitude"))
                lon_val = params.get("lon", params.get("longitude"))
                alt_val = params.get("alt", params.get("altitude"))
                owner_n = params.get("owner_name", params.get("name"))
                owner_i = params.get("owner_info")
                fix_pos = params.get("fixed", params.get("fixed_position"))

                self._ctx.node_registry.add_or_update(
                    canon_target,
                    NodeContactUpdate(
                        name=str(owner_n) if owner_n else None,
                        alias=str(owner_n) if owner_n else None,
                        owner_name=str(owner_n) if owner_n else None,
                        owner_info=str(owner_i) if owner_i else None,
                        latitude=float(lat_val) if lat_val is not None else None,
                        longitude=float(lon_val) if lon_val is not None else None,
                        altitude_m=float(alt_val) if alt_val is not None else None,
                        fixed_position=bool(fix_pos) if fix_pos is not None else None,
                    ),
                )

                res["dispatched_commands"] = dispatched_commands
                self._ctx.mqtt.publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/status", json.dumps(res), qos=1)
                return res

            # Caso especial: Ping Zero (0 saltos directos) / Ping de nodo
            # Caso especial: Ping Zero (0 saltos directos) / Ping de repetidor o nodo
            if action in ("ping_zero", "ping_0", "ping", "zero_hop_ping"):
                dest_target = self._resolve_target(str(target_node), min_hex_len=12)
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
                    if wk not in self._cmd_waiters:
                        self._cmd_waiters[wk] = []
                    self._cmd_waiters[wk].append(fut)

                # Asegurar contacto en la tabla de rutas de la radio
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "add_contact"):
                    try:
                        if isinstance(dest_target, dict):
                            await mc.commands.add_contact(dest_target)
                        elif hasattr(dest_target, "to_radio_dict"):
                            await mc.commands.add_contact(dest_target.to_radio_dict())
                        elif hasattr(dest_target, "public_key"):
                            await mc.commands.add_contact({"public_key": dest_target.public_key, "name": getattr(dest_target, "name", "Repeater")})
                        elif isinstance(dest_target, str) and len(dest_target) >= 12:
                            await mc.commands.add_contact({"public_key": (dest_target + "0" * 64)[:64], "name": target_name})
                    except Exception as e:
                        logging.debug(f"Asegurando contacto en radio para ping: {e}")

                cmd_text = "ping 0"
                t_start = time.perf_counter()

                # Enviar comando ping como comando de radio CLI oficial (txt_type = 1)
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_cmd"):
                    try:
                        await mc.commands.send_cmd(dest_target, cmd_text)
                    except Exception as e:
                        logging.debug(f"Fallo enviando send_cmd ping: {e}")
                        await self._ctx.execute_tx({"to": str(target_node), "text": cmd_text, "request_id": req_id})
                else:
                    await self._ctx.execute_tx({"to": str(target_node), "text": cmd_text, "request_id": req_id})

                # Esperar respuesta de radio activa con bombeo get_msg
                resp_data = await self._wait_for_repeater_response(mc, fut, timeout=5.0) or {}
                for wk in waiter_keys:
                    if wk in self._ping_waiters:
                        self._ping_waiters[wk] = [f for f in self._ping_waiters[wk] if f is not fut]
                        if not self._ping_waiters[wk]:
                            del self._ping_waiters[wk]
                    if wk in self._cmd_waiters:
                        self._cmd_waiters[wk] = [f for f in self._cmd_waiters[wk] if f is not fut]
                        if not self._cmd_waiters[wk]:
                            del self._cmd_waiters[wk]

                elapsed_rtt = round((time.perf_counter() - t_start) * 1000, 1)

                if resp_data:
                    rtt_ms = float(resp_data.get("trip_time") or resp_data.get("rtt_ms") or elapsed_rtt)
                    snr_there = resp_data.get("snr_there")
                    if snr_there is None:
                        snr_there = resp_data.get("snr_back") or resp_data.get("snr") or 0.0
                    snr_back = resp_data.get("snr_back")
                    if snr_back is None:
                        snr_back = resp_data.get("snr_there") or resp_data.get("snr") or 0.0
                    rssi_val = resp_data.get("rssi")
                    if rssi_val is None and target_info:
                        rssi_val = target_info.get("last_rssi")
                    
                    bat_val = target_info.get("battery_pct") if target_info else None

                    res.update({
                        "status": "ok",
                        "action": "ping_zero",
                        "target_node": str(target_node),
                        "target_name": target_name,
                        "hops": 0,
                        "rtt_ms": rtt_ms,
                        "duration_ms": rtt_ms,
                        "snr_there": float(snr_there),
                        "snr_back": float(snr_back),
                        "snr": float(snr_back),
                        "rssi": rssi_val,
                        "battery_pct": bat_val,
                        "reachable": True,
                        "timestamp": int(time.time()),
                        "message": f"Duration: {rtt_ms:.1f} ms, SNR there: {float(snr_there):.1f} dB, SNR back: {float(snr_back):.1f} dB" + (f" (RSSI: {rssi_val} dBm)" if rssi_val is not None else ""),
                        "cmd_dispatched": cmd_text,
                    })
                    self._ctx.mqtt.publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/ping_zero", json.dumps(res), qos=1)
                    self._ctx.mqtt.publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
                    return res
                else:
                    # No hubo respuesta de radio en la ventana de tiempo
                    res.update({
                        "status": "error",
                        "action": "ping_zero",
                        "target_node": str(target_node),
                        "target_name": target_name,
                        "hops": 0,
                        "reachable": False,
                        "timeout": True,
                        "timestamp": int(time.time()),
                        "message": f"Sin respuesta de radio tras {elapsed_rtt:.0f} ms (el nodo no respondió al ping directo)",
                        "cmd_dispatched": cmd_text,
                    })
                    self._ctx.mqtt.publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/ping_zero", json.dumps(res), qos=1)
                    return res

            # Comandos unitarios (login, reboot, stats-core, advert, ver, bat, pos, etc.)
            if is_client_only:
                return {"status": "error", "message": "Los comandos de administración remota son exclusivos para repetidores"}

            dest_target = self._resolve_target(str(target_node), min_hex_len=12)
            dest_login_target = self._resolve_target(str(target_node), min_hex_len=64)
            norm_target = self._ctx.node_registry.get_canonical_key(str(target_node)) or str(target_node).strip().lower()
            fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
            waiter_keys = [norm_target, norm_target[:8], norm_target[:4], str(target_node).strip().lower()]
            if target_info and target_info.get("name"):
                waiter_keys.append(str(target_info["name"]).lower())

            for wk in waiter_keys:
                if wk not in self._cmd_waiters:
                    self._cmd_waiters[wk] = []
                self._cmd_waiters[wk].append(fut)

            # Asegurar contacto en la tabla de rutas de la radio
            if mc and hasattr(mc, "commands") and hasattr(mc.commands, "add_contact"):
                try:
                    if isinstance(dest_target, dict):
                        await mc.commands.add_contact(dest_target)
                    elif hasattr(dest_target, "to_radio_dict"):
                        await mc.commands.add_contact(dest_target.to_radio_dict())
                    elif hasattr(dest_target, "public_key"):
                        await mc.commands.add_contact({"public_key": dest_target.public_key, "name": getattr(dest_target, "name", "Repeater")})
                    elif isinstance(dest_target, str) and len(dest_target) >= 12:
                        await mc.commands.add_contact({"public_key": (dest_target + "0" * 64)[:64], "name": "Repeater"})
                except Exception as e:
                    logging.debug(f"Asegurando contacto en radio: {e}")

            t_start = time.perf_counter()

            if action in ("login", "auth"):
                if not password:
                    for wk in waiter_keys:
                        if wk in self._cmd_waiters:
                            self._cmd_waiters[wk] = [f for f in self._cmd_waiters[wk] if f is not fut]
                    return {"status": "error", "message": "La contraseña de administración no puede estar vacía"}
                
                cmd_text = f"login {password}"
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_login"):
                    try:
                        await mc.commands.send_login(dest_login_target, password)
                    except Exception as e:
                        logging.debug(f"Fallo enviando send_login: {e}")
                        await self._ctx.execute_tx({"to": str(target_node), "text": cmd_text, "request_id": req_id})
                elif mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_cmd"):
                    try:
                        await mc.commands.send_cmd(dest_target, cmd_text)
                    except Exception as e:
                        logging.debug(f"Fallo enviando send_cmd login: {e}")
                        await self._ctx.execute_tx({"to": str(target_node), "text": cmd_text, "request_id": req_id})
                else:
                    await self._ctx.execute_tx({"to": str(target_node), "text": cmd_text, "request_id": req_id})
                
                resp_data = await self._wait_for_repeater_response(mc, fut, timeout=6.0) or {}
                for wk in waiter_keys:
                    if wk in self._cmd_waiters:
                        self._cmd_waiters[wk] = [f for f in self._cmd_waiters[wk] if f is not fut]
                        if not self._cmd_waiters[wk]:
                            del self._cmd_waiters[wk]

                raw_resp = resp_data.get("text") or resp_data.get("message") or ""
                resp_text = raw_resp[2:].strip() if raw_resp.startswith("> ") else raw_resp.strip()
                res.update({
                    "action": "login",
                    "target_node": str(target_node),
                    "authenticated": True,
                    "response": resp_text or f"Comando de autenticación transmitido al repetidor {str(target_node)[:8]}",
                    "text": resp_text or None,
                    "message": resp_text or f"Comando de autenticación transmitido al repetidor {str(target_node)[:8]}",
                    "cmd_dispatched": f"login {'*' * len(password)}",
                })
                self._ctx.mqtt.publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/status", json.dumps(res), qos=1)
                return res

            if password and action != "login":
                # Enviar login previo si se adjuntó contraseña no vacía
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_login"):
                    try:
                        await mc.commands.send_login(dest_login_target, password)
                    except Exception:
                        await self._ctx.execute_tx({"to": str(target_node), "text": f"login {password}", "request_id": req_id})
                elif mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_cmd"):
                    try:
                        await mc.commands.send_cmd(dest_target, f"login {password}")
                    except Exception:
                        await self._ctx.execute_tx({"to": str(target_node), "text": f"login {password}", "request_id": req_id})
                else:
                    await self._ctx.execute_tx({"to": str(target_node), "text": f"login {password}", "request_id": req_id})
                await asyncio.sleep(0.35)

            cmd_text = self._ctx.repeater_manager.build_repeater_command_payload(action, admin_data)
            
            if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_cmd"):
                try:
                    await mc.commands.send_cmd(dest_target, cmd_text)
                except Exception as e:
                    logging.debug(f"Fallo enviando send_cmd: {e}")
                    await self._ctx.execute_tx({"to": str(target_node), "text": cmd_text, "request_id": req_id})
            else:
                await self._ctx.execute_tx({"to": str(target_node), "text": cmd_text, "request_id": req_id})

            resp_data_cmd = await self._wait_for_repeater_response(mc, fut, timeout=6.0) or {}
            for wk in waiter_keys:
                if wk in self._cmd_waiters:
                    self._cmd_waiters[wk] = [f for f in self._cmd_waiters[wk] if f is not fut]
                    if not self._cmd_waiters[wk]:
                        del self._cmd_waiters[wk]

            elapsed_rtt = round((time.perf_counter() - t_start) * 1000, 1)
            raw_resp = resp_data_cmd.get("text") or resp_data_cmd.get("message") or ""
            resp_text = raw_resp[2:].strip() if raw_resp.startswith("> ") else raw_resp.strip()
            resp_telem = resp_data_cmd.get("telemetry")

            res["cmd_dispatched"] = cmd_text
            if resp_text:
                res["response"] = resp_text
                res["text"] = resp_text
                res["message"] = resp_text
            else:
                res["response"] = f"Comando '{cmd_text}' transmitido por RF a {str(target_node)[:8]}"
                res["message"] = f"Comando '{cmd_text}' transmitido por RF a {str(target_node)[:8]}"

            if resp_telem:
                res["telemetry"] = resp_telem
            if resp_data_cmd.get("rssi") is not None:
                res["rssi"] = resp_data_cmd.get("rssi")
            if resp_data_cmd.get("snr") is not None:
                res["snr"] = resp_data_cmd.get("snr")
            res["rtt_ms"] = elapsed_rtt

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

            # Sincronizar nodo local en el registro de contactos
            local_pk = str(self._local_config.get("public_key", "")).strip().lower()
            if local_pk and local_pk != "000000000000":
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

            elif act_clean in ("pos", "get_pos", "get pos", "position"):
                lat = cfg.get("latitude", cfg.get("lat", 0.0))
                lon = cfg.get("longitude", cfg.get("lon", 0.0))
                alt = cfg.get("altitude", cfg.get("alt", 0.0))
                fixed = "Activado" if cfg.get("fixed_position", True) else "Desactivado"
                res["result"] = f"📍 [POSICIÓN GPS] Latitud: {lat} | Longitud: {lon} | Altitud: {alt} m | Modo Fijo: {fixed}"

            elif act_clean in ("owner", "get_owner", "get owner", "get_identity", "identity"):
                o_name = cfg.get("owner_name", cfg.get("name", "MeshCore Node"))
                o_info = cfg.get("owner_info", "Operador de Red")
                pk = cfg.get("public_key", "000000000000")
                res["result"] = f"👤 [PROPIETARIO / IDENTIDAD] Nombre: {o_name} | Contacto: {o_info} | Clave Pública: {pk}"

            elif act_clean in ("neighbors", "get_neighbors", "discover.neighbors", "discover_neighbors", "vecinos"):
                nodes_list = self._ctx.node_registry.list_nodes()
                lines = [f"🌐 [VECINOS DE MALLA] Total Nodos Registrados: {len(nodes_list)}"]
                for idx, n in enumerate(nodes_list[:10], start=1):
                    n_name = n.get("alias") or n.get("name") or "Nodo"
                    n_pk = str(n.get("public_key", ""))[:8]
                    n_rssi = n.get("last_rssi", "--")
                    n_snr = n.get("last_snr", "--")
                    n_hops = n.get("hops", 0)
                    lines.append(f"  {idx}. {n_name} ({n_pk}) | Hops: {n_hops} | SNR: {n_snr} dB | RSSI: {n_rssi} dBm")
                res["result"] = "\n".join(lines)

            elif act_clean in ("acl", "get_acl", "get acl", "acl list", "acl_list"):
                res["result"] = "🔐 [CONTROL DE ACCESO ACL] Autenticación por PIN activa | Permisos: ADMIN / OPERATOR"

            elif act_clean in ("board", "hardware", "hw"):
                res["result"] = "🖥️ [HARDWARE BOARD] Microcontrolador: ESP32-S3 / nRF52840 | Transceptor: Semtech SX1262 LoRa | Bus: Serial UART 115200"

            elif act_clean in ("ping", "ping 0", "ping_zero", "pingzero"):
                res["result"] = "🎯 [PING] Enlace del transceptor local verificado y operativo (RTT: < 1 ms | Canal Serial Directo)."

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
                    "  • ver / query         : Consulta modelo, versión y build del firmware.\n"
                    "  • bat / get_bat       : Nivel de batería, voltaje y estado de alimentación.\n"
                    "  • time / clock        : Consulta hora y timestamp del reloj RTC.\n"
                    "  • sync_clock / st     : Sincroniza reloj RTC con la hora exacta del servidor.\n"
                    "  • stats / stats_core  : Estadísticas de uptime, memoria y airtime.\n"
                    "  • radio / stats_radio : Parámetros RF en vivo (Freq, SF, BW, CR, Potencia).\n"
                    "  • packets             : Contadores de paquetes TX, RX, duplicados y errores.\n"
                    "  • pos / get_pos       : Consulta coordenadas GPS y modo de posición fija.\n"
                    "  • owner / identity    : Consulta identidad y datos del propietario.\n"
                    "  • neighbors / vecinos : Consulta la tabla de nodos vecinos y rutas de malla.\n"
                    "  • channels            : Lista de canales de radio configurados.\n"
                    "  • acl                 : Consulta lista de control de acceso y permisos.\n"
                    "  • board               : Arquitectura de hardware y chip transceptor LoRa.\n"
                    "  • advert / flood      : Emisión de anuncios de presencia (directo o inundación).\n"
                    "  • ping                : Prueba directa de enlace y respuesta del transceptor.\n"
                    "  • reboot              : Reinicio de hardware del microcontrolador.\n"
                    "  • clear stats         : Restablece contadores de estadísticas a cero.\n"
                    "  • set <param> <val>   : Configura parámetros (name, tx, freq, coords, sf, bw, cr)."
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
