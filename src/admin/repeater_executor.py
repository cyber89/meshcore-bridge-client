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
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING, Any

import config
from src.admin.sdk_commands import require_success, run_sdk_command
from src.contact_manager import (
    NodeContactUpdate,
    PacketRecord,
    is_valid_node_key,
)
from src.protocol_types import (
    LORA_MAX_FREQ_MHZ,
    LORA_MIN_FREQ_MHZ,
    redact_command_str,
    redact_sensitive_mapping,
)
from src.repeater_manager import RepeaterManager
from src.shared_utils import normalize_battery, redact_sensitive_command

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

    def register(self, keys: list[str], fut: asyncio.Future[dict[str, Any]], include_ping: bool = False) -> None:
        """Registra un futuro bajo una lista de claves de nodo."""
        for k in keys:
            if k and len(k) >= 32:
                setattr(fut, "_target_canonical", k.strip().lower())  # noqa: B010
                break
        for k in keys:
            if not k:
                continue
            if k not in self.cmd_waiters:
                self.cmd_waiters[k] = []
            self.cmd_waiters[k].append(fut)
            if include_ping:
                if k not in self.ping_waiters:
                    self.ping_waiters[k] = []
                self.ping_waiters[k].append(fut)

    def unregister(self, keys: list[str], fut: asyncio.Future[dict[str, Any]], include_ping: bool = False) -> None:
        """Desregistra un futuro eliminando listas vacías."""
        for k in keys:
            if not k:
                continue
            if k in self.cmd_waiters:
                self.cmd_waiters[k] = [f for f in self.cmd_waiters[k] if f is not fut]
                if not self.cmd_waiters[k]:
                    del self.cmd_waiters[k]
            if include_ping and k in self.ping_waiters:
                self.ping_waiters[k] = [f for f in self.ping_waiters[k] if f is not fut]
                if not self.ping_waiters[k]:
                    del self.ping_waiters[k]

    @asynccontextmanager
    async def expect_response(
        self,
        keys: list[str],
        include_ping: bool = False,
    ) -> AsyncIterator[asyncio.Future[dict[str, Any]]]:
        """Context manager asíncrono para registro y desregistro determinista de promesas RF."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.register(keys, fut, include_ping=include_ping)
        try:
            yield fut
        finally:
            self.unregister(keys, fut, include_ping=include_ping)
            if not fut.done():
                fut.cancel()



@dataclass(slots=True)
class RfExecutionContext:
    """Contexto estructurado para ejecución de comandos RF individuales o login."""

    req: RemoteRepeaterRequest
    dest_target: Any
    dest_login_target: Any
    waiter_keys: list[str]
    fut: asyncio.Future[dict[str, Any]]
    res: dict[str, Any]
    cooldown_reserved: bool = False


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
        get_local_config: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._ctx = ctx
        self._waiters = waiters
        self._publish_safe = publish_safe
        self._resolve_target = resolve_target
        self._wait_for_repeater_response = wait_for_repeater_response
        self._get_local_config = get_local_config or (lambda: {})
        self._request_locks: dict[str, asyncio.Lock] = {}
        self._command_tag_sequence = 0

    async def execute(self, req: RemoteRepeaterRequest) -> dict[str, Any]:
        try:
            state_loader = getattr(self._ctx.repeater_manager, "load_state", None)
            if callable(state_loader):
                loading = state_loader()
                if asyncio.iscoroutine(loading):
                    await loading
            target = self._ctx.node_registry.get_canonical_key(str(req.target_node)) or str(req.target_node).strip().lower()
            lock = self._request_locks.setdefault(target, asyncio.Lock())
            async with lock:
                return await self._execute_request(req)
        except Exception as error:
            return {"status": "error", "target_node": str(req.target_node), "message": str(error)}

    async def _flush_cooldowns(self) -> None:
        writer = getattr(self._ctx.repeater_manager, "flush_state", None)
        if callable(writer):
            writing = writer()
            if asyncio.iscoroutine(writing):
                await writing

    async def _execute_request(self, req: RemoteRepeaterRequest) -> dict[str, Any]:
        """Punto de entrada principal para despachar acciones sobre un repetidor remoto."""
        res = req.res if req.res is not None else {}
        res["target_node"] = req.target_node
        redacted_action = redact_sensitive_command(req.action)
        logging.info(
            f"[TX-ADMIN] De: Estación Base Local -> Para: {req.target_node} | "
            f"Acción: '{redacted_action}' | ReqID: {req.req_id}"
        )

        target_info = self._collect_target_info(str(req.target_node))
        if target_info and target_info.get("public_key"):
            canonical_target = str(target_info["public_key"]).strip().lower()
        else:
            canonical_target = self._ctx.node_registry.get_canonical_key(str(req.target_node)) or str(req.target_node).strip().lower()

        local_key = str(self._get_local_config().get("public_key", "")).strip().lower()
        if self._ctx.node_registry.is_local_key(canonical_target) or (
            local_key and canonical_target and (local_key.startswith(canonical_target) or canonical_target.startswith(local_key))
        ):
            return {"status": "error", "message": "Bucle local prohibido: el destino es la estación base"}
        is_client_only = bool(
            target_info
            and str(target_info.get("role", "")).upper() in ("CLIENT", "NONE", "USER")
        )

        if req.action in ("remote_repeater_set_config", "set_remote_config"):
            if is_client_only:
                return {"status": "error", "message": "La configuración remota solo aplica a nodos repetidores"}
            return await self._execute_batch_config(req, res)

        if req.action in ("ping_zero", "ping_0", "ping", "zero_hop_ping"):
            return await self._execute_ping_zero(req, target_info, res)

        if req.action in ("refresh_telemetry", "full_telemetry", "refresh_repeater_telemetry", "get_telemetry_batch"):
            if target_info and str(target_info.get("role", "")).upper() not in ("REPEATER", "ROUTER"):
                return {"status": "error", "code": 422, "message": "El lote de administración requiere un repetidor"}
            return await self._execute_batch_telemetry_query(req, target_info, res)

        if is_client_only:
            return {"status": "error", "message": "Los comandos de administración remota son exclusivos para repetidores"}

        return await self._dispatch_rf_command(req, target_info, res)

    def _collect_target_info(self, target_node: str) -> dict[str, Any] | None:
        """Obtiene la información del nodo destino desde el NodeRegistry por pubkey, prefijo o alias/nombre."""
        tgt = str(target_node).strip()
        tgt_lower = tgt.lower()
        # 1. Búsqueda por clave pública exacta o prefijo hexadecimal
        for n in self._ctx.node_registry.list_nodes():
            pk = str(n.get("public_key", "")).lower()
            if pk == tgt_lower or (len(pk) >= 8 and (pk.startswith(tgt_lower) or tgt_lower.startswith(pk))):
                return n
        # 2. Búsqueda por nombre o alias (B12: evita que pasar nombre de cliente ignore el guard de rol)
        found = self._ctx.node_registry.find_by_name(tgt)
        if found is not None:
            return found.to_dict()
        for n in self._ctx.node_registry.list_nodes():
            n_name = str(n.get("name", "")).strip().lower()
            n_alias = str(n.get("alias", "")).strip().lower()
            if n_name == tgt_lower or n_alias == tgt_lower:
                return n
        return None

    async def _execute_batch_config(self, req: RemoteRepeaterRequest, res: dict[str, Any]) -> dict[str, Any]:
        """Aplica múltiples parámetros de configuración remota en el repetidor."""
        can_send, rem_cd = self._ctx.repeater_manager.check_airtime_cooldown(str(req.target_node), is_full_query=True)
        if not can_send:
            return self._ctx.repeater_manager.build_cooldown_error_response(rem_cd)

        params = req.admin_data.get("params", {})
        if not isinstance(params, dict):
            return {"status": "error", "message": "params debe ser un objeto"}
        aliases = (
            ("freq", "frequency"), ("bw", "bandwidth"), ("sf", "spreading_factor"),
            ("cr", "coding_rate"), ("tx_power", "power", "tx"), ("repeat", "repeat_enabled"),
            ("advert_interval", "beacon_interval"), ("name", "owner_name"),
            ("lat", "latitude"), ("lon", "longitude"),
            ("password", "new_password", "admin_password"), ("public_key", "pk"), ("permission", "perm"),
        )
        for group in aliases:
            provided = [params[key] for key in group if key in params]
            if len(provided) > 1 and any(str(value).lower() != str(provided[0]).lower() for value in provided[1:]):
                return {"status": "error", "code": 422, "message": f"Alias de configuración contradictorios: {', '.join(group)}"}

        allowed_keys = frozenset({
            "freq", "frequency", "bw", "bandwidth", "sf", "spreading_factor", "cr", "coding_rate",
            "region", "tx_power", "power", "tx", "repeat", "repeat_enabled",
            "advert_interval", "beacon_interval", "flood_advert_interval",
            "name", "owner_name", "owner_info", "lat", "latitude", "lon", "longitude",
            "password", "new_password", "admin_password", "guest_password",
            "public_key", "pk", "permission", "perm"
        })
        # Prevalidación estricta de parámetros permitidos y rechazo de no soportados (B09)
        if "region" in params:
            return {
                "status": "error",
                "message": "El parámetro 'region' no es compatible como comando remoto; configure los parámetros de radio (freq, bw, sf, cr) directamente.",
            }

        for p_key in params:
            if p_key not in allowed_keys:
                return {"status": "error", "message": f"Parámetro de configuración remota desconocido: '{p_key}'"}

        # Consolidación atómica de parámetros de radio si se recibieron configuraciones de RF (B11)
        radio_keys = {"freq", "frequency", "bw", "bandwidth", "sf", "spreading_factor", "cr", "coding_rate"}
        target_node_info = self._collect_target_info(str(req.target_node)) or {}
        has_radio = any(k in params for k in radio_keys)
        radio_cmd: str | None = None
        if has_radio:
            freq_cand = params.get("freq", params.get("frequency"))
            bw_cand = params.get("bw", params.get("bandwidth"))
            sf_cand = params.get("sf", params.get("spreading_factor"))
            cr_cand = params.get("cr", params.get("coding_rate"))

            if freq_cand is None or bw_cand is None or sf_cand is None or cr_cand is None:
                return {
                    "status": "error",
                    "message": "Baseline de parámetros de radio no disponible para el nodo remoto; se requiere especificar frequency, bandwidth, spreading_factor y coding_rate completos.",
                }
            try:
                freq_f = float(freq_cand)
                if not (LORA_MIN_FREQ_MHZ <= freq_f <= LORA_MAX_FREQ_MHZ):
                    return {"status": "error", "message": f"Frecuencia {freq_f} MHz fuera del rango permitido"}
                bw_f = float(bw_cand)
                if not (7.0 <= bw_f <= 500.0):
                    return {"status": "error", "message": f"Ancho de banda {bw_f} kHz inválido"}
                sf_i = RepeaterManager._integer(sf_cand)
                if sf_i not in range(5, 13):
                    return {"status": "error", "message": f"Spreading factor SF{sf_i} inválido (5..12)"}
                cr_raw = str(cr_cand).strip()
                cr_num = None
                if cr_raw in ("5", "6", "7", "8"):
                    cr_num = int(cr_raw)
                elif "/" in cr_raw:
                    parts = cr_raw.split("/")
                    if len(parts) == 2 and parts[0].strip() == "4" and parts[1].strip() in ("5", "6", "7", "8"):
                        cr_num = int(parts[1].strip())
                if cr_num is None:
                    return {"status": "error", "message": f"Coding rate CR '{cr_cand}' inválido (debe ser 5..8 o 4/5..4/8)"}
            except (ValueError, TypeError) as err:
                return {"status": "error", "message": f"Parámetros de radio inválidos: {err}"}

            radio_cmd = f"set radio {freq_f},{bw_f},{sf_i},{cr_num}"

        planned_commands: list[str] = []
        handled_keys: set[str] = set()

        # Potencia TX
        for p_k in ("tx_power", "power", "tx"):
            if p_k in params:
                raw_pwr = params[p_k]
                try:
                    pwr_i = RepeaterManager._integer(raw_pwr)
                    if pwr_i is None or not (-9 <= pwr_i <= 30):
                        return {"status": "error", "message": f"Potencia TX {pwr_i} dBm fuera de rango (-9..30)"}
                except (ValueError, TypeError):
                    return {"status": "error", "message": f"Potencia TX remota inválida: {raw_pwr}"}
                observed_node = self._ctx.node_registry.get_by_key_or_prefix(str(target_node_info.get("public_key") or req.target_node))
                max_power = observed_node.max_tx_power if observed_node is not None else None
                tx_cmd = self._ctx.repeater_manager.build_repeater_command_payload("set_tx_power", {"tx_power": pwr_i, "max_tx_power": max_power})
                if not tx_cmd:
                    return {"status": "error", "message": f"No se pudo compilar comando de potencia TX: {raw_pwr}"}
                planned_commands.append(tx_cmd)
                handled_keys.update({"tx_power", "power", "tx"})
                break

        # Repetición
        for r_k in ("repeat", "repeat_enabled"):
            if r_k in params:
                rep_val = params[r_k]
                rep_cmd = self._ctx.repeater_manager.build_repeater_command_payload("set_repeat", {"repeat": rep_val})
                if not rep_cmd:
                    return {"status": "error", "message": f"No se pudo compilar comando de repetición: {rep_val}"}
                planned_commands.append(rep_cmd)
                handled_keys.update({"repeat", "repeat_enabled"})
                break

        # Coordenadas: latitud
        for lat_k in ("lat", "latitude"):
            if lat_k in params:
                lat_val = params[lat_k]
                lat_cmd = self._ctx.repeater_manager.build_repeater_command_payload("set_lat", {"lat": lat_val})
                if not lat_cmd:
                    return {"status": "error", "message": f"Latitud remota inválida o fuera de rango: {lat_val}"}
                planned_commands.append(lat_cmd)
                handled_keys.update({"lat", "latitude"})
                break

        # Coordenadas: longitud
        for lon_k in ("lon", "longitude"):
            if lon_k in params:
                lon_val = params[lon_k]
                lon_cmd = self._ctx.repeater_manager.build_repeater_command_payload("set_lon", {"lon": lon_val})
                if not lon_cmd:
                    return {"status": "error", "message": f"Longitud remota inválida o fuera de rango: {lon_val}"}
                planned_commands.append(lon_cmd)
                handled_keys.update({"lon", "longitude"})
                break

        # Nombre
        for name_k in ("name", "owner_name"):
            if name_k in params:
                name_val = params[name_k]
                name_cmd = self._ctx.repeater_manager.build_repeater_command_payload("set_name", {"name": name_val})
                if not name_cmd:
                    return {"status": "error", "message": f"Nombre de nodo remoto inválido: {name_val}"}
                planned_commands.append(name_cmd)
                handled_keys.update({"name", "owner_name"})
                break

        # Owner info
        if "owner_info" in params:
            info_val = params["owner_info"]
            info_cmd = self._ctx.repeater_manager.build_repeater_command_payload("set_owner_info", {"owner_info": info_val})
            if not info_cmd:
                return {"status": "error", "message": "No se pudo compilar comando de owner_info"}
            planned_commands.append(info_cmd)
            handled_keys.add("owner_info")

        # Intervalo de baliza (advert / beacon)
        for adv_k in ("advert_interval", "beacon_interval"):
            if adv_k in params:
                adv_val = params[adv_k]
                adv_cmd = self._ctx.repeater_manager.build_repeater_command_payload("set_advert_interval", {"advert_interval": adv_val})
                if not adv_cmd:
                    return {"status": "error", "message": f"Intervalo de baliza inválido: {adv_val} (debe ser 0 o un número par entre 60 y 240 minutos)"}
                planned_commands.append(adv_cmd)
                handled_keys.update({"advert_interval", "beacon_interval"})
                break

        # Intervalo de flood advert
        if "flood_advert_interval" in params:
            fadv_val = params["flood_advert_interval"]
            fadv_cmd = self._ctx.repeater_manager.build_repeater_command_payload("set_flood_advert_interval", {"flood_advert_interval": fadv_val})
            if not fadv_cmd:
                return {"status": "error", "message": f"Intervalo de baliza flood inválido: {fadv_val} (debe ser 0 o entre 3 y 168 horas)"}
            planned_commands.append(fadv_cmd)
            handled_keys.add("flood_advert_interval")

        # Contraseña de administrador
        for pwd_k in ("password", "new_password", "admin_password"):
            if pwd_k in params:
                pwd_val = params[pwd_k]
                pwd_cmd = self._ctx.repeater_manager.build_repeater_command_payload("set_password", {"password": pwd_val})
                if not pwd_cmd:
                    return {"status": "error", "message": "Contraseña de administración remota inválida"}
                planned_commands.append(pwd_cmd)
                handled_keys.update({"password", "new_password", "admin_password"})
                break

        # Contraseña de invitado (guest)
        if "guest_password" in params:
            gpwd_val = params["guest_password"]
            gpwd_cmd = self._ctx.repeater_manager.build_repeater_command_payload("set_guest_password", {"guest_password": gpwd_val})
            if not gpwd_cmd:
                return {"status": "error", "message": "Contraseña de invitado (guest) remota inválida"}
            planned_commands.append(gpwd_cmd)
            handled_keys.add("guest_password")

        # ACL (public key / permission)
        if any(pk_k in params for pk_k in ("public_key", "pk")):
            pk_val = params.get("public_key", params.get("pk"))
            perm_val = params.get("permission", params.get("perm", 1))
            acl_cmd = self._ctx.repeater_manager.build_repeater_command_payload("setperm", {"public_key": pk_val, "permission": perm_val})
            if not acl_cmd:
                return {"status": "error", "message": f"Parámetros de ACL inválidos (clave pública: '{pk_val}', permiso: '{perm_val}')"}
            planned_commands.append(acl_cmd)
            handled_keys.update({"public_key", "pk", "permission", "perm"})

        # Comprobar si quedó alguna clave sin manejar
        for remaining_k in params:
            if remaining_k not in radio_keys and remaining_k not in handled_keys:
                return {"status": "error", "message": f"Parámetro de configuración remota no soportado o incompleto: '{remaining_k}'"}

        if not radio_cmd and not planned_commands:
            return {"status": "error", "message": "No se encontraron parámetros válidos para configurar"}

        self._ctx.repeater_manager.record_command_sent(str(req.target_node), is_full_query=True)
        await self._flush_cooldowns()
        dispatched: list[str] = []
        applied: dict[str, Any] = {}
        saved: dict[str, Any] = {}
        unconfirmed: dict[str, Any] = {}
        results: list[dict[str, Any]] = []

        try:
            if req.password:
                norm_target = self._ctx.node_registry.get_canonical_key(str(req.target_node)) or str(req.target_node).strip().lower()
                waiter_keys = [norm_target, norm_target[:8], norm_target[:4], str(req.target_node).strip().lower()]
                async with self._waiters.expect_response(waiter_keys) as fut:
                    rf_ctx = RfExecutionContext(
                        req=req,
                        dest_target=self._resolve_target(str(req.target_node), 12),
                        dest_login_target=self._resolve_target(str(req.target_node), 12),
                        waiter_keys=waiter_keys,
                        fut=fut,
                        res=res,
                    )
                    authenticated, message = await self._authenticate_repeater(rf_ctx, min_timeout=3.0)
                if not authenticated:
                    res.update({"status": "error", "authenticated": False, "message": message, "dispatched_commands": []})
                    self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{req.target_node}/status", json.dumps(redact_sensitive_mapping(res)), 1)
                    return redact_sensitive_mapping(res)
                dispatched.append("login ********")
                await asyncio.sleep(0.35)

            commands = ([radio_cmd] if radio_cmd else []) + planned_commands
            norm_target = self._ctx.node_registry.get_canonical_key(str(req.target_node)) or str(req.target_node).strip().lower()
            waiter_keys = [norm_target, norm_target[:8], norm_target[:4], str(req.target_node).strip().lower()]
            for cmd_str in commands:
                async with self._waiters.expect_response(waiter_keys) as command_fut:
                    await self._send_rf_command(req.mc, self._resolve_target(str(req.target_node), 12), cmd_str, str(req.target_node), req.req_id, response_future=command_fut)
                    reply = await self._wait_for_repeater_response(req.mc, command_fut, timeout=6.0) or {}
                dispatched.append(redact_command_str(cmd_str))
                text = str(reply.get("text") or reply.get("message") or "").removeprefix("> ").strip()
                fields = self._ctx.repeater_manager.command_parameters(cmd_str)
                if self._ctx.repeater_manager.response_is_error(text):
                    safe_error = self._safe_response_text(cmd_str, text)
                    results.append({"command": redact_command_str(cmd_str), "status": "error", "response": safe_error})
                    raise RuntimeError(safe_error)
                confirmed = self._setter_response_confirmed(cmd_str, text)
                if confirmed:
                    if cmd_str.startswith("set radio ") or "reboot to apply" in text.lower():
                        saved.update(fields)
                        res["pending_reboot"] = True
                    else:
                        applied.update(fields)
                        await self._update_local_registry_from_params(str(req.target_node), fields)
                else:
                    unconfirmed.update(fields)
                results.append({"command": redact_command_str(cmd_str), "status": "saved" if confirmed and cmd_str.startswith("set radio ") else ("applied" if confirmed else "dispatched"), "response": self._safe_response_text(cmd_str, text)})
                await asyncio.sleep(0.35)

            res.update({"status": "dispatched" if unconfirmed else "ok", "dispatched_commands": dispatched, "applied": applied, "saved": saved, "unconfirmed": unconfirmed, "results": results})
            self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{req.target_node}/status", json.dumps(redact_sensitive_mapping(res)), 1)
            return redact_sensitive_mapping(res)
        except Exception as error:
            res.update({
                "status": "partial" if applied or saved or unconfirmed else "error",
                "message": str(error),
                "dispatched_commands": dispatched,
                "applied": applied, "saved": saved, "unconfirmed": unconfirmed, "results": results,
            })
            self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{req.target_node}/status", json.dumps(redact_sensitive_mapping(res)), 1)
            return redact_sensitive_mapping(res)

    async def _update_local_registry_from_params(self, target_node: str, params: dict[str, Any]) -> None:
        """Actualiza inmediatamente los parámetros del repetidor en el registro local."""
        canon = self._ctx.node_registry.get_canonical_key(target_node) or target_node.strip().lower()
        owner_n = params.get("owner_name", params.get("name"))
        lat_val = params.get("lat", params.get("latitude"))
        lon_val = params.get("lon", params.get("longitude"))
        alt_val = params.get("alt", params.get("altitude", params.get("altitude_m")))
        tx_pwr = params.get("tx_power", params.get("power"))

        freq_raw = params.get("freq", params.get("frequency"))
        sf_raw = params.get("sf", params.get("spreading_factor"))
        bw_raw = params.get("bw", params.get("bandwidth"))
        cr_raw = params.get("cr", params.get("coding_rate"))
        hop_raw = params.get("hop_limit", params.get("hops"))
        rep_raw = params.get("repeat", params.get("repeat_enabled"))
        adv_raw = params.get("beacon_interval", params.get("advert_interval"))
        clk_raw = params.get("clock")
        bat_raw = params.get("battery_pct")
        volt_raw = params.get("voltage_v")
        duty_raw = params.get("duty_cycle_pct")
        up_raw = params.get("uptime")
        at_raw = params.get("airtime_ms")
        nf_raw = params.get("noise_floor_dbm")
        temp_raw = params.get("temperature_c", params.get("temperature"))
        hum_raw = params.get("humidity_pct", params.get("humidity"))
        press_raw = params.get("pressure_hpa", params.get("pressure"))
        fixed_val = params.get("fixed_position", params.get("fixed", params.get("pos_fixed")))

        update = NodeContactUpdate(
            name=str(owner_n) if owner_n else None,
            alias=str(owner_n) if owner_n else None,
            owner_name=str(owner_n) if owner_n else None,
            owner_info=str(params.get("owner_info")) if "owner_info" in params else None,
            latitude=float(lat_val) if lat_val is not None else None,
            longitude=float(lon_val) if lon_val is not None else None,
            altitude_m=float(alt_val) if alt_val is not None else None,
            fixed_position=RepeaterManager._boolean(fixed_val) if fixed_val is not None else None,
            frequency=float(freq_raw) if freq_raw is not None else None,
            spreading_factor=int(sf_raw) if sf_raw is not None else None,
            bandwidth=float(bw_raw) if bw_raw is not None else None,
            coding_rate=str(cr_raw) if cr_raw is not None else None,
            tx_power=int(tx_pwr) if tx_pwr is not None else None,
            hop_limit=int(hop_raw) if hop_raw is not None else None,
            repeat_enabled=RepeaterManager._boolean(rep_raw) if rep_raw is not None else None,
            advert_interval=int(adv_raw) if adv_raw is not None else None,
            flood_advert_interval=int(params["flood_advert_interval"]) if "flood_advert_interval" in params else None,
            allow_read_only=RepeaterManager._boolean(params["allow_read_only"]) if "allow_read_only" in params else None,
            clock=str(clk_raw) if clk_raw else None,
            battery_pct=int(bat_raw) if bat_raw is not None else None,
            voltage_v=float(volt_raw) if volt_raw is not None else None,
            duty_cycle_pct=float(duty_raw) if duty_raw is not None else None,
            uptime=str(up_raw) if up_raw else None,
            airtime_ms=int(at_raw) if at_raw is not None else None,
            noise_floor_dbm=int(nf_raw) if nf_raw is not None else None,
            temperature_c=float(temp_raw) if temp_raw is not None else None,
            humidity_pct=float(hum_raw) if hum_raw is not None else None,
            pressure_hpa=float(press_raw) if press_raw is not None else None,
            solar_v=params.get("solar_v"),
            last_rssi=params.get("last_rssi"), last_snr=params.get("last_snr"),
            packets_sent=params.get("packets_sent"), packets_recv=params.get("packets_recv"),
            duplicate_packets=params.get("duplicate_packets"), packet_errors=params.get("packet_errors"),
            queue_len=params.get("queue_len"), firmware_version=params.get("firmware_version"), hardware_board=params.get("hardware_board"),
        )
        updated_contact = self._ctx.node_registry.add_or_update(canon, update)
        if updated_contact and self._ctx.web_server and hasattr(self._ctx.web_server, "broadcast_event"):
            try:
                broadcast_data = {
                    "type": "contact_updated",
                    "event_type": "contact_updated",
                    "contact": updated_contact.to_dict(),
                }
                coro = self._ctx.web_server.broadcast_event(broadcast_data)
                if asyncio.iscoroutine(coro):
                    await coro
            except Exception:
                pass

    async def _execute_ping_zero(
        self, req: RemoteRepeaterRequest, target_info: dict[str, Any] | None, res: dict[str, Any]
    ) -> dict[str, Any]:
        """Ejecuta un ping directo de 0 saltos y calcula RTT y métricas de señal."""
        force = bool(req.admin_data.get("force", False))
        if not force and hasattr(self._ctx, "repeater_manager") and hasattr(self._ctx.repeater_manager, "check_ping_cooldown"):
            can_send, rem_cd = self._ctx.repeater_manager.check_ping_cooldown(str(req.target_node))
            if not can_send:
                return self._ctx.repeater_manager.build_cooldown_error_response(rem_cd)

        dest_target = self._resolve_target(str(req.target_node), 12)
        norm_target = self._ctx.node_registry.get_canonical_key(str(req.target_node)) or str(req.target_node).strip().lower()
        target_name = str((target_info.get("name") or target_info.get("alias")) if target_info else f"Nodo {norm_target[:8]}")

        # Guarda contra bucle local (Regla Inmutable SSoT 1.1)
        cfg = self._get_local_config()
        local_pk = str(cfg.get("public_key", "")).lower().strip()
        if local_pk and (norm_target == local_pk or norm_target.startswith(local_pk[:12])):
            return {
                "status": "error",
                "error": "Bucle local prohibido: no se pueden enviar pruebas de enlace dirigidas a la propia estación base",
                "target_node": str(req.target_node),
            }

        waiter_keys = [norm_target, norm_target[:8], norm_target[:4], str(req.target_node).strip().lower()]
        if target_info and target_info.get("name"):
            waiter_keys.append(str(target_info["name"]).lower())

        async with self._waiters.expect_response(waiter_keys, include_ping=True) as fut:
            contact_key = str(dest_target.get("public_key", "")) if isinstance(dest_target, dict) else str(dest_target)
            cached = getattr(req.mc, "_contacts", {})
            original = dict(cached[contact_key]) if isinstance(cached, dict) and contact_key in cached else None
            try:
                await self._ensure_radio_contact(
                    req.mc, dest_target, target_name, out_path_override="", out_path_len_override=0
                )

                t_start = time.perf_counter()
                cmd_text = "ping 0"
                if hasattr(self._ctx, "repeater_manager") and hasattr(self._ctx.repeater_manager, "record_ping_sent"):
                    self._ctx.repeater_manager.record_ping_sent(str(req.target_node))
                    await self._flush_cooldowns()
                await self._send_rf_command(req.mc, dest_target, cmd_text, str(req.target_node), req.req_id)

                resp_data = await self._wait_for_repeater_response(req.mc, fut, timeout=5.0) or {}
            finally:
                if original is not None and cached.get(contact_key) != original:
                    response = await run_sdk_command(self._ctx, req.mc, "add_contact", original)
                    require_success(response, "add_contact")
                    cached[contact_key] = original

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

    async def _execute_batch_telemetry_query(
        self, req: RemoteRepeaterRequest, target_info: dict[str, Any] | None, res: dict[str, Any]
    ) -> dict[str, Any]:
        """Ejecuta una consulta consolidada y ordenada de telemetría remota respetando Airtime LoRa."""
        force = bool(req.admin_data.get("force", False))
        if not force and hasattr(self._ctx, "repeater_manager") and hasattr(self._ctx.repeater_manager, "check_airtime_cooldown"):
            can_send, rem_cd = self._ctx.repeater_manager.check_airtime_cooldown(str(req.target_node), is_full_query=True)
            if not can_send:
                return self._ctx.repeater_manager.build_cooldown_error_response(rem_cd)

        if hasattr(self._ctx, "repeater_manager") and hasattr(self._ctx.repeater_manager, "record_command_sent"):
            self._ctx.repeater_manager.record_command_sent(str(req.target_node), is_full_query=True)
            await self._flush_cooldowns()

        dest_target = self._resolve_target(str(req.target_node), 12)
        dest_login_target = self._resolve_target(str(req.target_node), 12)
        norm_target = self._ctx.node_registry.get_canonical_key(str(req.target_node)) or str(req.target_node).strip().lower()

        waiter_keys = [norm_target, norm_target[:8], norm_target[:4], str(req.target_node).strip().lower()]
        if target_info and target_info.get("name"):
            waiter_keys.append(str(target_info["name"]).lower())

        target_name = str((target_info.get("name") or target_info.get("alias")) if target_info else f"Repeater {norm_target[:8]}")
        await self._ensure_radio_contact(req.mc, dest_target, target_name)

        if req.password:
            async with self._waiters.expect_response(waiter_keys) as login_fut:
                login_ctx = RfExecutionContext(req, dest_target, dest_login_target, waiter_keys, login_fut, res)
                authenticated, message = await self._authenticate_repeater(login_ctx, min_timeout=4.0)
            if not authenticated:
                res.update({"status": "error", "authenticated": False, "message": message, "dispatched": []})
                self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{norm_target}/telemetry", json.dumps(res), 1)
                return res
            await asyncio.sleep(0.4)

        accumulated_telemetry: dict[str, Any] = {}
        binary_responses: list[str] = []
        binary_requested: list[str] = []

        # 1. Consulta binaria directa de estado (RepeaterStats del firmware MeshCore)
        if req.mc and hasattr(req.mc, "commands") and hasattr(req.mc.commands, "req_status_sync"):
            binary_requested.append("req_status_sync")
            try:
                status_res = await run_sdk_command(self._ctx, req.mc, "req_status_sync", dest_login_target, timeout=4.0)
                if status_res and isinstance(status_res, dict):
                    require_success(status_res, "req_status_sync")
                    raw_bat = status_res.get("bat")
                    if isinstance(raw_bat, bool) or not isinstance(raw_bat, int) or not 0 <= raw_bat <= 65535:
                        raise ValueError("Lectura binaria de batería inválida")
                    binary_responses.append("req_status_sync")
                    if raw_bat is not None:
                        volt_norm = raw_bat / 1000
                        pct_norm, _ = normalize_battery(f"{raw_bat}mV")
                        accumulated_telemetry["battery_pct"] = int(round(pct_norm))
                        accumulated_telemetry["voltage_v"] = volt_norm
                        accumulated_telemetry["battery_mv"] = int(raw_bat)
                        accumulated_telemetry["battery_source"] = "repeater_status"
                        accumulated_telemetry["battery_pct_source"] = "voltage_estimate"
                    if status_res.get("noise_floor") is not None:
                        accumulated_telemetry["noise_floor_dbm"] = int(status_res["noise_floor"])
                    if status_res.get("last_rssi") is not None:
                        accumulated_telemetry["last_rssi"] = int(status_res["last_rssi"])
                    if status_res.get("last_snr") is not None:
                        accumulated_telemetry["last_snr"] = float(status_res["last_snr"])
                    if status_res.get("nb_recv") is not None:
                        accumulated_telemetry["packets_recv"] = int(status_res["nb_recv"])
                    if status_res.get("nb_sent") is not None:
                        accumulated_telemetry["packets_sent"] = int(status_res["nb_sent"])
                    if status_res.get("uptime") is not None:
                        up_s = int(status_res["uptime"])
                        days, rem = divmod(up_s, 86400)
                        hours, rem = divmod(rem, 3600)
                        mins, secs = divmod(rem, 60)
                        accumulated_telemetry["uptime"] = f"{days}d {hours}h {mins}m" if days > 0 else (f"{hours}h {mins}m {secs}s" if hours > 0 else f"{mins}m {secs}s")
                        accumulated_telemetry["uptime_secs"] = up_s
                    if status_res.get("airtime") is not None:
                        accumulated_telemetry["airtime_ms"] = int(status_res["airtime"] * 1000)
                    if status_res.get("tx_queue_len") is not None:
                        accumulated_telemetry["queue_len"] = int(status_res["tx_queue_len"])
                    if status_res.get("recv_errors") is not None:
                        accumulated_telemetry["packet_errors"] = int(status_res["recv_errors"])
                    dups = int(status_res.get("direct_dups") or 0) + int(status_res.get("flood_dups") or 0)
                    accumulated_telemetry["duplicate_packets"] = dups
            except Exception as e:
                logging.debug(f"Fallo en req_status_sync: {e}")

        # 2. Consulta binaria directa de telemetría / sensores LPP
        if req.mc and hasattr(req.mc, "commands") and hasattr(req.mc.commands, "req_telemetry_sync"):
            binary_requested.append("req_telemetry_sync")
            try:
                lpp_res = await run_sdk_command(self._ctx, req.mc, "req_telemetry_sync", dest_login_target, timeout=3.5)
                if lpp_res:
                    require_success(lpp_res, "req_telemetry_sync")
                    from src.sensor_decoder import extract_telemetry_fields
                    decoded_lpp = extract_telemetry_fields({"lpp": lpp_res})
                    if decoded_lpp:
                        accumulated_telemetry.update(decoded_lpp)
                        binary_responses.append("req_telemetry_sync")
            except Exception as e:
                logging.debug(f"Fallo en req_telemetry_sync: {e}")

        queries = ["ver", "clock", "get radio", "get dutycycle"]
        dispatched: list[str] = []
        responses: dict[str, str] = {}

        for cmd in queries:
            async with self._waiters.expect_response(waiter_keys, include_ping=False) as cmd_fut:
                await self._send_rf_command(req.mc, dest_target, cmd, str(req.target_node), req.req_id, response_future=cmd_fut)
                dispatched.append(cmd)
                resp_data = await self._wait_for_repeater_response(req.mc, cmd_fut, timeout=4.0) or {}
                raw_resp = resp_data.get("text") or resp_data.get("message") or ""
                resp_text = raw_resp[2:].strip() if raw_resp.startswith("> ") else raw_resp.strip()
                if resp_text and not self._ctx.repeater_manager.response_is_error(resp_text):
                    responses[cmd] = resp_text
                    parsed = self._ctx.repeater_manager.parse_command_response(cmd, resp_text)
                    if cmd == "get radio":
                        res["saved"] = parsed
                        res["radio_settings_source"] = "saved_preferences"
                        parsed = {}
                    if parsed:
                        accumulated_telemetry.update(parsed)
                    if cmd == "clock" and resp_text:
                        clk_val = (parsed.get("clock") if parsed else None) or resp_text
                        accumulated_telemetry["clock"] = clk_val
                if resp_data.get("telemetry"):
                    received_telemetry = resp_data["telemetry"]
                    if cmd == "get radio":
                        received_telemetry = {key: value for key, value in received_telemetry.items() if key not in ("frequency", "bandwidth", "spreading_factor", "coding_rate")}
                    accumulated_telemetry.update(received_telemetry)
                if resp_data.get("rssi") is not None:
                    accumulated_telemetry["last_rssi"] = resp_data["rssi"]
                if resp_data.get("snr") is not None:
                    accumulated_telemetry["last_snr"] = resp_data["snr"]
            await asyncio.sleep(0.35)

        if accumulated_telemetry:
            update = NodeContactUpdate(
                last_seen=time.time(),
                last_rssi=accumulated_telemetry.get("last_rssi"),
                last_snr=accumulated_telemetry.get("last_snr"),
                battery_pct=accumulated_telemetry.get("battery_pct"),
                voltage_v=accumulated_telemetry.get("voltage_v"),
                solar_v=accumulated_telemetry.get("solar_v"),
                temperature_c=accumulated_telemetry.get("temperature_c"),
                uptime=accumulated_telemetry.get("uptime"),
                clock=accumulated_telemetry.get("clock"),
                airtime_ms=accumulated_telemetry.get("airtime_ms"),
                duty_cycle_pct=accumulated_telemetry.get("duty_cycle_pct"),
                noise_floor_dbm=accumulated_telemetry.get("noise_floor_dbm"),
                packets_sent=accumulated_telemetry.get("packets_sent"),
                packets_recv=accumulated_telemetry.get("packets_recv"),
                duplicate_packets=accumulated_telemetry.get("duplicate_packets"),
                packet_errors=accumulated_telemetry.get("packet_errors"),
                queue_len=accumulated_telemetry.get("queue_len"),
                firmware_version=accumulated_telemetry.get("firmware_version"),
                hardware_board=accumulated_telemetry.get("hardware_board"),
                frequency=accumulated_telemetry.get("frequency"),
                tx_power=accumulated_telemetry.get("tx_power"),
                spreading_factor=accumulated_telemetry.get("spreading_factor"),
                bandwidth=accumulated_telemetry.get("bandwidth"),
                coding_rate=accumulated_telemetry.get("coding_rate"),
                repeat_enabled=accumulated_telemetry.get("repeat_enabled"),
                advert_interval=accumulated_telemetry.get("advert_interval"),
                hop_limit=accumulated_telemetry.get("hop_limit"),
                hops=accumulated_telemetry.get("hops"),
            )
            updated_contact = self._ctx.node_registry.add_or_update(norm_target, update)
            if updated_contact:
                broadcast_data = {
                    "type": "contact_updated",
                    "event_type": "contact_updated",
                    "contact": updated_contact.to_dict(),
                }
                if self._ctx.web_server and hasattr(self._ctx.web_server, "broadcast_event"):
                    try:
                        coro = self._ctx.web_server.broadcast_event(broadcast_data)
                        if asyncio.iscoroutine(coro):
                            await coro
                    except Exception:
                        pass

        confirmed_count = len(responses) + len(binary_responses)
        requested_count = len(queries) + len(binary_requested)
        res.update({
            "status": "ok" if confirmed_count == requested_count else ("partial" if confirmed_count else "error"),
            "action": req.action,
            "target_node": norm_target,
            "dispatched": dispatched,
            "responses": responses,
            "binary_responses": binary_responses,
            "confirmed_count": confirmed_count,
            "requested_count": requested_count,
            "telemetry": accumulated_telemetry,
            "message": f"Telemetría consolidada de {norm_target[:8]} ({confirmed_count}/{requested_count} respuestas válidas)",
        })
        self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{norm_target}/telemetry", json.dumps(res), 1)
        return res

    async def _dispatch_rf_command(
        self, req: RemoteRepeaterRequest, target_info: dict[str, Any] | None, res: dict[str, Any]
    ) -> dict[str, Any]:
        """Enruta comandos administrativos individuales o autenticación."""
        if req.action in ("refresh_telemetry", "full_telemetry", "refresh_repeater_telemetry", "get_telemetry_batch"):
            return await self._execute_batch_telemetry_query(req, target_info, res)

        dest_target = self._resolve_target(str(req.target_node), 12)
        dest_login_target = self._resolve_target(str(req.target_node), 12)
        norm_target = self._ctx.node_registry.get_canonical_key(str(req.target_node)) or str(req.target_node).strip().lower()

        # Guarda contra bucle local (Regla Inmutable SSoT 1.1)
        cfg = self._get_local_config()
        local_pk = str(cfg.get("public_key", "")).lower().strip()
        if local_pk and (norm_target == local_pk or norm_target.startswith(local_pk[:12])):
            return {
                "status": "error",
                "error": "Bucle local prohibido: no se permite enviar comandos dirigidos a la propia estación base",
                "target_node": str(req.target_node),
            }

        waiter_keys = [norm_target, norm_target[:8], norm_target[:4], str(req.target_node).strip().lower()]
        if target_info and target_info.get("name"):
            waiter_keys.append(str(target_info["name"]).lower())

        async with self._waiters.expect_response(waiter_keys, include_ping=False) as fut:
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

            if req.action.strip().lower() in (
                "req_neighbours", "req_neighbors", "neighbours", "neighbors",
                "req_owner", "req_regions", "req_clock", "req_acl",
                "acl", "get_acl",
                "req_status", "status", "req_telemetry", "telemetry",
                "bat", "get_bat", "get bat", "battery",
            ):
                allowed, remaining = self._ctx.repeater_manager.check_airtime_cooldown(str(req.target_node), is_full_query=False)
                if not allowed:
                    return self._ctx.repeater_manager.build_cooldown_error_response(remaining)
                self._ctx.repeater_manager.record_command_sent(str(req.target_node), is_full_query=False)
                await self._flush_cooldowns()
                if req.password:
                    authenticated, message = await self._authenticate_repeater(rf_ctx, min_timeout=4.0)
                    if not authenticated:
                        res.update({"status": "error", "authenticated": False, "message": message})
                        return res
                    # Auth completed; a fallback CLI must not log in again.
                    req.password = ""
                bin_res = await self._try_execute_binary_or_anon(rf_ctx)
                if bin_res is not None:
                    return bin_res

            if req.action in ("get_stats_core", "get_stats_radio", "get_stats_packets"):
                # Expose via binary/anon req logic if supported by SDK, otherwise fallback to unit command
                return await self._execute_unit_command(rf_ctx)

            return await self._execute_unit_command(rf_ctx)

    async def _try_execute_binary_or_anon(self, rf_ctx: RfExecutionContext) -> dict[str, Any] | None:
        """Intenta ejecutar solicitudes binarias o anónimas oficiales si el SDK las soporta."""
        mc = rf_ctx.req.mc
        if not mc or not hasattr(mc, "commands"):
            return None

        action = rf_ctx.req.action.strip().lower()
        action = {"acl": "req_acl", "get_acl": "req_acl"}.get(action, action)
        battery_only = action in ("bat", "get_bat", "get bat", "battery")
        if battery_only:
            action = "req_status"
        target = rf_ctx.dest_login_target
        cmds = mc.commands

        supported_methods = {
            "req_neighbours": "req_neighbours_sync", "req_neighbors": "req_neighbours_sync",
            "neighbours": "req_neighbours_sync", "neighbors": "req_neighbours_sync",
            "req_status": "req_status_sync", "status": "req_status_sync",
            "req_telemetry": "req_telemetry_sync", "telemetry": "req_telemetry_sync",
            "req_owner": "req_owner_sync", "owner": "req_owner_sync",
            "req_regions": "req_regions_sync", "regions": "req_regions_sync",
            "req_clock": "req_basic_sync", "clock": "req_basic_sync", "req_basic": "req_basic_sync",
            "req_acl": "req_acl_sync", "acl": "req_acl_sync",
        }
        method = supported_methods.get(action)
        if method is None or not hasattr(cmds, method):
            return None

        try:
            data: Any = None
            if action in ("req_neighbours", "req_neighbors", "neighbours", "neighbors"):
                force = bool(rf_ctx.req.admin_data.get("force", False))
                if not force and hasattr(self._ctx, "repeater_manager") and hasattr(self._ctx.repeater_manager, "check_neighbours_cooldown"):
                    can_send, rem_cd = self._ctx.repeater_manager.check_neighbours_cooldown(str(rf_ctx.req.target_node))
                    if not can_send:
                        rf_ctx.res.update(self._ctx.repeater_manager.build_cooldown_error_response(rem_cd))
                        return rf_ctx.res

                if hasattr(cmds, "req_neighbours_sync"):
                    if hasattr(self._ctx, "repeater_manager") and hasattr(self._ctx.repeater_manager, "record_neighbours_sent"):
                        self._ctx.repeater_manager.record_neighbours_sent(str(rf_ctx.req.target_node))
                        await self._flush_cooldowns()
                    count = int(rf_ctx.req.admin_data.get("count", 255))
                    offset = int(rf_ctx.req.admin_data.get("offset", 0))
                    data = await run_sdk_command(self._ctx, mc, "req_neighbours_sync", target, count=count, offset=offset, min_timeout=4.0)
                if data is not None and isinstance(data, dict):
                    rf_ctx.res.update({
                        "status": "ok",
                        "action": action,
                        "target_node": str(rf_ctx.req.target_node),
                        "neighbours_count": data.get("neighbours_count", 0),
                        "results_count": data.get("results_count", 0),
                        "neighbours": data.get("neighbours", []),
                        "message": f"{data.get('results_count', 0)} vecinos directos descubiertos por radio",
                    })
                    self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{rf_ctx.req.target_node}/neighbours", json.dumps(rf_ctx.res), 1)
                    return rf_ctx.res

            elif action in ("req_status", "status") and hasattr(cmds, "req_status_sync"):
                data = await run_sdk_command(self._ctx, mc, "req_status_sync", target, min_timeout=4.0)
                if data is not None and isinstance(data, dict):
                    require_success(data, "req_status_sync")
                    normalized = dict(data)
                    for source, field in {"bat": "battery_mv", "nb_recv": "packets_recv", "nb_sent": "packets_sent", "airtime": "tx_air_secs", "tx_queue_len": "queue_len"}.items():
                        if source in data:
                            normalized[field] = data[source]
                    telemetry = self._ctx.repeater_manager.parse_repeater_telemetry_or_response(json.dumps(normalized))
                    if "bat" in data:
                        raw_bat = data["bat"]
                        if isinstance(raw_bat, bool) or not isinstance(raw_bat, int) or not 0 <= raw_bat <= 65535:
                            raise ValueError("Lectura binaria de batería inválida")
                        voltage = raw_bat / 1000
                        estimated_pct, _ = normalize_battery(f"{raw_bat}mV")
                        telemetry.update(battery_mv=raw_bat, voltage_v=voltage,
                                         battery_pct=int(round(estimated_pct)),
                                         battery_source="repeater_status", battery_pct_source="voltage_estimate")
                    elif battery_only:
                        raise ValueError("La respuesta de estado no contiene batería")
                    if "direct_dups" in data or "flood_dups" in data:
                        telemetry["duplicate_packets"] = int(data.get("direct_dups") or 0) + int(data.get("flood_dups") or 0)
                    if isinstance(data.get("telemetry"), dict):
                        telemetry.update(data["telemetry"])
                    rf_ctx.res.update({
                        "status": "ok",
                        "action": action,
                        "target_node": str(rf_ctx.req.target_node),
                        "data": data,
                        "telemetry": telemetry,
                        "message": "Estado binario del repetidor obtenido correctamente",
                    })
                    if telemetry:
                        await self._update_local_registry_from_params(str(rf_ctx.req.target_node), telemetry)
                    self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{rf_ctx.req.target_node}/status", json.dumps(rf_ctx.res), 1)
                    return rf_ctx.res

            elif action in ("req_telemetry", "telemetry") and hasattr(cmds, "req_telemetry_sync"):
                data = await run_sdk_command(self._ctx, mc, "req_telemetry_sync", target, min_timeout=4.0)
                if data is not None:
                    from src.sensor_decoder import extract_telemetry_fields
                    if isinstance(data, list):
                        telem_dict = extract_telemetry_fields({"lpp": data})
                    elif isinstance(data, dict):
                        telem_dict = extract_telemetry_fields(data) if "lpp" in data else data
                    else:
                        telem_dict = {}

                    if telem_dict or isinstance(data, list):
                        rf_ctx.res.update({
                            "status": "ok",
                            "action": action,
                            "target_node": str(rf_ctx.req.target_node),
                            "telemetry": telem_dict,
                            "message": "Telemetría binaria del repetidor obtenida",
                        })
                        if telem_dict:
                            await self._update_local_registry_from_params(str(rf_ctx.req.target_node), telem_dict)
                        self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{rf_ctx.req.target_node}/telemetry", json.dumps(rf_ctx.res), 1)
                        return rf_ctx.res

            elif action in ("req_owner", "owner") and hasattr(cmds, "req_owner_sync"):
                data = await run_sdk_command(self._ctx, mc, "req_owner_sync", target, min_timeout=4.0)
                if data is not None and isinstance(data, dict):
                    require_success(data, "req_owner_sync")
                    owner_fields = {"name": str(data.get("name", "")), "owner_info": str(data.get("owner", ""))}
                    await self._update_local_registry_from_params(str(rf_ctx.req.target_node), owner_fields)
                    rf_ctx.res.update({
                        "status": "ok",
                        "action": action,
                        "target_node": str(rf_ctx.req.target_node),
                        "owner_name": data.get("name", ""),
                        "owner_info": data.get("owner", ""),
                        "telemetry": owner_fields,
                        "message": f"Propietario: {data.get('owner', '')} ({data.get('name', '')})",
                    })
                    self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{rf_ctx.req.target_node}/owner", json.dumps(rf_ctx.res), 1)
                    return rf_ctx.res

            elif action in ("req_regions", "regions") and hasattr(cmds, "req_regions_sync"):
                data = await run_sdk_command(self._ctx, mc, "req_regions_sync", target, min_timeout=4.0)
                if data is not None:
                    rf_ctx.res.update({
                        "status": "ok",
                        "action": action,
                        "target_node": str(rf_ctx.req.target_node),
                        "regions": data,
                        "message": f"Regiones configuradas: {data}",
                    })
                    self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{rf_ctx.req.target_node}/regions", json.dumps(rf_ctx.res), 1)
                    return rf_ctx.res

            elif action in ("req_clock", "clock", "req_basic") and hasattr(cmds, "req_basic_sync"):
                data = await run_sdk_command(self._ctx, mc, "req_basic_sync", target, min_timeout=4.0)
                if isinstance(data, dict):
                    require_success(data, "req_basic_sync")
                    clock_str = ""
                    raw_data = data.get("data")
                    if not isinstance(raw_data, str):
                        raise ValueError("El nodo no devolvió los bytes de su RTC")
                    clock_bytes = bytes.fromhex(raw_data)
                    if len(clock_bytes) < 4:
                        raise ValueError("Respuesta RTC incompleta")
                    ts_int = int.from_bytes(clock_bytes[:4], byteorder="little")
                    from datetime import datetime
                    dt = datetime.fromtimestamp(ts_int, UTC)
                    clock_str = dt.strftime("%H:%M - %d/%m/%Y UTC")
                    rf_ctx.res.update({
                        "status": "ok",
                        "action": action,
                        "target_node": str(rf_ctx.req.target_node),
                        "data": data,
                        "clock": clock_str,
                        "telemetry": {"clock": clock_str} if clock_str else {},
                        "message": f"Respuesta de reloj obtenida: {clock_str}" if clock_str else "Respuesta de reloj y estado básico obtenida",
                    })
                    if clock_str:
                        await self._update_local_registry_from_params(str(rf_ctx.req.target_node), {"clock": clock_str})
                    self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{rf_ctx.req.target_node}/clock", json.dumps(rf_ctx.res), 1)
                    return rf_ctx.res

            elif action in ("req_acl", "acl") and hasattr(cmds, "req_acl_sync"):
                data = await run_sdk_command(self._ctx, mc, "req_acl_sync", target, min_timeout=4.0)
                if data is not None:
                    rf_ctx.res.update({
                        "status": "ok",
                        "action": action,
                        "target_node": str(rf_ctx.req.target_node),
                        "acl_data": data,
                        "message": "Tabla de control de acceso obtenida del repetidor",
                    })
                    self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{rf_ctx.req.target_node}/acl", json.dumps(rf_ctx.res), 1)
                    return rf_ctx.res

        except Exception as e:
            logging.debug(f"Fallo en ejecución de solicitud binaria/anónima ({action}): {e}")

        rf_ctx.res.update({"status": "error", "action": action, "target_node": str(rf_ctx.req.target_node),
                           "message": "Solicitud binaria sin respuesta válida del repetidor"})
        return rf_ctx.res

    @staticmethod
    def _login_event_name(event: Any) -> str:
        """Normaliza tipos SDK Enum y sus nombres/valores serializados."""
        event_type = event.get("type", event.get("event_type")) if isinstance(event, dict) else getattr(event, "type", None)
        event_name = getattr(event_type, "name", getattr(event_type, "value", event_type))
        return str(event_name or "").rsplit(".", 1)[-1].upper()

    async def _authenticate_repeater(self, rf_ctx: RfExecutionContext, min_timeout: float) -> tuple[bool, str]:
        """Exige confirmación de autenticación; MSG_SENT/ACK solo confirman transporte."""
        req = rf_ctx.req
        if len(req.password.encode("utf-8")) > 15 or "\x00" in req.password:
            return False, "Contraseña no representable: máximo oficial 15 bytes UTF-8 sin NUL"
        if req.mc and hasattr(req.mc, "commands") and hasattr(req.mc.commands, "send_login_sync"):
            try:
                login_ev = await run_sdk_command(self._ctx, req.mc, "send_login_sync", rf_ctx.dest_login_target, req.password, min_timeout=min_timeout)
            except Exception:
                return False, "No se pudo confirmar la autenticación del repetidor"
            if self._login_is_authorized(login_ev, rf_ctx.dest_login_target):
                return True, "Autenticación exitosa (LOGIN_SUCCESS)"
            return False, "Contraseña incorrecta o autenticación no confirmada por el repetidor"

        try:
            login_ev = await self._send_login_fallback(rf_ctx)
            if self._login_is_authorized(login_ev, rf_ctx.dest_login_target):
                return True, "Autenticación exitosa (LOGIN_SUCCESS)"
            event_type = getattr(login_ev, "type", None)
            success_type = getattr(type(event_type), "LOGIN_SUCCESS", None)
            dispatcher = getattr(req.mc, "dispatcher", None)
            if success_type is not None and dispatcher is not None and hasattr(dispatcher, "wait_for_event"):
                login_result = await dispatcher.wait_for_event(success_type, timeout=6.0)
                if self._login_is_authorized(login_result, rf_ctx.dest_login_target):
                    return True, "Autenticación exitosa (LOGIN_SUCCESS)"
                return False, "Autenticación no confirmada por el repetidor"
            resp_data = await self._wait_for_repeater_response(req.mc, rf_ctx.fut, timeout=6.0) or {}
        except Exception:
            return False, "No se pudo confirmar la autenticación del repetidor"
        event_name = self._login_event_name(resp_data)
        auth_status = resp_data.get("auth_status")
        if event_name in ("ERROR", "ERR", "COMMAND_ERROR", "LOGIN_FAILED") or auth_status == "failed":
            return False, "Autenticación rechazada por el repetidor"
        if self._login_is_authorized(resp_data, rf_ctx.dest_login_target):
            return True, "Autenticación exitosa (LOGIN_SUCCESS)"
        return False, "Autenticación no confirmada por el repetidor"

    def _login_is_authorized(self, event: Any, target: Any) -> bool:
        if self._login_event_name(event) != "LOGIN_SUCCESS":
            return False
        payload = event if isinstance(event, dict) else getattr(event, "payload", {})
        if not isinstance(payload, dict):
            return False
        if payload.get("is_admin") is False:
            return False
        prefix = str(payload.get("pubkey_prefix") or "").lower()
        target_key = target.get("public_key", "") if isinstance(target, dict) else str(target)
        return not prefix or str(target_key).lower().startswith(prefix)

    async def _execute_auth_command(self, rf_ctx: RfExecutionContext) -> dict[str, Any]:
        """Ejecuta inicio de sesión remoto en el repetidor."""
        req = rf_ctx.req
        if not req.password:
            return {"status": "error", "message": "La contraseña de administración no puede estar vacía"}

        login_success, message = await self._authenticate_repeater(rf_ctx, min_timeout=4.0)

        status_str = "ok" if login_success else "error"
        rf_ctx.res.update({
            "status": status_str,
            "action": "login",
            "target_node": str(req.target_node),
            "authenticated": login_success,
            "message": message,
            "cmd_dispatched": f"login {'*' * len(req.password)}",
        })
        self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{req.target_node}/status", json.dumps(rf_ctx.res), 1)
        return rf_ctx.res

    async def _execute_unit_command(self, rf_ctx: RfExecutionContext) -> dict[str, Any]:
        """Ejecuta un comando unitario con protección de Airtime LoRa."""
        req = rf_ctx.req
        cmd_text = self._ctx.repeater_manager.build_repeater_command_payload(req.action, req.admin_data)
        if not cmd_text:
            rf_ctx.res.update({
                "status": "error",
                "code": 422,
                "message": "Comando remoto no compatible o parámetros inválidos",
            })
            return rf_ctx.res
        can_send, rem_cd = self._ctx.repeater_manager.check_airtime_cooldown(str(req.target_node), is_full_query=False)
        if not can_send:
            return self._ctx.repeater_manager.build_cooldown_error_response(rem_cd)

        self._ctx.repeater_manager.record_command_sent(str(req.target_node), is_full_query=False)
        await self._flush_cooldowns()
        rf_ctx.cooldown_reserved = True
        if req.password and req.action != "login":
            authenticated, message = await self._send_pre_login(rf_ctx)
            if not authenticated:
                rf_ctx.res.update({"status": "error", "authenticated": False, "message": message})
                self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{req.target_node}/status", json.dumps(rf_ctx.res), 1)
                return rf_ctx.res
            await asyncio.sleep(0.35)
            # La respuesta de login no debe completar la espera del comando siguiente.
            self._waiters.unregister(rf_ctx.waiter_keys, rf_ctx.fut)
            async with self._waiters.expect_response(rf_ctx.waiter_keys) as command_fut:
                rf_ctx.fut = command_fut
                return await self._execute_unit_command_rf(rf_ctx, cmd_text)

        return await self._execute_unit_command_rf(rf_ctx, cmd_text)

    async def _execute_unit_command_rf(self, rf_ctx: RfExecutionContext, cmd_text: str) -> dict[str, Any]:
        """Envía el comando con su propia espera, después de validar el prelogin solicitado."""
        req = rf_ctx.req

        if not rf_ctx.cooldown_reserved:
            self._ctx.repeater_manager.record_command_sent(str(req.target_node), is_full_query=False)
            await self._flush_cooldowns()
            rf_ctx.cooldown_reserved = True
        t_start = time.perf_counter()

        await self._send_rf_command(req.mc, rf_ctx.dest_target, cmd_text, str(req.target_node), req.req_id, response_future=rf_ctx.fut)
        resp_data = await self._wait_for_repeater_response(req.mc, rf_ctx.fut, timeout=6.0) or {}

        elapsed = round((time.perf_counter() - t_start) * 1000, 1)
        raw_resp = resp_data.get("text") or resp_data.get("message") or ""
        resp_text = raw_resp[2:].strip() if raw_resp.startswith("> ") else raw_resp.strip()

        is_error = self._ctx.repeater_manager.response_is_error(raw_resp)

        redacted_cmd = redact_sensitive_command(cmd_text)
        rf_ctx.res["cmd_dispatched"] = redacted_cmd
        parameters = self._ctx.repeater_manager.command_parameters(cmd_text) if not is_error else {}
        confirmed = bool(parameters) and self._setter_response_confirmed(cmd_text, resp_text)
        if is_error:
            rf_ctx.res["status"] = "error"
            rf_ctx.res["error"] = self._safe_response_text(cmd_text, resp_text)
        else:
            rf_ctx.res["status"] = "ok" if (confirmed or (raw_resp and not parameters)) else "dispatched"
        if confirmed:
            if cmd_text.startswith("set radio ") or "reboot to apply" in resp_text.lower():
                rf_ctx.res["saved"] = redact_sensitive_mapping(parameters)
                rf_ctx.res["pending_reboot"] = True
            else:
                rf_ctx.res["applied"] = redact_sensitive_mapping(parameters)
                await self._update_local_registry_from_params(str(req.target_node), parameters)
        elif parameters and not is_error:
            rf_ctx.res["unconfirmed"] = redact_sensitive_mapping(parameters)
        rf_ctx.res["response"] = self._safe_response_text(cmd_text, resp_text) or f"Comando '{redacted_cmd}' transmitido por RF a {str(req.target_node)[:8]}"
        rf_ctx.res["message"] = rf_ctx.res["response"]

        sensitive = cmd_text.startswith(("password ", "set guest.password ", "get guest.password"))
        parsed_telem = self._ctx.repeater_manager.parse_command_response(cmd_text, raw_resp) if raw_resp and not is_error and not sensitive else {}
        if cmd_text == "get radio" and parsed_telem:
            rf_ctx.res["saved"] = parsed_telem
            rf_ctx.res["radio_settings_source"] = "saved_preferences"
            parsed_telem = {}
        telem = {**parsed_telem, **(resp_data.get("telemetry") or {})} if not is_error and not sensitive else {}
        if cmd_text == "get radio" or cmd_text.startswith("set radio "):
            telem = {key: value for key, value in telem.items() if key not in ("frequency", "bandwidth", "spreading_factor", "coding_rate")}
        if req.action.lower() in ("clock", "get clock", "req_clock", "time", "sync_clock", "clock sync") and resp_text and not is_error:
            clk_val = (parsed_telem.get("clock") if parsed_telem else None) or resp_text
            telem["clock"] = clk_val

        if telem:
            rf_ctx.res["telemetry"] = telem
            await self._update_local_registry_from_params(str(req.target_node), telem)

        if resp_data.get("rssi") is not None:
            rf_ctx.res["rssi"] = resp_data["rssi"]
        if resp_data.get("snr") is not None:
            rf_ctx.res["snr"] = resp_data["snr"]
        rf_ctx.res["rtt_ms"] = elapsed

        self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{req.target_node}/status", json.dumps(rf_ctx.res), 1)
        return rf_ctx.res

    @staticmethod
    def _setter_response_confirmed(command: str, text: str) -> bool:
        clean = text.removeprefix("> ").strip().lower()
        if command.startswith("password "):
            return clean.startswith("password now: ")
        return re.match(r"^\(?ok(?:\b|\s|$)", clean) is not None

    @staticmethod
    def _safe_response_text(command: str, text: str) -> str:
        if command.startswith(("password ", "set guest.password ", "get guest.password")):
            if not text:
                return ""
            if RepeaterManager.response_is_error(text):
                return "Error: operación de credenciales rechazada"
            return "Credencial confirmada" if RepeaterAdminExecutor._setter_response_confirmed(command, text) else "********"
        return redact_command_str(text)

    # --------------------------------------------------------------------------
    # Helpers Privados de Radio y Registro
    # --------------------------------------------------------------------------

    async def _ensure_radio_contact(
        self,
        mc: Any,
        dest_target: Any,
        target_name: str,
        out_path_override: str | None = None,
        out_path_len_override: int | None = None,
    ) -> None:
        """Asegura que el nodo destino esté presente en la tabla del firmware."""
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "add_contact"):
            try:
                pubkey = ""
                name = target_name
                out_path = ""
                out_path_len = -1
                out_path_hash_mode = 0
                node_type = 2  # ADV_TYPE_REPEATER
                lat = 0.0
                lon = 0.0

                if isinstance(dest_target, dict):
                    pubkey = str(dest_target.get("public_key", "")).strip()
                    name = str(dest_target.get("adv_name", dest_target.get("name", target_name))).strip()
                    out_path = str(dest_target.get("out_path", ""))
                    out_path_len = dest_target.get("out_path_len", -1)
                    out_path_hash_mode = dest_target.get("out_path_hash_mode", 0)
                    node_type = dest_target.get("type", 2)
                    lat = float(dest_target.get("adv_lat", dest_target.get("latitude", 0.0)) or 0.0)
                    lon = float(dest_target.get("adv_lon", dest_target.get("longitude", 0.0)) or 0.0)
                elif hasattr(dest_target, "to_radio_dict"):
                    d = dest_target.to_radio_dict()
                    pubkey = str(d.get("public_key", "")).strip()
                    name = str(d.get("adv_name", d.get("name", target_name))).strip()
                    out_path = str(d.get("out_path", ""))
                    out_path_len = d.get("out_path_len", -1)
                    out_path_hash_mode = d.get("out_path_hash_mode", 0)
                    node_type = d.get("type", 2)
                    lat = float(d.get("adv_lat", 0.0) or 0.0)
                    lon = float(d.get("adv_lon", 0.0) or 0.0)
                elif hasattr(dest_target, "public_key"):
                    pubkey = str(getattr(dest_target, "public_key", "")).strip()
                    name = getattr(dest_target, "name", "") or getattr(dest_target, "alias", target_name)
                    out_path = getattr(dest_target, "out_path", "") or ""
                    out_path_len = getattr(dest_target, "out_path_len", -1)
                    out_path_hash_mode = getattr(dest_target, "out_path_hash_mode", 0)
                    lat = float(getattr(dest_target, "latitude", 0.0) or 0.0)
                    lon = float(getattr(dest_target, "longitude", 0.0) or 0.0)
                elif isinstance(dest_target, str):
                    pubkey = dest_target.strip()

                if out_path_override is not None:
                    out_path = out_path_override
                if out_path_len_override is not None:
                    out_path_len = out_path_len_override

                if pubkey and re.fullmatch(r"[a-fA-F0-9]{64}", pubkey):
                    full_pk = pubkey.lower()
                    cached = getattr(mc, "_contacts", None)
                    if isinstance(cached, dict) and full_pk in cached and out_path_override is None and out_path_len_override is None:
                        return
                    clean_name = (name or target_name or f"Node_{full_pk[:6]}").encode("utf-8")[:31].decode("utf-8", "ignore")
                    clean_contact = {
                        "public_key": full_pk,
                        "adv_name": clean_name,
                        "type": int(node_type) if node_type is not None else 2,
                        "flags": 0,
                        "out_path": str(out_path or ""),
                        "out_path_len": int(out_path_len) if out_path_len is not None else -1,
                        "out_path_hash_mode": int(out_path_hash_mode) if out_path_hash_mode is not None else 0,
                        "last_advert": int(time.time()),
                        "adv_lat": float(lat or 0.0),
                        "adv_lon": float(lon or 0.0),
                    }
                    if isinstance(cached, dict) and full_pk in cached:
                        clean_contact = dict(cached[full_pk])
                        if out_path_override is not None:
                            clean_contact["out_path"] = out_path_override
                        if out_path_len_override is not None:
                            clean_contact["out_path_len"] = out_path_len_override
                    response = await run_sdk_command(self._ctx, mc, "add_contact", clean_contact)
                    require_success(response, "add_contact")
                    if hasattr(mc, "_contacts") and isinstance(mc._contacts, dict):
                        mc._contacts[full_pk] = clean_contact
            except Exception as e:
                raise RuntimeError("No se pudo registrar el contacto oficial en la radio") from e

    def _determine_target_hops(self, dest_target: Any, target_node: str) -> int:
        """Determina la distancia estimada en saltos hacia el nodo destino."""
        if isinstance(dest_target, dict):
            out_path_len = dest_target.get("out_path_len", -1)
            if isinstance(out_path_len, int) and out_path_len > 0:
                return out_path_len
            if dest_target.get("hops") is not None:
                try:
                    return int(dest_target["hops"])
                except Exception:
                    pass
        elif hasattr(dest_target, "out_path_len"):
            val = getattr(dest_target, "out_path_len", -1)
            if isinstance(val, int) and val > 0:
                return val

        if hasattr(self._ctx, "node_registry") and self._ctx.node_registry:
            node = self._ctx.node_registry.get_node(target_node)
            if node:
                if hasattr(node, "out_path_len") and isinstance(node.out_path_len, int) and node.out_path_len > 0:
                    return node.out_path_len
                if hasattr(node, "hop_count") and isinstance(node.hop_count, int) and node.hop_count > 0:
                    return node.hop_count
                if hasattr(node, "hops") and isinstance(node.hops, int) and node.hops > 0:
                    return node.hops
                if hasattr(node, "out_path") and node.out_path and len(node.out_path) >= 2:
                    return len(node.out_path) // 2
        return 0

    async def _send_rf_command(self, mc: Any, dest_target: Any, cmd_text: str, target_node: str, req_id: Any, response_future: asyncio.Future[dict[str, Any]] | None = None) -> None:
        """Envía un comando RF aplicando Pre-Send Delay si el nodo está a múltiples saltos."""
        hops = self._determine_target_hops(dest_target, target_node)
        if getattr(config, "REPEATER_PRE_SEND_DELAY_ENABLED", True) and hops >= 1:
            delay_s = float(getattr(config, "REPEATER_PRE_SEND_DELAY_S", 2.5))
            logging.info(
                f"[PRE-SEND-DELAY] Retardando emisión {delay_s}s hacia repetidor {str(target_node)[:8]} "
                f"({hops} saltos) para evitar colisión con eco LoRa."
            )
            await asyncio.sleep(delay_s)

        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_cmd"):
            if response_future is not None:
                # CommonCLI reflects exactly two prefix characters followed by '|'.
                tag = f"{self._command_tag_sequence % 256:02x}"
                self._command_tag_sequence += 1
                setattr(response_future, "_command_tag", tag)  # noqa: B010
                setattr(response_future, "_command_sensitive", cmd_text.startswith(("password ", "set guest.password ", "get guest.password")))  # noqa: B010
                cmd_text = f"{tag}|{cmd_text}"
            if len(cmd_text.encode("utf-8")) > 160 or any(ord(char) < 32 for char in cmd_text):
                raise ValueError("Comando CLI inválido: máximo oficial 160 bytes UTF-8 sin NUL")
            response = await run_sdk_command(self._ctx, mc, "send_cmd", dest_target, cmd_text)
            require_success(response, "send_cmd")
            return
        raise NotImplementedError("SDK sin send_cmd: no se permite fallback de administración a chat")


    async def _send_login_fallback(self, rf_ctx: RfExecutionContext) -> Any:
        """Usa el login binario disponible; nunca transmite la contraseña como texto CLI/chat."""
        req = rf_ctx.req
        if req.mc and hasattr(req.mc, "commands") and hasattr(req.mc.commands, "send_login"):
            login_ev = await run_sdk_command(self._ctx, req.mc, "send_login", rf_ctx.dest_login_target, req.password)
            if self._login_event_name(login_ev) in ("ERROR", "ERR", "COMMAND_ERROR", "LOGIN_FAILED"):
                raise RuntimeError("Autenticación rechazada por el repetidor")
            return login_ev
        raise RuntimeError("El SDK no dispone de autenticación binaria para el repetidor")

    async def _send_pre_login(self, rf_ctx: RfExecutionContext) -> tuple[bool, str]:
        """Confirma autenticación previa antes de ejecutar un comando."""
        return await self._authenticate_repeater(rf_ctx, min_timeout=4.0)
