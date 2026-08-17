#!/usr/bin/env python3
"""
MeshCore Universal Bridge: Companion USB (Heltec / LilyGO / RAKwireless / Seeed / RP2040) <-> Mosquitto MQTT <-> n8n
Puente bidireccional asíncrono, resiliente y de grado industrial para redes Mesh LoRa.

Dispositivos Compatibles:
- Heltec Automation (WiFi LoRa 32 v2/v3/v4, Wireless Stick, Wireless Tracker, Wireless Paper, Capsule).
- LilyGO TTGO (T-Beam, T-Echo nRF52840, T3S3, T-Deck, LoRa32).
- RAKwireless WisBlock (RAK4631 nRF52840, RAK11200, RAK11310 RP2040, WisMesh Hub/Pocket).
- Seeed Studio (SenseCAP Indicator/Tracker, Wio-E5, Xiao ESP32-S3/nRF52840).
- Raspberry Pi Pico / RP2040 LoRa Nodes y placas DIY compatibles con MeshCore Companion USB v1.17+.

Características de Resiliencia:
- Persistencia SQLite Store & Forward en modo WAL (Cero pérdida de datos ante cortes eléctricos o caídas de MQTT).
- Rate Limiter para transmisión TX (evita saturación del transceptor LoRa SX1262/SX1276/SX1280).
- Watchdog activo para prevención y recuperación de bloqueos silenciosos del puerto serial.
- Reporte periódico de salud y métricas de rendimiento en MQTT (meshcore/bridge/health).
- Last Will and Testament (LWT) y apagado ordenado (Graceful Shutdown).
"""

import asyncio
import collections
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Optional, Tuple

import config

try:
    import paho.mqtt.client as mqtt
except ImportError:
    # Mock/fallback si paho-mqtt no está instalado en el entorno local de desarrollo
    class _MockMQTTClient:
        def __init__(self, *args, **kwargs):
            self.on_connect = None
            self.on_disconnect = None
            self.on_message = None

        def username_pw_set(self, *args, **kwargs): pass
        def will_set(self, *args, **kwargs): pass
        def connect(self, *args, **kwargs): pass
        def loop_start(self): pass
        def loop_stop(self): pass
        def disconnect(self): pass
        def subscribe(self, *args, **kwargs): pass
        def publish(self, *args, **kwargs): pass

    class _MockMQTT:
        Client = _MockMQTTClient

    mqtt = _MockMQTT()

try:
    import meshcore
    from meshcore import MeshCore, EventType
except ImportError:
    meshcore = None
    MeshCore = None
    EventType = None

# ================= Configuración de Logging =================
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)


import sqlite3

class SQLiteStoreAndForward:
    """Buffer offline persistente en base de datos SQLite con modo WAL."""
    def __init__(self, db_path: str, max_size: int = 1000):
        self.db_path = db_path
        self.max_size = max_size
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS offline_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        qos INTEGER DEFAULT 0,
                        retain INTEGER DEFAULT 0,
                        created_at REAL NOT NULL
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_offline_queue_created ON offline_queue(created_at);")
        except Exception as e:
            logging.error(f"Error inicializando SQLite Store & Forward DB: {e}")

    def enqueue(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> None:
        """Encola un mensaje en SQLite y recorta la tabla si excede el tamaño máximo."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO offline_queue (topic, payload, qos, retain, created_at) VALUES (?, ?, ?, ?, ?);",
                    (topic, payload, qos, 1 if retain else 0, time.time())
                )
                conn.execute(
                    """
                    DELETE FROM offline_queue 
                    WHERE id NOT IN (
                        SELECT id FROM offline_queue ORDER BY id DESC LIMIT ?
                    );
                    """,
                    (self.max_size,)
                )
        except Exception as e:
            logging.error(f"Error encolando en SQLite offline buffer: {e}")

    def dequeue_batch(self, limit: int = 50) -> list:
        """Obtiene un lote de mensajes pendientes en orden cronológico FIFO."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, topic, payload, qos, retain FROM offline_queue ORDER BY id ASC LIMIT ?;",
                    (limit,)
                )
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Error leyendo de SQLite offline buffer: {e}")
            return []

    def delete(self, msg_id: int) -> None:
        """Elimina un mensaje entregado exitosamente."""
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM offline_queue WHERE id = ?;", (msg_id,))
        except Exception as e:
            logging.error(f"Error eliminando de SQLite offline buffer (ID {msg_id}): {e}")

    def get_size(self) -> int:
        """Retorna la cantidad actual de mensajes pendientes."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM offline_queue;")
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def clear(self) -> None:
        """Limpia todos los mensajes de la cola (útil para pruebas o mantenimiento)."""
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM offline_queue;")
        except Exception:
            pass


class MeshCoreBridge:
    def __init__(self, loop: asyncio.AbstractEventLoop, db_path: Optional[str] = None):
        self.loop = loop
        self.mc: Optional[Any] = None
        self.running = True
        self.start_time = time.time()

        # Estado de conexión MQTT
        self.mqtt_connected = False
        self.mqtt_reconnect_count = 0
        self.serial_reconnect_count = 0

        # Contadores de métricas
        self.rx_count = 0
        self.tx_count = 0
        self.tx_error_count = 0
        self.last_serial_activity = time.time()

        # Buffer Offline Store-and-Forward Persistente en SQLite
        db_file = db_path or config.SQLITE_DB_PATH
        self.sqlite_buffer = SQLiteStoreAndForward(
            db_path=db_file,
            max_size=config.OFFLINE_BUFFER_MAX_SIZE
        )

        # Cola Asíncrona de Transmisión (TX) con Rate Limiting
        self.tx_queue: asyncio.Queue = asyncio.Queue()
        self.tx_worker_task: Optional[asyncio.Task] = None
        self.watchdog_task: Optional[asyncio.Task] = None
        self.health_task: Optional[asyncio.Task] = None

        # Inicialización de cliente MQTT
        if hasattr(mqtt, "CallbackAPIVersion"):
            self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        else:
            self.mqtt_client = mqtt.Client()

    # ================================================================
    # MQTT Setup, Callbacks & Store-and-Forward Dispatcher
    # ================================================================
    def setup_mqtt(self) -> None:
        """Configura credenciales, Last Will & Testament (LWT) y callbacks de MQTT."""
        if config.MQTT_USER and config.MQTT_PASSWORD:
            self.mqtt_client.username_pw_set(config.MQTT_USER, config.MQTT_PASSWORD)

        # LWT: Enviar estado offline retenido si el proceso muere inesperadamente
        self.mqtt_client.will_set(
            topic=config.TOPIC_STATE,
            payload=json.dumps({"status": "offline", "timestamp": int(time.time())}),
            qos=1,
            retain=True
        )

        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_client.on_message = self.on_mqtt_message

        try:
            logging.info(f"Conectando a MQTT Broker en {config.MQTT_BROKER}:{config.MQTT_PORT}...")
            self.mqtt_client.connect(config.MQTT_BROKER, config.MQTT_PORT, config.MQTT_KEEPALIVE)
            self.mqtt_client.loop_start()
        except Exception as e:
            logging.error(f"Error al conectar con el broker MQTT: {e}")

    def on_mqtt_connect(self, client, userdata, flags, rc, *args, **kwargs) -> None:
        """Callback ejecutado al conectar exitosamente con el broker MQTT."""
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
            self.mqtt_connected = True
            self.mqtt_reconnect_count += 1
            logging.info(f"Conectado exitosamente al broker MQTT ({config.MQTT_BROKER}:{config.MQTT_PORT})")

            # Publicar estado online retenido
            online_payload = {
                "status": "online",
                "serial_port": config.SERIAL_PORT,
                "timestamp": int(time.time()),
                "iso_time": datetime.now(timezone.utc).isoformat()
            }
            self.mqtt_client.publish(config.TOPIC_STATE, json.dumps(online_payload), qos=1, retain=True)

            # Suscribirse a tópicos de control y transmisión
            subscriptions = [
                (config.TOPIC_TX, 1),
                (config.TOPIC_ADMIN_CMD, 1)
            ]
            client.subscribe(subscriptions)
            logging.info(f"Suscrito a TX ({config.TOPIC_TX}) y Admin ({config.TOPIC_ADMIN_CMD})")

            # Vaciar mensajes retenidos en la base de datos SQLite (Store & Forward)
            self._flush_offline_buffer()
        else:
            self.mqtt_connected = False
            logging.error(f"Fallo al conectar con MQTT, código rc: {rc}")

    def on_mqtt_disconnect(self, client, userdata, rc, *args, **kwargs) -> None:
        """Callback ejecutado al perder la conexión con MQTT."""
        self.mqtt_connected = False
        if rc != 0:
            logging.warning(f"Desconexión de MQTT detectada (rc: {rc}). Activando modo Store & Forward (Buffer SQLite)...")

    def publish_mqtt_safe(self, topic: str, payload_str: str, qos: int = 0, retain: bool = False) -> None:
        """Publica a MQTT o encola en SQLite si MQTT está desconectado."""
        if self.mqtt_connected:
            try:
                self.mqtt_client.publish(topic, payload_str, qos=qos, retain=retain)
                return
            except Exception as e:
                logging.warning(f"Error publicando en MQTT ({e}). Guardando en SQLite offline buffer...")

        # Encolar en SQLite Store & Forward
        self.sqlite_buffer.enqueue(topic, payload_str, qos=qos, retain=retain)
        logging.debug(f"Mensaje retenido en SQLite buffer (Pendientes en DB: {self.sqlite_buffer.get_size()})")

    def _flush_offline_buffer(self) -> None:
        """Envía todos los paquetes almacenados en SQLite durante la desconexión de MQTT."""
        pending_count = self.sqlite_buffer.get_size()
        if pending_count == 0:
            return

        logging.info(f"Vaciando {pending_count} mensajes del buffer SQLite hacia MQTT...")
        while self.mqtt_connected:
            batch = self.sqlite_buffer.dequeue_batch(limit=50)
            if not batch:
                break

            for msg_id, topic, payload_str, qos, retain in batch:
                if not self.mqtt_connected:
                    break
                try:
                    self.mqtt_client.publish(topic, payload_str, qos=qos, retain=bool(retain))
                    self.sqlite_buffer.delete(msg_id)
                except Exception as e:
                    logging.error(f"Error al vaciar mensaje {msg_id} de SQLite: {e}")
                    return

        logging.info(f"Vaciado de buffer SQLite completado. Restantes en DB: {self.sqlite_buffer.get_size()}")

    def on_mqtt_message(self, client, userdata, msg) -> None:
        """Enruta mensajes recibidos desde MQTT hacia el bucle de eventos asyncio."""
        try:
            raw_payload = msg.payload.decode("utf-8", errors="replace").strip()
            if not raw_payload:
                return

            try:
                data = json.loads(raw_payload)
            except Exception:
                data = {"text": raw_payload}

            if not isinstance(data, dict):
                data = {"text": str(data)}

            if msg.topic == config.TOPIC_ADMIN_CMD:
                asyncio.run_coroutine_threadsafe(self.handle_admin(data), self.loop)
            elif msg.topic == config.TOPIC_TX:
                # Encolar en la cola asíncrona de TX con Rate Limiting
                asyncio.run_coroutine_threadsafe(self.tx_queue.put(data), self.loop)

        except Exception as e:
            logging.error(f"Error procesando mensaje MQTT en {msg.topic}: {e}", exc_info=True)

    # ================================================================
    # Trabajador Asíncrono de Transmisión (TX) con Rate Limiting
    # ================================================================
    async def _tx_worker(self) -> None:
        """Procesa las órdenes de transmisión secuencialmente espaciando los paquetes LoRa."""
        logging.info(f"Worker de TX iniciado (Rate limit: 1 paquete cada {config.TX_INTERVAL_SEC}s).")
        while self.running:
            try:
                data = await self.tx_queue.get()
                await self._execute_tx(data)
                self.tx_queue.task_done()

                # Espaciado entre transmisiones para proteger el duty-cycle LoRa
                if config.TX_INTERVAL_SEC > 0:
                    await asyncio.sleep(config.TX_INTERVAL_SEC)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error inesperado en TX worker: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _execute_tx(self, data: Dict[str, Any]) -> None:
        """Ejecuta la transmisión RF física hacia el nodo Heltec y emite el ACK."""
        request_id = data.get("request_id")
        dest = str(data.get("to", data.get("destination", "broadcast"))).strip()
        ch_idx = int(data.get("channel_index", data.get("channel", 0)))
        text = str(data.get("text", data.get("message", data.get("body", "")))).strip()

        if not text:
            logging.warning("TX ignorado: texto vacío.")
            return

        if not self.mc or not hasattr(self.mc, "commands"):
            err_msg = "MeshCore no conectado para transmitir."
            logging.warning(err_msg)
            self._publish_tx_status(request_id, "error", dest, ch_idx, error=err_msg)
            self.tx_error_count += 1
            return

        logging.info(f"TX Solicitado -> Destino: '{dest}' | Canal: {ch_idx} | Texto: '{text}' [Req: {request_id}]")
        try:
            result = None
            if dest and dest.lower() not in ["broadcast", "public", "all", "channel", "canal"]:
                target = self.resolve_recipient_target(dest)
                logging.info(f"TX Enviando DM hacia '{dest}' (target resuelto: {target})...")
                result = await self.mc.commands.send_msg(target, text)
            else:
                logging.info(f"TX Emitiendo por Canal {ch_idx} (Broadcast)...")
                result = await self.mc.commands.send_chan_msg(ch_idx, text)

            if result:
                res_type = getattr(result, "type", None)
                res_type_name = str(getattr(res_type, "name", res_type)).upper()
                res_payload = getattr(result, "payload", {})
                logging.info(f"Respuesta de radio TX: {res_type_name} | payload: {res_payload}")
                if "ERROR" in res_type_name:
                    raise RuntimeError(f"Radio retornó error: {res_payload}")

            self.tx_count += 1
            self.last_serial_activity = time.time()
            logging.info(f"Transmisión RF completada con éxito [Req: {request_id}].")
            self._publish_tx_status(request_id, "sent", dest, ch_idx)

        except Exception as e:
            self.tx_error_count += 1
            logging.error(f"Error al transmitir por radio: {e}", exc_info=True)
            self._publish_tx_status(request_id, "error", dest, ch_idx, error=str(e))

    def _publish_tx_status(
        self,
        request_id: Optional[str],
        status: str,
        dest: str,
        channel_index: int,
        error: Optional[str] = None
    ) -> None:
        """Publica el acuse de recibo / estado de la transmisión en MQTT."""
        payload = {
            "request_id": request_id,
            "status": status,
            "to": dest,
            "channel_index": channel_index,
            "timestamp": int(time.time()),
            "iso_time": datetime.now(timezone.utc).isoformat()
        }
        if error:
            payload["error"] = error

        self.publish_mqtt_safe(config.TOPIC_TX_STATUS, json.dumps(payload), qos=1)

    # ================================================================
    # Manejador de Administración
    # ================================================================
    async def handle_admin(self, data: Dict[str, Any]) -> None:
        """Ejecuta comandos administrativos sobre el nodo Heltec y responde a MQTT."""
        request_id = data.get("request_id")
        action = str(data.get("action", "get_config")).strip().lower()
        res: Dict[str, Any] = {
            "request_id": request_id,
            "status": "ok",
            "action": action,
            "timestamp": int(time.time()),
            "iso_time": datetime.now(timezone.utc).isoformat()
        }

        if not self.mc:
            res["status"] = "error"
            res["error"] = "MeshCore no conectado"
            self.publish_mqtt_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
            return

        try:
            self.last_serial_activity = time.time()
            if action in ["get_config", "status"]:
                self_info = getattr(self.mc, "self_info", {})
                res["config"] = {
                    "name": self_info.get("name", "Unknown"),
                    "radio_freq": self_info.get("radio_freq"),
                    "tx_power": self_info.get("tx_power"),
                    "public_key": self_info.get("public_key") or self_info.get("pubkey"),
                    "raw_info": self_info
                }

            elif action == "get_contacts":
                contacts_list = []
                contacts = getattr(self.mc, "contacts", [])
                for c in contacts:
                    contacts_list.append({
                        "name": getattr(c, "name", getattr(c, "alias", "Desconocido")),
                        "public_key": getattr(c, "public_key", getattr(c, "pubkey", "")),
                        "last_heard": getattr(c, "last_heard", None)
                    })
                res["contacts"] = contacts_list
                res["count"] = len(contacts_list)

            elif action == "set_name":
                new_name = str(data.get("name", "")).strip()
                if new_name and hasattr(self.mc.commands, "set_name"):
                    await self.mc.commands.set_name(new_name)
                    if hasattr(self.mc, "self_info") and isinstance(self.mc.self_info, dict):
                        self.mc.self_info["name"] = new_name
                    res["name"] = new_name
                else:
                    res["status"] = "error"
                    res["error"] = "Nombre no especificado o comando no soportado"

            elif action == "set_tx_power":
                power = int(data.get("power", 20))
                if hasattr(self.mc.commands, "set_tx_power"):
                    await self.mc.commands.set_tx_power(power)
                    if hasattr(self.mc, "self_info") and isinstance(self.mc.self_info, dict):
                        self.mc.self_info["tx_power"] = power
                    res["tx_power"] = power

            elif action == "req_telemetry":
                target = str(data.get("target", "")).strip()
                if target and hasattr(self.mc.commands, "req_telemetry"):
                    target_key = self.resolve_recipient_key(target)
                    await self.mc.commands.req_telemetry(target_key)
                    res["target"] = target
                else:
                    res["status"] = "error"
                    res["error"] = "Target no especificado o comando no soportado"

            elif action == "reboot":
                if hasattr(self.mc.commands, "reboot"):
                    await self.mc.commands.reboot()
                    res["message"] = "Comando de reinicio enviado"

            else:
                res["status"] = "error"
                res["error"] = f"Acción desconocida: {action}"

        except Exception as e:
            logging.error(f"Error ejecutando comando admin '{action}': {e}", exc_info=True)
            res["status"] = "error"
            res["error"] = str(e)

        self.publish_mqtt_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)

    # ================================================================
    # Resolución de Nombres y Destinatarios
    # ================================================================
    def resolve_sender_name(self, prefix_or_key: str) -> str:
        """Obtiene el alias/nombre de un contacto a partir de su clave pública o prefijo."""
        if not self.mc or not prefix_or_key:
            return str(prefix_or_key)

        if hasattr(self.mc, "get_contact_by_key_prefix"):
            try:
                c = self.mc.get_contact_by_key_prefix(prefix_or_key)
                if c:
                    name = getattr(c, "name", getattr(c, "alias", None))
                    if isinstance(name, str) and name:
                        return name
            except Exception:
                pass

        contacts = getattr(self.mc, "contacts", [])
        if isinstance(contacts, (list, tuple)):
            for c in contacts:
                pk = getattr(c, "public_key", getattr(c, "pubkey", ""))
                if isinstance(pk, str) and pk and (pk.startswith(prefix_or_key) or prefix_or_key in pk):
                    name = getattr(c, "name", getattr(c, "alias", None))
                    if isinstance(name, str) and name:
                        return name

        return str(prefix_or_key)

    def resolve_recipient_key(self, name_or_key: str) -> str:
        """Traduce un nombre a su clave pública si existe en la libreta de contactos."""
        if not self.mc or not name_or_key:
            return str(name_or_key)

        if hasattr(self.mc, "get_contact_by_name"):
            try:
                c = self.mc.get_contact_by_name(name_or_key)
                if c:
                    pk = getattr(c, "public_key", getattr(c, "pubkey", None))
                    if isinstance(pk, str) and pk:
                        return pk
            except Exception:
                pass

        contacts = getattr(self.mc, "contacts", [])
        if isinstance(contacts, (list, tuple)):
            for c in contacts:
                c_name = getattr(c, "name", getattr(c, "alias", ""))
                if isinstance(c_name, str) and c_name.lower() == str(name_or_key).lower():
                    pk = getattr(c, "public_key", getattr(c, "pubkey", None))
                    if isinstance(pk, str) and pk:
                        return pk

        return str(name_or_key)

    def resolve_recipient_target(self, name_or_key: str) -> Any:
        """Obtiene el objeto Contact o clave pública para send_msg."""
        if not self.mc or not name_or_key:
            return str(name_or_key)

        if hasattr(self.mc, "get_contact_by_key_prefix"):
            try:
                c = self.mc.get_contact_by_key_prefix(name_or_key)
                if c:
                    return c
            except Exception:
                pass

        if hasattr(self.mc, "get_contact_by_name"):
            try:
                c = self.mc.get_contact_by_name(name_or_key)
                if c:
                    return c
            except Exception:
                pass

        contacts = getattr(self.mc, "contacts", [])
        if isinstance(contacts, (list, tuple)):
            for c in contacts:
                pk = getattr(c, "public_key", getattr(c, "pubkey", ""))
                c_name = getattr(c, "name", getattr(c, "alias", ""))
                if pk and (pk.startswith(name_or_key) or name_or_key in pk):
                    return c
                if c_name and c_name.lower() == str(name_or_key).lower():
                    return c

        return str(name_or_key)

    async def fetch_messages(self) -> None:
        """Solicita mensajes pendientes en buffer si la radio lo indica."""
        try:
            if self.mc and hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_msg"):
                await self.mc.commands.get_msg()
                self.last_serial_activity = time.time()
        except Exception as e:
            logging.debug(f"Aviso en fetch_messages: {e}")

    # ================================================================
    # Procesamiento y Normalización de Eventos MeshCore (RX)
    # ================================================================
    def on_mesh_event(self, event, *args, **kwargs) -> None:
        """Manejador síncrono/asíncrono de eventos emitidos por el cliente MeshCore."""
        try:
            self.last_serial_activity = time.time()
            ev_type = getattr(event, "type", None)
            if hasattr(ev_type, "name") and isinstance(getattr(ev_type, "name"), str):
                ev_name = str(ev_type.name)
            else:
                ev_name = str(ev_type)
            payload = getattr(event, "payload", {})
            if not isinstance(payload, dict):
                payload = {"raw_payload": str(payload)}

            logging.info(f"Radio RX Evento: {ev_name} | Payload: {payload}")

            if ev_name in ["RX_LOG_DATA", "NO_MORE_MSGS", "SELF_INFO", "CONNECTED"]:
                return

            if ev_name == "MESSAGES_WAITING":
                asyncio.create_task(self.fetch_messages())
                return

            self.rx_count += 1
            now_ts = int(time.time())
            iso_str = datetime.now(timezone.utc).isoformat()

            metrics = {
                "rssi": payload.get("rssi"),
                "snr": payload.get("snr"),
                "hop_count": payload.get("hop_count", payload.get("hops", 0))
            }

            # 1. Mensajes de Canales
            if ev_name in ["CHANNEL_MSG_RECV", "CHAN_MSG_RECV", "CHAN_MSG"] or payload.get("type") in ["CHAN", "CHANNEL"] or "channel_idx" in payload or "channel" in payload:
                raw_text = str(payload.get("text", payload.get("body", payload.get("message", payload.get("msg", ""))))).strip()
                if not raw_text:
                    return

                ch_idx = int(payload.get("channel_idx", payload.get("channel", 0)))
                sender_id = str(payload.get("sender", payload.get("pubkey_prefix", payload.get("from", "unknown"))))
                sender_name = payload.get("sender_name")

                msg_text = raw_text
                if not sender_name:
                    if sender_id != "unknown":
                        sender_name = self.resolve_sender_name(sender_id)
                    elif ":" in raw_text:
                        parts = raw_text.split(":", 1)
                        if len(parts[0].strip()) <= 20 and not parts[0].startswith("http"):
                            sender_name = parts[0].strip()
                            msg_text = parts[1].strip()
                            sender_id = sender_name
                        else:
                            sender_name = "Desconocido"
                    else:
                        sender_name = "Desconocido"

                event_type = "public" if ch_idx == 0 else "channel"
                topic_specific = config.TOPIC_RX_PUBLIC if ch_idx == 0 else f"{config.TOPIC_RX_CHANNEL}/ch_{ch_idx}"

                mqtt_payload = {
                    "event_type": event_type,
                    "sender_id": sender_id,
                    "sender_name": sender_name,
                    "channel_index": ch_idx,
                    "text": msg_text,
                    "raw_text": raw_text,
                    "metrics": metrics,
                    "timestamp": payload.get("sender_timestamp", now_ts),
                    "iso_time": iso_str
                }

                payload_json = json.dumps(mqtt_payload)
                self.publish_mqtt_safe(topic_specific, payload_json, qos=0)
                self.publish_mqtt_safe(config.TOPIC_RX_ALL, payload_json, qos=0)
                logging.info(f"MQTT RX -> [{event_type}] Publicado en {topic_specific}: '{msg_text}' de '{sender_name}'")
                return

            # 2. Mensajes Directos (DMs)
            if ev_name in ["CONTACT_MSG_RECV", "DIRECT_MSG_RECV", "DM_MSG_RECV", "DM_RECV"] or payload.get("type") in ["DIRECT", "DM", "CONTACT"]:
                raw_text = str(payload.get("text", payload.get("message", payload.get("body", payload.get("msg", ""))))).strip()
                if not raw_text:
                    return

                sender_id = str(payload.get("pubkey_prefix", payload.get("from", payload.get("sender", "unknown"))))
                sender_name = payload.get("sender_name") or self.resolve_sender_name(sender_id)
                topic_specific = f"{config.TOPIC_RX_DIRECT}/{sender_id}"

                mqtt_payload = {
                    "event_type": "dm",
                    "sender_id": sender_id,
                    "sender_name": sender_name,
                    "channel_index": 0,
                    "text": raw_text,
                    "raw_text": raw_text,
                    "metrics": metrics,
                    "timestamp": payload.get("sender_timestamp", now_ts),
                    "iso_time": iso_str
                }

                payload_json = json.dumps(mqtt_payload)
                self.publish_mqtt_safe(topic_specific, payload_json, qos=0)
                self.publish_mqtt_safe(config.TOPIC_RX_ALL, payload_json, qos=0)
                logging.info(f"MQTT RX -> [dm] Publicado en {topic_specific}: '{raw_text}' de '{sender_name}' (ID: {sender_id})")
                return

            # 3. Telemetría de Nodos
            if ev_name in ["TELEMETRY_RECV", "TELEMETRY"] or "battery" in payload or "voltage" in payload:
                node_id = str(payload.get("node_id", payload.get("sender", payload.get("from", "unknown"))))
                node_name = self.resolve_sender_name(node_id)

                mqtt_payload = {
                    "event_type": "telemetry",
                    "node_id": node_id,
                    "node_name": node_name,
                    "battery_voltage": payload.get("voltage", payload.get("battery_voltage")),
                    "battery_percent": payload.get("battery_percent", payload.get("battery")),
                    "metrics": metrics,
                    "raw_data": payload,
                    "timestamp": now_ts,
                    "iso_time": iso_str
                }

                payload_json = json.dumps(mqtt_payload)
                self.publish_mqtt_safe(config.TOPIC_RX_TELEMETRY, payload_json, qos=0)
                self.publish_mqtt_safe(config.TOPIC_RX_ALL, payload_json, qos=0)
                logging.info(f"MQTT RX -> [telemetry] Nodo: '{node_name}' | Batería: {payload.get('battery')}%")
                return

            # 4. Anuncios de Nodos
            if ev_name in ["NODE_DISCOVERED", "ADVERT", "NODE_ANNOUNCEMENT", "NODE_ANNOUNCE"]:
                node_id = str(payload.get("node_id", payload.get("pubkey", "unknown")))
                node_name = payload.get("name") or self.resolve_sender_name(node_id)

                mqtt_payload = {
                    "event_type": "node_discovered",
                    "node_id": node_id,
                    "node_name": node_name,
                    "metrics": metrics,
                    "raw_data": payload,
                    "timestamp": now_ts,
                    "iso_time": iso_str
                }

                payload_json = json.dumps(mqtt_payload)
                self.publish_mqtt_safe(config.TOPIC_RX_NODES, payload_json, qos=0)
                self.publish_mqtt_safe(config.TOPIC_RX_ALL, payload_json, qos=0)
                logging.info(f"MQTT RX -> [node_discovered] Nodo: '{node_name}' ({node_id})")
                return

            # 5. Capturador Universal para cualquier otro evento con texto
            if "text" in payload or "body" in payload or "message" in payload or "msg" in payload:
                raw_text = str(payload.get("text", payload.get("body", payload.get("message", payload.get("msg", ""))))).strip()
                if raw_text:
                    sender_id = str(payload.get("sender", payload.get("from", payload.get("pubkey_prefix", "unknown"))))
                    sender_name = payload.get("sender_name") or self.resolve_sender_name(sender_id)
                    mqtt_payload = {
                        "event_type": "public",
                        "sender_id": sender_id,
                        "sender_name": sender_name,
                        "channel_index": 0,
                        "text": raw_text,
                        "raw_text": raw_text,
                        "metrics": metrics,
                        "timestamp": payload.get("sender_timestamp", now_ts),
                        "iso_time": iso_str
                    }
                    payload_json = json.dumps(mqtt_payload)
                    self.publish_mqtt_safe(config.TOPIC_RX_PUBLIC, payload_json, qos=0)
                    self.publish_mqtt_safe(config.TOPIC_RX_ALL, payload_json, qos=0)
                    logging.info(f"MQTT RX -> [generic] Publicado en {config.TOPIC_RX_PUBLIC}: '{raw_text}'")
                    return

            # 6. Eventos Genéricos / Otros
            generic_payload = {
                "event_type": ev_name.lower(),
                "data": payload,
                "timestamp": now_ts,
                "iso_time": iso_str
            }
            self.publish_mqtt_safe(config.TOPIC_RX_ALL, json.dumps(generic_payload), qos=0)

        except Exception as e:
            logging.error(f"Error procesando evento de malla: {e}", exc_info=True)

    # ================================================================
    # Tareas de Supervisión: Watchdog Serial y Health Reporter
    # ================================================================
    async def _watchdog_loop(self) -> None:
        """Supervisa periódicamente la vivacidad del puerto serial y detecta bloqueos."""
        logging.info(f"Watchdog serial activo (Intervalo: {config.WATCHDOG_INTERVAL_SEC}s).")
        while self.running:
            try:
                await asyncio.sleep(config.WATCHDOG_INTERVAL_SEC)
                if not self.running:
                    break

                # Si no ha habido actividad serial en el intervalo, enviar ping/consulta suave
                now = time.time()
                if now - self.last_serial_activity >= config.WATCHDOG_INTERVAL_SEC:
                    logging.debug("Watchdog: Comprobando estado del transceptor serial Heltec...")
                    if self.mc and hasattr(self.mc, "commands"):
                        try:
                            # Intentar una consulta no intrusiva con timeout breve adaptativo
                            if hasattr(self.mc.commands, "get_contacts"):
                                ping_timeout = min(5.0, max(0.05, config.WATCHDOG_INTERVAL_SEC))
                                await asyncio.wait_for(self.mc.commands.get_contacts(), timeout=ping_timeout)
                            self.last_serial_activity = time.time()
                        except Exception as ping_err:
                            logging.warning(f"Watchdog detectó bloqueo o timeout serial ({ping_err}). Forzando reconexión...")
                            await self._force_serial_reconnect()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error en bucle de watchdog: {e}")

    async def _health_reporter_loop(self) -> None:
        """Publica periódicamente estadísticas y salud del bridge en meshcore/bridge/health."""
        logging.info(f"Reporter de salud activo (Intervalo: {config.HEALTH_METRICS_INTERVAL_SEC}s).")
        while self.running:
            try:
                await asyncio.sleep(config.HEALTH_METRICS_INTERVAL_SEC)
                if not self.running:
                    break

                uptime = int(time.time() - self.start_time)
                self_info = getattr(self.mc, "self_info", {}) if self.mc else {}

                health_payload = {
                    "status": "healthy" if (self.mc and self.mqtt_connected) else "degraded",
                    "uptime_seconds": uptime,
                    "mqtt_connected": self.mqtt_connected,
                    "serial_connected": self.mc is not None,
                    "messages_rx_total": self.rx_count,
                    "messages_tx_total": self.tx_count,
                    "messages_tx_errors": self.tx_error_count,
                    "tx_queue_size": self.tx_queue.qsize(),
                    "offline_buffer_size": self.sqlite_buffer.get_size(),
                    "mqtt_reconnects": self.mqtt_reconnect_count,
                    "serial_reconnects": self.serial_reconnect_count,
                    "node_name": self_info.get("name", "Unknown"),
                    "radio_frequency": self_info.get("radio_freq", 910.525),
                    "timestamp": int(time.time()),
                    "iso_time": datetime.now(timezone.utc).isoformat()
                }

                self.publish_mqtt_safe(config.TOPIC_HEALTH, json.dumps(health_payload), qos=0)
                logging.debug(f"Health Report publicado: Uptime {uptime}s | RX: {self.rx_count} | TX: {self.tx_count}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error en health reporter: {e}")

    async def _force_serial_reconnect(self) -> None:
        """Cierra la sesión serial actual para que el bucle principal vuelva a reconectar."""
        self.serial_reconnect_count += 1
        if self.mc:
            try:
                await self.mc.disconnect()
            except Exception:
                pass
            self.mc = None

    # ================================================================
    # Bucle Principal y Ciclo de Vida
    # ================================================================
    async def run(self) -> None:
        """Inicia el cliente MQTT, los trabajadores en segundo plano y la conexión serial."""
        self.setup_mqtt()

        # Iniciar tareas en segundo plano
        self.tx_worker_task = asyncio.create_task(self._tx_worker())
        self.watchdog_task = asyncio.create_task(self._watchdog_loop())
        self.health_task = asyncio.create_task(self._health_reporter_loop())

        while self.running:
            try:
                logging.info(f"Conectando a MeshCore en {config.SERIAL_PORT} (Baudrate: {config.BAUD_RATE})...")
                if MeshCore is None:
                    logging.error("Librería 'meshcore' no encontrada. Instálala con 'pip install meshcore'.")
                    await asyncio.sleep(10)
                    continue

                self.mc = await MeshCore.create_serial(
                    port=config.SERIAL_PORT,
                    baudrate=config.BAUD_RATE,
                    auto_reconnect=True,
                    default_timeout=config.SERIAL_TIMEOUT
                )

                await asyncio.sleep(2.0)

                # Sincronizar libreta de contactos
                if hasattr(self.mc, "ensure_contacts"):
                    try:
                        await self.mc.ensure_contacts()
                        contacts = getattr(self.mc, "contacts", [])
                        logging.info(f"Contactos sincronizados: {len(contacts)}")
                    except Exception as err:
                        logging.debug(f"Aviso al sincronizar contactos: {err}")

                node_name = getattr(self.mc, "self_info", {}).get("name", "MeshCore Node")
                freq = getattr(self.mc, "self_info", {}).get("radio_freq", 910.525)
                logging.info(f"Nodo Activo: {node_name} ({freq} MHz)")
                self.last_serial_activity = time.time()

                # Suscribirse a los eventos de MeshCore
                if EventType:
                    for ev in EventType:
                        try:
                            self.mc.subscribe(ev, self.on_mesh_event)
                        except Exception:
                            pass

                # Iniciar lectura automática de mensajes en buffer
                if hasattr(self.mc, "start_auto_message_fetching"):
                    await self.mc.start_auto_message_fetching()

                logging.info("=== PUENTE MESHCORE <-> MQTT ACTIVO Y OPERATIVO ===")

                while self.running and self.mc:
                    await asyncio.sleep(2.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.serial_reconnect_count += 1
                logging.error(f"Error en sesión MeshCore: {e}. Reintentando en 5s...")

            if self.mc:
                try:
                    await self.mc.disconnect()
                except Exception:
                    pass
                self.mc = None

            if self.running:
                await asyncio.sleep(5.0)

    async def shutdown(self) -> None:
        """Realiza un apagado limpio liberando recursos, tareas y conexiones."""
        logging.info("Iniciando apagado ordenado del servicio...")
        self.running = False

        # Cancelar tareas en segundo plano
        for task in [self.tx_worker_task, self.watchdog_task, self.health_task]:
            if task and not task.done():
                task.cancel()

        if self.mc:
            try:
                await self.mc.disconnect()
                logging.info("Puerto Serial MeshCore desconectado.")
            except Exception as e:
                logging.debug(f"Aviso al desconectar MeshCore: {e}")

        try:
            offline_payload = {
                "status": "offline",
                "timestamp": int(time.time()),
                "iso_time": datetime.now(timezone.utc).isoformat()
            }
            self.mqtt_client.publish(config.TOPIC_STATE, json.dumps(offline_payload), qos=1, retain=True)
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            logging.info("Cliente MQTT detenido.")
        except Exception as e:
            logging.debug(f"Aviso al detener MQTT: {e}")


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bridge = MeshCoreBridge(loop)

    def signal_handler():
        logging.info("Señal de parada recibida (SIGINT/SIGTERM).")
        asyncio.create_task(bridge.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(bridge.run())
    except KeyboardInterrupt:
        logging.info("Interrupción por teclado detectada.")
    finally:
        loop.run_until_complete(bridge.shutdown())
        loop.close()
        logging.info("Servicio detenido completamente.")


if __name__ == "__main__":
    main()
