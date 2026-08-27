"""
MqttInboundDispatcher: Procesamiento de mensajes MQTT entrantes (n8n -> Bridge).
Extraído de MeshCoreBridge (God Class) para aislar la responsabilidad de entrada MQTT.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import config
from src.mqtt_client import AsyncBridgeMQTTClient
from src.rate_limiter import TxPriority, TxRateLimiter


@dataclass(slots=True)
class MqttInboundContext:
    """Dependencias del despachador MQTT entrante."""
    loop: asyncio.AbstractEventLoop | None
    background_tasks: set[asyncio.Task[Any]]
    mqtt: AsyncBridgeMQTTClient
    rate_limiter: TxRateLimiter
    handle_admin: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class MqttInboundDispatcher:
    """Enruta mensajes recibidos desde MQTT (TX o Admin) hacia la cola de eventos."""

    def __init__(self, ctx: MqttInboundContext) -> None:
        self._ctx = ctx

    def handle_incoming(self, topic: str, payload_str: str) -> None:
        """Punto de entrada sincrónico que programa el procesamiento asíncrono."""
        try:
            loop = self._ctx.loop or asyncio.get_running_loop()
            task = loop.create_task(self._process_mqtt_input(topic, payload_str))
            self._ctx.background_tasks.add(task)
            task.add_done_callback(self._ctx.background_tasks.discard)
        except RuntimeError as e:
            logging.error(f"No se pudo programar procesamiento de mensaje MQTT entrante ({topic}): {e}")

    async def _process_mqtt_input(self, topic: str, payload_str: str) -> None:
        """Clasifica el tópico entrante y delega en el manejador correspondiente."""
        try:
            if topic == self._ctx.mqtt.topic_tx:
                await self._handle_tx_request(payload_str)
            elif topic == self._ctx.mqtt.topic_admin_cmd:
                await self._handle_admin_request(payload_str)
            elif topic.startswith(config.TOPIC_ADMIN_REPEATER):
                # Extraer prefijo de nodo: {prefix}/admin/repeater/{target_node}/cmd
                parts = topic.split("/")
                target_node = parts[3] if len(parts) > 3 else "repeater"
                try:
                    data = json.loads(payload_str)
                    if isinstance(data, dict):
                        data["target_node"] = target_node
                        await self._ctx.handle_admin(data)
                    else:
                        await self._ctx.handle_admin({"action": str(data), "target_node": target_node})
                except Exception:
                    await self._ctx.handle_admin({"action": payload_str, "target_node": target_node})
        except Exception as e:
            logging.error(f"Error procesando mensaje MQTT entrante ({topic}): {e}", exc_info=True)

    async def _handle_tx_request(self, payload_str: str) -> None:
        """Parsea solicitud de transmisión y la encola en el Rate Limiter."""
        text = ""
        target = None
        channel_idx = 0
        req_id = None
        priority = TxPriority.NORMAL

        try:
            data = json.loads(payload_str)
            if isinstance(data, dict):
                text = str(data.get("text", data.get("message", "")))
                target = data.get("dest_node_id", data.get("target", data.get("to", data.get("recipient"))))
                raw_ch = data.get("channel_idx", data.get("channel_index", data.get("channel", 0)))
                channel_idx = int(raw_ch) if raw_ch is not None else 0
                req_id = data.get("request_id", data.get("id"))
                prio_val = data.get("priority", 1)
                priority = TxPriority(prio_val) if prio_val in (0, 1, 2) else TxPriority.NORMAL
            else:
                text = str(data)
        except (json.JSONDecodeError, ValueError):
            text = payload_str

        if not text:
            return

        future = await self._ctx.rate_limiter.submit(
            payload=text,
            priority=priority,
            target=str(target) if target else None,
            channel_idx=channel_idx,
            request_id=str(req_id) if req_id else None,
        )

        try:
            res = await asyncio.wait_for(future, timeout=30.0)
            status_payload = {
                "status": res.get("status", "sent"),
                "request_id": req_id,
                "target": target,
                "channel_idx": channel_idx,
                "queue_depth": self._ctx.rate_limiter.get_queue_depth(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._ctx.mqtt.publish_safe(config.TOPIC_TX_STATUS, json.dumps(status_payload), qos=1)
        except asyncio.TimeoutError:
            logging.error("TX future timeout, activating diagnostic alert")
            status_payload = {
                "status": "error",
                "error": "TX future timeout",
                "request_id": req_id,
                "target": target,
                "channel_idx": channel_idx,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._ctx.mqtt.publish_safe(config.TOPIC_TX_STATUS, json.dumps(status_payload), qos=1)

    async def _handle_admin_request(self, payload_str: str) -> None:
        """Ejecuta comandos de administración sobre el hardware."""
        action = ""
        params: dict[str, Any] = {}
        try:
            data = json.loads(payload_str)
            if isinstance(data, dict):
                action = str(data.get("action", data.get("command", "")))
                params = data.get("params", data)
            else:
                action = str(data)
        except Exception:
            action = payload_str

        await self._ctx.handle_admin(params if isinstance(params, dict) else {"action": action})
