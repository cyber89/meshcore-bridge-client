"""
Channel message strategy handler for RxEventRouter.
Handles broadcast and group channel messages across LoRa mesh.
"""

from __future__ import annotations

from typing import Any

from src.routers.base import BaseRxHandler, MeshMessageEvent, RxMeta


class ChannelMessageHandler(BaseRxHandler):
    """Manejador especializado para mensajes de canal broadcast y grupos."""

    def can_handle(self, meta: RxMeta, payload: dict[str, Any]) -> bool:
        p_type_upper = str(payload.get("type", "")).upper()
        is_direct = (
            "CONTACT" in meta.ev_upper
            or "DIRECT" in meta.ev_upper
            or "PRIV" in p_type_upper
            or payload.get("event_type") == "direct"
        )
        is_channel = (
            "CHANNEL" in meta.ev_upper
            or "CHAN" in p_type_upper
            or payload.get("event_type") in ("public", "channel")
            or (bool(meta.text) and not is_direct)
        )
        return is_channel and bool(meta.text)

    async def handle(
        self,
        ctx: Any,
        payload: dict[str, Any],
        meta: RxMeta,
        raw_event: Any,
    ) -> bool:
        if meta.is_local_sender:
            return True
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

        await ctx._handle_mesh_channel_msg(msg_evt)
        return True
