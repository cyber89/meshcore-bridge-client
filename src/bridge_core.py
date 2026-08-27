"""
Core Orchestrator and Lifecycle Manager for MeshCore Universal Bridge.
Integra el adaptador serial, cliente MQTT asíncrono, Rate Limiter con PriorityQueue,
Deduplicación en Memoria RAM, Registro Dinámico de Nodos y Gestión Remota de Repetidores.
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
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.deduplicator import PacketDeduplicator
from src.diagnostics import DiagnosticManager, SystemLogHandler
from src.health_reporter import HealthContext, HealthReporter
from src.mqtt_client import AsyncBridgeMQTTClient, MQTTConfig
from src.mqtt_dispatcher import MqttInboundContext, MqttInboundDispatcher
from src.preflight import PreflightChecker
from src.rate_limiter import CustomTxQueue, LoRaRadioConfig, TxItem, TxRateLimiter
from src.repeater_manager import RepeaterManager
from src.rx_router import RxEventRouter, RxRouterContext
from src.serial_driver import (
    BaseSerialAdapter,
    MeshcoreSDKAdapter,
    RawSerialFramingAdapter,
    SerialWatchdog,
)
from src.tcp_companion_server import MeshCoreCompanionServer
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

        self._init_storage_and_network()
        self._init_adapters_and_watchdog()
        self._init_metrics_and_tasks()
        self._build_sub_components()

    def _init_storage_and_network(self) -> None:
        """Inicializa deduplicador en RAM, registros y rate limiter."""
        self.deduplicator = PacketDeduplicator(
            window_seconds=getattr(config, "DEDUPLICATION_WINDOW_SEC", 60.0),
        )
        self.node_registry = NodeRegistry()
        self.repeater_manager = RepeaterManager()
        self.rate_limiter = TxRateLimiter(
            tx_interval_sec=config.TX_INTERVAL_SEC,
            radio_config=LoRaRadioConfig(
                sf=getattr(config, "LORA_DEFAULT_SF", 11),
                bw_khz=getattr(config, "LORA_DEFAULT_BW_KHZ", 250.0),
            ),
            transmit_callback=self._execute_tx_transmission,
        )
        self.mqtt = AsyncBridgeMQTTClient(
            config=MQTTConfig(
                broker=config.MQTT_BROKER,
                port=config.MQTT_PORT,
                username=config.MQTT_USER,
                password=config.MQTT_PASSWORD,
                keepalive=config.MQTT_KEEPALIVE,
                topic_prefix=config.TOPIC_PREFIX,
            ),
            on_rx_message_callback=self._on_incoming_mqtt_message,
        )
        self.preflight = PreflightChecker()

    def _init_adapters_and_watchdog(self) -> None:
        """Inicializa adaptador serial, watchdog, gestor de diagnóstico y servidor web."""
        self.log_handler = SystemLogHandler(
            max_records=500,
            broadcast_callback=self._broadcast_system_log,
        )
        logging.getLogger().addHandler(self.log_handler)
        self.diagnostics = DiagnosticManager(bridge=self, log_handler=self.log_handler)

        self.serial_adapter = self._create_serial_adapter()
        self.serial_adapter.set_rx_callback(self.on_mesh_event)
        self.serial_adapter.set_companion_rx_callback(self._on_raw_companion_frame_rx)
        self.watchdog = SerialWatchdog(
            adapter=self.serial_adapter,
            timeout_sec=config.SERIAL_TIMEOUT,
            interval_sec=config.WATCHDOG_INTERVAL_SEC,
            on_timeout_reconnect=self._reconnect_serial,
        )
        self.web_server = self._create_web_server()
        self.tcp_server = self._create_tcp_server()

    def _broadcast_system_log(self, payload: dict[str, Any]) -> None:
        """Difunde logs en tiempo real vía WebSocket a la interfaz web."""
        web = getattr(self, "web_server", None)
        if web is not None and getattr(self, "running", False):
            import asyncio; asyncio.create_task(web.broadcast_event(payload))

    def _on_raw_companion_frame_rx(self, payload: bytes) -> None:
        """Difunde tramas binarias de la radio hacia clientes TCP Companion conectados (App Móvil / CLI)."""
        tcp_srv = getattr(self, "tcp_server", None)
        if tcp_srv is not None and getattr(self, "running", False):
            import asyncio; asyncio.create_task(tcp_srv.broadcast_companion_frame(payload))

    async def handle_tcp_companion_command(self, payload: bytes, client_writer: Any) -> None:
        """Maneja comandos binarios enviados por apps móviles o CLI a través del socket TCP Companion."""
        if not payload:
            return
        if hasattr(self.serial_adapter, "send_raw_companion_frame"):
            await self.serial_adapter.send_raw_companion_frame(payload)

    def _init_metrics_and_tasks(self) -> None:
        """Inicializa contadores y conjuntos de tareas en background."""
        self.rx_count = 0
        self.tx_count = 0
        self.tx_error_count = 0
        self.err_count = 0
        self.serial_reconnect_count = 0
        self._health_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._tasks_lock = asyncio.Lock()
        self._tx_metrics_lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None

    async def _add_background_task(self, task: asyncio.Task[Any]) -> None:
        async with self._tasks_lock:
            self._background_tasks.add(task)

    async def _discard_background_task(self, task: asyncio.Task[Any]) -> None:
        async with self._tasks_lock:
            self._background_tasks.discard(task)

    async def _cleanup_loop(self) -> None:
        while self.running:
            await asyncio.sleep(60.0)
            async with self._tasks_lock:
                self._background_tasks = {t for t in self._background_tasks if not t.done()}

    def _create_web_server(self) -> MeshCoreWebServer | None:
        """Crea el servidor HTTP/WebSocket asíncrono si está habilitado por configuración."""
        if not getattr(config, "WEB_ENABLED", True):
            return None
        return MeshCoreWebServer(
            bridge=self,
            host=getattr(config, "WEB_HOST", "0.0.0.0"),  # nosec B104
            port=getattr(config, "WEB_PORT", 8080),
        )

    def _create_tcp_server(self) -> MeshCoreCompanionServer | None:
        """Crea el servidor TCP Companion asíncrono si está habilitado por configuración."""
        if not getattr(config, "TCP_SERVER_ENABLED", True):
            return None
        return MeshCoreCompanionServer(
            bridge=self,
            host=getattr(config, "TCP_SERVER_HOST", "0.0.0.0"),  # nosec B104
            port=getattr(config, "TCP_SERVER_PORT", 5000),
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
        self.rx_router._ctx.admin_handler = self.admin_handler

        self.health_reporter = HealthReporter(
            HealthContext(
                mqtt=self.mqtt,
                serial_adapter=self.serial_adapter,
                node_registry=self.node_registry,
                rate_limiter=self.rate_limiter,
                counters=self,
                start_time=self.start_time,
            ),
            interval_sec=config.HEALTH_METRICS_INTERVAL_SEC,
        )

    # ================= Propiedades de compatibilidad =================
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
    def mc(self) -> MeshCoreProtocol | Any | None:
        if isinstance(self.serial_adapter, MeshcoreSDKAdapter):
            return cast(MeshCoreProtocol | None, self.serial_adapter.mc)
        if hasattr(self.serial_adapter, "mc"):
            return getattr(self.serial_adapter, "mc", None)
        return None

    @mc.setter
    def mc(self, mc_val: MeshCoreProtocol | Any | None) -> None:
        if hasattr(self.serial_adapter, "mc"):
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
        if not contact:
            contact = self.node_registry.find_by_name(name_or_key)
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
                node_registry=self.node_registry,
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

        # 0. Diagnósticos Preflight de arranque
        report = self.preflight.run_all(
            mqtt_host=config.MQTT_BROKER,
            mqtt_port=config.MQTT_PORT,
            serial_port=getattr(self.serial_adapter, "port", config.SERIAL_PORT),
            tcp_server_port=getattr(config, "TCP_SERVER_PORT", 5000),
            tcp_server_enabled=getattr(config, "TCP_SERVER_ENABLED", True),
            tcp_server_host=getattr(config, "TCP_SERVER_HOST", "0.0.0.0"),  # nosec B104
        )
        logging.info(f"Preflight Diagnostics: Estado {report['status']} ({len(report['checks'])} comprobaciones realizadas)")

        # Iniciar Rate Limiter y Cliente MQTT
        self.rate_limiter.start()
        self.mqtt.start(loop=loop)

        # Conectar con hardware serial
        await self.serial_adapter.connect()
        self.watchdog.start()

        # Iniciar servidor web si está habilitado
        if self.web_server:
            await self.web_server.start()

        # Iniciar servidor TCP Companion si está habilitado
        if self.tcp_server:
            await self.tcp_server.start()

        # Auto-importación en arranque: canales, contactos y configuración del hardware Heltec
        await self._auto_bootstrap_heltec_state()

        # Iniciar reporte periódico de salud
        self._health_task = self.health_reporter.start()
        asyncio.create_task(self._add_background_task(self._health_task))
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logging.info("MeshCore Bridge iniciado y operativo (v3.0).")

    async def stop(self) -> None:
        """Detención ordenada de todos los subsistemas."""
        logging.info("Deteniendo MeshCore Bridge...")
        self.running = False

        # Detención resiliente: cada subsistema se cierra independientemente
        # para evitar que un fallo deje zombies activos (BUG-02 fix)
        for subsystem_name, coro in [
            ("tcp_server", self.tcp_server.stop() if self.tcp_server else None),
            ("web_server", self.web_server.stop() if self.web_server else None),
            ("health_reporter", self.health_reporter.stop()),
            ("watchdog", self.watchdog.stop()),
            ("rate_limiter", self.rate_limiter.stop()),
            ("serial_adapter", self.serial_adapter.disconnect()),
        ]:
            if coro is None:
                continue
            try:
                await coro
            except Exception as e:
                logging.error(f"Error deteniendo {subsystem_name}: {e}", exc_info=True)

        # Emitir estado offline explícito antes de cerrar
        try:
            offline_payload = json.dumps({"status": "offline", "timestamp": int(time.time())})
            self.mqtt.publish_safe(config.TOPIC_STATE, offline_payload, qos=1, retain=True)
        except Exception as e:
            logging.error(f"Error publicando estado offline MQTT: {e}")

        try:
            self.mqtt.stop()
        except Exception as e:
            logging.error(f"Error deteniendo cliente MQTT: {e}")

        if hasattr(self, "log_handler") and self.log_handler in logging.getLogger().handlers:
            logging.getLogger().removeHandler(self.log_handler)
        logging.info("MeshCore Bridge detenido correctamente.")

    async def shutdown(self) -> None:
        """Alias retrocompatible para detener de forma ordenada el bridge."""
        await self.stop()

    async def _auto_bootstrap_heltec_state(self) -> None:
        """
        Importa automáticamente canales, contactos y configuración del transceptor Heltec
        al arrancar el script, garantizando que la Web Station disponga de todos los datos reales.
        """
        logging.info("Iniciando auto-importación inicial de canales, contactos y configuración del nodo Heltec...")
        # 1. Sincronizar canales configurados en el hardware
        if hasattr(self.serial_adapter, "get_channels") and self.web_server:
            try:
                node_channels = await self.serial_adapter.get_channels()
                if node_channels:
                    for ch in node_channels:
                        idx = int(ch.get("index", 0))
                        self.web_server.router.channels[idx] = ch
                    logging.info(f"Auto-importados {len(node_channels)} canales desde el transceptor serial.")
            except Exception as e:
                logging.debug(f"Error en auto-importación de canales: {e}")

        # 2. Sincronizar libreta de contactos desde el hardware
        if hasattr(self.serial_adapter, "sync_all_contacts"):
            try:
                imported_contacts = await self.serial_adapter.sync_all_contacts()
                if imported_contacts:
                    for c in imported_contacts:
                        pk = str(c.get("public_key", "")).strip()
                        if pk:
                            self.node_registry.add_or_update(
                                pk,
                                NodeContactUpdate(
                                    name=c.get("name") or c.get("adv_name"),
                                    alias=c.get("alias"),
                                    role=c.get("role", "CLIENT"),
                                    auto_discovered=False,
                                    is_favorite=True,
                                ),
                            )

                    logging.info(f"Auto-importados {len(imported_contacts)} contactos desde el transceptor serial.")
            except Exception as e:
                logging.debug(f"Error en auto-importación de contactos: {e}")

        # 3. Consultar y cachear configuración del dispositivo
        if hasattr(self.admin_handler, "fetch_device_config"):
            try:
                cfg = await self.admin_handler.fetch_device_config()
                if cfg and "public_key" in cfg:
                    local_pk = str(cfg["public_key"]).strip().lower()
                    self.node_registry.set_local_pubkey(local_pk)
                    self.node_registry.add_or_update(
                        local_pk,
                        NodeContactUpdate(
                            name=cfg.get("name", "Estación Base"),
                            role="LOCAL",
                            is_local=True,
                            auto_discovered=False,
                            hops=0,
                        ),
                    )
                logging.info("Configuración de radio y hardware del nodo Heltec sincronizada.")
            except Exception as e:
                logging.debug(f"Error consultando parámetros de radio del nodo: {e}")

    async def _reconnect_serial(self) -> None:
        """Rutina de reconexión segura invocada por el Watchdog con pausa de estabilización USB."""
        logging.info("Ejecutando reconexión de puerto serial con estabilización USB...")
        self.serial_reconnect_count += 1
        await self.serial_adapter.disconnect()
        # Pausa esencial de 1.5s para permitir que el kernel y el USB CDC liberen el endpoint
        await asyncio.sleep(1.5)
        success = await self.serial_adapter.connect()
        if success:
            logging.info("Reconexión de transceptor serial completada con éxito.")
        else:
            logging.warning("Intento de reconexión serial no completado. El Watchdog continuará intentando en background.")

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
        try:
            await self.serial_adapter.connect()
        except Exception as e:
            logging.warning(f"Error reconnecting in _force_serial_reconnect: {e}")

    async def _watchdog_loop(self) -> None:
        """Bucle de supervisión del Watchdog para compatibilidad de tests."""
        while getattr(self, "running", True):
            await asyncio.sleep(config.WATCHDOG_INTERVAL_SEC)


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

        async with self._tx_metrics_lock:
            self.tx_count += 1
        status_val = "sent"
        error_detail: str | None = None

        expected_ack_hex: str | None = None
        try:
            if self.serial_adapter and self.serial_adapter.is_connected:
                target_arg = str(target) if target and str(target).lower() not in ("broadcast", "public", "0xffff") and not str(target).lower().startswith("channel") else None
                send_res = await self.serial_adapter.send_message(text=text, target=target_arg, channel_idx=ch_idx)
                if isinstance(send_res, dict):
                    expected_ack_hex = send_res.get("expected_ack")
                    res_obj = send_res.get("event")
                    if res_obj is not None:
                        ev_type = str(getattr(res_obj, "type", ""))
                        if ev_type.upper() in ("ERROR", "ERR") or "ERR_" in str(res_obj):
                            status_val = "error"
                            async with self._tx_metrics_lock:
                                self.tx_error_count += 1
                            error_detail = str(getattr(res_obj, "payload", "Radio returned error event"))
            elif self.mc and hasattr(self.mc, "commands"):
                res_obj = None
                target_str = str(target).lower()
                if target and target_str not in ("broadcast", "public", "0xffff") and not target_str.startswith("channel"):
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
                        async with self._tx_metrics_lock:
                            self.tx_error_count += 1
                        error_detail = str(getattr(res_obj, "payload", "Radio returned error event"))
                    elif hasattr(res_obj, "payload") and isinstance(res_obj.payload, dict):
                        exp_raw = res_obj.payload.get("expected_ack")
                        if isinstance(exp_raw, (bytes, bytearray)):
                            expected_ack_hex = exp_raw.hex().lower()
                        elif isinstance(exp_raw, str):
                            expected_ack_hex = exp_raw.lower()
            else:
                raise ConnectionError("Puerto serial / MeshCore no conectado")

        except Exception as e:
            async with self._tx_metrics_lock:
                self.tx_error_count += 1
            status_val = "error"
            error_detail = str(e)

        # Publicar ACK de transmisión
        ack_payload: dict[str, Any] = {
            "status": status_val,
            "request_id": req_id,
            "target": target,
            "channel_idx": ch_idx,
            "expected_ack": expected_ack_hex,
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
            asyncio.create_task(self._add_background_task(task))

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
            
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
            loop.close()
