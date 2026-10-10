"""
External Bridge MQTT Client Layer for MeshCore Bridge.
Implementa cliente MQTT autónomo con paho-mqtt v2.x, Last Will & Testament (LWT),
transporte TCP y WebSockets, cifrado TLS, autenticación por token/usuario,
búfer circular en RAM (Store-and-Forward de 100 tramas), Geofuzzing y prueba efímera de conexión.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import ssl
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from src.services_config import ExternalMqttConfig

try:
    import paho.mqtt.client as _paho_mqtt
    mqtt: Any = _paho_mqtt
except ImportError:
    class _MockClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.on_connect: Any = None
            self.on_disconnect: Any = None
            self.on_message: Any = None

        def username_pw_set(self, *args: Any, **kwargs: Any) -> None: pass
        def will_set(self, *args: Any, **kwargs: Any) -> None: pass
        def connect(self, *args: Any, **kwargs: Any) -> None: pass
        def connect_async(self, *args: Any, **kwargs: Any) -> None: pass
        def reconnect_delay_set(self, *args: Any, **kwargs: Any) -> None: pass
        def loop_start(self) -> None: pass
        def loop_stop(self) -> None: pass
        def disconnect(self) -> None: pass
        def subscribe(self, *args: Any, **kwargs: Any) -> None: pass
        def publish(self, *args: Any, **kwargs: Any) -> Any:
            class _MockInfo:
                rc = 0
            return _MockInfo()

    class _MockMQTT:
        Client = _MockClient

    mqtt = _MockMQTT()

logger = logging.getLogger("meshcore.external_mqtt")


class ExternalBridgeMQTTClient:
    """Cliente MQTT upstream para reenvío pasivo de tramas a servidores externos o comunitarios."""

    MAX_BUFFER_SIZE = 100

    def __init__(
        self,
        config_data: ExternalMqttConfig,
        local_pubkey: str = "",
        on_downlink_message_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self.config = config_data
        self.local_pubkey = local_pubkey.lower().strip()
        self.on_downlink_message_callback = on_downlink_message_callback

        self.is_connected = False
        self.reconnect_count = 0
        self.total_published = 0
        self.total_received = 0
        self.total_buffered = 0
        self.total_dropped_buffer = 0

        self._ring_buffer: deque[tuple[str, str, int, bool]] = deque(maxlen=self.MAX_BUFFER_SIZE)
        self._sent_hashes: deque[str] = deque(maxlen=200)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._drain_lock = threading.Lock()
        self.client: Any = None

        if self.config.enabled:
            self._init_paho_client()

    def _init_paho_client(self) -> None:
        """Inicializa la instancia de Paho MQTT con transporte, TLS y credenciales."""
        transport_type = "websockets" if self.config.transport == "websockets" else "tcp"
        client_uid = f"meshcore_ext_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        if hasattr(mqtt, "CallbackAPIVersion"):
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_uid,
                protocol=mqtt.MQTTv311,
                transport=transport_type,
            )
        else:
            self.client = mqtt.Client(
                client_id=client_uid,
                protocol=mqtt.MQTTv311,
                transport=transport_type,
            )

        # Configuración TLS
        if self.config.tls_enabled:
            try:
                context = ssl.create_default_context()
                if not self.config.tls_verify:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                self.client.tls_set_context(context)
            except Exception as e:
                logger.error(f"Error configurando contexto SSL/TLS para MQTT externo: {e}")

        # Configuración de Autenticación
        if self.config.auth_type == "user_pass":
            if self.config.username:
                self.client.username_pw_set(self.config.username, self.config.password)
        elif self.config.auth_type == "token":
            # Para LetsMesh y brokers comunitarios: token como contraseña o token como username
            user = self.config.username if self.config.username else "token"
            token_secret = self.config.token or self.config.password
            self.client.username_pw_set(user, token_secret)

        # Last Will & Testament (LWT)
        state_topic = self.build_topic("state")
        lwt_payload = json.dumps({
            "status": "offline",
            "reason": "unexpected_disconnect",
            "gateway_id": self.local_pubkey or "gateway",
            "timestamp": int(time.time()),
            "iso_time": datetime.now(UTC).isoformat(),
        })
        try:
            self.client.will_set(state_topic, lwt_payload, qos=1, retain=True)
        except Exception as e:
            logger.debug(f"No se pudo establecer LWT en MQTT externo: {e}")

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Inicia el bucle de red de Paho en segundo plano con reconexión exponencial."""
        if not self.config.enabled:
            logger.debug("Cliente MQTT externo desactivado por configuración.")
            return

        if not self.config.host:
            logger.warning("No se puede iniciar MQTT externo: Host vacío.")
            return

        self._loop = loop or (asyncio.get_running_loop() if asyncio._get_running_loop() is not None else None)

        if self.client is None:
            self._init_paho_client()

        # Deterministic exponential backoff (2s..60s)
        self.client.reconnect_delay_set(min_delay=2, max_delay=60)

        logger.info(
            f"Iniciando conexión a Broker MQTT Externo en {self.config.host}:{self.config.port} "
            f"(transporte={self.config.transport}, tls={self.config.tls_enabled})..."
        )
        try:
            self.client.connect_async(self.config.host, self.config.port, self.config.keepalive)
            self.client.loop_start()
        except Exception as e:
            self.is_connected = False
            logger.error(f"Fallo al conectar con Broker MQTT Externo ({self.config.host}:{self.config.port}): {e}")

    def stop(self) -> None:
        """Detiene ordenadamente el cliente MQTT externo y publica estado offline."""
        if self.client is None:
            self.is_connected = False
            return

        if self.is_connected:
            try:
                state_topic = self.build_topic("state")
                offline_payload = json.dumps({
                    "status": "offline",
                    "reason": "graceful_shutdown",
                    "gateway_id": self.local_pubkey or "gateway",
                    "timestamp": int(time.time()),
                    "iso_time": datetime.now(UTC).isoformat(),
                })
                self.client.publish(state_topic, offline_payload, qos=0, retain=True)
            except Exception as e:
                logger.debug(f"Error publicando LWT offline externo: {e}")

        try:
            self.client.disconnect()
        except Exception as e:
            logger.debug(f"Error desconectando cliente MQTT externo: {e}")

        try:
            thread = getattr(self.client, "_thread", None)
            if isinstance(thread, threading.Thread) and thread.is_alive():
                self.client._thread_terminate = True
                thread.join(timeout=1.0)
                if thread.is_alive():
                    logger.warning("Hilo MQTT externo no terminó en timeout; desacoplando")
                    self.client._thread = None
            self.client.loop_stop()
        except Exception as e:
            logger.debug(f"Error deteniendo bucle MQTT externo: {e}")

        self.is_connected = False
        logger.info("Cliente MQTT Externo detenido correctamente.")

    def set_local_pubkey(self, pubkey: str) -> None:
        """Actualiza la clave pública local del gateway para filtrado y tópicos jerárquicos."""
        self.local_pubkey = pubkey.lower().strip()

    def build_topic(self, event_type: str, channel_idx: int = 0, pubkey: str = "") -> str:
        """Construye el tópico de destino según el modo: standard, hierarchical o custom."""
        mode = self.config.topic_mode
        prefix = (self.config.topic_prefix or "meshcore/remote").strip("/")

        if mode == "hierarchical":
            iata = (self.config.region_iata or "XXX").strip().upper()
            gw_id = self.local_pubkey or "gateway"
            base = f"{prefix}/{iata}/{gw_id}"

            if event_type == "state":
                return f"{base}/status"
            if event_type in ("packet", "rx", "raw"):
                return f"{base}/packets"
            if event_type == "telemetry":
                return f"{base}/telemetry"
            if event_type in ("advert", "node"):
                return f"{base}/nodes"
            if event_type == "channel":
                return f"{base}/channels/{channel_idx}"
            if event_type == "direct":
                clean_pk = pubkey.lower().strip() or "dm"
                return f"{base}/direct/{clean_pk}"
            if event_type == "tx":
                return f"{base}/tx"
            return f"{base}/{event_type}"

        # standard o custom
        base = prefix
        if event_type == "state":
            return f"{base}/state"
        if event_type == "rx":
            return f"{base}/rx/all"
        if event_type == "channel":
            return f"{base}/rx/channel/{channel_idx}"
        if event_type == "direct":
            clean_pk = pubkey.lower().strip() or "dm"
            return f"{base}/rx/direct/{clean_pk}"
        if event_type == "telemetry":
            clean_pk = pubkey.lower().strip() or "all"
            return f"{base}/rx/telemetry/{clean_pk}"
        if event_type in ("advert", "node"):
            clean_pk = pubkey.lower().strip() or "all"
            return f"{base}/rx/node/{clean_pk}"
        if event_type == "raw":
            return f"{base}/rx/raw"
        if event_type == "tx":
            return f"{base}/tx"
        return f"{base}/{event_type}"

    def apply_geofuzzing(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Aplica la política de privacidad de coordenadas (exact, fuzzed o hidden)."""
        privacy = self.config.location_privacy
        if privacy == "exact":
            return payload

        data = copy.deepcopy(payload)

        coord_keys = ("lat", "lon", "latitude", "longitude", "gps_lat", "gps_lon", "adv_lat", "adv_lon")
        alt_keys = ("alt", "altitude", "elevation")

        def _clean_dict(d: dict[str, Any]) -> None:
            for k in list(d.keys()):
                val = d[k]
                if isinstance(val, dict):
                    _clean_dict(val)
                elif k in coord_keys and isinstance(val, (int, float)):
                    if privacy == "hidden":
                        d.pop(k, None)
                    elif privacy == "fuzzed":
                        # 2 decimales representan aprox ~1.1 km de precisión (barrio/ciudad)
                        d[k] = round(float(val), 2)
                elif k in alt_keys:
                    if privacy in ("hidden", "fuzzed"):
                        d.pop(k, None)

            if privacy == "hidden":
                for loc_sub in ("location", "gps", "position", "pos"):
                    if loc_sub in d and not d[loc_sub]:
                        d.pop(loc_sub, None)

        _clean_dict(data)
        return data

    def should_forward_event(self, event_type: str, is_public: bool = True, is_channel: bool = False, is_direct: bool = False) -> bool:
        """Evalúa si un evento debe ser reenviado según los filtros configurados."""
        if not self.config.enabled:
            return False

        # Modo Observer: Bloquea chats de texto por completo
        if self.config.filter_observer_mode and event_type in ("public", "channel", "direct", "chat", "text", "CHANNEL_MSG", "DIRECT_MSG"):
            return False

        if event_type in ("public", "chat") and is_public:
            return self.config.filter_public
        if event_type == "channel" or is_channel:
            return self.config.filter_channels
        if event_type == "direct" or is_direct:
            return self.config.filter_direct
        if event_type == "telemetry":
            return self.config.filter_telemetry
        if event_type in ("advert", "node", "discovery"):
            return self.config.filter_nodes
        if event_type == "raw":
            return self.config.filter_raw

        return True

    def publish_event(
        self,
        event_type: str,
        payload_data: dict[str, Any],
        channel_idx: int = 0,
        pubkey: str = "",
        raw_hex: str = "",
    ) -> bool:
        """
        Publica o encola en el ring buffer un evento LoRa con destino al broker externo.
        Aplica filtro de eventos, guarda de origen propio, geofuzzing y formateo de payload.
        """
        if not self.config.enabled:
            return False

        # Guarda de origen propio inmutable (Evita reflejos y bucles)
        sender_pk = str(payload_data.get("sender") or payload_data.get("from") or "").lower().strip()
        if self.local_pubkey and sender_pk == self.local_pubkey:
            return False

        # Verificar filtros de contenido
        is_pub = channel_idx == 0 and event_type in ("public", "chat", "mesh_packet")
        is_chan = channel_idx > 0
        is_dir = bool(pubkey) and event_type == "direct"
        if not self.should_forward_event(event_type, is_public=is_pub, is_channel=is_chan, is_direct=is_dir):
            return False

        # Aplicar privacidad geográfica
        safe_data = self.apply_geofuzzing(payload_data)

        # Construir tópico
        topic = self.build_topic(event_type, channel_idx=channel_idx, pubkey=pubkey)

        # Formatear carga útil según el modo
        if self.config.payload_format == "analyzer_packet":
            msg_payload = {
                "timestamp": int(time.time()),
                "iso_time": datetime.now(UTC).isoformat(),
                "gateway_id": self.local_pubkey or "gateway",
                "region": self.config.region_iata,
                "event": event_type,
                "raw": raw_hex or safe_data.get("raw_hex", ""),
                "rssi": safe_data.get("rssi"),
                "snr": safe_data.get("snr"),
                "sender": sender_pk,
                "channel": channel_idx,
            }
            if "telemetry" in safe_data:
                msg_payload["telemetry"] = safe_data["telemetry"]
            if "location" in safe_data:
                msg_payload["location"] = safe_data["location"]
            payload_str = json.dumps(msg_payload, ensure_ascii=False)
        else:
            # Formato JSON canónico estándar
            if "timestamp" not in safe_data:
                safe_data["timestamp"] = int(time.time())
            if "iso_time" not in safe_data:
                safe_data["iso_time"] = datetime.now(UTC).isoformat()
            safe_data["event"] = event_type
            safe_data["gateway_id"] = self.local_pubkey or "gateway"
            payload_str = json.dumps(safe_data, ensure_ascii=False)

        # Registrar hash para supresión de eco
        pkt_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()[:16]
        self._sent_hashes.append(pkt_hash)

        return self._send_or_buffer(topic, payload_str, qos=self.config.qos, retain=False)

    def _send_or_buffer(self, topic: str, payload_str: str, qos: int = 0, retain: bool = False) -> bool:
        """Envía el paquete inmediatamente si está conectado, o lo encola en el ring buffer si está offline."""
        if self.is_connected and self.client is not None:
            try:
                info = self.client.publish(topic, payload_str, qos=qos, retain=retain)
                if getattr(info, "rc", 0) == 0:
                    self.total_published += 1
                    return True
            except Exception as e:
                logger.debug(f"Error publicando mensaje a MQTT externo ({e}), encolando en ring buffer...")

        # Encolar en ring buffer en RAM
        with self._drain_lock:
            if len(self._ring_buffer) >= self.MAX_BUFFER_SIZE:
                self.total_dropped_buffer += 1
            self._ring_buffer.append((topic, payload_str, qos, retain))
            self.total_buffered += 1

        return False

    def _drain_ring_buffer(self) -> None:
        """Vacía ordenadamente las tramas acumuladas en el búfer circular tras reconectar."""
        if not self.is_connected or self.client is None:
            return

        with self._drain_lock:
            if not self._ring_buffer:
                return

            drained_count = 0
            while self._ring_buffer and self.is_connected:
                topic, payload_str, qos, retain = self._ring_buffer.popleft()
                try:
                    info = self.client.publish(topic, payload_str, qos=qos, retain=retain)
                    if getattr(info, "rc", 0) == 0:
                        self.total_published += 1
                        drained_count += 1
                except Exception as e:
                    logger.debug(f"Interrupción al vaciar ring buffer MQTT externo: {e}")
                    # Reinsertar al inicio y pausar
                    self._ring_buffer.appendleft((topic, payload_str, qos, retain))
                    break

            if drained_count > 0:
                logger.info(f"Vaciadas {drained_count} tramas del ring buffer hacia MQTT externo.")

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, *args: Any, **kwargs: Any) -> None:
        """Callback al conectarse con éxito al broker externo."""
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
            logger.info(f"Conexión exitosa con Broker MQTT Externo ({self.config.host}:{self.config.port})")

            # Publicar estado online retenido
            state_topic = self.build_topic("state")
            online_payload = json.dumps({
                "status": "online",
                "gateway_id": self.local_pubkey or "gateway",
                "region": self.config.region_iata,
                "timestamp": int(time.time()),
                "iso_time": datetime.now(UTC).isoformat(),
            })
            try:
                self.client.publish(state_topic, online_payload, qos=1, retain=True)
            except Exception as e:
                logger.debug(f"Error publicando estado online en MQTT externo: {e}")

            # DOWNLINK: Solo suscribir si el usuario lo activó explícitamente en la configuración
            if self.config.downlink_enabled:
                downlink_topic = self.build_topic("tx")
                try:
                    self.client.subscribe([(downlink_topic, 1)])
                    logger.warning(
                        f"Downlink activado en MQTT externo. Suscrito a {downlink_topic}. "
                        "El tráfico entrante pasará por el limitador de tasa LoRa."
                    )
                except Exception as e:
                    logger.error(f"Error suscribiendo a tópico downlink externo {downlink_topic}: {e}")
            else:
                logger.debug("Downlink desactivado en MQTT externo (Modo Solo Uplink seguro).")

            # Vaciar el búfer circular acumulado en memoria
            threading.Thread(target=self._drain_ring_buffer, daemon=True, name="ext_mqtt_drain").start()
        else:
            self.is_connected = False
            logger.warning(f"Rechazo de conexión con Broker MQTT Externo (rc: {rc})")

    def _on_disconnect(
        self,
        client: Any,
        userdata: Any,
        disconnect_flags_or_rc: Any,
        rc_or_props: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Callback al desconectarse del broker externo."""
        self.is_connected = False
        rc = rc_or_props if rc_or_props is not None else disconnect_flags_or_rc
        rc_code = getattr(rc, "value", rc)
        is_clean = (rc_code == 0) or str(rc).lower() in ("0", "success", "clean disconnect", "disconnect", "none")
        if not is_clean:
            reason = getattr(rc, "getName", lambda: str(rc))()
            logger.info(f"Desconexión del Broker MQTT Externo ({reason}). Reconectando automáticamente...")

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """Callback al recibir un mensaje por MQTT (Downlink)."""
        if not self.config.downlink_enabled:
            return

        self.total_received += 1
        try:
            topic = str(msg.topic)
            raw_payload = getattr(msg, "payload", b"")
            payload_str = raw_payload.decode("utf-8", errors="replace").strip()
            if not payload_str:
                return

            # Echo Suppression: Si coincide con un hash recién enviado por nosotros, descartar
            pkt_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()[:16]
            if pkt_hash in self._sent_hashes:
                logger.debug(f"Eco detectado en tópico downlink {topic}, descartando mensaje.")
                return

            if self.on_downlink_message_callback:
                if self._loop and self._loop.is_running():
                    self._loop.call_soon_threadsafe(self.on_downlink_message_callback, topic, payload_str)
                else:
                    self.on_downlink_message_callback(topic, payload_str)
        except Exception as e:
            logger.error(f"Error procesando mensaje entrante en downlink MQTT externo: {e}")

    @classmethod
    async def test_connection(cls, test_config: ExternalMqttConfig, timeout: float = 5.0) -> dict[str, Any]:
        """
        Ejecuta una prueba efímera de conexión hacia el broker externo con timeout de seguridad.
        Mide la latencia en milisegundos y devuelve el diagnóstico detallado.
        """
        host = (test_config.host or "").strip()
        port = test_config.port

        if not host:
            return {"ok": False, "error": "El host del broker no puede estar vacío.", "latency_ms": None}
        if not (1 <= port <= 65535):
            return {"ok": False, "error": f"Puerto inválido: {port}.", "latency_ms": None}

        connected_event = asyncio.Event()
        error_container: list[str] = []
        start_time = time.perf_counter()

        transport_type = "websockets" if test_config.transport == "websockets" else "tcp"
        ephemeral_uid = f"meshcore_test_{int(time.time())}_{uuid.uuid4().hex[:4]}"

        if hasattr(mqtt, "CallbackAPIVersion"):
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=ephemeral_uid,
                protocol=mqtt.MQTTv311,
                transport=transport_type,
            )
        else:
            client = mqtt.Client(
                client_id=ephemeral_uid,
                protocol=mqtt.MQTTv311,
                transport=transport_type,
            )

        if test_config.tls_enabled:
            try:
                context = ssl.create_default_context()
                if not test_config.tls_verify:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                client.tls_set_context(context)
            except Exception as e:
                return {"ok": False, "error": f"Fallo al configurar TLS: {e}", "latency_ms": None}

        if test_config.auth_type == "user_pass":
            if test_config.username:
                client.username_pw_set(test_config.username, test_config.password)
        elif test_config.auth_type == "token":
            user = test_config.username if test_config.username else "token"
            token_secret = test_config.token or test_config.password
            client.username_pw_set(user, token_secret)

        loop = asyncio.get_running_loop()

        def _test_on_connect(c: Any, ud: Any, fl: Any, rc: Any, *args: Any, **kwargs: Any) -> None:
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
                loop.call_soon_threadsafe(connected_event.set)
            else:
                err_msg = getattr(rc, "getName", lambda: f"Código {rc}")()
                error_container.append(f"Rechazo de conexión: {err_msg}")
                loop.call_soon_threadsafe(connected_event.set)

        client.on_connect = _test_on_connect

        try:
            client.connect_async(host, port, keepalive=10)
            client.loop_start()

            try:
                async with asyncio.timeout(timeout):
                    await connected_event.wait()
            except TimeoutError:
                return {
                    "ok": False,
                    "error": f"Tiempo de espera agotado ({timeout}s) conectando a {host}:{port}.",
                    "latency_ms": None,
                }

            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)

            if error_container:
                return {
                    "ok": False,
                    "error": error_container[0],
                    "latency_ms": elapsed_ms,
                }

            return {
                "ok": True,
                "latency_ms": elapsed_ms,
                "message": f"Conexión exitosa a {host}:{port} ({elapsed_ms} ms).",
            }

        except Exception as e:
            return {"ok": False, "error": f"Error de red: {e}", "latency_ms": None}
        finally:
            try:
                client.disconnect()
            except Exception:
                pass
            try:
                client.loop_stop()
            except Exception:
                pass
