"""tx_coordinator.py: Coordinación de transmisiones LoRa, métricas, validaciones y ACKs."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import config
from src.core.ack_tracker import AckTracker
from src.integrations.mqtt.topics import MqttTopics
from src.rate_limiter import TxItem, estimate_lora_airtime_ms
from src.rx_router import is_common_chat_message

logger = logging.getLogger(__name__)


class TxCoordinator:
    """Coordina la validación, ejecución en transceptor y registro de transmisiones salientes."""

    def __init__(
        self,
        node_registry_provider: Callable[[], Any],
        serial_adapter_provider: Callable[[], Any],
        rate_limiter_provider: Callable[[], Any],
        packet_buffer_provider: Callable[[], Any],
        web_server_provider: Callable[[], Any],
        database_provider: Callable[[], Any],
        mqtt_provider: Callable[[], Any],
        message_service_provider: Callable[[], Any],
        ack_tracker: AckTracker,
        persist_fn: Callable[..., Awaitable[Any]] | None,
        publish_chat_event_fn: Callable[[dict[str, Any]], Awaitable[Any]] | None,
        publish_mqtt_safe_fn: Callable[..., Any],
        broadcast_system_log_fn: Callable[[dict[str, Any]], None],
        tx_metrics_lock: asyncio.Lock,
        on_tx_increment: Callable[[bool], Awaitable[None]],
    ) -> None:
        self.node_registry_provider = node_registry_provider
        self.serial_adapter_provider = serial_adapter_provider
        self.rate_limiter_provider = rate_limiter_provider
        self.packet_buffer_provider = packet_buffer_provider
        self.web_server_provider = web_server_provider
        self.database_provider = database_provider
        self.mqtt_provider = mqtt_provider
        self.message_service_provider = message_service_provider
        self.ack_tracker = ack_tracker
        self.persist_fn = persist_fn
        self.publish_chat_event_fn = publish_chat_event_fn
        self.publish_mqtt_safe_fn = publish_mqtt_safe_fn
        self.broadcast_system_log_fn = broadcast_system_log_fn
        self.tx_metrics_lock = tx_metrics_lock
        self.on_tx_increment = on_tx_increment

    @staticmethod
    def parse_tx_input(item: Any) -> tuple[Any, str, int, str]:
        """Normaliza el payload de entrada de transmisión (dict, TxItem o string)."""
        if isinstance(item, dict):
            req_id = item.get("request_id", item.get("id"))
            target_raw = item.get("to", item.get("target", "broadcast"))
            target = str(target_raw) if target_raw is not None else "broadcast"
            raw_ch = item.get("channel_index", item.get("channel_idx", item.get("channel", 0)))
            ch_idx = int(raw_ch) if raw_ch is not None else 0
            text = str(item.get("text", item.get("message", "")))
            return req_id, target, ch_idx, text
        if isinstance(item, TxItem):
            req_id = item.request_id
            target = item.target or "broadcast"
            ch_idx = item.channel_idx
            if isinstance(item.payload, dict):
                text = str(item.payload.get("text", item.payload.get("message", "")))
            else:
                text = str(item.payload)
            return req_id, target, ch_idx, text
        return None, "broadcast", 0, str(item)

    def validate_tx_target(self, target_str: str, text: str, is_broadcast: bool) -> str | None:
        """Valida que el destino no viole reglas inmutables de dominio."""
        if is_broadcast:
            return None
        node_reg = self.node_registry_provider()
        if node_reg and node_reg.is_local_key(target_str):
            return "No se puede enviar mensajes de chat hacia el nodo local."
        if node_reg and node_reg.is_repeater_key(target_str):
            return "Los repetidores son nodos de infraestructura y no admiten mensajería de chat."
        return None

    def record_tx_packet(
        self,
        target: str,
        ch_idx: int,
        text: str,
        is_admin_cmd: bool,
        ack_payload: dict[str, Any],
    ) -> None:
        """Graba la trama de transmisión en el búfer circular y la notifica vía Web."""
        pkt_buf = self.packet_buffer_provider()
        if not pkt_buf:
            return
        node_reg = self.node_registry_provider()
        sender_pk = node_reg.get_local_pubkey() if node_reg else "LOCAL"
        try:
            tx_pkt = pkt_buf.record(
                direction="tx",
                channel_idx=ch_idx,
                packet_type="CHAT" if not is_admin_cmd else "ADMIN",
                sender=sender_pk or "LOCAL",
                sender_name="Estación Base Local",
                target=str(target),
                text=text,
                raw_bytes=text.encode("utf-8", errors="replace"),
                payload_dict=ack_payload,
            )
            web = self.web_server_provider()
            if tx_pkt and web:
                self.broadcast_system_log_fn(
                    {"type": "rf_packet", "event": "rf_packet", "data": tx_pkt.to_dict()}
                )
        except Exception as ex:
            logging.debug("Error grabando paquete TX en packet_buffer: %s", ex)

    def outgoing_chat(
        self, req_id: str, target: str, ch_idx: int, text: str, broadcast: bool
    ) -> dict[str, Any]:
        """Crea el objeto de evento de chat para transmisión saliente."""
        node_reg = self.node_registry_provider()
        kind = "public" if broadcast and ch_idx == 0 else "channel" if broadcast else "direct"
        event = {
            "type": kind,
            "event_type": kind,
            "msg_id": req_id,
            "sender": (node_reg.get_local_pubkey() if node_reg else None) or "local",
            "sender_name": "Local station",
            "text": text,
            "is_outgoing": True,
            "channel_idx": ch_idx,
            "status": "queued",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if not broadcast:
            event.update(dm_target=target, is_direct=True, recipient=target)
            event["recipient_name"] = (
                node_reg.get_contact_name(target)
                if node_reg and hasattr(node_reg, "get_contact_name")
                else target
            )
        return event

    async def execute_tx(self, item: Any) -> dict[str, Any]:
        """Ejecuta una transmisión sobre el transceptor LoRa gestionando reintentos, ACKs y logs."""
        req_id, target, ch_idx, text = self.parse_tx_input(item)
        req_id = str(req_id) if req_id is not None else f"tx_{uuid.uuid4().hex}"
        target_str = str(target).lower().strip()
        is_broadcast = target_str in ("broadcast", "public", "0xffff", "") or target_str.startswith(
            "channel"
        )

        clean_txt = text.strip().lower()
        first_token = clean_txt.split()[0] if clean_txt.split() else ""
        node_reg = self.node_registry_provider()
        is_rep_target = bool(
            node_reg and getattr(node_reg, "is_repeater_key", lambda k: False)(target_str)
        )
        is_explicit_admin = False
        if isinstance(item, dict):
            is_explicit_admin = bool(item.get("is_admin") or item.get("admin"))
        elif isinstance(item, TxItem):
            is_explicit_admin = bool(
                getattr(item, "is_admin", False) or getattr(item, "context", "") == "admin"
            )
        is_admin_cmd = is_explicit_admin or (
            is_rep_target
            and first_token
            in ("login", "cmd", "set", "get", "reboot", "ping", "trace", "ver", "status", "info")
        )

        if not is_admin_cmd and not is_broadcast:
            msg_service = self.message_service_provider()
            if msg_service:
                validation = msg_service.validate_tx_request(text, target_str, ch_idx)
                if not validation.is_valid:
                    return {"status": "error", "error": validation.error, "request_id": req_id}
                target = target_str = validation.clean_target

        err_msg = self.validate_tx_target(target_str, text, is_broadcast)
        if err_msg:
            return {"status": "error", "error": err_msg, "request_id": req_id}

        if hasattr(item, "future") and item.future is not None and item.future.cancelled():
            logging.info(
                "TxRateLimiter: Transmisión cancelada/expirada antes de radio (req_id=%s)", req_id
            )
            return {"status": "cancelled", "error": "TX cancelled or expired", "request_id": req_id}

        chat_event: dict[str, Any] | None = None
        if not is_admin_cmd and is_common_chat_message(text):
            chat_event = self.outgoing_chat(req_id, target_str, ch_idx, text, is_broadcast)
            if self.publish_chat_event_fn is not None:
                await self.publish_chat_event_fn(chat_event)

        status_val = "sent"
        error_detail: str | None = None
        expected_ack_hex: str | None = None
        serial_adapter = self.serial_adapter_provider()
        try:
            if not serial_adapter or not serial_adapter.is_connected:
                raise ConnectionError("Puerto serial / MeshCore no conectado")

            target_arg = str(target) if not is_broadcast else None
            send_res = await serial_adapter.send_message(
                text=text, target=target_arg, channel_idx=ch_idx
            )
            if not isinstance(send_res, dict) or str(send_res.get("status", "")).lower() not in (
                "ok",
                "sent",
                "success",
            ):
                raise RuntimeError("El transceptor no confirmó la transmisión")
            expected_ack_hex = send_res.get("expected_ack")
            res_obj = send_res.get("event")
            if res_obj is not None:
                ev_type = getattr(res_obj, "type", None)
                if str(getattr(ev_type, "name", ev_type)).upper() == "ERROR":
                    raise RuntimeError("El transceptor rechazó la transmisión")

            await self.on_tx_increment(True)

        except Exception as e:
            await self.on_tx_increment(False)
            pkt_buf = self.packet_buffer_provider()
            if pkt_buf and getattr(pkt_buf, "metrics_aggregator", None):
                pkt_buf.metrics_aggregator.record_error("timeouts")
            status_val = "error"
            logging.warning("Transmisión no confirmada: %s", type(e).__name__)
            error_detail = "No se confirmó la transmisión por radio"

        ack_payload: dict[str, Any] = {
            "status": status_val,
            "request_id": req_id,
            "target": target,
            "channel_idx": ch_idx,
            "expected_ack": expected_ack_hex,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if error_detail:
            ack_payload["error"] = error_detail

        database = self.database_provider()
        if status_val == "sent" and expected_ack_hex and req_id:
            ack_payload["delivery_tracking"] = self.ack_tracker.register(
                expected_ack_hex, req_id, str(target)
            )
            if database is not None and ack_payload["delivery_tracking"] == "registered":
                try:
                    if self.persist_fn is not None:
                        tracking = await self.persist_fn(
                            database.save_pending_ack,
                            expected_ack_hex,
                            req_id,
                            str(target),
                            time.time(),
                        )
                    else:
                        tracking = database.save_pending_ack(
                            expected_ack_hex, req_id, str(target), time.time()
                        )
                except Exception as error:
                    tracking = "persistence_failed"
                    ack_payload["storage_error"] = True
                    logging.error(
                        "Radio send confirmed; pending delivery persistence failed: %s",
                        type(error).__name__,
                        extra={"skip_broadcast": True},
                    )
                ack_payload["delivery_tracking"] = tracking
                if tracking not in ("registered", "persistence_failed"):
                    self.ack_tracker.remove(expected_ack_hex)

        if chat_event is not None:
            chat_event["status"] = "sent" if status_val == "sent" else "failed"
            if ack_payload.get("delivery_tracking") == "registered":
                chat_event["expected_ack"] = expected_ack_hex
            try:
                if self.publish_chat_event_fn is not None:
                    await self.publish_chat_event_fn(chat_event)
            except Exception as error:
                ack_payload["storage_error"] = True
                logging.error(
                    "Radio outcome recorded in memory; chat persistence failed: %s",
                    type(error).__name__,
                    extra={"skip_broadcast": True},
                )

        mqtt_obj = self.mqtt_provider()
        topics_obj = getattr(mqtt_obj, "topics", None) if mqtt_obj else None
        status_topic = str(
            getattr(mqtt_obj, "topic_tx_status", None)
            or (topics_obj.tx_status if isinstance(topics_obj, MqttTopics) else None)
            or getattr(config, "TOPIC_TX_STATUS", "meshcore/tx/status")
        )
        self.publish_mqtt_safe_fn(status_topic, json.dumps(ack_payload), qos=1)
        self.record_tx_packet(str(target), ch_idx, text, is_admin_cmd, ack_payload)

        rate_limiter = self.rate_limiter_provider()
        if status_val == "sent":
            if not isinstance(item, TxItem) and rate_limiter:
                try:
                    plen = len(text.encode("utf-8")) if text else 32
                    est_ms = estimate_lora_airtime_ms(plen, rate_limiter.radio_config)
                    rate_limiter.airtime_tracker.record_tx(
                        airtime_ms=est_ms,
                        channel_idx=ch_idx,
                        target=str(target) if target else None,
                    )
                except Exception as ex:
                    logging.debug("Error registrando airtime de TX directa en rate_limiter: %s", ex)

            dest_label = (
                "Broadcast / Canal 0"
                if is_broadcast
                else f"Nodo [{target[:8] if len(str(target)) >= 8 else target}]"
            )
            logging.info(
                "[TX-TRANSMISIÓN] Destino: %s | Canal: #%d | Tamaño: %d bytes | ACK esperado: %s",
                dest_label,
                ch_idx,
                len(text),
                expected_ack_hex or "None",
            )
        else:
            logging.warning(
                "[TX-ERROR] Fallo transmitiendo a %s (Canal #%d): %s",
                target,
                ch_idx,
                error_detail or "Desconocido",
            )

        return ack_payload
