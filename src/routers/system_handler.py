"""
System and remaining protocol events strategy handler for RxEventRouter.
Handles ACK, PATH_UPDATE, MESSAGES_WAITING, and all other unhandled events.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.routers.base import BaseRxHandler, RxMeta
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

        now_iso = datetime.now(timezone.utc).isoformat()
        if "timestamp" not in payload:
            payload["timestamp"] = now_iso

        evt_json = json.dumps(payload, sort_keys=True)
        router_ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)
        if event_type in ("log_data", "rx_log_data"):
            router_ctx.mqtt.publish_safe(config.TOPIC_RX_LOG, evt_json, qos=0)

        if event_type not in ("log_data", "rx_log_data"):
            logging.info(f"[RX-SISTEMA] Evento de red: {event_type.upper()} | Carga: {payload}")

        if router_ctx.web_server:
            try:
                loop = router_ctx.loop or asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop:
                task = loop.create_task(router_ctx.web_server.broadcast_event(payload))
                router_ctx.background_tasks.add(task)
                task.add_done_callback(router_ctx.background_tasks.discard)

        return True
