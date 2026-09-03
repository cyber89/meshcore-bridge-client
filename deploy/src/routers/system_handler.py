"""
System and remaining protocol events strategy handler for RxEventRouter.
Handles ACK, PATH_UPDATE, MESSAGES_WAITING, and all other unhandled events.
"""

from __future__ import annotations

from typing import Any

from src.routers.base import BaseRxHandler, RxMeta


class SystemHandler(BaseRxHandler):
    """Manejador para eventos misceláneos y notificaciones del sistema."""

    def can_handle(self, meta: RxMeta, payload: dict[str, Any]) -> bool:
        unhandled = {
            "ACK", "PATH_UPDATE", "MESSAGES_WAITING", "NEW_CONTACT", "CONTACT_DELETED",
            "CONTACTS_FULL", "NEIGHBOURS_RESPONSE", "DISCOVER_RESPONSE", "BINARY_RESPONSE",
            "CONTROL_DATA", "MMA_RESPONSE", "ACL_RESPONSE", "SIGN_START", "SIGNATURE",
            "ALLOWED_REPEAT_FREQ", "DEFAULT_FLOOD_SCOPE", "STATS_PACKETS", "TUNING_PARAMS",
            "CUSTOM_VARS", "AUTOADD_CONFIG", "ADVERT_PATH", "CHANNEL_INFO", "CONTACT_URI",
            "LOG_DATA", "STATUS_RESPONSE", "LOGIN_SUCCESS", "LOGIN_FAILED", "RX_LOG_DATA",
            "STATS_CORE", "STATS_RADIO"
        }
        if meta.ev_upper in unhandled or str(payload.get("event_type", "")).upper() in unhandled:
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

        event_type = payload.get("event_type", meta.ev_upper).lower()
        if "event_type" not in payload:
            payload["event_type"] = event_type

        import json
        from datetime import datetime, timezone

        import config

        now_iso = datetime.now(timezone.utc).isoformat()
        if "timestamp" not in payload:
            payload["timestamp"] = now_iso

        evt_json = json.dumps(payload, sort_keys=True)
        router_ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)

        if router_ctx.web_server:
            import asyncio
            try:
                loop = router_ctx.loop or asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop:
                task = loop.create_task(router_ctx.web_server.broadcast_event(payload))
                router_ctx.background_tasks.add(task)
                task.add_done_callback(router_ctx.background_tasks.discard)

        return True
