"""
Async-Bridged MQTT Client Layer for MeshCore Bridge.
Implementa cliente MQTT de grado industrial con paho-mqtt v2.x, Last Will & Testament (LWT),
reconexión determinista y puente thread-safe hacia el event loop de asyncio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import config

try:
    import paho.mqtt.client as _paho_mqtt
    mqtt: Any = _paho_mqtt
except ImportError:
    # Fallback/Mock para desarrollo o entornos sin paho-mqtt
    class _MockClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.on_connect: Any = None
            self.on_disconnect: Any = None
            self.on_message: Any = None

        def username_pw_set(self, *args: Any, **kwargs: Any) -> None: pass
        def will_set(self, *args: Any, **kwargs: Any) -> None: pass
        def connect(self, *args: Any, **kwargs: Any) -> None: pass
        def loop_start(self) -> None: pass
        def loop_stop(self) -> None: pass
        def disconnect(self) -> None: pass
        def subscribe(self, *args: Any, **kwargs: Any) -> None: pass
        def publish(self, *args: Any, **kwargs: Any) -> None: pass

    class _MockMQTT:
        Client = _MockClient

    mqtt = _MockMQTT()


@dataclass(slots=True)
class MQTTConfig:
    """Objeto de configuración MQTT: agrupa credenciales, broker y tópico base."""
    broker: str = "127.0.0.1"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    keepalive: int = 60
    topic_prefix: str = "meshcore"


class AsyncBridgeMQTTClient:
    """Cliente MQTT asíncrono puenteado con reconexión automática."""

    def __init__(
        self,
        config: MQTTConfig,
        on_rx_message_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self.config = config
        self.broker = config.broker
        self.port = config.port
        self.username = config.username
        self.password = config.password
        self.keepalive = config.keepalive
        self.topic_prefix = config.topic_prefix.strip("/")
        self.on_rx_message_callback = on_rx_message_callback

        self.topic_state = f"{self.topic_prefix}/bridge/state"
        self.topic_health = f"{self.topic_prefix}/bridge/health"
        self.topic_tx = f"{self.topic_prefix}/tx"
        self.topic_tx_status = f"{self.topic_prefix}/tx/status"
        self.topic_admin_cmd = f"{self.topic_prefix}/admin/cmd"
        self.topic_admin_stat = f"{self.topic_prefix}/admin/status"

        self.is_connected = False
        self.reconnect_count = 0
        self.total_published = 0
        self.total_received = 0
        self._loop: asyncio.AbstractEventLoop | None = None

        # Inicialización de cliente con compatibilidad de versiones paho
        if hasattr(mqtt, "CallbackAPIVersion"):
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"meshcore_bridge_{int(time.time())}",
                protocol=mqtt.MQTTv311,
            )
        else:
            self.client = mqtt.Client(client_id=f"meshcore_bridge_{int(time.time())}", protocol=mqtt.MQTTv311)

        if self.username:
            self.client.username_pw_set(self.username, self.password)

        lwt_payload = json.dumps({
            "status": "offline",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": "unexpected_disconnect",
        })
        self.client.will_set(self.topic_state, lwt_payload, qos=1, retain=True)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Configura credenciales, LWT e inicia el bucle de red MQTT en hilo dedicado."""
        self._loop = loop or asyncio.get_running_loop()

        # Backoff de reconexión determinista (1s..30s) para resiliencia ante caídas del broker
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

        # connect_async + loop_start garantizan reintentos automáticos en segundo plano
        # aunque el broker esté caído al arrancar (loop_forever con retry_first_connection=True).
        logging.info(f"Conectando al Broker MQTT en {self.broker}:{self.port}...")
        self.client.connect_async(self.broker, self.port, self.keepalive)
        self.client.loop_start()

    def stop(self) -> None:
        """Detiene el cliente MQTT y emite estado offline ordenado."""
        if self.is_connected:
            try:
                offline_payload = json.dumps({
                    "status": "offline",
                    "reason": "graceful_shutdown",
                    "timestamp": int(time.time()),
                })
                self.client.publish(self.topic_state, offline_payload, qos=1, retain=True)
            except Exception:
                pass

        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        self.is_connected = False
        logging.info("Cliente MQTT detenido correctamente.")

    def publish_safe(
        self,
        topic: str,
        payload_str: str,
        qos: int = 0,
        retain: bool = False,
        ttl_seconds: float | None = None,
    ) -> bool:
        """Publica directamente en MQTT con validación de tamaño de payload."""
        if not self.is_connected:
            return False

        payload_bytes = payload_str.encode("utf-8") if isinstance(payload_str, str) else payload_str
        max_payload_size = getattr(config, "MQTT_MAX_PAYLOAD_BYTES", 128 * 1024)
        if len(payload_bytes) > max_payload_size:
            logging.warning(
                f"Payload MQTT excede el tamaño máximo permitido ({len(payload_bytes)} > {max_payload_size} bytes). Descartando mensaje en {topic}."
            )
            return False

        try:
            self.client.publish(topic, payload_str, qos=qos, retain=retain)
            self.total_published += 1
            return True
        except Exception as e:
            logging.warning(f"Fallo al publicar en MQTT ({e})")
            return False

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, *args: Any, **kwargs: Any) -> None:
        """Callback ejecutado al establecer conexión con el broker."""
        rc_val = getattr(rc, "value", rc)
        is_success = False
        if hasattr(rc, "is_failure"):
            is_success = not rc.is_failure
        elif isinstance(rc_val, int):
            is_success = (rc_val == 0)
        elif str(rc).lower() in ["0", "success", "connection accepted"]:
            is_success = True
        else:
            is_success = (rc == 0)

        if is_success:
            self.is_connected = True
            self.reconnect_count += 1
            logging.info(f"Conexión exitosa con MQTT Broker ({self.broker}:{self.port})")

            # Publicar estado online retenido
            online_payload = json.dumps({
                "status": "online",
                "timestamp": int(time.time()),
                "iso_time": datetime.now(timezone.utc).isoformat(),
            })
            self.client.publish(self.topic_state, online_payload, qos=1, retain=True)

            # Suscribir a tópicos de entrada
            self.client.subscribe([(self.topic_tx, 1), (self.topic_admin_cmd, 1)])
            logging.info(f"Suscrito a: {self.topic_tx} y {self.topic_admin_cmd}")
        else:
            self.is_connected = False
            logging.error(f"Fallo de conexión MQTT (rc: {rc})")

    def _on_disconnect(self, client: Any, userdata: Any, rc: Any, *args: Any, **kwargs: Any) -> None:
        """Callback ejecutado al perder la conexión MQTT."""
        self.is_connected = False
        if rc != 0:
            logging.warning(f"Desconexión de MQTT detectada (rc: {rc}). El cliente intentará reconectar automáticamente...")

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """Callback ejecutado al recibir un mensaje suscrito en MQTT."""
        self.total_received += 1
        try:
            topic = str(msg.topic)
            payload_str = msg.payload.decode("utf-8", errors="replace").strip()
            if not payload_str:
                return

            if self.on_rx_message_callback:
                if self._loop and self._loop.is_running():
                    self._loop.call_soon_threadsafe(self.on_rx_message_callback, topic, payload_str)
                else:
                    try:
                        self.on_rx_message_callback(topic, payload_str)
                    except Exception as e:
                        logging.error(f"MQTT callback error: {e}")
        except Exception as e:
            logging.error(f"Error procesando mensaje MQTT entrante: {e}")
