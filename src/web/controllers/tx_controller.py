"""
Transmission and messages REST controller.
Handles /api/tx and /api/messages/recent.
Delegates domain validation, invariant enforcement and transmission queuing to MessageService.
"""

from __future__ import annotations

import time
from typing import Any

from src.application.messaging import MessageService
from src.rate_limiter import TxPriority
from src.web.controllers.base import ApiContext, BaseController, problem_details


class TxController(BaseController):
    """Controlador para transmisión de paquetes RF (Broadcast, Grupos, DM) e historial reciente."""

    def __init__(self, ctx: ApiContext) -> None:
        super().__init__(ctx)
        self.message_service: MessageService = (
            getattr(ctx.bridge, "message_service", None)
            or MessageService(
                node_registry=getattr(ctx.bridge, "node_registry", None),
                rate_limiter=getattr(ctx.bridge, "rate_limiter", None),
                database=getattr(ctx.bridge, "database", None),
                log_system_event=self.ctx.log_system_event,
            )
        )

    async def send_tx(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Valida y ejecuta una transmisión hacia la red Mesh LoRa delegando en MessageService."""
        if "to" not in req_body and "target" not in req_body:
            return problem_details(
                400,
                "Bad Request",
                "Debe especificar explícitamente el destino en el campo 'to' o 'target' (ej. 'broadcast' o clave pública)",
                "missing_target_destination",
            )

        raw_text = req_body.get("text", "")
        target = req_body.get("to") if "to" in req_body else req_body.get("target")
        raw_ch = req_body.get("channel_index", req_body.get("channel_idx", 0))
        req_id = req_body.get("request_id", f"web_{int(time.time() * 1000)}")

        service = getattr(self.ctx.bridge, "message_service", self.message_service)
        res = await service.submit_chat(
            text=raw_text,
            target=target,
            channel_idx=raw_ch,
            priority=TxPriority.NORMAL,
            request_id=str(req_id),
            timeout=30.0,
        )

        if res.status != "sent":
            title = "Request Timeout" if res.http_code == 408 else (
                "Too Many Requests" if res.http_code == 429 else (
                    "Service Unavailable" if res.http_code == 503 else (
                        "Unprocessable Entity" if res.http_code == 422 else "Bad Request"
                    )
                )
            )
            extra = {"data": res.data} if res.data else None
            return problem_details(
                res.http_code,
                title,
                res.error or "Error en transmisión por radio LoRa",
                res.error_code or "tx_failed",
                extra,
            )

        return 200, {"status": "ok", "data": res.data}

    async def get_recent_messages(self) -> tuple[int, dict[str, Any]]:
        """Keep the recent-message envelope while reading durable station history."""
        service = getattr(self.ctx.bridge, "message_service", self.message_service)
        msgs = await service.get_recent_messages(limit=200)
        if not msgs and hasattr(self.ctx, "recent_messages"):
            msgs = list(self.ctx.recent_messages)
        return 200, {
            "status": "ok",
            "data": msgs,
            "count": len(msgs),
        }
