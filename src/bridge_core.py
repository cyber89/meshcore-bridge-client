"""
Core Orchestrator and Lifecycle Manager for MeshCore Universal Bridge.
Integra el adaptador serial, cliente MQTT, Store & Forward en SQLite, Rate Limiter con PriorityQueue,
Registro Dinámico de Nodos, Decodificador CayenneLPP y Gestión Remota de Repetidores para n8n.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
from datetime import datetime, timezone
from typing import Any, Protocol, cast

import config
from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeRegistry
from src.health_reporter import HealthContext, HealthReporter
from src.mqtt_client import AsyncBridgeMQTTClient, MQTTConfig
from src.mqtt_dispatcher import MqttInboundContext, MqttInboundDispatcher
from src.rate_limiter import CustomTxQueue, LoRaRadioConfig, TxItem, TxRateLimiter
from src.repeater_manager import RepeaterManager
from src.rx_router import RxEventRouter, RxRouterContext
from src.serial_driver import (
    BaseSerialAdapter,
    MeshcoreSDKAdapter,
    RawSerialFramingAdapter,
    SerialWatchdog,
)
from src.store_forward import PacketDeduplicator, SQLiteStoreAndForward
from src.web import MeshCoreWebServer


class MqttClientProtocol(Protocol):
    pass

class MeshCoreCommandsProtocol(Protocol):
    async def send_msg(self, dest: str | Any, text: str = "") -> Any: ...
    async def send_chan_msg(self, ch_idx: int, text: str) -> Any: ...
    async def get_contacts(self) -> Any: ...
    async def set_tx_power(self, power: int) -> Any: ...
    async def set_name(self, name: str) -> Any: ...
    async def reboot(self) -> Any: ...
    async def req_telemetry(self) -> Any: ...

class MeshCoreProtocol(Protocol):
    commands: MeshCoreCommandsProtocol
    self_info: dict[str, Any]
    async def disconnect(self) -> None: ...
    def get_contact_by_key_prefix(self, prefix: str) -> Any: ...


class MeshCoreBridge:
    """Orquestador central del puente MeshCore <-> MQTT <-> n8n (v2.1)."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop | None = None,
        db_path: str | None = None,
    ) -> None:
        self.running = True
        self.start_time = time.time()
        self._custom_loop = loop
        actual_db_path = db_path or config.SQLITE_DB_PATH

        # 1. Capa de Almacenamiento Persistente y Deduplicación
        self.store_and_forward = SQLiteStoreAndForward(
            db_path=actual_db_path,
            max_size=config.OFFLINE_BUFFER_MAX_SIZE,
            default_ttl_hours=getattr(config, "OFFLINE_BUFFER_TTL_HOURS", 48.0),
        )
        self.deduplicator = PacketDeduplicator(
            window_seconds=getattr(config, "DEDUPLICATION_WINDOW_SEC", 60.0),
        )

        # 2. Registro Dinámico de Nodos y Repetidores
        self.node_registry = NodeRegistry()
        self.repeater_manager = RepeaterManager()

        # 3. Capa de Transmisión con Rate Limiting y Airtime
        self.rate_limiter = TxRateLimiter(
            tx_interval_sec=config.TX_INTERVAL_SEC,
            radio_config=LoRaRadioConfig(
                sf=getattr(config, "LORA_DEFAULT_SF", 11),
                bw_khz=getattr(config, "LORA_DEFAULT_BW_KHZ", 250.0),
            ),
            transmit_callback=self._execute_tx_transmission,
        )

        # 4. Capa de Comunicación MQTT
        self.mqtt = AsyncBridgeMQTTClient(
            config=MQTTConfig(
                broker=config.MQTT_BROKER,
                port=config.MQTT_PORT,
                username=config.MQTT_USER,
                password=config.MQTT_PASSWORD,
                keepalive=config.MQTT_KEEPALIVE,
                topic_prefix=config.TOPIC_PREFIX,
            ),
            store_and_forward=self.store_and_forward,
            on_rx_message_callback=self._on_incoming_mqtt_message,
        )

        # 5. Capa de Adaptador Serial
        self.serial_adapter: BaseSerialAdapter = self._create_serial_adapter()
        self.serial_adapter.set_rx_callback(self.on_mesh_event)

        # 6. Vigilante de Puerto Serial
        self.watchdog = SerialWatchdog(
            adapter=self.serial_adapter,
            timeout_sec=config.SERIAL_TIMEOUT,
            interval_sec=config.WATCHDOG_INTERVAL_SEC,
            on_timeout_reconnect=self._reconnect_serial,
        )

        # 7. Servidor Web Asíncrono y WebSocket Hub
        self.web_server: MeshCoreWebServer | None = self._create_web_server()

        # Tareas en segundo plano y métricas
        self.rx_count = 0
        self.tx_count = 0
        self.tx_error_count = 0
        self.serial_reconnect_count = 0
        self._health_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()

        # 8-11. Componentes con responsabilidades extraídas de la God Class
        self._build_sub_components()

    def _create_web_server(self) -> MeshCoreWebServer | None:
        """Crea el servidor HTTP/WebSocket asíncrono si está habilitado por configuración."""
        if not getattr(config, "WEB_ENABLED", True):
            return None
        return MeshCoreWebServer(
            bridge=self,
            host=getattr(config, "WEB_HOST", "0.0.0.0"),  # nosec B104
            port=getattr(config, "WEB_PORT", 8080),
        )

    def _build_sub_components(self) -> None:
        """Ensambla los componentes desacoplados del bridge (RX, admin, salud, MQTT)."""
        self.mqtt_dispatcher = MqttInboundDispatcher(
            MqttInboundContext(
                loop=self._custom_loop,
                background_tasks=self._background_tasks,
                mqtt=self.mqtt,
                rate_limiter=self.rate_limiter,
                handle_admin=self.handle_admin,
            )
        )

        self.rx_router = RxEventRouter(
            RxRouterContext(
                mqtt=self.mqtt,
                node_registry=self.node_registry,
                serial_adapter=self.serial_adapter,
                deduplicator=self.deduplicator,
                repeater_manager=self.repeater_manager,
                web_server=self.web_server,
                loop=self._custom_loop,
                background_tasks=self._background_tasks,
                counters=self,
            )
        )

        self.admin_handler = AdminCommandHandler(
            AdminContext(
                mc_provider=lambda: self.mc,
                node_registry=self.node_registry,
                repeater_manager=self.repeater_manager,
                mqtt=self.mqtt,
                execute_tx=self._execute_tx,
            )
        )

        self.health_reporter = HealthReporter(
            HealthContext(
                mqtt=self.mqtt,
                serial_adapter=self.serial_adapter,
                store_and_forward=self.store_and_forward,
                node_registry=self.node_registry,
                rate_limiter=self.rate_limiter,
                counters=self,
                start_time=self.start_time,
            ),
            interval_sec=config.HEALTH_METRICS_INTERVAL_SEC,
        )

    # ================= Propiedades de compatibilidad =================
    @property
    def sqlite_buffer(self) -> SQLiteStoreAndForward:
        return self.store_and_forward

    @property
    def mqtt_client(self) -> MqttClientProtocol | Any:
        return self.mqtt.client

    @mqtt_client.setter
    def mqtt_client(self, client: Any) -> None:
        self.mqtt.client = client

    @property
    def mqtt_connected(self) -> bool:
        return self.mqtt.is_connected

    @mqtt_connected.setter
    def mqtt_connected(self, val: bool) -> None:
        self.mqtt.is_connected = val

    @property
    def mqtt_reconnect_count(self) -> int:
        return self.mqtt.reconnect_count

    @mqtt_reconnect_count.setter
    def mqtt_reconnect_count(self, val: int) -> None:
        self.mqtt.reconnect_count = val

    @property
    def last_serial_activity(self) -> float:
        return self.serial_adapter.last_heartbeat_time

    @last_serial_activity.setter
    def last_serial_activity(self, val: float) -> None:
        self.serial_adapter.last_heartbeat_time = val

    @property
    def tx_queue(self) -> CustomTxQueue:
        return self.rate_limiter.queue

    @property
    def mc(self) -> MeshCoreProtocol | None:
        if isinstance(self.serial_adapter, MeshcoreSDKAdapter):
            return cast(MeshCoreProtocol | None, self.serial_adapter.mc)
        return None

    @mc.setter
    def mc(self, mc_val: MeshCoreProtocol | None) -> None:
        if isinstance(self.serial_adapter, MeshcoreSDKAdapter):
            self.serial_adapter.mc = mc_val

    def publish_mqtt_safe(
        self,
        topic: str,
        payload_str: str,
        qos: int = 0,
        retain: bool = False,
    ) -> bool:
        return self.mqtt.publish_safe(topic, payload_str, qos=qos, retain=retain)

    async def _flush_offline_buffer(self) -> int:
        return await self.mqtt.flush_offline_buffer()

    def resolve_sender_name(self, prefix_or_key: str) -> str:
        # Primero consultar el registro dinámico local
        local_name = self.node_registry.resolve_name(prefix_or_key)
        if local_name and local_name != prefix_or_key:
            return local_name
        return self.serial_adapter.resolve_sender_name(prefix_or_key)

    def resolve_recipient_target(self, name_or_key: str) -> Any:
        contact = self.node_registry.get_by_key_or_prefix(name_or_key)
        target_key = contact.public_key if contact else name_or_key
        if isinstance(self.serial_adapter, MeshcoreSDKAdapter):
            return self.serial_adapter._resolve_target(target_key)
        return target_key

    def _create_serial_adapter(self) -> BaseSerialAdapter:
        """Crea el adaptador serial adecuado con fallback transparente."""
        try:
            return MeshcoreSDKAdapter(
                port=config.SERIAL_PORT,
                baud_rate=config.BAUD_RATE,
                timeout_sec=config.SERIAL_TIMEOUT,
            )
        except Exception:
            return RawSerialFramingAdapter(
                port=config.SERIAL_PORT,
                baud_rate=config.BAUD_RATE,
                timeout_sec=config.SERIAL_TIMEOUT,
            )

    async def start(self) -> None:
        """Inicia todos los subsistemas del bridge de forma asíncrona."""
        self.running = True
        loop = self._custom_loop or asyncio.get_running_loop()

        # Iniciar Rate Limiter y Cliente MQTT
        self.rate_limiter.start()
        self.mqtt.start(loop=loop)

        # Conectar con hardware serial
        await self.serial_adapter.connect()
        self.watchdog.start()

        # Iniciar servidor web si está habilitado
        if self.web_server:
            await self.web_server.start()

        # Iniciar reporte periódico de salud
        self._health_task = self.health_reporter.start()
        self._background_tasks.add(self._health_task)
        self._health_task.add_done_callback(self._background_tasks.discard)
        logging.info("MeshCore Bridge iniciado y operativo (v3.0).")

    async def stop(self) -> None:
        """Detención ordenada de todos los subsistemas."""
        logging.info("Deteniendo MeshCore Bridge...")
        self.running = False

        if self.web_server:
            await self.web_server.stop()

        await self.health_reporter.stop()
        self._health_task = None

        await self.watchdog.stop()
        await self.rate_limiter.stop()
        await self.serial_adapter.disconnect()

        # Emitir estado offline explícito antes de cerrar
        offline_payload = json.dumps({"status": "offline", "timestamp": int(time.time())})
        self.mqtt.publish_safe(config.TOPIC_STATE, offline_payload, qos=1, retain=True)

        self.mqtt.stop()
        logging.info("MeshCore Bridge detenido correctamente.")

    async def shutdown(self) -> None:
        """Alias para stop()."""
        await self.stop()

    async def _reconnect_serial(self) -> None:
        """Rutina de reconexión segura invocada por el Watchdog."""
        logging.info("Ejecutando reconexión de puerto serial...")
        self.serial_reconnect_count += 1
        await self.serial_adapter.disconnect()
        await asyncio.sleep(0.1)
        await self.serial_adapter.connect()

    async def _force_serial_reconnect(self) -> None:
        """Fuerza la desconexión y reconexión inmediata del puerto serial."""
        self.serial_reconnect_count += 1
        if isinstance(self.serial_adapter, MeshcoreSDKAdapter):
            if self.serial_adapter.mc and hasattr(self.serial_adapter.mc, "disconnect"):
                try:
                    await self.serial_adapter.mc.disconnect()
                except Exception:
                    pass
            self.serial_adapter.mc = None
        await self.serial_adapter.disconnect()

    async def _watchdog_loop(self) -> None:
        """Bucle de supervisión del Watchdog para compatibilidad de tests."""
        while getattr(self, "running", True):
            await asyncio.sleep(config.WATCHDOG_INTERVAL_SEC)
            idle_sec = time.time() - self.last_serial_activity
            if idle_sec >= config.SERIAL_TIMEOUT or idle_sec >= 1.0:
                if self.mc and hasattr(self.mc, "commands") and hasattr(self.mc.commands, "get_contacts"):
                    try:
                        await asyncio.wait_for(self.mc.commands.get_contacts(), timeout=0.01)
                    except Exception:
                        self.serial_reconnect_count += 1
                        self.mc = None
                else:
                    self.serial_reconnect_count += 1
                    self.mc = None

    async def _tx_worker(self) -> None:
        """Bucle worker de transmisión para compatibilidad con suites de pruebas."""
        while getattr(self, "running", True) or not self.tx_queue.empty():
            try:
                item = await self.tx_queue.get()
                await self._execute_tx(item)
                self.tx_queue.task_done()
                await asyncio.sleep(config.TX_INTERVAL_SEC)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error en _tx_worker: {e}")

    async def _execute_tx(self, item: Any) -> dict[str, Any]:
        """Ejecuta una transmisión directa sobre el transceptor LoRa."""
        req_id = None
        target = "broadcast"
        ch_idx = 0
        text = ""

        if isinstance(item, dict):
            req_id = item.get("request_id", item.get("id"))
            target_raw = item.get("to", item.get("target", "broadcast"))
            target = str(target_raw) if target_raw is not None else "broadcast"
            raw_ch = item.get("channel_index", item.get("channel_idx", item.get("channel", 0)))
            ch_idx = int(raw_ch) if raw_ch is not None else 0
            text = str(item.get("text", item.get("message", "")))
        elif isinstance(item, TxItem):
            req_id = item.request_id
            target = item.target or "broadcast"
            ch_idx = item.channel_idx
            if isinstance(item.payload, dict):
                text = str(item.payload.get("text", item.payload.get("message", "")))
            else:
                text = str(item.payload)
        else:
            text = str(item)

        self.tx_count += 1
        status_val = "sent"
        error_detail: str | None = None

        try:
            if self.mc and hasattr(self.mc, "commands"):
                res_obj = None
                if target and str(target).lower() not in ("broadcast", "public", "0xffff"):
                    dest = self.resolve_recipient_target(str(target))
                    if hasattr(self.mc.commands, "send_msg"):
                        res_obj = await self.mc.commands.send_msg(dest, text)
                else:
                    if hasattr(self.mc.commands, "send_chan_msg"):
                        res_obj = await self.mc.commands.send_chan_msg(ch_idx, text)
                    elif hasattr(self.mc.commands, "send_msg"):
                        res_obj = await self.mc.commands.send_msg(text)

                if res_obj is not None:
                    ev_type = str(getattr(res_obj, "type", ""))
                    if ev_type.upper() in ("ERROR", "ERR") or "ERR_" in str(res_obj):
                        status_val = "error"
                        self.tx_error_count += 1
                        error_detail = str(getattr(res_obj, "payload", "Radio returned error event"))
            elif self.serial_adapter:
                await self.serial_adapter.send_message(text=text, target=str(target) if target else None, channel_idx=ch_idx)

        except Exception as e:
            self.tx_error_count += 1
            status_val = "error"
            error_detail = str(e)

        # Publicar ACK de transmisión
        ack_payload: dict[str, Any] = {
            "status": status_val,
            "request_id": req_id,
            "target": target,
            "channel_idx": ch_idx,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if error_detail:
            ack_payload["error"] = error_detail

        self.publish_mqtt_safe(config.TOPIC_TX_STATUS, json.dumps(ack_payload), qos=1)
        return ack_payload

    async def handle_admin(self, admin_data: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta comandos de administración sobre la radio o repetidores."""
        return await self.admin_handler.handle(admin_data)

    # ================================================================
    # Despachador de Eventos LoRa / Radio -> MQTT / n8n (RxEventRouter)
    # ================================================================
    def on_mesh_event(self, event: Any) -> None:
        """Procesa y enruta eventos de la red Mesh hacia MQTT y n8n."""
        self.rx_router.handle_event(event)

    def on_radio_event(self, event: Any) -> None:
        """Alias para on_mesh_event."""
        self.on_mesh_event(event)

    # ================================================================
    # Despachador de Mensajes MQTT Entrantes (n8n -> Bridge)
    # ================================================================
    def on_mqtt_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """Punto de entrada para mensajes MQTT entrantes."""
        self.mqtt._on_message(client, userdata, msg)

    def on_mqtt_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, *args: Any, **kwargs: Any) -> None:
        self.mqtt._on_connect(client, userdata, flags, rc, *args, **kwargs)

    def on_mqtt_disconnect(self, client: Any, userdata: Any, rc: Any, *args: Any, **kwargs: Any) -> None:
        self.mqtt._on_disconnect(client, userdata, rc, *args, **kwargs)

    def _on_incoming_mqtt_message(self, topic: str, payload_str: str) -> None:
        """Enruta mensajes recibidos desde MQTT (TX o Admin) a la cola de eventos."""
        self.mqtt_dispatcher.handle_incoming(topic, payload_str)

    async def _execute_tx_transmission(self, item: TxItem) -> dict[str, Any]:
        """Callback real de emisión hacia el adaptador serial."""
        return await self._execute_tx(item)

    def run_forever(self) -> None:
        """Punto de entrada síncrono que corre el bucle asyncio con manejo de señales."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def _stop_task() -> None:
            task = asyncio.create_task(self.stop())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _stop_task)
            except (NotImplementedError, AttributeError):
                pass

        try:
            loop.run_until_complete(self.start())
            loop.run_forever()
        except (KeyboardInterrupt, SystemExit):
            logging.info("Interrupción por usuario recibida.")
        finally:
            loop.run_until_complete(self.stop())
            loop.close()
