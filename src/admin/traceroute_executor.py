"""
TracerouteExecutor: Ejecución especializada de diagnósticos de trazado de ruta RF (traceroute).
Descompone el cálculo de saltos, emisión RF y formateo de resultados multihop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import config
from src.admin.sdk_commands import require_success, run_sdk_command
from src.target_resolver import TargetResolver

if TYPE_CHECKING:
    from src.admin_handler import AdminContext


class TracerouteExecutor:
    """Ejecutor de diagnósticos de traceroute y visualización de saltos de red."""

    def __init__(
        self,
        ctx: AdminContext,
        get_local_config: Callable[[], dict[str, Any]],
        publish_safe: Callable[[str, str, int], None],
    ) -> None:
        self._ctx = ctx
        self._get_local_config = get_local_config
        self._publish_safe = publish_safe

    async def execute(
        self,
        admin_data: dict[str, Any],
        action: str,
        target_node: Any,
        res: dict[str, Any],
        mc: Any,
    ) -> dict[str, Any]:
        """Punto de entrada principal para trazar la ruta de saltos hacia un nodo."""
        target_str = str(target_node or "").strip()
        force = bool(admin_data.get("force", False))
        rep_mgr = getattr(self._ctx, "repeater_manager", None)
        if rep_mgr is not None and hasattr(rep_mgr, "load_state"):
            loading = rep_mgr.load_state()
            if asyncio.iscoroutine(loading):
                await loading
        if not force and rep_mgr is not None and hasattr(rep_mgr, "check_traceroute_cooldown"):
            chk_result = rep_mgr.check_traceroute_cooldown(target_str)
            if isinstance(chk_result, tuple) and len(chk_result) >= 2:
                can_send, rem_cd = chk_result[0], chk_result[1]
                if not can_send:
                    if hasattr(rep_mgr, "build_cooldown_error_response"):
                        res.update(rep_mgr.build_cooldown_error_response(rem_cd))
                    else:
                        res.update({"status": "error", "error": f"Cooldown activo ({rem_cd}s)"})
                    return res

        t_start = time.perf_counter()
        raw_path = admin_data.get("path")
        if raw_path is None and isinstance(admin_data.get("params"), dict):
            raw_path = admin_data.get("params", {}).get("path")

        path_list = self._parse_path_list(raw_path)
        if not path_list and target_str:
            d_node = self._find_node_info(target_str)
            if d_node and d_node.get("out_path"):
                hash_mode = int(d_node.get("out_path_hash_mode") or 0)
                hash_bytes = hash_mode + 1
                if hash_bytes == 3:
                    return {"status": "error", "message": "send_trace no representa hashes de ruta de 3 bytes"}
                path_hex = str(d_node["out_path"])
                hops = int(d_node.get("out_path_len") or len(path_hex) // (hash_bytes * 2))
                path_list = [path_hex[pos:pos + hash_bytes * 2] for pos in range(0, hops * hash_bytes * 2, hash_bytes * 2)]

        trace_path_arg, trace_flags = self._format_trace_hops(path_list)

        tag = random.randint(1, 0xFFFFFFFF)
        trace_data_payload: dict[str, Any] | None = None
        trace_waiter: asyncio.Task[Any] | None = None
        try:
            if rep_mgr is not None and hasattr(rep_mgr, "record_traceroute_sent"):
                rep_mgr.record_traceroute_sent(target_str)
                if hasattr(rep_mgr, "flush_state"):
                    writing = rep_mgr.flush_state()
                    if asyncio.iscoroutine(writing):
                        await writing
            from meshcore.events import EventType
            if mc and hasattr(mc, "dispatcher") and hasattr(mc.dispatcher, "wait_for_event"):
                # Subscribe before sending: a valid trace may arrive before MSG_SENT.
                trace_waiter = asyncio.create_task(mc.dispatcher.wait_for_event(EventType.TRACE_DATA, attribute_filters={"tag": tag}, timeout=None))
                await asyncio.sleep(0)
            send_ev = await self._dispatch_trace_rf(mc, trace_path_arg, trace_flags, tag=tag)
            require_success(send_ev, "send_trace")
            if trace_waiter is not None:
                suggested_to = 6.0
                if send_ev and hasattr(send_ev, "payload") and isinstance(send_ev.payload, dict):
                    raw_to = send_ev.payload.get("suggested_timeout")
                    if raw_to:
                        suggested_to = max(4.0, float(raw_to) / 800.0)
                async with asyncio.timeout(suggested_to):
                    trace_ev = await trace_waiter
                if trace_ev and hasattr(trace_ev, "payload") and isinstance(trace_ev.payload, dict):
                    trace_data_payload = trace_ev.payload
            if trace_data_payload is None:
                return {"status": "error", "action": "traceroute", "target_node": target_str, "timeout": True, "message": "Sin respuesta TRACE_DATA del firmware"}
        except Exception as error:
            return {"status": "error", "action": "traceroute", "target_node": target_str, "message": str(error)}
        finally:
            if trace_waiter is not None and not trace_waiter.done():
                trace_waiter.cancel()
                await asyncio.gather(trace_waiter, return_exceptions=True)

        rtt_ms = round((time.perf_counter() - t_start) * 1000, 1)

        hops_breakdown = self._build_hops_breakdown(path_list, str(target_node), rtt_ms, trace_data_payload)

        res.update({
            "status": "ok",
            "action": "traceroute",
            "target_node": str(target_node),
            "path": path_list,
            "total_hops": len(hops_breakdown) - 1,
            "total_rtt_ms": rtt_ms,
            "hops_breakdown": hops_breakdown,
            "timestamp": int(time.time()),
            "cmd_dispatched": f"send_trace({trace_path_arg or ''})",
        })

        res_json = json.dumps(res)
        self._publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/trace", res_json, 1)
        self._publish_safe(config.TOPIC_ADMIN_STAT, res_json, 1)
        if self._ctx.web_server:
            try:
                await self._ctx.web_server.broadcast_event({"type": "trace_data", "data": res})
            except Exception as e:
                logging.warning(f"Error difundiendo trace_data a la WebUI: {e}")
        return res

    def _parse_path_list(self, raw_path: Any) -> list[str]:
        """Convierte una cadena separada por comas o lista en una lista limpia de saltos."""
        if isinstance(raw_path, str):
            return [p.strip() for p in raw_path.split(",") if p.strip()]
        if isinstance(raw_path, (list, tuple)):
            return [str(p).strip() for p in raw_path if str(p).strip()]
        return []

    def _format_trace_hops(self, path_list: list[str]) -> tuple[str | None, int]:
        """Normaliza los saltos a hashes hexadecimales válidos para el firmware MeshCore."""
        if not path_list:
            return None, 0

        resolver = TargetResolver(mc_provider=lambda: None, node_registry=self._ctx.node_registry)
        formatted: list[str] = []
        for p in path_list:
            clean_p = p.strip()
            clean_hex = ""
            test_p = clean_p[2:] if clean_p.lower().startswith("0x") else clean_p
            if test_p and all(char in "0123456789abcdefABCDEF" for char in test_p):
                if len(test_p) in (2, 4) or (len(test_p) == 8 and not self._find_node_info(test_p)):
                    formatted.append(test_p.lower())
                    continue
            # 1. Intentar resolver con TargetResolver
            resolved = resolver.resolve(clean_p, min_hex_len=4)
            if resolved != clean_p:
                if isinstance(resolved, str):
                    clean_hex = resolved.lower()
                elif isinstance(resolved, dict):
                    clean_hex = str(resolved.get("public_key", "")).lower()
                elif hasattr(resolved, "public_key"):
                    clean_hex = str(getattr(resolved, "public_key", "")).lower()

            # 2. Si no resolvió, buscar por nombre o alias directamente
            if not clean_hex:
                n_info = self._find_node_info(clean_p)
                if n_info:
                    clean_hex = str(n_info.get("public_key", "")).lower()

            # 3. Si aún no resolvió, verificar si la entrada ya es hexadecimal válida
            if not clean_hex:
                test_p = clean_p[2:] if clean_p.lower().startswith("0x") else clean_p
                if all(c in "0123456789abcdefABCDEF" for c in test_p):
                    clean_hex = test_p.lower()

            if clean_hex.startswith("0x"):
                clean_hex = clean_hex[2:]

            if clean_hex:
                if len(clean_hex) >= 4:
                    formatted.append(clean_hex[:4])
                elif len(clean_hex) >= 2:
                    formatted.append(clean_hex[:2])
            else:
                raise ValueError(f"Salto de traceroute no resuelto: {clean_p}")

        if not formatted:
            return None, 0

        widths = {len(h) for h in formatted}
        if len(widths) != 1:
            raise ValueError("Todos los hashes de traceroute deben tener la misma longitud")
        width = next(iter(widths))
        return ",".join(formatted), {2: 0, 4: 1, 8: 2}[width]

    async def _dispatch_trace_rf(
        self, mc: Any, trace_path_arg: str | None, trace_flags: int, tag: int | None = None
    ) -> Any:
        """Despacha el comando send_trace si la API de radio lo soporta."""
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_trace"):
            try:
                kwargs: dict[str, Any] = {"path": trace_path_arg, "flags": trace_flags}
                if tag is not None:
                    kwargs["tag"] = tag
                return await run_sdk_command(self._ctx, mc, "send_trace", **kwargs)
            except Exception as e:
                logging.debug(f"Error invocando mc.commands.send_trace: {e}")
        return None

    def _build_hops_breakdown(
        self,
        path_list: list[str],
        target_node: str,
        rtt_ms: float,
        trace_data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Construye el detalle de cada salto del traceroute consultando el NodeRegistry y trace_data."""
        hops: list[dict[str, Any]] = []
        cfg = self._get_local_config()

        # Salto 0: Estación Base Local
        hops.append({
            "hop_index": 0,
            "pubkey": cfg.get("public_key", "local"),
            "name": cfg.get("name", "Estación Base"),
            "role": "LOCAL",
            "snr": None,
            "rtt_ms": 0.0,
            "snr_in": None,
            "snr_out": None,
            "rtt_segment_ms": 0.0,
        })

        # Extraer SNR medido en tiempo real por el firmware si TRACE_DATA fue recibido
        snr_by_hop: list[float | None] = []
        if trace_data and isinstance(trace_data.get("path"), list):
            for p_node in trace_data["path"]:
                if isinstance(p_node, dict) and "snr" in p_node:
                    if "hash" in p_node:
                        snr_by_hop.append(float(p_node["snr"]))
                    else:
                        # The final unhashed SNR is the packet received locally.
                        hops[0]["snr"] = float(p_node["snr"])
                        hops[0]["snr_in"] = float(p_node["snr"])

        # Saltos intermedios
        for idx, hop_key in enumerate(path_list, start=1):
            n_info = self._find_node_info(hop_key)
            h_name = (n_info.get("name") or n_info.get("alias")) if n_info else f"Repetidor {hop_key[:6]}"
            h_role = (n_info.get("role") or n_info.get("type")) if n_info else "REPEATER"

            measured_snr = snr_by_hop[idx - 1] if idx - 1 < len(snr_by_hop) else None
            h_snr = measured_snr if measured_snr is not None else (
                float(n_info["last_snr"]) if n_info and n_info.get("last_snr") is not None else None
            )

            hops.append({
                "hop_index": idx,
                "pubkey": hop_key,
                "name": h_name,
                "role": str(h_role),
                "snr": h_snr,
                "rtt_ms": None,
                "snr_in": h_snr,
                "snr_out": h_snr,
                "rtt_segment_ms": None,
            })

        # Destino final si no estaba incluido
        if not path_list or path_list[-1] != target_node:
            d_info = self._find_node_info(target_node)
            d_name = (d_info.get("name") or d_info.get("alias")) if d_info else f"Destino {target_node[:8]}"
            d_role = (d_info.get("role") or d_info.get("type")) if d_info else "CLIENT"

            final_snr = float(d_info["last_snr"]) if d_info and d_info.get("last_snr") is not None else None

            hops.append({
                "hop_index": len(hops),
                "pubkey": target_node,
                "name": d_name,
                "role": str(d_role),
                "snr": final_snr,
                "rtt_ms": rtt_ms,
                "snr_in": final_snr,
                "snr_out": final_snr,
                "rtt_segment_ms": None,
            })

        return hops

    def _find_node_info(self, key: str) -> dict[str, Any] | None:
        """Busca metadatos de un nodo por clave completa, prefijo, nombre o alias."""
        k = key.lower()
        if hasattr(self._ctx, "node_registry") and self._ctx.node_registry:
            if hasattr(self._ctx.node_registry, "find_by_name"):
                found = self._ctx.node_registry.find_by_name(key)
                if found:
                    if isinstance(found, dict):
                        return found
                    if hasattr(found, "to_dict"):
                        return found.to_dict()
                    return {"public_key": getattr(found, "public_key", ""), "name": getattr(found, "name", "")}
            if hasattr(self._ctx.node_registry, "list_nodes"):
                for n in self._ctx.node_registry.list_nodes():
                    pk = str(n.get("public_key", "")).lower()
                    name = str(n.get("name", "")).lower()
                    alias = str(n.get("alias", "")).lower()
                    if pk == k or (len(pk) >= 8 and (pk.startswith(k) or k.startswith(pk))):
                        return n
                    if name == k or alias == k:
                        return n
        return None
