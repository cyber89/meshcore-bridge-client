"""
Repeater admin and diagnostic strategy handler for RxEventRouter.
Handles repeater CLI responses, delivery acknowledgments, pings and traceroutes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import config
from src.routers.base import BaseRxHandler, RxMeta


class RepeaterAdminHandler(BaseRxHandler):
    """Manejador especializado para respuestas administrativas de repetidores y traceroutes."""

    def can_handle(self, meta: RxMeta, payload: dict[str, Any]) -> bool:
        p_type_upper = str(payload.get("type", "")).upper()
        return (
            "ACK" in meta.ev_upper
            or "ACK" in p_type_upper
            or payload.get("event_type") in ("ack", "delivered", "message_delivered")
            or "TRACE" in meta.ev_upper
            or "TRACE" in p_type_upper
            or payload.get("event_type") == "trace"
        )

    async def handle(
        self,
        ctx: Any,
        payload: dict[str, Any],
        meta: RxMeta,
        raw_event: Any,
    ) -> bool:
        router_ctx = getattr(ctx, "_ctx", ctx)
        p_type_upper = str(payload.get("type", "")).upper()

        # Caso ACK / Entrega Confirmada
        if (
            "ACK" in meta.ev_upper
            or "ACK" in p_type_upper
            or payload.get("event_type") in ("ack", "delivered", "message_delivered")
        ):
            ack_code = payload.get("ack_code", payload.get("code", 0))
            ack_msg_id = payload.get("msg_id", payload.get("id", payload.get("request_id")))
            trip_time = payload.get("trip_time_ms", payload.get("rtt_ms"))

            logging.info(
                f"[RX-ACK] Mensaje {ack_msg_id} confirmado por la malla. "
                f"Código: {ack_code} | RTT: {trip_time} ms"
            )

            ack_evt_data = {
                "event_type": "message_delivered",
                "type": "message_delivered",
                "msg_id": ack_msg_id,
                "ack_code": ack_code,
                "trip_time_ms": trip_time,
                "sender": meta.sender,
            }

            if router_ctx.web_server:
                t = asyncio.create_task(router_ctx.web_server.broadcast_event(ack_evt_data))
                router_ctx.background_tasks.add(t)
                t.add_done_callback(router_ctx.background_tasks.discard)

            router_ctx.mqtt.publish_safe(
                config.TOPIC_TX_STATUS,
                json.dumps(ack_evt_data),
                qos=1,
            )
            return True

        # Caso Trace Path / Traceroute
        if (
            "TRACE" in meta.ev_upper
            or "TRACE" in p_type_upper
            or payload.get("event_type") == "trace"
        ):
            path_nodes = payload.get("path", [])
            snr_there = path_nodes[0].get("snr") if path_nodes and isinstance(path_nodes[0], dict) else None
            snr_back = path_nodes[-1].get("snr") if path_nodes and isinstance(path_nodes[-1], dict) else None
            rssi_trace = payload.get("rssi", payload.get("RSSI", meta.effective_rssi))
            tag = payload.get("tag")

            logging.info(
                f"[RX-TRACE] De: {meta.sender or 'Desconocido'} -> Para: Estación Base Local | "
                f"Saltos: {len(path_nodes)} | Tag: {tag}"
            )

            admin = getattr(router_ctx, "admin_handler", None)
            if admin and hasattr(admin, "notify_ping_response"):
                admin.notify_ping_response(
                    str(tag) if tag else meta.sender,
                    {
                        "snr_there": snr_there,
                        "snr_back": snr_back,
                        "rssi": rssi_trace,
                        "tag": tag,
                        "source": "trace",
                    },
                )

            if router_ctx.web_server:
                t = asyncio.create_task(router_ctx.web_server.broadcast_event({
                    "type": "trace_data",
                    "data": payload,
                }))
                router_ctx.background_tasks.add(t)
                t.add_done_callback(router_ctx.background_tasks.discard)
            return True

        return False
