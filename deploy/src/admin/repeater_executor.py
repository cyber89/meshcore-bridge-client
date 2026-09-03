"""
RepeaterAdminExecutor: Ejecución especializada de comandos remotos a repetidores de la malla.
Descompone el método monolítico anterior en ejecutores específicos:
- Configuración remota en lote (_execute_batch_config)
- Ping 0 RF directo (_execute_ping_zero)
- Autenticación administrativa remota (_execute_auth_command)
- Comandos unitarios RF con cooldown de Airtime (_execute_unit_command)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import config
from src.contact_manager import (
    NodeContactUpdate,
    PacketRecord,
    is_valid_node_key,
)

if TYPE_CHECKING:
    from src.admin_handler import AdminContext


@dataclass(slots=True)
class RemoteRepeaterRequest:
    """Objeto de parámetros para ejecución de comandos remotos sobre repetidores."""

    admin_data: dict[str, Any]
    action: str
    req_id: Any
    target_node: Any
    password: str = ""
    res: dict[str, Any] | None = None
    mc: Any = None


@dataclass(slots=True)
class WaiterRegistry:
    """Registro compartido de futuros pendientes para respuestas RF de radio."""

    cmd_waiters: dict[str, list[asyncio.Future[dict[str, Any]]]]
    ping_waiters: dict[str, list[asyncio.Future[dict[str, Any]]]]


@dataclass(slots=True)
class RfExecutionContext:
    """Contexto estructurado para ejecución de comandos RF individuales o login."""

    req: RemoteRepeaterRequest
    dest_target: Any
    dest_login_target: Any
    waiter_keys: list[str]
    fut: asyncio.Future[dict[str, Any]]
    res: dict[str, Any]


@dataclass(slots=True)
class PingZeroOutcome:
    """Parámetros para procesar el resultado de un ping zero."""

    norm_target: str
    target_name: str
    resp_data: dict[str, Any]
    elapsed_rtt: float
    cmd_text: str


class RepeaterAdminExecutor:
    """Ejecutor de comandos de administración remota sobre nodos repetidores."""

    def __init__(
        self,
        ctx: AdminContext,
        waiters: WaiterRegistry,
        publish_safe: Callable[[str, str, int], None],
        resolve_target: Callable[[str, int], Any],
        wait_for_repeater_response: Callable[..., Awaitable[dict[str, Any] | None]],
    ) -> None:
        self._ctx = ctx
        self._waiters = waiters
        self._publish_safe = publish_safe
        self._resolve_target = resolve_target
        self._wait_for_repeater_response = wait_for_repeater_response

    async def execute(self, req: RemoteRepeaterRequest) -> dict[str, Any]:
        """Punto de entrada principal para despachar acciones sobre un repetidor remoto."""
        res = req.res if req.res is not None else {}
        res["target_node"] = req.target_node
        logging.info(
            f"[TX-ADMIN] De: Estación Base Local -> Para: {req.target_node} | "
            f"Acción: '{req.action}' | ReqID: {req.req_id}"
        )

        target_info = self._collect_target_info(str(req.target_node))
        is_client_only = bool(
            target_info
            and target_info.get("role") == "CLIENT"
            and not (
                "REPEATER" in str(target_info.get("name", "")).upper()
                or str(target_info.get("name", "")).upper().startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-"))
            )
        )

        if req.action in ("remote_repeater_set_config", "set_remote_config"):
            if is_client_only:
                return {"status": "error", "message": "La configuración remota solo aplica a nodos repetidores"}
            return await self._execute_batch_config(req, res)

        if req.action in ("ping_zero", "ping_0", "ping", "zero_hop_ping"):
            return await self._execute_ping_zero(req, target_info, res)

        if is_client_only:
            return {"status": "error", "message": "Los comandos de administración remota son exclusivos para repetidores"}

        return await self._dispatch_rf_command(req, target_info, res)

    def _collect_target_info(self, target_node: str) -> dict[str, Any] | None:
        """Obtiene la información del nodo destino desde el NodeRegistry."""
        tgt = target_node.lower()
        for n in self._ctx.node_registry.list_nodes():
            pk = str(n.get("public_key", "")).lower()
            if pk == tgt or (len(pk) >= 8 and (pk.startswith(tgt) or tgt.startswith(pk))):
                return n
        return None

    async def _execute_batch_config(self, req: RemoteRepeaterRequest, res: dict[str, Any]) -> dict[str, Any]:
        """Aplica múltiples parámetros de configuración remota en el repetidor."""
        params = req.admin_data.get("params", {})
        dispatched: list[str] = []

        if req.password:
            login_cmd = f"cmd login {req.password}"
            await self._ctx.execute_tx({"to": str(req.target_node), "text": login_cmd, "request_id": req.req_id})
            dispatched.append(f"login {'*' * len(req.password)}")

        for p_key, p_val in params.items():
            cmd_str = self._ctx.repeater_manager.build_repeater_command_payload(f"set_{p_key}", {p_key: p_val})
            if cmd_str:
                await self._ctx.execute_tx({"to": str(req.target_node), "text": f"cmd {cmd_str}", "request_id": req.req_id})
                dispatched.append(cmd_str)

        self._update_local_registry_from_params(str(req.target_node), params)
        res["dispatched_commands"] = dispatched
        self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{req.target_node}/status", json.dumps(res), 1)
        return res

    def _update_local_registry_from_params(self, target_node: str, params: dict[str, Any]) -> None:
        """Actualiza inmediatamente los parámetros del repetidor en el registro local."""
        canon = self._ctx.node_registry.get_canonical_key(target_node) or target_node.strip().lower()
        owner_n = params.get("owner_name", params.get("name"))
        lat_val = params.get("lat", params.get("latitude"))
        lon_val = params.get("lon", params.get("longitude"))
        alt_val = params.get("alt", params.get("altitude"))
        tx_pwr = params.get("tx_power", params.get("power"))

        freq_raw = params.get("freq", params.get("frequency"))
        hop_raw = params.get("hop_limit", params.get("hops"))
        rep_raw = params.get("repeat", params.get("repeat_enabled"))
        adv_raw = params.get("beacon_interval", params.get("advert_interval"))
        self._ctx.node_registry.add_or_update(
            canon,
            NodeContactUpdate(
                name=str(owner_n) if owner_n else None,
                alias=str(owner_n) if owner_n else None,
                owner_name=str(owner_n) if owner_n else None,
                owner_info=str(params.get("owner_info")) if params.get("owner_info") else None,
                latitude=float(lat_val) if lat_val is not None else None,
                longitude=float(lon_val) if lon_val is not None else None,
                altitude_m=float(alt_val) if alt_val is not None else None,
                frequency=float(freq_raw) if freq_raw is not None else None,
                tx_power=int(tx_pwr) if tx_pwr is not None else None,
                hop_limit=int(hop_raw) if hop_raw is not None else None,
                repeat_enabled=bool(rep_raw) if rep_raw is not None else None,
                advert_interval=int(adv_raw) if adv_raw is not None else None,
            ),
        )

    async def _execute_ping_zero(
        self, req: RemoteRepeaterRequest, target_info: dict[str, Any] | None, res: dict[str, Any]
    ) -> dict[str, Any]:
        """Ejecuta un ping directo de 0 saltos y calcula RTT y métricas de señal."""
        dest_target = self._resolve_target(str(req.target_node), 12)
        norm_target = self._ctx.node_registry.get_canonical_key(str(req.target_node)) or str(req.target_node).strip().lower()
        target_name = str((target_info.get("name") or target_info.get("alias")) if target_info else f"Nodo {norm_target[:8]}")

        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        waiter_keys = [norm_target, norm_target[:8], norm_target[:4], str(req.target_node).strip().lower()]
        if target_info and target_info.get("name"):
            waiter_keys.append(str(target_info["name"]).lower())

        self._register_waiters(waiter_keys, fut, include_ping=True)
        await self._ensure_radio_contact(req.mc, dest_target, target_name)

        t_start = time.perf_counter()
        cmd_text = "ping 0"
        await self._send_rf_command(req.mc, dest_target, cmd_text, str(req.target_node), req.req_id)

        resp_data = await self._wait_for_repeater_response(req.mc, fut, timeout=5.0) or {}
        self._unregister_waiters(waiter_keys, fut, include_ping=True)

        elapsed_rtt = round((time.perf_counter() - t_start) * 1000, 1)
        if resp_data:
            outcome = PingZeroOutcome(norm_target, target_name, resp_data, elapsed_rtt, cmd_text)
            return self._build_ping_zero_success(outcome, res)
        return self._build_ping_zero_timeout(str(req.target_node), target_name, elapsed_rtt, res, cmd_text)

    def _build_ping_zero_success(self, outcome: PingZeroOutcome, res: dict[str, Any]) -> dict[str, Any]:
        """Construye la respuesta de ping exitoso y actualiza telemetría."""
        rtt_ms = float(outcome.resp_data.get("trip_time") or outcome.resp_data.get("rtt_ms") or outcome.elapsed_rtt)
        snr_back = float(outcome.resp_data.get("snr_back") or outcome.resp_data.get("snr") or 0.0)
        snr_there = float(outcome.resp_data.get("snr_there") or snr_back)
        rssi_val = outcome.resp_data.get("rssi") or outcome.resp_data.get("RSSI")

        if is_valid_node_key(outcome.norm_target) and not self._ctx.node_registry.is_local_key(outcome.norm_target):
            self._ctx.node_registry.record_packet(
                PacketRecord(public_key=outcome.norm_target, is_rx=True, rssi=rssi_val, snr=snr_back, hop_count=0)
            )
            self._ctx.node_registry.add_or_update(outcome.norm_target, NodeContactUpdate(last_rssi=rssi_val, last_snr=snr_back, hops=0))

        res.update({
            "status": "ok",
            "action": "ping_zero",
            "target_node": outcome.norm_target,
            "target_name": outcome.target_name,
            "hops": 0,
            "rtt_ms": rtt_ms,
            "duration_ms": rtt_ms,
            "snr_there": snr_there,
            "snr_back": snr_back,
            "snr": snr_back,
            "rssi": rssi_val,
            "reachable": True,
            "timestamp": int(time.time()),
            "message": f"Duration: {rtt_ms:.1f} ms, SNR there: {snr_there:.1f} dB, SNR back: {snr_back:.1f} dB",
            "cmd_dispatched": outcome.cmd_text,
        })
        self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{outcome.norm_target}/ping_zero", json.dumps(res), 1)
        return res

    def _build_ping_zero_timeout(
        self, target_node: str, target_name: str, elapsed_rtt: float, res: dict[str, Any], cmd_text: str
    ) -> dict[str, Any]:
        """Construye la respuesta de timeout para ping zero."""
        res.update({
            "status": "error",
            "action": "ping_zero",
            "target_node": target_node,
            "target_name": target_name,
            "hops": 0,
            "reachable": False,
            "timeout": True,
            "timestamp": int(time.time()),
            "message": f"Sin respuesta de radio tras {elapsed_rtt:.0f} ms",
            "cmd_dispatched": cmd_text,
        })
        self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/ping_zero", json.dumps(res), 1)
        return res

    async def _dispatch_rf_command(
        self, req: RemoteRepeaterRequest, target_info: dict[str, Any] | None, res: dict[str, Any]
    ) -> dict[str, Any]:
        """Enruta comandos administrativos individuales o autenticación."""
        dest_target = self._resolve_target(str(req.target_node), 12)
        dest_login_target = self._resolve_target(str(req.target_node), 64)
        norm_target = self._ctx.node_registry.get_canonical_key(str(req.target_node)) or str(req.target_node).strip().lower()

        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        waiter_keys = [norm_target, norm_target[:8], norm_target[:4], str(req.target_node).strip().lower()]
        if target_info and target_info.get("name"):
            waiter_keys.append(str(target_info["name"]).lower())

        self._register_waiters(waiter_keys, fut, include_ping=False)
        await self._ensure_radio_contact(req.mc, dest_target, "Repeater")

        rf_ctx = RfExecutionContext(
            req=req,
            dest_target=dest_target,
            dest_login_target=dest_login_target,
            waiter_keys=waiter_keys,
            fut=fut,
            res=res,
        )

        if req.action in ("login", "auth"):
            return await self._execute_auth_command(rf_ctx)

        if req.action in ("get_stats_core", "get_stats_radio", "get_stats_packets"):
            # Expose via binary/anon req logic if supported by SDK, otherwise fallback to unit command
            return await self._execute_unit_command(rf_ctx)

        return await self._execute_unit_command(rf_ctx)

    async def _execute_auth_command(self, rf_ctx: RfExecutionContext) -> dict[str, Any]:
        """Ejecuta inicio de sesión remoto en el repetidor."""
        req = rf_ctx.req
        if not req.password:
            self._unregister_waiters(rf_ctx.waiter_keys, rf_ctx.fut, include_ping=False)
            return {"status": "error", "message": "La contraseña de administración no puede estar vacía"}

        cmd_text = f"login {req.password}"
        login_success = False
        resp_text = ""
        error_msg: str | None = None

        if req.mc and hasattr(req.mc, "commands") and hasattr(req.mc.commands, "send_login_sync"):
            try:
                login_ev = await req.mc.commands.send_login_sync(rf_ctx.dest_login_target, req.password, min_timeout=4.0)
                if login_ev is not None and getattr(login_ev, "type", None) not in ("ERROR", "ERR"):
                    login_success = True
                    resp_text = "Autenticación exitosa (LOGIN_SUCCESS)"
                else:
                    error_msg = "Contraseña incorrecta o repetidor fuera de alcance"
            except Exception as e:
                logging.debug(f"send_login_sync falló ({e}), usando fallback...")

        if not login_success and error_msg is None:
            await self._send_login_fallback(rf_ctx, cmd_text)
            resp_data = await self._wait_for_repeater_response(req.mc, rf_ctx.fut, timeout=6.0) or {}
            raw_resp = resp_data.get("text") or resp_data.get("message") or ""
            resp_text = raw_resp[2:].strip() if raw_resp.startswith("> ") else raw_resp.strip()
            lower = resp_text.lower()

            if resp_data.get("auth_status") == "failed" or any(p in lower for p in ("invalid", "denied", "wrong", "failed")):
                login_success = False
                error_msg = resp_text or "Contraseña incorrecta en el repetidor"
            elif resp_data.get("auth_status") == "success" or any(p in lower for p in ("ok", "success", "logged in", "auth ok")):
                login_success = True
            elif resp_text:
                login_success = True
            else:
                error_msg = f"Sin respuesta del repetidor {str(req.target_node)[:8]}"

        self._unregister_waiters(rf_ctx.waiter_keys, rf_ctx.fut, include_ping=False)
        status_str = "ok" if login_success else "error"
        rf_ctx.res.update({
            "status": status_str,
            "action": "login",
            "target_node": str(req.target_node),
            "authenticated": login_success,
            "message": resp_text if login_success else (error_msg or "Error en autenticación"),
            "cmd_dispatched": f"login {'*' * len(req.password)}",
        })
        self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{req.target_node}/status", json.dumps(rf_ctx.res), 1)
        return rf_ctx.res

    async def _execute_unit_command(self, rf_ctx: RfExecutionContext) -> dict[str, Any]:
        """Ejecuta un comando unitario con protección de Airtime LoRa."""
        req = rf_ctx.req
        if req.password and req.action != "login":
            await self._send_pre_login(rf_ctx)
            await asyncio.sleep(0.35)

        can_send, rem_cd = self._ctx.repeater_manager.check_airtime_cooldown(str(req.target_node), is_full_query=False)
        if not can_send:
            self._unregister_waiters(rf_ctx.waiter_keys, rf_ctx.fut, include_ping=False)
            return {
                "status": "error",
                "message": f"Protección de Airtime LoRa activa: Espera {rem_cd}s",
                "code": 429,
                "cooldown_remaining": rem_cd,
            }

        cmd_text = self._ctx.repeater_manager.build_repeater_command_payload(req.action, req.admin_data)
        self._ctx.repeater_manager.record_command_sent(str(req.target_node), is_full_query=False)
        t_start = time.perf_counter()

        await self._send_rf_command(req.mc, rf_ctx.dest_target, cmd_text, str(req.target_node), req.req_id)
        resp_data = await self._wait_for_repeater_response(req.mc, rf_ctx.fut, timeout=6.0) or {}
        self._unregister_waiters(rf_ctx.waiter_keys, rf_ctx.fut, include_ping=False)

        elapsed = round((time.perf_counter() - t_start) * 1000, 1)
        raw_resp = resp_data.get("text") or resp_data.get("message") or ""
        resp_text = raw_resp[2:].strip() if raw_resp.startswith("> ") else raw_resp.strip()

        rf_ctx.res["cmd_dispatched"] = cmd_text
        rf_ctx.res["response"] = resp_text or f"Comando '{cmd_text}' transmitido por RF a {str(req.target_node)[:8]}"
        rf_ctx.res["message"] = rf_ctx.res["response"]
        if resp_data.get("telemetry"):
            rf_ctx.res["telemetry"] = resp_data["telemetry"]
        if resp_data.get("rssi") is not None:
            rf_ctx.res["rssi"] = resp_data["rssi"]
        if resp_data.get("snr") is not None:
            rf_ctx.res["snr"] = resp_data["snr"]
        rf_ctx.res["rtt_ms"] = elapsed

        self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{req.target_node}/status", json.dumps(rf_ctx.res), 1)
        return rf_ctx.res

    # --------------------------------------------------------------------------
    # Helpers Privados de Radio y Registro
    # --------------------------------------------------------------------------

    def _register_waiters(self, keys: list[str], fut: asyncio.Future[dict[str, Any]], include_ping: bool) -> None:
        """Registra un future en los diccionarios de espera."""
        for k in keys:
            if k not in self._waiters.cmd_waiters:
                self._waiters.cmd_waiters[k] = []
            self._waiters.cmd_waiters[k].append(fut)
            if include_ping:
                if k not in self._waiters.ping_waiters:
                    self._waiters.ping_waiters[k] = []
                self._waiters.ping_waiters[k].append(fut)

    def _unregister_waiters(self, keys: list[str], fut: asyncio.Future[dict[str, Any]], include_ping: bool) -> None:
        """Remueve un future de los diccionarios de espera."""
        for k in keys:
            if k in self._waiters.cmd_waiters:
                self._waiters.cmd_waiters[k] = [f for f in self._waiters.cmd_waiters[k] if f is not fut]
                if not self._waiters.cmd_waiters[k]:
                    del self._waiters.cmd_waiters[k]
            if include_ping and k in self._waiters.ping_waiters:
                self._waiters.ping_waiters[k] = [f for f in self._waiters.ping_waiters[k] if f is not fut]
                if not self._waiters.ping_waiters[k]:
                    del self._waiters.ping_waiters[k]

    async def _ensure_radio_contact(self, mc: Any, dest_target: Any, target_name: str) -> None:
        """Asegura que el nodo destino esté presente en la tabla del firmware."""
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "add_contact"):
            try:
                if isinstance(dest_target, dict):
                    await mc.commands.add_contact(dest_target)
                elif hasattr(dest_target, "to_radio_dict"):
                    await mc.commands.add_contact(dest_target.to_radio_dict())
                elif hasattr(dest_target, "public_key"):
                    await mc.commands.add_contact({"public_key": dest_target.public_key, "name": target_name})
                elif isinstance(dest_target, str) and len(dest_target) >= 12:
                    await mc.commands.add_contact({"public_key": (dest_target + "0" * 64)[:64], "name": target_name})
            except Exception as e:
                logging.debug(f"Asegurando contacto en radio: {e}")

    async def _send_rf_command(self, mc: Any, dest_target: Any, cmd_text: str, target_node: str, req_id: Any) -> None:
        """Envía un comando RF usando el método send_cmd del SDK o el fallback de transmisión."""
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_cmd"):
            try:
                await mc.commands.send_cmd(dest_target, cmd_text)
                return
            except Exception as e:
                logging.debug(f"Fallo send_cmd: {e}")
        await self._ctx.execute_tx({"to": target_node, "text": cmd_text, "request_id": req_id})

    async def _send_login_fallback(self, rf_ctx: RfExecutionContext, cmd_text: str) -> None:
        """Envía login usando send_login o send_cmd según capacidades."""
        req = rf_ctx.req
        if req.mc and hasattr(req.mc, "commands") and hasattr(req.mc.commands, "send_login"):
            try:
                await req.mc.commands.send_login(rf_ctx.dest_login_target, cmd_text.split(" ", 1)[1])
                return
            except Exception:
                pass
        await self._send_rf_command(req.mc, rf_ctx.dest_target, cmd_text, str(req.target_node), req.req_id)

    async def _send_pre_login(self, rf_ctx: RfExecutionContext) -> None:
        """Envía autenticación previa antes de ejecutar un comando."""
        await self._send_login_fallback(rf_ctx, f"login {rf_ctx.req.password}")
