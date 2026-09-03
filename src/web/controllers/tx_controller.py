"""
Transmission and messages REST controller.
Handles /api/tx and /api/messages/recent.
"""

from __future__ import annotations

import time
from typing import Any

from src.contact_manager import PacketRecord
from src.web.controllers.base import BaseController, problem_details


class TxController(BaseController):
    """Controlador para transmisión de paquetes RF (Broadcast, Grupos, DM) e historial reciente."""

    async def send_tx(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Valida y ejecuta una transmisión hacia la red Mesh LoRa."""
        text = str(req_body.get("text", "")).strip()
        if not text:
            return problem_details(400, "Bad Request", "El campo 'text' no puede estar vacío", "missing_text_field")

        target = req_body.get("to", req_body.get("target", "broadcast"))
        try:
            ch_idx = int(req_body.get("channel_index", req_body.get("channel_idx", 0)))
        except (ValueError, TypeError):
            return problem_details(400, "Bad Request", "Invalid channel index", "invalid_channel_index")

        req_id = req_body.get("request_id", f"web_{int(time.time() * 1000)}")

        tx_item = {
            "to": target,
            "channel_index": ch_idx,
            "text": text,
            "request_id": req_id,
        }

        res = await self.ctx.bridge._execute_tx(tx_item)
        if isinstance(res, dict) and res.get("status") == "error":
            err_msg = res.get("error") or "Error en transmisión por radio LoRa"
            self.ctx.log_system_event("ERROR", f"Fallo en TX hacia {target}: {err_msg}", source="mesh_tx")
            return problem_details(400, "Bad Request", err_msg, "tx_transmission_failed", {"data": res})

        if target and str(target).lower() not in ("broadcast", "public", "0xffff"):
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
