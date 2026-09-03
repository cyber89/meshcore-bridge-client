"""
Telemetry and sensor strategy handler for RxEventRouter.
Handles environmental metrics, hardware telemetry and RF signal logs.
"""

from __future__ import annotations

from typing import Any

from src.contact_manager import PacketRecord, is_valid_node_key
from src.routers.base import BaseRxHandler, RxMeta


class TelemetryHandler(BaseRxHandler):
    """Manejador especializado para telemetría ambiental, voltajes y métricas de señal."""

    def can_handle(self, meta: RxMeta, payload: dict[str, Any]) -> bool:
        is_log = "LOG" in meta.ev_upper or payload.get("event_type") in ("log_data", "rx_log_data")
        is_explicit_telem = (
            "TELEM" in meta.ev_upper
            or "STATS" in meta.ev_upper
            or payload.get("event_type") in ("telemetry", "repeater_telemetry", "stats_radio", "stats_core")
            or "temperature_c" in payload
            or "battery_mv" in payload
            or "solar_mv" in payload
            or is_log
        )
        return is_explicit_telem

    async def handle(
        self,
        ctx: Any,
        payload: dict[str, Any],
        meta: RxMeta,
        raw_event: Any,
    ) -> bool:
        router_ctx = getattr(ctx, "_ctx", ctx)

        # Caso Log de RF / Métricas de señal a bajo nivel (LOG_DATA / RX_LOG_DATA)
        if "LOG" in meta.ev_upper or payload.get("event_type") in ("log_data", "rx_log_data"):
            rx_rssi = payload.get("rssi", payload.get("RSSI"))
            rx_snr = payload.get("snr", payload.get("SNR"))
            if rx_rssi is not None:
                try:
                    router_ctx.last_rx_rssi = int(rx_rssi)
                    if router_ctx.admin_handler and hasattr(router_ctx.admin_handler, "_ctx"):
                        router_ctx.admin_handler._ctx.last_rx_rssi = int(rx_rssi)
                except (ValueError, TypeError):
                    pass
            if rx_snr is not None:
                try:
                    router_ctx.last_rx_snr = float(rx_snr)
                    if router_ctx.admin_handler and hasattr(router_ctx.admin_handler, "_ctx"):
                        router_ctx.admin_handler._ctx.last_rx_snr = float(rx_snr)
                except (ValueError, TypeError):
                    pass
            if meta.sender and is_valid_node_key(meta.sender) and not meta.is_local_sender:
                router_ctx.node_registry.record_packet(
                    PacketRecord(
                        public_key=meta.sender,
                        is_rx=True,
                        rssi=router_ctx.last_rx_rssi,
                        snr=router_ctx.last_rx_snr,
                        hop_count=meta.hops,
                    )
                )
            return True

        if "event_type" not in payload:
            payload["event_type"] = "telemetry"

        ctx._handle_mesh_telemetry_msg(payload)
        return True
