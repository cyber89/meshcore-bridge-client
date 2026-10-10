"""
Transmission and messages REST controller.
Handles /api/tx and /api/messages/recent.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from src.contact_manager import PacketRecord
from src.rate_limiter import TxPriority
from src.web.controllers.base import BaseController, problem_details


class TxController(BaseController):
    """Controlador para transmisión de paquetes RF (Broadcast, Grupos, DM) e historial reciente."""

    async def send_tx(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Valida y ejecuta una transmisión hacia la red Mesh LoRa."""
        text = str(req_body.get("text", "")).strip()
        if not text:
            return problem_details(400, "Bad Request", "El campo 'text' no puede estar vacío", "missing_text_field")

        if "to" not in req_body and "target" not in req_body:
            return problem_details(
                400,
                "Bad Request",
                "Debe especificar explícitamente el destino en el campo 'to' o 'target' (ej. 'broadcast' o clave pública)",
                "missing_target_destination",
            )

        target = req_body.get("to") if "to" in req_body else req_body.get("target")
        if target is None:
            return problem_details(
                422,
                "Unprocessable Entity",
                "El campo de destino ('to'/'target') no puede ser nulo",
                "null_target_destination",
            )

        target_str = str(target).strip()
        if not target_str:
            return problem_details(
                422,
                "Unprocessable Entity",
                "El campo de destino ('to'/'target') no puede ser una cadena vacía. Especifique 'broadcast' para difusión general o una clave pública válida.",
                "empty_target_destination",
            )

        is_broadcast = target_str.lower() in ("broadcast", "public", "0xffff", "*") or target_str.lower().startswith("channel")
        if not is_broadcast:
            if self.ctx.bridge.node_registry.is_local_key(target_str):
                return problem_details(400, "Bad Request", "No se permite enviar mensajes de chat a la estación base local", "tx_to_local_forbidden")
            dest_node = self.ctx.bridge.node_registry.get_by_key_or_prefix(target_str)
            if dest_node and dest_node.role in ("REPEATER", "ROUTER"):
                return problem_details(400, "Bad Request", "Los repetidores son nodos de infraestructura y no procesan mensajes de chat", "tx_to_repeater_forbidden")

        try:
            ch_idx = int(req_body.get("channel_index", req_body.get("channel_idx", 0)))
        except (ValueError, TypeError):
            return problem_details(400, "Bad Request", "Invalid channel index", "invalid_channel_index")

        req_id = req_body.get("request_id", f"web_{int(time.time() * 1000)}")

        rate_limiter = getattr(self.ctx.bridge, "rate_limiter", None)
        if rate_limiter and hasattr(rate_limiter, "submit") and callable(rate_limiter.submit):
            try:
                submit_res = rate_limiter.submit(
                    payload=text,
                    priority=TxPriority.NORMAL,
                    target=str(target) if target else None,
                    channel_idx=ch_idx,
                    request_id=str(req_id),
                )
                if asyncio.iscoroutine(submit_res):
                    future = await submit_res
                else:
                    future = submit_res

                if asyncio.isfuture(future) or asyncio.iscoroutine(future):
                    async with asyncio.timeout(30.0):
                        res = await future
                else:
                    return problem_details(503, "Service Unavailable", "La cola no confirmó la admisión de la transmisión", "tx_submission_failed")
            except TimeoutError:
                err_msg = "Timeout esperando turno de transmisión en cola de Airtime LoRa (30s)"
                self.ctx.log_system_event("ERROR", f"Fallo en TX hacia {target}: {err_msg}", source="mesh_tx")
                return problem_details(408, "Request Timeout", err_msg, "tx_timeout")
            except Exception as ex:
                err_msg = str(ex) or "Fallo en cola de transmisión LoRa"
                if isinstance(ex, asyncio.QueueFull) or "Full" in err_msg or "RateLimit" in err_msg:
                    self.ctx.log_system_event("ERROR", f"Fallo en TX hacia {target}: {err_msg}", source="mesh_tx")
                    return problem_details(429, "Too Many Requests", err_msg, "tx_submission_failed")
                self.ctx.log_system_event("ERROR", f"Fallo en TX hacia {target}: {err_msg}", source="mesh_tx")
                return problem_details(503, "Service Unavailable", "No se pudo admitir la transmisión en la cola", "tx_submission_failed")
        else:
            return problem_details(503, "Service Unavailable", "La cola de transmisión no está disponible", "tx_submission_failed")
        failure = self.command_failure(res)
        if failure:
            return failure
        if isinstance(res, dict) and res.get("status") == "error":
            err_msg = res.get("error") or "Error en transmisión por radio LoRa"
            self.ctx.log_system_event("ERROR", f"Fallo en TX hacia {target}: {err_msg}", source="mesh_tx")
            return problem_details(400, "Bad Request", err_msg, "tx_transmission_failed", {"data": res})

        if target and not is_broadcast:
            self.ctx.bridge.node_registry.record_packet(PacketRecord(public_key=str(target), is_rx=False))

        self.ctx.log_system_event("INFO", f"Transmisión TX enviada a {target} (Ch {ch_idx})", source="mesh_tx")
        return 200, {"status": "ok", "data": res}

    async def get_recent_messages(self) -> tuple[int, dict[str, Any]]:
        """Devuelve los mensajes de chat recientemente capturados en memoria."""
        msgs = list(self.ctx.recent_messages)
        return 200, {
            "status": "ok",
            "data": msgs,
            "count": len(msgs),
        }
