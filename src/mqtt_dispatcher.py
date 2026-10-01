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
    register_task: Callable[[asyncio.Task[Any]], asyncio.Task[Any]] | None = None


class MqttInboundDispatcher:
    """Enruta mensajes recibidos desde MQTT (TX o Admin) hacia la cola de eventos."""

    def __init__(self, ctx: MqttInboundContext) -> None:
        self._ctx = ctx

    def handle_incoming(self, topic: str, payload_str: str) -> None:
        """Punto de entrada sincrónico que programa el procesamiento asíncrono."""
        def schedule() -> None:
            if loop.is_closed():
                return
            task = loop.create_task(self._process_mqtt_input(topic, payload_str))
            if self._ctx.register_task is not None:
                self._ctx.register_task(task)
            else:
                self._ctx.background_tasks.add(task)
                task.add_done_callback(self._ctx.background_tasks.discard)

        try:
            loop = self._ctx.loop or asyncio.get_running_loop()
            if loop.is_closed():
                return
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                schedule()
            else:
                loop.call_soon_threadsafe(schedule)
        except RuntimeError:
            logging.error("No se pudo programar procesamiento MQTT")

    async def _process_mqtt_input(self, topic: str, payload_str: str) -> None:
        """Clasifica el tópico entrante y delega en el manejador correspondiente."""
        try:
            if topic == self._ctx.mqtt.topic_tx:
                await self._handle_tx_request(payload_str)
            elif topic == self._ctx.mqtt.topic_admin_cmd:
                await self._handle_admin_request(payload_str)
            elif topic.startswith(config.TOPIC_ADMIN_REPEATER.rstrip("/") + "/"):
                relative = topic[len(config.TOPIC_ADMIN_REPEATER.rstrip("/")) + 1:].split("/")
                if len(relative) != 2 or not relative[0] or relative[1] != "cmd":
                    return
                target_node = relative[0]
                try:
                    data = json.loads(payload_str)
                except json.JSONDecodeError:
                    data = payload_str
                command = dict(data) if isinstance(data, dict) else {"action": str(data)}
                command["target_node"] = target_node
                await self._ctx.handle_admin(command)
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
        except json.JSONDecodeError:
            if payload_str.lstrip().startswith(("{", "[")):
                self._reject_tx_input("Solicitud JSON de transmisión inválida")
                return
            data = payload_str

        try:
            if isinstance(data, dict):
                raw_text = data.get("text", data.get("message", ""))
                if not isinstance(raw_text, str):
                    raise ValueError("El texto debe ser una cadena")
                text = raw_text
                target = data.get("dest_node_id", data.get("target", data.get("to", data.get("recipient"))))
                if target is not None and not isinstance(target, str):
                    raise ValueError("El destino debe ser una cadena")
                raw_ch = data.get("channel_idx", data.get("channel_index", data.get("channel", 0)))
                if isinstance(raw_ch, bool) or not isinstance(raw_ch, (str, int, type(None))):
                    raise ValueError("El canal debe ser un entero")
                channel_idx = int(raw_ch) if raw_ch is not None else 0
                req_id = data.get("request_id", data.get("id"))
                prio_val = data.get("priority", 1)
                priority = TxPriority(prio_val) if prio_val in (0, 1, 2) else TxPriority.NORMAL
            elif isinstance(data, str):
                text = data
            else:
                raise ValueError("La transmisión debe ser texto o un objeto JSON")
        except (ValueError, TypeError):
            # Invalid control objects never become chat text, which could leak
            # credentials or transmit to the default broadcast destination.
            self._reject_tx_input("Campos de transmisión inválidos")
            return

        if not text:
            return

        logging.info(
            f"[MQTT-TX-IN] Solicitud TX recibida vía MQTT: '{text[:50]}' -> Destino: {target or 'broadcast'} (Canal #{channel_idx})"
        )

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
        except Exception as e:
            logging.error(f"TX execution error: {e}", exc_info=True)
            status_payload = {
                "status": "error",
                "error": str(e) if str(e) else "TX failed",
                "request_id": req_id,
                "target": target,
                "channel_idx": channel_idx,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._ctx.mqtt.publish_safe(config.TOPIC_TX_STATUS, json.dumps(status_payload), qos=1)

    def _reject_tx_input(self, error: str) -> None:
        self._ctx.mqtt.publish_safe(config.TOPIC_TX_STATUS, json.dumps({
            "status": "error", "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), qos=1)

    async def _handle_admin_request(self, payload_str: str) -> None:
        """Ejecuta comandos de administración sobre el hardware."""
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            data = payload_str
        command = dict(data) if isinstance(data, dict) else {"action": str(data)}
        command.setdefault("action", command.get("command", ""))
        logging.info("[MQTT-ADMIN-IN] Solicitud de administración recibida")
        await self._ctx.handle_admin(command)
