"""
Repeater admin and diagnostic strategy handler for RxEventRouter.
Handles repeater CLI responses, delivery acknowledgments, pings and traceroutes.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import config
from src.contact_manager import NodeContactUpdate, PacketRecord, is_valid_node_key
from src.routers.base import BaseRxHandler, RxMeta


class RepeaterAdminHandler(BaseRxHandler):
    """Manejador especializado para respuestas administrativas de repetidores y traceroutes."""

    def can_handle(self, meta: RxMeta, payload: dict[str, Any]) -> bool:
        p_type_upper = str(payload.get("type", "")).upper()
        clean_ev = meta.ev_upper.replace("EVENTTYPE.", "").strip()
        clean_p_type = p_type_upper.replace("EVENTTYPE.", "").strip()
        is_ack = (
            clean_ev == "ACK"
            or clean_ev.startswith("ACK_")
            or clean_ev.endswith("_ACK")
            or clean_p_type == "ACK"
            or clean_p_type.startswith("ACK_")
            or clean_p_type.endswith("_ACK")
            or payload.get("event_type") in ("ack", "delivered", "message_delivered")
        )
        is_trace = (
            "TRACE" in clean_ev
            or "TRACE" in clean_p_type
            or payload.get("event_type") == "trace"
        )
        return is_ack or is_trace

    async def handle(
        self,
        ctx: Any,
        payload: dict[str, Any],
        meta: RxMeta,
        raw_event: Any,
    ) -> bool:
        router_ctx = getattr(ctx, "_ctx", ctx)
        p_type_upper = str(payload.get("type", "")).upper()
        clean_ev = meta.ev_upper.replace("EVENTTYPE.", "").strip()
        clean_p_type = p_type_upper.replace("EVENTTYPE.", "").strip()
        is_ack = (
            clean_ev == "ACK"
            or clean_ev.startswith("ACK_")
            or clean_ev.endswith("_ACK")
            or clean_p_type == "ACK"
            or clean_p_type.startswith("ACK_")
            or clean_p_type.endswith("_ACK")
            or payload.get("event_type") in ("ack", "delivered", "message_delivered")
        )

        # Caso ACK / Entrega Confirmada
        if is_ack:
            if meta.is_local_sender:
                return True
            ack_code_raw = payload.get("ack_code", payload.get("code"))
            if ack_code_raw is None:
                ack_code = ""
            elif isinstance(ack_code_raw, bool):
                ack_code = ""
            elif isinstance(ack_code_raw, int):
                ack_code = ack_code_raw.to_bytes(4, "little").hex() if 0 < ack_code_raw <= 0xFFFFFFFF else ""
            elif isinstance(ack_code_raw, (bytes, bytearray)):
                ack_code = ack_code_raw.hex().lower()
            else:
                ack_code = str(ack_code_raw).strip().lower()
                if ack_code.startswith("0x"):
                    ack_code = ack_code[2:]

            # Si el código ACK está vacío o compuesto exclusivamente por ceros, descartar silenciosamente
            if len(ack_code) != 8 or any(char not in "0123456789abcdef" for char in ack_code) or set(ack_code) <= {"0"}:
                logging.debug(
                    f"[RX-ACK] Trama ACK nula/vacía descartada (código: '{ack_code or '00000000'}'). "
                    f"Ignorando confirmación no asociada a mensaje real."
                )
                return True

            ack_msg_id = payload.get("msg_id", payload.get("id", payload.get("request_id")))
            trip_time = payload.get("trip_time_ms", payload.get("trip_time", payload.get("rtt_ms")))

            bridge = getattr(router_ctx, "bridge", None) or getattr(router_ctx, "_bridge", None)
            if ack_code and bridge and hasattr(bridge, "resolve_pending_ack"):
                ack_info = bridge.resolve_pending_ack(ack_code)
                # Incoming IDs cannot bypass lifetime/capacity/one-shot tracking.
                ack_msg_id = None
                if isinstance(ack_info, dict):
                    ack_msg_id = ack_info.get("req_id")
                    if not meta.sender and ack_info.get("target"):
                        meta.sender = str(ack_info.get("target"))

            rtt_str = f" | RTT: {trip_time} ms" if trip_time is not None else ""
            if ack_msg_id:
                logging.info(
                    f"[RX-ACK] Mensaje {ack_msg_id} confirmado por la malla. "
                    f"Código: {ack_code}{rtt_str}"
                )
            else:
                logging.info(
                    f"[RX-ACK] Confirmación recibida de la malla (Código: {ack_code}{rtt_str}). "
                    f"Mensaje no correlacionado localmente."
                )

            ack_evt_data = {
                "event_type": "message_delivered",
                "type": "message_delivered",
                "msg_id": ack_msg_id,
                "ack_code": ack_code,
                "trip_time_ms": trip_time,
                "sender": meta.sender,
            }

            if router_ctx.web_server and ack_msg_id:
                await router_ctx.web_server.broadcast_event(ack_evt_data)

            # Actualizar presencia del emisor del ACK si es un nodo remoto
            ack_sender = meta.sender or str(payload.get("sender") or payload.get("from") or "").strip()
            if ack_sender and is_valid_node_key(ack_sender) and not router_ctx.node_registry.is_local_key(ack_sender):
                eff_rssi = meta.effective_rssi
                eff_snr = meta.effective_snr
                router_ctx.node_registry.record_packet(
                    PacketRecord(
                        public_key=ack_sender,
                        is_rx=True,
                        rssi=eff_rssi,
                        snr=eff_snr,
                        hop_count=meta.effective_hops,
                    )
                )
                updated_node = router_ctx.node_registry.add_or_update(
                    ack_sender,
                    NodeContactUpdate(
                        last_seen=time.time(),
                        last_rssi=eff_rssi,
                        last_snr=eff_snr,
                    ),
                )
                if updated_node and router_ctx.web_server:
                    await router_ctx.web_server.broadcast_event({
                        "type": "contact_updated",
                        "event_type": "contact_updated",
                        "contact": updated_node.to_dict(),
                    })

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
                await router_ctx.web_server.broadcast_event({
                    "type": "trace_data",
                    "data": payload,
                })
            return True

        return False
