"""
System and remaining protocol events strategy handler for RxEventRouter.
Handles ACK, PATH_UPDATE, MESSAGES_WAITING, and all other unhandled events.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.protocol_types import parse_sensor_push_payload
from src.routers.base import BaseRxHandler, RxMeta
from src.sensor_decoder import CayenneLPPDecoder
from src.shared_utils import is_empty_channel_slot, sanitize_public_payload


class SystemHandler(BaseRxHandler):
    """Manejador para eventos misceláneos y notificaciones del sistema."""

    def can_handle(self, meta: RxMeta, payload: dict[str, Any]) -> bool:
        unhandled = {
            "ACK", "PATH_UPDATE", "MESSAGES_WAITING", "NEW_CONTACT", "CONTACT_DELETED",
            "CONTACTS_FULL", "NEIGHBOURS_RESPONSE", "DISCOVER_RESPONSE", "BINARY_RESPONSE",
            "CONTROL_DATA", "MMA_RESPONSE", "ACL_RESPONSE", "SIGN_START", "SIGNATURE",
            "ALLOWED_REPEAT_FREQ", "DEFAULT_FLOOD_SCOPE", "STATS_PACKETS", "TUNING_PARAMS",
            "CUSTOM_VARS", "AUTOADD_CONFIG", "ADVERT_PATH", "CHANNEL_INFO", "CONTACT_URI",
            "STATUS_RESPONSE", "LOGIN_SUCCESS", "LOGIN_FAILED",
            "STATS_CORE", "STATS_RADIO"
        }
        clean_ev = meta.ev_upper.replace("EVENTTYPE.", "").strip()
        if clean_ev in unhandled or str(payload.get("event_type", "")).upper() in unhandled:
            return True
        return False

    async def _handle_binary_response(
        self,
        ctx: Any,
        router_ctx: Any,
        payload: dict[str, Any],
        meta: RxMeta,
    ) -> dict[str, Any] | None:
        """Correlate 0x8C BINARY_RESPONSE against active manual sensor subscriptions.

        Returns None if the event was promoted and dispatched as SENSOR telemetry,
        or returns a sanitized opaque binary_response dict without sender attribution.
        """
        raw_tag = str(payload.get("tag") or "").strip().lower().removeprefix("0x")
        raw_data = payload.get("data", payload.get("raw", ""))
        if isinstance(raw_data, (bytes, bytearray)):
            data_hex = bytes(raw_data).hex()
        else:
            data_hex = str(raw_data or "").strip().lower().removeprefix("0x")

        node_reg = getattr(router_ctx, "node_registry", None)
        db = getattr(node_reg, "database", None) if node_reg is not None else None
        if len(raw_tag) == 8 and db is not None and hasattr(db, "resolve_sensor_subscription_by_tag"):
            sub = await asyncio.to_thread(db.resolve_sensor_subscription_by_tag, raw_tag)
            if sub is not None:
                target_pk = str(sub.get("public_key", "")).strip().lower()
                contact = node_reg.get_contact(target_pk) if node_reg is not None else None
                if (
                    contact is not None
                    and not contact.is_local
                    and str(contact.role).upper() == "SENSOR"
                ):
                    parsed_push = parse_sensor_push_payload(data_hex)
                    if parsed_push is not None:
                        lpp_bytes = parsed_push["lpp_bytes"]
                        readings, summary = CayenneLPPDecoder.decode(lpp_bytes)
                        if readings:
                            confirmed = await asyncio.to_thread(
                                db.resolve_sensor_subscription_by_tag,
                                raw_tag,
                                sample_timestamp=int(parsed_push["sample_timestamp"]),
                            )
                            if confirmed is not None:
                                telem_payload: dict[str, Any] = {
                                    "type": "telemetry",
                                    "event_type": "telemetry",
                                    "telemetry_source": "sensor_subscription",
                                    "sender": target_pk,
                                    "sender_name": contact.alias or contact.name or f"Sensor [{target_pk[:8]}]",
                                    "role": "SENSOR",
                                    "sample_timestamp": int(parsed_push["sample_timestamp"]),
                                    "lpp_hex": lpp_bytes.hex(),
                                    "lpp_readings": [
                                        {
                                            "channel": r.channel,
                                            "data_type": r.data_type,
                                            "type_name": r.type_name,
                                            "value": r.value,
                                            "unit": r.unit,
                                        }
                                        for r in readings
                                    ],
                                }
                                if confirmed.get("scope_name"):
                                    telem_payload["scope_name"] = confirmed["scope_name"]
                                if summary:
                                    telem_payload.update(summary)
                                if meta.effective_rssi is not None:
                                    telem_payload["rssi"] = meta.effective_rssi
                                if meta.effective_snr is not None:
                                    telem_payload["snr"] = meta.effective_snr
                                ctx._handle_mesh_telemetry_msg(telem_payload)
                                return None

        byte_len = 0
        if data_hex and len(data_hex) % 2 == 0 and all(c in "0123456789abcdef" for c in data_hex):
            byte_len = len(data_hex) // 2
        opaque: dict[str, Any] = {
            "type": "binary_response",
            "event_type": "binary_response",
            "tag": "********",
            "data": data_hex,
            "byte_len": byte_len,
            "sender": None,
            "sender_known": False,
        }
        if meta.effective_rssi is not None:
            opaque["rssi"] = meta.effective_rssi
        if meta.effective_snr is not None:
            opaque["snr"] = meta.effective_snr
        return opaque

    async def handle(
        self,
        ctx: Any,
        payload: dict[str, Any],
        meta: RxMeta,
        raw_event: Any,
    ) -> bool:
        router_ctx = getattr(ctx, "_ctx", ctx)
        payload = sanitize_public_payload(payload)

        clean_ev = meta.ev_upper.replace("EVENTTYPE.", "").strip()
        event_type = payload.get("event_type", clean_ev).lower()
        if "event_type" not in payload:
            payload["event_type"] = event_type

        if event_type == "binary_response" or clean_ev == "BINARY_RESPONSE":
            opaque_payload = await self._handle_binary_response(ctx, router_ctx, payload, meta)
            if opaque_payload is None:
                return True
            payload = opaque_payload
            event_type = "binary_response"

        if event_type == "path_update" or clean_ev == "PATH_UPDATE":
            ctx._handle_path_update(payload, meta)

        # Tratamiento limpio para respuestas de canales del transceptor local
        if event_type == "channel_info" or clean_ev == "CHANNEL_INFO":
            ch_name = str(payload.get("channel_name", "")).strip()
            ch_sec = payload.get("channel_secret")
            if is_empty_channel_slot(ch_name, ch_sec):
                logging.debug(f"[ESTACIÓN LOCAL] Canal #{payload.get('channel_idx')} no configurado / vacío")
                return True
            ch_idx = int(payload.get("channel_idx", 0))
            ch_hash = str(payload.get("channel_hash", "--"))
            logging.info(f"[ESTACIÓN LOCAL] Canal #{ch_idx}: {ch_name} (Hash: {ch_hash})")
            if router_ctx.web_server and hasattr(router_ctx.web_server, "router") and hasattr(router_ctx.web_server.router, "channels"):
                router_ctx.web_server.router.channels[ch_idx] = {
                    "index": ch_idx,
                    "name": ch_name,
                    "channel_hash": ch_hash,
                }
            return True

        import config

        now_iso = datetime.now(UTC).isoformat()
        if "timestamp" not in payload:
            payload["timestamp"] = now_iso

        evt_json = json.dumps(payload, sort_keys=True)
        router_ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)
        if event_type in ("log_data", "rx_log_data"):
            router_ctx.mqtt.publish_safe(config.TOPIC_RX_LOG, evt_json, qos=0)

        if event_type not in ("log_data", "rx_log_data"):
            logging.info(f"[RX-SISTEMA] Evento de red: {event_type.upper()} | Carga: {payload}")

        if router_ctx.web_server:
            # The ingress worker already owns this asynchronous operation.
            await router_ctx.web_server.broadcast_event(payload)

        return True
