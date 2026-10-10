"""
MqttInboundDispatcher: Procesamiento de mensajes MQTT entrantes (n8n -> Bridge).
Extraído de MeshCoreBridge (God Class) para aislar la responsabilidad de entrada MQTT.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
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
        self._admission_lock = threading.Lock()
        self._admission_tokens: set[object] = set()
        self._scheduled_handles: dict[object, asyncio.Handle] = {}
        self._inbound_tasks: dict[asyncio.Task[Any], object] = {}
        self._closed = False

    def start(self) -> None:
        with self._admission_lock:
            self._closed = False

    async def close(self) -> None:
        """Stop queued callbacks and join only this dispatcher's owned tasks."""
        with self._admission_lock:
            self._closed = True
            handles = list(self._scheduled_handles.values())
            tasks = list(self._inbound_tasks)
            self._scheduled_handles.clear()
            self._admission_tokens.clear()
        for handle in handles:
            handle.cancel()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _release_admission(self, token: object, task: asyncio.Task[Any] | None = None) -> None:
        with self._admission_lock:
            self._admission_tokens.discard(token)
            self._scheduled_handles.pop(token, None)
            if task is not None:
                self._inbound_tasks.pop(task, None)

    def handle_incoming(self, topic: str, payload_str: str) -> None:
        """Punto de entrada sincrónico que programa el procesamiento asíncrono."""
        max_payload_size = getattr(config, "MQTT_MAX_PAYLOAD_BYTES", 128 * 1024)
        if len(payload_str.encode("utf-8")) > max_payload_size:
            logging.warning(
                f"Payload MQTT entrante en dispatcher excede el límite permitido ({len(payload_str.encode('utf-8'))} > {max_payload_size} B). Descartando en {topic}."
            )
            return

        max_inbound_tasks = getattr(config, "MAX_MQTT_INBOUND_TASKS", 50)
        token = object()
        with self._admission_lock:
            current_tasks = max(0, len(self._ctx.background_tasks) - len(self._inbound_tasks)) + len(self._admission_tokens)
            if self._closed or current_tasks >= max_inbound_tasks:
                logging.warning("MQTT admission rejected: pending=%d, limit=%d, topic=%s", current_tasks, max_inbound_tasks, topic)
                return
            self._admission_tokens.add(token)

        def schedule() -> None:
            with self._admission_lock:
                self._scheduled_handles.pop(token, None)
                if self._closed or token not in self._admission_tokens or loop.is_closed():
                    self._admission_tokens.discard(token)
                    return
                operation = self._process_mqtt_input(topic, payload_str)
                try:
                    task = loop.create_task(operation)
                except Exception:
                    operation.close()
                    self._admission_tokens.discard(token)
                    logging.exception("MQTT inbound task creation failed")
                    return
                self._inbound_tasks[task] = token
            task.add_done_callback(lambda completed: self._release_admission(token, completed))
            try:
                if self._ctx.register_task is not None:
                    self._ctx.register_task(task)
                else:
                    self._ctx.background_tasks.add(task)
                    task.add_done_callback(self._ctx.background_tasks.discard)
            except Exception:
                task.cancel()
                self._release_admission(token, task)
                logging.exception("MQTT task ownership registration failed")

        try:
            loop = self._ctx.loop or asyncio.get_running_loop()
            if loop.is_closed():
                self._release_admission(token)
                return
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                schedule()
            else:
                handle = loop.call_soon_threadsafe(schedule)
                with self._admission_lock:
                    if self._closed or token not in self._admission_tokens:
                        handle.cancel()
                    elif token not in self._inbound_tasks.values():
                        self._scheduled_handles[token] = handle
        except RuntimeError:
            self._release_admission(token)
            logging.error("No se pudo programar procesamiento MQTT")

    @property
    def topic_tx_status(self) -> str:
        if self._ctx.mqtt and hasattr(self._ctx.mqtt, "topic_tx_status"):
            return str(self._ctx.mqtt.topic_tx_status)
        return getattr(config, "TOPIC_TX_STATUS", "meshcore/tx/status")

    @property
    def topic_admin_stat(self) -> str:
        if self._ctx.mqtt and hasattr(self._ctx.mqtt, "topic_admin_stat"):
            return str(self._ctx.mqtt.topic_admin_stat)
        return getattr(config, "TOPIC_ADMIN_STAT", "meshcore/admin/status")

    @property
    def topic_admin_repeater(self) -> str:
        if self._ctx.mqtt and hasattr(self._ctx.mqtt, "topic_admin_repeater"):
            return str(self._ctx.mqtt.topic_admin_repeater).rstrip("/")
        prefix = getattr(self._ctx.mqtt, "topic_prefix", config.TOPIC_PREFIX)
        return f"{prefix}/admin/repeater"

    async def _process_mqtt_input(self, topic: str, payload_str: str) -> None:
        """Clasifica el tópico entrante y delega en el manejador correspondiente."""
        try:
            repeater_base = self.topic_admin_repeater
            if topic == self._ctx.mqtt.topic_tx:
                await self._handle_tx_request(payload_str)
            elif topic == self._ctx.mqtt.topic_admin_cmd:
                await self._handle_admin_request(payload_str)
            elif topic.startswith(repeater_base + "/"):
                relative = topic[len(repeater_base) + 1:].split("/")
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
            async with asyncio.timeout(30.0):
                res = await future
            status_payload = {
                "status": res.get("status", "sent"),
                "request_id": req_id,
                "target": target,
                "channel_idx": channel_idx,
                "queue_depth": self._ctx.rate_limiter.get_queue_depth(),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            if "error" in res:
                status_payload["error"] = res["error"]
            if "expected_ack" in res:
                status_payload["expected_ack"] = res["expected_ack"]
            if "delivery_tracking" in res:
                status_payload["delivery_tracking"] = res["delivery_tracking"]
            if "message" in res and "error" not in status_payload:
                status_payload["message"] = res["message"]
            self._ctx.mqtt.publish_safe(self.topic_tx_status, json.dumps(status_payload), qos=1)

        except TimeoutError:
            logging.error("TX future timeout, activating diagnostic alert")
            status_payload = {
                "status": "error",
                "error": "TX future timeout",
                "request_id": req_id,
                "target": target,
                "channel_idx": channel_idx,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self._ctx.mqtt.publish_safe(self.topic_tx_status, json.dumps(status_payload), qos=1)
        except Exception as e:
            logging.error(f"TX execution error: {e}", exc_info=True)
            status_payload = {
                "status": "error",
                "error": str(e) if str(e) else "TX failed",
                "request_id": req_id,
                "target": target,
                "channel_idx": channel_idx,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self._ctx.mqtt.publish_safe(self.topic_tx_status, json.dumps(status_payload), qos=1)

    def _reject_tx_input(self, error: str) -> None:
        self._ctx.mqtt.publish_safe(self.topic_tx_status, json.dumps({
            "status": "error", "error": error,
            "timestamp": datetime.now(UTC).isoformat(),
        }), qos=1)

    async def _handle_admin_request(self, payload_str: str) -> None:
        """Ejecuta comandos de administración sobre el hardware y publica el resultado."""
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            data = payload_str
        command = dict(data) if isinstance(data, dict) else {"action": str(data)}
        command.setdefault("action", command.get("command", ""))
        logging.info("[MQTT-ADMIN-IN] Solicitud de administración recibida")
        res = await self._ctx.handle_admin(command)
        if isinstance(res, dict):
            action = str(command.get("action", "")).strip()
            if action in (
                "get_custom_vars",
                "set_custom_vars",
                "set_custom_var",
                "delete_custom_var",
                "get_path_hash_mode",
                "set_path_hash_mode",
                "get_autoadd_config",
                "set_autoadd_config",
                "get_flood_scope",
                "set_flood_scope",
            ) or res.get("status") == "error":
                self._ctx.mqtt.publish_safe(self.topic_admin_stat, json.dumps(res), qos=1)
