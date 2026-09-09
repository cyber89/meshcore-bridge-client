"""
Packets REST controller for LoRa sniffer packet inspection, filtering and export.
Handles /api/packets and /api/packets/export.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from src.web.controllers.base import BaseController, problem_details


class PacketsController(BaseController):
    """Controlador para inspección, filtrado y exportación de paquetes LoRa."""

    async def get_packets(
        self,
        limit: int = 100,
        offset: int = 0,
        direction: str = "",
        p_type: str = "",
    ) -> tuple[int, dict[str, Any]]:
        """Devuelve un lote paginado de paquetes capturados en el búfer."""
        packet_buf = getattr(self.ctx, "packet_buffer", None)
        if not packet_buf:
            bridge = getattr(self.ctx, "bridge", None)
            packet_buf = getattr(bridge, "packet_buffer", None)

        if not packet_buf:
            return problem_details(503, "Service Unavailable", "PacketBuffer no inicializado", "packet_buffer_unavailable")

        packets, total_count = packet_buf.get_packets(
            limit=limit,
            offset=offset,
            direction=direction if direction else None,
            p_type=p_type if p_type else None,
        )

        return 200, {
            "status": "ok",
            "data": packets,
            "count": len(packets),
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "capture_enabled": getattr(packet_buf, "capture_enabled", True),
        }

    async def export_packets(self, export_format: str = "json") -> tuple[int, dict[str, Any]]:
        """Exporta los paquetes almacenados en el formato solicitado (pcap, json, csv)."""
        packet_buf = getattr(self.ctx, "packet_buffer", None)
        if not packet_buf:
            bridge = getattr(self.ctx, "bridge", None)
            packet_buf = getattr(bridge, "packet_buffer", None)

        if not packet_buf:
            return problem_details(503, "Service Unavailable", "PacketBuffer no inicializado", "packet_buffer_unavailable")

        fmt = (export_format or "json").strip().lower()
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        if fmt == "pcap":
            pcap_bytes = packet_buf.generate_pcap()
            filename = f"meshcore_packets_{now_str}.pcap"
            b64_data = base64.b64encode(pcap_bytes).decode("ascii")
            return 200, {
                "status": "ok",
                "format": "pcap",
                "filename": filename,
                "mime_type": "application/vnd.tcpdump.pcap",
                "base64_data": b64_data,
                "size_bytes": len(pcap_bytes),
            }

        if fmt == "csv":
            csv_text = packet_buf.generate_csv()
            filename = f"meshcore_packets_{now_str}.csv"
            return 200, {
                "status": "ok",
                "format": "csv",
                "filename": filename,
                "mime_type": "text/csv; charset=utf-8",
                "text_data": csv_text,
                "size_bytes": len(csv_text.encode("utf-8")),
            }

        # Formato JSON por defecto
        json_text = packet_buf.generate_json()
        filename = f"meshcore_packets_{now_str}.json"
        return 200, {
            "status": "ok",
            "format": "json",
            "filename": filename,
            "mime_type": "application/json; charset=utf-8",
            "text_data": json_text,
            "size_bytes": len(json_text.encode("utf-8")),
        }

    async def clear_packets(self) -> tuple[int, dict[str, Any]]:
        """Limpia el búfer de paquetes en memoria."""
        packet_buf = getattr(self.ctx, "packet_buffer", None)
        if not packet_buf:
            bridge = getattr(self.ctx, "bridge", None)
            packet_buf = getattr(bridge, "packet_buffer", None)

        if packet_buf:
            packet_buf.clear()

        return 200, {
            "status": "ok",
            "message": "Búfer de paquetes RF limpiado con éxito",
        }
