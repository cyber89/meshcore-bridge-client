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
from src.admin import (
    CliCommandExecutor,
    LocalConfigExecutor,
    RemoteRepeaterRequest,
    RepeaterAdminExecutor,
    TracerouteExecutor,
    WaiterRegistry,
)
from src.contact_manager import (
    NodeRegistry,
)
from src.mqtt_client import AsyncBridgeMQTTClient
from src.repeater_manager import RepeaterManager
from src.target_resolver import TargetResolver


def _extract_payload_dict(data: Any) -> dict[str, Any]:
    """Extrae un diccionario de datos tanto de objetos Event (SDK oficial) como de dicts nativos."""
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if hasattr(data, "payload") and isinstance(data.payload, dict):
        return data.payload
    return {}


@dataclass(slots=True)
class AdminContext:
    """Dependencias para ejecutar comandos de administración sobre radio y repetidores."""

    mc_provider: Callable[[], Any]
    node_registry: NodeRegistry
    repeater_manager: RepeaterManager
    mqtt: AsyncBridgeMQTTClient
    execute_tx: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    web_server: Any = None
    serial_adapter: Any = None
    last_rx_rssi: int | None = None
    last_rx_snr: float | None = None
    rate_limiter: Any = None
    counters: Any = None
    start_time: float = 0.0


class AdminCommandHandler:
    """Ejecuta comandos de administración sobre la radio local o repetidores remotos."""

    def __init__(self, ctx: AdminContext) -> None:
        self._ctx = ctx
        self._init_time = time.time()
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
            "repeat": False,
            "beacon_interval": 300,
            "telemetry_interval": 60,
        }
        self._local_config_executor = LocalConfigExecutor(
            self._ctx, self._local_config, self._init_time, self._publish_safe
        )
        self._traceroute_executor = TracerouteExecutor(
            self._ctx, self.get_local_config, self._publish_safe
        )
        self._waiters = WaiterRegistry(
            cmd_waiters=self._cmd_waiters,
            ping_waiters=self._ping_waiters,
        )
        self._repeater_executor = RepeaterAdminExecutor(
            self._ctx,
            self._waiters,
            self._publish_safe,
            self._resolve_target,
            self._wait_for_repeater_response,
        )
        self._cli_executor = CliCommandExecutor(
            ctx=self._ctx,
            local_config=self._local_config,
            get_local_config=self.get_local_config,
            publish_safe=self._publish_safe,
            broadcast_advert=self.broadcast_advert,
            handle_set_local_config=self._handle_set_local_config,
            init_time=self._init_time,
        )

    def _publish_safe(self, topic: str, payload: str, qos: int = 1) -> None:
        """Publica de forma segura a MQTT si el cliente está disponible."""
        if self._ctx.mqtt and hasattr(self._ctx.mqtt, "publish_safe"):
            try:
                self._ctx.mqtt.publish_safe(topic, payload, qos=qos)
            except Exception as e:
                logging.debug(f"Error publicando en MQTT ({topic}): {e}")

    def get_local_config(self) -> dict[str, Any]:
        """Devuelve la configuración consolidada del nodo local y su telemetría."""
        return self._local_config_executor.get_local_config()

    async def fetch_device_config(self, force: bool = False) -> dict[str, Any]:
        """Consulta directamente al hardware serial los parámetros de configuración y telemetría."""
        return await self._local_config_executor.fetch_device_config(force=force)

    async def sync_device_clock(self, epoch_ts: int | None = None) -> dict[str, Any]:
        """Sincroniza el reloj RTC de hardware del dispositivo con la hora del host."""
        return await self._local_config_executor.sync_device_clock(epoch_ts=epoch_ts)

    async def clear_device_stats(self) -> dict[str, Any]:
        """Restablece los contadores de estadísticas y airtime en el nodo local."""
        return await self._local_config_executor.clear_device_stats()

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

    async def get_custom_vars(self) -> dict[str, Any]:
        """Obtiene las variables personalizadas del nodo local."""
        return await self._local_config_executor.get_custom_vars()

    async def set_custom_var(self, key: str, val: str) -> dict[str, Any]:
        """Configura una variable personalizada en el transceptor."""
        return await self._local_config_executor.set_custom_var(key, val)

    async def delete_custom_var(self, key: str) -> dict[str, Any]:
        """Elimina una variable personalizada del transceptor."""
        return await self._local_config_executor.delete_custom_var(key)

    async def get_path_hash_mode(self) -> int:
        """Obtiene el modo de path hash del nodo local."""
        return await self._local_config_executor.get_path_hash_mode()

    async def set_path_hash_mode(self, mode: int) -> dict[str, Any]:
        """Configura el modo de path hash."""
        return await self._local_config_executor.set_path_hash_mode(mode)

    async def get_autoadd_config(self) -> dict[str, Any]:
        """Obtiene la configuración de auto-adición de contactos."""
        return await self._local_config_executor.get_autoadd_config()

    async def set_autoadd_config(self, flags: int, max_hops: int | None = None) -> dict[str, Any]:
        """Configura la máscara de auto-adición de contactos."""
        return await self._local_config_executor.set_autoadd_config(flags, max_hops)

    async def get_flood_scope(self) -> dict[str, Any]:
        """Obtiene el ámbito de inundación configurado."""
        return await self._local_config_executor.get_flood_scope()

    async def set_flood_scope(self, scope: str | None) -> dict[str, Any]:
        """Configura o reinicia el ámbito de inundación."""
        return await self._local_config_executor.set_flood_scope(scope)


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
                or (len(k_lower) >= 8 and s_clean.startswith(k_lower))
                or (len(s_clean) >= 8 and k_lower.startswith(s_clean))
                or (bool(tag_clean) and k_lower == tag_clean)
            )
            if is_match:
                waiters = self._ping_waiters.get(k, [])
                while waiters:
                    fut = waiters.pop(0)
                    if not fut.done():
                        fut.set_result(data)
                        matched = True
                        break
                if not waiters:
                    self._ping_waiters.pop(k, None)
                if matched:
                    break
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
                or (len(k_lower) >= 8 and s_clean.startswith(k_lower))
                or (len(s_clean) >= 8 and k_lower.startswith(s_clean))
                or (len(canon_k) >= 8 and canon_sender.startswith(canon_k))
                or (len(canon_sender) >= 8 and canon_k.startswith(canon_sender))
                or (bool(tag_clean) and k_lower == tag_clean)
            )
            if is_match:
                waiters = self._cmd_waiters.get(k, [])
                while waiters:
                    fut = waiters.pop(0)
                    if not fut.done():
                        fut.set_result(data)
                        matched = True
                        break
                if not waiters:
                    self._cmd_waiters.pop(k, None)
                if matched:
                    break
        return matched

    def _resolve_target(self, name_or_key: str, min_hex_len: int = 12) -> Any:
        """Resuelve el identificador de un nodo a su clave de radio."""
        resolver = TargetResolver(
            mc_provider=self._ctx.mc_provider,
            node_registry=self._ctx.node_registry,
        )
        return resolver.resolve(name_or_key, min_hex_len=min_hex_len)

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
                    await asyncio.sleep(0.05)
                except Exception:
                    await asyncio.sleep(0.15)
            else:
                await asyncio.sleep(0.15)
        if fut.done():
            return fut.result()
        return None

    async def handle(self, admin_data: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta comandos de administración sobre la radio o repetidores."""
        raw_cmd = str(admin_data.get("command", admin_data.get("cmd", ""))).strip()
        raw_act = str(admin_data.get("action", "")).strip()
        if raw_act.lower() in ("cmd", "exec", "terminal", "cli", "run") and raw_cmd:
            action = raw_cmd
        elif not raw_act and raw_cmd:
            action = raw_cmd
        else:
            action = raw_act or raw_cmd

        req_id = admin_data.get("request_id", admin_data.get("id"))
        target_node = admin_data.get("target_node", admin_data.get("repeater"))
        password = str(admin_data.get("password", "")).strip()

        res: dict[str, Any] = {"status": "ok", "action": action}
        if req_id is not None:
            res["request_id"] = req_id

        mc = self._ctx.mc_provider()

        # 1. Caso especial: Traceroute Multi-Salto (se ejecuta con o sin target_node)
        if action in ("traceroute", "trace", "trace_route", "send_trace"):
            return await self._handle_traceroute(admin_data, action, target_node, res, mc)

        # 2. Comandos dirigidos a un repetidor remoto (solo si target_node no es la estación local)
        is_local_target = bool(target_node and (self._ctx.node_registry.is_local_key(str(target_node)) or str(target_node).lower() in ("local", "000000000000")))
        if target_node and not is_local_target:
            req = RemoteRepeaterRequest(
                admin_data=admin_data,
                action=action,
                req_id=req_id,
                target_node=target_node,
                password=password,
                res=res,
                mc=mc,
            )
            return await self._handle_remote_repeater(req)

        # 2. Comandos locales sobre el nodo conectado
        if action in ("get_config", "get_local_config"):
            res["config"] = self.get_local_config()
            self._publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
            return res

        if action in ("set_config", "set_local_config"):
            return await self._handle_set_local_config(admin_data, res, mc)

        if action == "list_nodes":
            res["nodes"] = self._ctx.node_registry.list_nodes()
            self._publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
            return res

        if action == "get_custom_vars":
            res["custom_vars"] = await self.get_custom_vars()
            return res

        if action in ("set_custom_vars", "set_custom_var"):
            vars_data = admin_data.get("vars", admin_data.get("custom_vars", {}))
            if not vars_data and "key" in admin_data:
                vars_data = {admin_data["key"]: admin_data.get("value", admin_data.get("val", ""))}
            for k, v in vars_data.items():
                await self.set_custom_var(str(k), str(v))
            res["custom_vars"] = await self.get_custom_vars()
            return res

        if action == "delete_custom_var":
            k_del = str(admin_data.get("key", ""))
            if k_del:
                await self.delete_custom_var(k_del)
            res["custom_vars"] = await self.get_custom_vars()
            return res

        if action == "get_path_hash_mode":
            res["path_hash_mode"] = await self.get_path_hash_mode()
            return res

        if action == "set_path_hash_mode":
            ph_mode = int(admin_data.get("mode", admin_data.get("path_hash_mode", 0)))
            return await self.set_path_hash_mode(ph_mode)

        if action == "get_autoadd_config":
            res["autoadd_config"] = await self.get_autoadd_config()
            return res

        if action == "set_autoadd_config":
            flags = int(admin_data.get("flags", admin_data.get("config", 0)))
            max_h = admin_data.get("max_hops")
            return await self.set_autoadd_config(flags, int(max_h) if max_h is not None else None)

        if action == "get_flood_scope":
            res["flood_scope"] = await self.get_flood_scope()
            return res

        if action == "set_flood_scope":
            f_scope = admin_data.get("scope", admin_data.get("scope_name"))
            return await self.set_flood_scope(str(f_scope) if f_scope else None)

        # 3. Comandos CLI y de Control Directo Local (Formato String Legible)
        return await self._handle_cli_command(action, res, mc)

    # ------------------------------------------------------------------ #
    #  Extracted handlers — reduce handle() nesting & line count          #
    # ------------------------------------------------------------------ #

    async def _handle_traceroute(
        self,
        admin_data: dict[str, Any],
        action: str,
        target_node: Any,
        res: dict[str, Any],
        mc: Any,
    ) -> dict[str, Any]:
        """Ejecuta el trazado de ruta de radio (traceroute multi-hop) mediante TracerouteExecutor."""
        return await self._traceroute_executor.execute(admin_data, action, target_node, res, mc)

    async def _handle_remote_repeater(self, req: RemoteRepeaterRequest) -> dict[str, Any]:
        """Ejecuta comandos de administración remota sobre un repetidor empaquetando en RemoteRepeaterRequest."""
        return await self._repeater_executor.execute(req)

    async def execute_repeater_request(self, req: RemoteRepeaterRequest) -> dict[str, Any]:
        """Ejecuta una solicitud estructurada de comando a repetidor."""
        return await self._repeater_executor.execute(req)

    async def _handle_set_local_config(
        self,
        admin_data: dict[str, Any],
        res: dict[str, Any],
        mc: Any,
    ) -> dict[str, Any]:
        """Aplica configuraciones locales sobre el nodo conectado mediante LocalConfigExecutor."""
        return await self._local_config_executor.set_local_config(admin_data, res, mc)

    async def _handle_cli_command(
        self,
        action: str,
        res: dict[str, Any],
        mc: Any,
    ) -> dict[str, Any]:
        """Ejecuta comandos CLI y de control directo local delegando en CliCommandExecutor."""
        return await self._cli_executor.execute(action, res, mc)

    # ---- CLI Delegators for backward compatibility ---- #

    async def _cli_version(self, res: dict[str, Any], cfg: dict[str, Any], mc: Any) -> dict[str, Any]:
        return await self._cli_executor._cli_version(res, cfg, mc)

    async def _cli_battery(self, res: dict[str, Any], cfg: dict[str, Any], mc: Any) -> dict[str, Any]:
        return await self._cli_executor._cli_battery(res, cfg, mc)

    async def _cli_time(self, res: dict[str, Any], cfg: dict[str, Any], mc: Any) -> dict[str, Any]:
        return await self._cli_executor._cli_time(res, cfg, mc)

    async def _cli_sync_clock(self, res: dict[str, Any], mc: Any) -> dict[str, Any]:
        return await self._cli_executor._cli_sync_clock(res, mc)

    async def _cli_stats_core(self, res: dict[str, Any], cfg: dict[str, Any], mc: Any) -> dict[str, Any]:
        return await self._cli_executor._cli_stats_core(res, cfg, mc)

    def _cli_radio_info(self, cfg: dict[str, Any]) -> str:
        return self._cli_executor._cli_radio_info(cfg)

    def _cli_packets_info(self, cfg: dict[str, Any]) -> str:
        return self._cli_executor._cli_packets_info(cfg)

    def _cli_position_info(self, cfg: dict[str, Any]) -> str:
        return self._cli_executor._cli_position_info(cfg)

    def _cli_owner_info(self, cfg: dict[str, Any]) -> str:
        return self._cli_executor._cli_owner_info(cfg)

    def _cli_neighbors(self, cfg: dict[str, Any], local_pk: str, local_name: str) -> str:
        return self._cli_executor._cli_neighbors(cfg, local_pk, local_name)

    def _cli_nodes_list(self, cfg: dict[str, Any], local_pk: str, local_name: str) -> str:
        return self._cli_executor._cli_nodes_list(cfg, local_pk, local_name)

    def _cli_lqi(self, res: dict[str, Any], cfg: dict[str, Any], local_pk: str) -> dict[str, Any]:
        return self._cli_executor._cli_lqi(res, cfg, local_pk)

    async def _cli_send_advert(self, mc: Any, flood: bool = False) -> None:
        await self._cli_executor._cli_send_advert(mc, flood=flood)

    def _cli_help_text(self) -> str:
        return self._cli_executor._cli_help_text()

    async def _cli_set_param(self, act_clean: str, res: dict[str, Any]) -> dict[str, Any]:
        return await self._cli_executor._cli_set_param(act_clean, res)
