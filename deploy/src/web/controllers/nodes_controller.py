"""
Nodes and analytics REST controller.
Handles /api/nodes, /api/lqi, /api/analytics, /api/rf/heatmap, and /api/airtime/stats.
"""

from __future__ import annotations

from typing import Any

from src.web.controllers.base import BaseController


class NodesController(BaseController):
    """Controlador para listado de nodos, métricas LQI, Heatmap RF y analítica."""

    async def list_nodes(self, limit: int = 100, offset: int = 0) -> tuple[int, dict[str, Any]]:
        """Devuelve el listado paginado de nodos de la red Mesh."""
        all_nodes = self.ctx.bridge.node_registry.list_nodes()
        nodes_page = all_nodes[offset : offset + limit]

        return 200, {
            "status": "ok",
            "data": nodes_page,
            "count": len(nodes_page),
            "total_count": len(all_nodes),
            "limit": limit,
            "offset": offset,
        }

    async def get_lqi(self) -> tuple[int, dict[str, Any]]:
        """Devuelve las métricas de calidad de enlace LQI para todos los vecinos."""
        if hasattr(self.ctx.bridge, "node_registry") and hasattr(self.ctx.bridge.node_registry, "get_all_lqi_metrics"):
            lqi_data = self.ctx.bridge.node_registry.get_all_lqi_metrics()
        else:
            lqi_data = []

        return 200, {
            "status": "ok",
            "data": lqi_data,
            "count": len(lqi_data),
        }

    async def get_analytics(self) -> tuple[int, dict[str, Any]]:
        """Devuelve el resumen consolidado de telemetría y tráfico de la malla."""
        analytics = self.ctx.bridge.node_registry.get_analytics_summary()
        analytics["queue_depth"] = self.ctx.bridge.rate_limiter.get_queue_depth()
        analytics["deduplication_count"] = getattr(self.ctx.bridge, "dup_count", 0)

        ser_adapter = getattr(self.ctx.bridge, "serial_adapter", None)
        ser_connected = bool(ser_adapter.is_hardware_alive()) if ser_adapter and hasattr(ser_adapter, "is_hardware_alive") else bool(getattr(ser_adapter, "is_connected", False))
        mqtt_client = getattr(self.ctx.bridge, "mqtt", getattr(self.ctx.bridge, "mqtt_client", None))
        mqtt_connected = bool(getattr(mqtt_client, "is_connected", False)) if mqtt_client else False

        analytics["serial_connected"] = ser_connected
        analytics["mqtt_connected"] = mqtt_connected

        bridge_rx = getattr(self.ctx.bridge, "rx_count", 0)
        bridge_tx = getattr(self.ctx.bridge, "tx_count", 0)
        bridge_err = getattr(self.ctx.bridge, "err_count", 0) + getattr(self.ctx.bridge, "tx_error_count", 0)

        sum_rx = analytics["summary"]["total_rx_packets"]
        sum_tx = analytics["summary"]["total_tx_packets"]
        sum_err = analytics["summary"]["total_errors"]

        final_rx = max(bridge_rx, sum_rx)
        final_tx = max(bridge_tx, sum_tx)
        final_err = max(bridge_err, sum_err)
        total_p = final_rx + final_tx

        analytics["summary"]["total_rx_packets"] = final_rx
        analytics["summary"]["total_tx_packets"] = final_tx
        analytics["summary"]["total_errors"] = final_err
        analytics["summary"]["global_error_rate_pct"] = round((final_err / (total_p or 1)) * 100, 2)

        return 200, {"status": "ok", "data": analytics}

    async def get_rf_heatmap(self) -> tuple[int, dict[str, Any]]:
        """Genera los puntos geolocalizados para el Heatmap táctico RF."""
        points: list[dict[str, Any]] = []
        nodes = self.ctx.bridge.node_registry.list_nodes()

        for node in nodes:
            lat = node.get("latitude") or node.get("lat")
            lon = node.get("longitude") or node.get("lon")
            if lat is not None and lon is not None:
                try:
                    f_lat = float(lat)
                    f_lon = float(lon)
                    if not (f_lat == 0.0 and f_lon == 0.0):
                        points.append({
                            "public_key": node.get("public_key"),
                            "name": node.get("name") or node.get("alias") or "Nodo",
                            "role": node.get("role", "CLIENT"),
                            "lat": f_lat,
                            "lon": f_lon,
                            "rssi": node.get("last_rssi"),
                            "snr": node.get("last_snr"),
                            "noise_floor": node.get("noise_floor_dbm"),
                            "is_local": bool(node.get("is_local") or node.get("role") == "LOCAL"),
                        })
                except (ValueError, TypeError):
                    continue

        return 200, {
            "status": "ok",
            "data": {
                "points": points,
                "count": len(points),
            },
        }

    async def get_airtime_stats(self) -> tuple[int, dict[str, Any]]:
        """Devuelve el consumo y presupuesto horario de transmisión LoRa."""
        limiter = getattr(self.ctx.bridge, "rate_limiter", None)
        if limiter and hasattr(limiter, "airtime_tracker"):
            stats = limiter.airtime_tracker.get_stats()
            return 200, {"status": "ok", "data": stats}

        return 200, {
            "status": "ok",
            "data": {
                "hourly_used_ms": 0,
                "hourly_budget_ms": 360000,
                "hourly_duty_cycle_pct": 0.0,
            },
        }
