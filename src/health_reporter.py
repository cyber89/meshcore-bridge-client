"""
HealthReporter: Reporte periódico de métricas de salud del bridge en MQTT.
Extraído de MeshCoreBridge (God Class) para aislar la responsabilidad de observabilidad.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import config
from src.contact_manager import NodeRegistry
from src.rate_limiter import TxRateLimiter
from src.rx_router import BridgeCounters
from src.serial_driver import BaseSerialAdapter


@dataclass(slots=True)
class HealthContext:
    """Dependencias necesarias para construir y publicar el payload de salud."""
    mqtt: Any
    serial_adapter: BaseSerialAdapter
    node_registry: NodeRegistry
    rate_limiter: TxRateLimiter
    counters: BridgeCounters
    start_time: float
    bridge: Any | None = None


class HealthReporter:
    """Publica periódicamente métricas de salud en meshcore/bridge/health."""

    def __init__(self, ctx: HealthContext, interval_sec: float) -> None:
        self._ctx = ctx
        self._interval_sec = interval_sec
        self._task: asyncio.Task[None] | None = None

    def start(self) -> asyncio.Task[None]:
        """Lanza la tarea periódica de reporte de salud."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="HealthReporter")
        return self._task

    async def stop(self) -> None:
        """Detiene limpiamente la tarea periódica."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def build_payload(self) -> dict[str, Any]:
        """Construye el snapshot de métricas de salud del bridge."""
        serial_conn = bool(self._ctx.serial_adapter.is_connected)
        mqtt_conn = bool(getattr(self._ctx.mqtt, "is_connected", False))

        mqtt_required = True
        capabilities_dict: dict[str, Any] | None = None
        bridge_obj = getattr(self._ctx, "bridge", None)
        if bridge_obj is not None and hasattr(bridge_obj, "capabilities") and bridge_obj.capabilities is not None:
            caps = bridge_obj.capabilities
            capabilities_dict = caps.to_dict()
            mqtt_required = caps.mqtt_local.is_active or caps.mqtt_external.is_active
        elif not getattr(config, "MQTT_ENABLED", True):
            mqtt_required = False

        status = "healthy" if serial_conn and (mqtt_conn or not mqtt_required) else "degraded"

        payload: dict[str, Any] = {
            "status": status,
            "uptime_seconds": int(time.time() - self._ctx.start_time),
            "serial_port": getattr(self._ctx.serial_adapter, "port", config.SERIAL_PORT),
            "serial_connected": serial_conn,
            "mqtt_connected": mqtt_conn,
            "known_mesh_nodes": self._ctx.node_registry.get_count(),
            "tx_queue_depth": self._ctx.rate_limiter.get_queue_depth(),
            "total_rx_packets": self._ctx.counters.rx_count,
            "total_tx_packets": self._ctx.counters.tx_count,
            "total_tx_errors": self._ctx.counters.tx_error_count,
            "total_processing_errors": self._ctx.counters.err_count,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if capabilities_dict is not None:
            payload["capabilities"] = capabilities_dict
        return payload

    async def _loop(self) -> None:
        """Bucle periódico de publicación de métricas."""
        while True:
            try:
                await asyncio.sleep(self._interval_sec)
                payload = await self.build_payload()
                topic_health = getattr(self._ctx.mqtt, "topic_health", config.TOPIC_HEALTH)
                if hasattr(self._ctx.mqtt, "publish_safe"):
                    self._ctx.mqtt.publish_safe(topic_health, json.dumps(payload), qos=0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error en reporte de salud: {e}")
