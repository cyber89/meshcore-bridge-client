"""
Direct message strategy handler for RxEventRouter.
Handles direct messages (DMs) between mesh nodes with strict loopback guard.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.routers.base import BaseRxHandler, MeshMessageEvent, RxMeta


class DirectMessageHandler(BaseRxHandler):
    """Manejador especializado para mensajería directa (DM)."""

    def can_handle(self, meta: RxMeta, payload: dict[str, Any]) -> bool:
        p_type_upper = str(payload.get("type", "")).upper()
        is_direct = (
            "CONTACT" in meta.ev_upper
            or "DIRECT" in meta.ev_upper
            or "PRIV" in p_type_upper
            or payload.get("event_type") == "direct"
        )
        return is_direct and bool(meta.text)

    async def handle(
        self,
        ctx: Any,
        payload: dict[str, Any],
        meta: RxMeta,
        raw_event: Any,
    ) -> bool:
        if meta.is_local_sender:
            logging.debug("[RX-DM] Ignorando mensaje directo originado en la propia estación local (loopback guard).")
            return True

        router_ctx = getattr(ctx, "_ctx", ctx)
        raw_txt_type = payload.get("txt_type", payload.get("text_type", 0))
        try:
            txt_type = int(raw_txt_type)
        except (ValueError, TypeError):
            txt_type = 0

        msg_evt = MeshMessageEvent(
            sender=meta.sender,
            sender_name=meta.sender_name,
            text=meta.text,
            channel_idx=meta.channel_idx,
            rssi=meta.effective_rssi,
            snr=meta.effective_snr,
            txt_type=txt_type,
        )

        loop = router_ctx.loop or asyncio.get_running_loop()
        task = loop.create_task(ctx._handle_mesh_direct_msg(msg_evt))
        router_ctx.background_tasks.add(task)
        task.add_done_callback(router_ctx.background_tasks.discard)
        return True
