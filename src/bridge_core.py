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
from src.diagnostics import DiagnosticManager, SystemLogHandler, setup_file_logging
from src.health_reporter import HealthContext, HealthReporter
from src.mqtt_client import AsyncBridgeMQTTClient, MQTTConfig
from src.mqtt_dispatcher import MqttInboundContext, MqttInboundDispatcher
from src.packet_buffer import PacketBuffer
from src.preflight import PreflightChecker
from src.rate_limiter import (
    CustomTxQueue,
    LoRaRadioConfig,
    TxItem,
    TxRateLimiter,
    estimate_lora_airtime_ms,
)
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
    def publish(self, topic: str, payload: str | bytes, qos: int = 0, retain: bool = False) -> None: ...
    def subscribe(self, topic: str, qos: int = 0) -> None: ...
    def loop_start(self) -> None: ...
    def loop_stop(self) -> None: ...
    def connect_async(self, host: str, port: int, keepalive: int) -> None: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...

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
        self._is_stopped = False
        self._cleanup_task: asyncio.Task[None] | None = None
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
        self.packet_buffer = PacketBuffer(max_packets=500)
        self.node_registry = NodeRegistry()
        try:
            self.node_registry.load_from_file()
        except Exception as e:
            logging.debug(f"No se pudo cargar NodeRegistry previo: {e}")
        self.repeater_manager = RepeaterManager()
        self.rate_limiter = TxRateLimiter(
            tx_interval_sec=config.TX_INTERVAL_SEC,
            radio_config=LoRaRadioConfig(
                sf=getattr(config, "LORA_DEFAULT_SF", 11),
                bw_khz=getattr(config, "LORA_DEFAULT_BW_KHZ", 250.0),
                cr=getattr(config, "LORA_DEFAULT_CR", 5),
                preamble_len=getattr(config, "LORA_PREAMBLE_LEN", 8),
            ),
            transmit_callback=self._execute_tx_transmission,
            duty_cycle_limit_pct=getattr(config, "DUTY_CYCLE_LIMIT_PCT", 1.0),
            warn_threshold_pct=getattr(config, "DUTY_CYCLE_WARN_THRESHOLD_PCT", 80.0),
            history_file=getattr(config, "AIRTIME_HISTORY_FILE", None),
            on_alert_callback=self._on_duty_cycle_alert,
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
        self._pending_acks: dict[str, dict[str, Any]] = {}

    def register_pending_ack(self, expected_ack: str, req_id: str, target: str = "") -> None:
        """Registra un expected_ack para correlacionar la entrega con el msg_id."""
        clean_ack = str(expected_ack).lower().strip()
        if clean_ack.startswith("0x"):
            clean_ack = clean_ack[2:]
        if not clean_ack:
            return
        now = time.time()
        # Podar entradas de más de 1 hora si la tabla supera 200 elementos
        if len(self._pending_acks) > 200:
            self._pending_acks = {k: v for k, v in self._pending_acks.items() if now - v.get("timestamp", 0) < 3600}
        self._pending_acks[clean_ack] = {
            "req_id": req_id,
            "timestamp": now,
            "target": target,
        }

    def resolve_pending_ack(self, ack_code: str) -> dict[str, Any] | None:
        """Resuelve el msg_id y target asociados a un código ACK recibido."""
        clean_ack = str(ack_code).lower().strip()
        if clean_ack.startswith("0x"):
            clean_ack = clean_ack[2:]
        if not clean_ack:
            return None
        return self._pending_acks.get(clean_ack)

    def _init_adapters_and_watchdog(self) -> None:
        """Inicializa adaptador serial, watchdog, gestor de diagnóstico y servidor web."""
        default_lvl = getattr(logging, getattr(config, "LOG_LEVEL", "INFO").upper(), logging.INFO)
        self.log_handler = SystemLogHandler(
            max_records=500,
            broadcast_callback=self._broadcast_system_log,
            level=default_lvl,
        )
        self.log_handler.setLevel(default_lvl)
        logging.getLogger().addHandler(self.log_handler)
        self.diagnostics = DiagnosticManager(bridge=self, log_handler=self.log_handler)

        # Asegurar logging persistente rotativo a disco si no fue configurado previamente
        has_file_handler = any(
            isinstance(h, logging.Handler) and getattr(h, "baseFilename", None)
            for h in logging.getLogger().handlers
        )
        if not has_file_handler:
            setup_file_logging(
                log_file_path=getattr(config, "LOG_FILE_PATH", "logs/meshcore-bridge.log"),
                error_file_path=getattr(config, "LOG_ERROR_FILE_PATH", "logs/meshcore-bridge.error.log"),
                max_bytes=getattr(config, "LOG_MAX_BYTES", 5 * 1024 * 1024),
                backup_count=getattr(config, "LOG_BACKUP_COUNT", 3),
                level=getattr(config, "LOG_LEVEL", "INFO"),
            )

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
        """Difunde logs en tiempo real vía WebSocket a la interfaz web de forma thread-safe."""
        web = getattr(self, "web_server", None)
        if web is None or not getattr(self, "running", False):
            return

        loop = getattr(self, "_custom_loop", None)
        if loop and loop.is_running():
            try:
                running_loop = asyncio.get_running_loop()
                if running_loop is loop:
                    task = asyncio.create_task(web.broadcast_event(payload))
                    self._add_background_task(task)
                else:
                    asyncio.run_coroutine_threadsafe(web.broadcast_event(payload), loop)
            except RuntimeError:
                asyncio.run_coroutine_threadsafe(web.broadcast_event(payload), loop)
        else:
            try:
                coro = web.broadcast_event(payload)
                try:
                    task = asyncio.create_task(coro)
                    self._add_background_task(task)
                except RuntimeError:
                    coro.close()
            except Exception:
                pass

    def _on_raw_companion_frame_rx(self, payload: bytes) -> None:
        """Difunde tramas binarias de la radio hacia clientes TCP Companion conectados (App Móvil / CLI)."""
        tcp_srv = getattr(self, "tcp_server", None)
        if tcp_srv is not None and getattr(self, "running", False):
            task = asyncio.create_task(tcp_srv.broadcast_companion_frame(payload))
            self._add_background_task(task)

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
        self.last_rx_snr: float | None = None
        self.last_rx_rssi: int | None = None
        self._health_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._tasks_lock = asyncio.Lock()
        self._tx_metrics_lock = asyncio.Lock()

    def reset_counters(self) -> dict[str, Any]:
        """Restablece los contadores de paquetes y errores acumulados del bridge."""
        self.rx_count = 0
        self.tx_count = 0
        self.tx_error_count = 0
        self.err_count = 0
        res: dict[str, Any] = {"nodes_reset": 0}
        if hasattr(self, "node_registry") and hasattr(self.node_registry, "reset_analytics"):
            res = self.node_registry.reset_analytics()
        return res

    def _add_background_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        """Registra una tarea asíncrona previniendo recolección prematura por GC."""
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def _discard_background_task(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.discard(task)

    async def _cleanup_loop(self) -> None:
        while self.running:
            await asyncio.sleep(60.0)
            async with self._tasks_lock:
                self._background_tasks = {t for t in self._background_tasks if not t.done()}
            try:
                if hasattr(self, "node_registry"):
                    if hasattr(self.node_registry, "cleanup_inactive"):
                        await asyncio.to_thread(self.node_registry.cleanup_inactive)
                    if hasattr(self.node_registry, "save_to_file"):
                        await asyncio.to_thread(self.node_registry.save_to_file)
            except Exception as e:
                logging.debug(f"Fallo en mantenimiento periódico de NodeRegistry: {e}")

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
                packet_buffer=self.packet_buffer,
                bridge=self,
            )
        )

        self.admin_handler = AdminCommandHandler(
            AdminContext(
                mc_provider=lambda: self.mc,
                node_registry=self.node_registry,
                repeater_manager=self.repeater_manager,
                mqtt=self.mqtt,
                execute_tx=self._execute_tx,
                web_server=self.web_server,
                serial_adapter=self.serial_adapter,
                rate_limiter=self.rate_limiter,
                counters=self,
                start_time=self.start_time,
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

    def get_health(self) -> dict[str, Any]:
        """Devuelve un snapshot consolidado de la salud de todos los subsistemas del bridge."""
        if hasattr(self, "diagnostics") and hasattr(self.diagnostics, "collect_health_snapshot"):
            return self.diagnostics.collect_health_snapshot()
        serial_adapter = getattr(self, "serial_adapter", None)
        mqtt_client = getattr(self, "mqtt", None)
        is_ser_ok = getattr(serial_adapter, "is_connected", False) if serial_adapter else False
        is_mqtt_ok = getattr(mqtt_client, "is_connected", False) if mqtt_client else False
        port_val = getattr(serial_adapter, "port", getattr(config, "SERIAL_PORT", "desconocido")) if serial_adapter else "none"
        return {
            "status": "healthy" if is_ser_ok and is_mqtt_ok else "degraded",
            "timestamp": time.time(),
            "uptime_seconds": int(time.time() - getattr(self, "start_time", time.time())),
            "subsystems": {
                "serial_companion": {
                    "connected": is_ser_ok,
                    "port": port_val,
                },
                "mqtt_broker": {
                    "connected": is_mqtt_ok,
                },
            },
        }

    async def _flush_offline_buffer(self) -> int:
        return 0

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
        logging.debug(f"Preflight Diagnostics: Estado {report['status']} ({len(report['checks'])} comprobaciones realizadas)")

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
        self._add_background_task(self._health_task)
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._add_background_task(self._cleanup_task)
        logging.info("MeshCore Bridge iniciado y operativo (v3.0).")

    async def stop(self) -> None:
        """Detención ordenada de todos los subsistemas."""
        if getattr(self, "_is_stopped", False):
            return
        self._is_stopped = True
        logging.info("Deteniendo MeshCore Bridge...")
        self.running = False

        cleanup_task = self._cleanup_task
        if cleanup_task is not None and not cleanup_task.done():
            cleanup_task.cancel()
            try:
                await asyncio.wait_for(cleanup_task, timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            self._cleanup_task = None

        # Detención resiliente: cada subsistema se cierra con timeout individual estricto (1.5s máx)
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
                await asyncio.wait_for(coro, timeout=1.5)
            except asyncio.TimeoutError:
                logging.warning(f"Timeout (1.5s) al detener subsistema '{subsystem_name}'.")
            except Exception as e:
                logging.error(f"Error deteniendo {subsystem_name}: {e}", exc_info=True)

        # Persistir libreta de contactos y métricas de nodos de forma no bloqueante
        try:
            if hasattr(self, "node_registry") and hasattr(self.node_registry, "save_to_file"):
                await asyncio.wait_for(asyncio.to_thread(self.node_registry.save_to_file, None, True), timeout=1.0)
        except (asyncio.TimeoutError, Exception) as e:
            logging.debug(f"Error o timeout guardando NodeRegistry al detener: {e}")

        # Emitir estado offline explícito antes de cerrar (QoS 0 para entrega inmediata)
        try:
            offline_payload = json.dumps({"status": "offline", "timestamp": int(time.time())})
            self.mqtt.publish_safe(config.TOPIC_STATE, offline_payload, qos=0, retain=True)
        except Exception as e:
            logging.error(f"Error publicando estado offline MQTT: {e}")

        try:
            await asyncio.wait_for(asyncio.to_thread(self.mqtt.stop), timeout=1.5)
        except (asyncio.TimeoutError, Exception) as e:
            logging.warning(f"Error o timeout deteniendo cliente MQTT: {e}")

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
                    now_cur = time.time()
                    for c in imported_contacts:
                        pk = str(c.get("public_key", "")).strip()
                        if pk:
                            last_adv = c.get("last_advert")
                            valid_last_seen = None
                            if isinstance(last_adv, (int, float)) and 1_000_000_000 < last_adv <= now_cur:
                                valid_last_seen = float(last_adv)
                            self.node_registry.add_or_update(
                                pk,
                                NodeContactUpdate(
                                    name=c.get("name") or c.get("adv_name"),
                                    alias=c.get("alias"),
                                    role=c.get("role", "CLIENT"),
                                    auto_discovered=False,
                                    is_favorite=True,
                                    last_seen=valid_last_seen,
                                    last_advert=float(last_adv) if isinstance(last_adv, (int, float)) and last_adv > 0 else None,
                                    latitude=c.get("latitude"),
                                    longitude=c.get("longitude"),
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

    @staticmethod
    def _parse_tx_input(item: Any) -> tuple[Any, str, int, str]:
        """Normaliza el payload de entrada de transmisión (dict, TxItem o string)."""
        if isinstance(item, dict):
            req_id = item.get("request_id", item.get("id"))
            target_raw = item.get("to", item.get("target", "broadcast"))
            target = str(target_raw) if target_raw is not None else "broadcast"
            raw_ch = item.get("channel_index", item.get("channel_idx", item.get("channel", 0)))
            ch_idx = int(raw_ch) if raw_ch is not None else 0
            text = str(item.get("text", item.get("message", "")))
            return req_id, target, ch_idx, text
        if isinstance(item, TxItem):
            req_id = item.request_id
            target = item.target or "broadcast"
            ch_idx = item.channel_idx
            if isinstance(item.payload, dict):
                text = str(item.payload.get("text", item.payload.get("message", "")))
            else:
                text = str(item.payload)
            return req_id, target, ch_idx, text
        return None, "broadcast", 0, str(item)

    def _validate_tx_target(self, target_str: str, text: str, is_broadcast: bool) -> str | None:
        """Valida que el destino no viole reglas inmutables de dominio."""
        if is_broadcast:
            return None
        clean_txt = text.strip().lower()
        first_token = clean_txt.split()[0] if clean_txt.split() else ""
        is_admin_cmd = first_token in ("login", "cmd", "set", "get", "reboot", "ping", "trace", "ver", "status", "info")

        if self.node_registry.is_local_key(target_str):
            return "No se puede enviar mensajes de chat hacia el nodo local."
        if not is_admin_cmd and self.node_registry.is_repeater_key(target_str):
            return "Los repetidores son nodos de infraestructura y no admiten mensajería de chat."
        return None

    def _record_tx_packet(
        self,
        target: str,
        ch_idx: int,
        text: str,
        is_admin_cmd: bool,
        ack_payload: dict[str, Any],
    ) -> None:
        """Graba la trama de transmisión en el búfer circular y la notifica vía Web."""
        if not (hasattr(self, "packet_buffer") and self.packet_buffer):
            return
        try:
            tx_pkt = self.packet_buffer.record(
                direction="tx",
                channel_idx=ch_idx,
                packet_type="CHAT" if not is_admin_cmd else "ADMIN",
                sender=self.node_registry.get_local_pubkey() or "LOCAL",
                sender_name="Estación Base Local",
                target=str(target),
                text=text,
                raw_bytes=text.encode("utf-8", errors="replace"),
                payload_dict=ack_payload,
            )
            if tx_pkt and self.web_server:
                self._broadcast_system_log({"type": "rf_packet", "event": "rf_packet", "data": tx_pkt.to_dict()})
        except Exception as ex:
            logging.debug(f"Error grabando paquete TX en packet_buffer: {ex}")

    async def _execute_tx(self, item: Any) -> dict[str, Any]:
        """Ejecuta una transmisión directa sobre el transceptor LoRa."""
        req_id, target, ch_idx, text = self._parse_tx_input(item)
        target_str = str(target).lower().strip()
        is_broadcast = target_str in ("broadcast", "public", "0xffff", "") or target_str.startswith("channel")

        clean_txt = text.strip().lower()
        first_token = clean_txt.split()[0] if clean_txt.split() else ""
        is_admin_cmd = first_token in ("login", "cmd", "set", "get", "reboot", "ping", "trace", "ver", "status", "info")

        err_msg = self._validate_tx_target(target_str, text, is_broadcast)
        if err_msg:
            return {"status": "error", "error": err_msg, "request_id": req_id}

        async with self._tx_metrics_lock:
            self.tx_count += 1
        status_val = "sent"
        error_detail: str | None = None
        expected_ack_hex: str | None = None

        try:
            if self.serial_adapter and self.serial_adapter.is_connected:
                target_arg = str(target) if not is_broadcast else None
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
                target_lower = str(target).lower()
                if target and target_lower not in ("broadcast", "public", "0xffff") and not target_lower.startswith("channel"):
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
        self._record_tx_packet(str(target), ch_idx, text, is_admin_cmd, ack_payload)

        if status_val == "sent":
            if not isinstance(item, TxItem) and hasattr(self, "rate_limiter") and self.rate_limiter:
                try:
                    plen = len(text.encode("utf-8")) if text else 32
                    est_ms = estimate_lora_airtime_ms(plen, self.rate_limiter.radio_config)
                    self.rate_limiter.airtime_tracker.record_tx(
                        airtime_ms=est_ms,
                        channel_idx=ch_idx,
                        target=str(target) if target else None,
                    )
                except Exception as ex:
                    logging.debug(f"Error registrando airtime de TX directa en rate_limiter: {ex}")

            if expected_ack_hex and req_id:
                self.register_pending_ack(expected_ack_hex, req_id, str(target))
            dest_label = "Broadcast / Canal 0" if is_broadcast else f"Nodo [{target[:8] if len(str(target)) >= 8 else target}]"
            logging.info(
                f"[TX-TRANSMISIÓN] Destino: {dest_label} | Canal: #{ch_idx} | "
                f"Texto: '{text}' | ACK esperado: {expected_ack_hex or 'None'}"
            )
        else:
            logging.warning(
                f"[TX-ERROR] Fallo transmitiendo a {target} (Canal #{ch_idx}): {error_detail or 'Desconocido'}"
            )

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

    def _on_duty_cycle_alert(self, level: str, stats: dict[str, Any]) -> None:
        """Maneja transiciones de advertencia/crítico del ciclo de trabajo de radio."""
        payload = {
            "type": "duty_cycle_alert",
            "event": "duty_cycle_alert",
            "level": level,
            "status_level": level,
            "hourly_duty_cycle_pct": stats.get("hourly_duty_cycle_pct", 0.0),
            "hourly_limit_pct": stats.get("hourly_limit_pct", 1.0),
            "warn_threshold_pct": stats.get("warn_threshold_pct", 80.0),
            "hourly_used_ms": stats.get("hourly_used_ms", 0.0),
            "hourly_budget_ms": stats.get("hourly_budget_ms", 0.0),
            "timestamp": time.time(),
        }

        # 1. Notificar a clientes WebSockets de la SPA
        ws_server = self.web_server
        if ws_server is not None:
            try:
                loop = self._custom_loop or asyncio.get_running_loop()
                loop.create_task(ws_server.broadcast_event(payload))
            except RuntimeError:
                pass
            except Exception as e:
                logging.debug(f"Error emitiendo duty_cycle_alert a WebSockets: {e}")

        # 2. Publicar en tópico MQTT de alertas
        if getattr(self, "mqtt", None):
            try:
                alert_topic = getattr(config, "TOPIC_ALERT", f"{config.TOPIC_PREFIX}/bridge/alert")
                self.mqtt.publish_safe(alert_topic, json.dumps(payload), qos=1)
            except Exception as e:
                logging.debug(f"Error publicando duty_cycle_alert en MQTT: {e}")

    def run_forever(self) -> None:
        """Punto de entrada síncrono que corre el bucle asyncio con manejo de señales y apagado acotado."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        if getattr(config, "LOG_LEVEL", "INFO") == "DEBUG":
            loop.set_debug(True)
            logging.getLogger("asyncio").setLevel(logging.DEBUG)

        _shutdown_triggered = False

        def _stop_task() -> None:
            nonlocal _shutdown_triggered
            if _shutdown_triggered:
                return
            _shutdown_triggered = True

            async def _async_shutdown() -> None:
                try:
                    await asyncio.wait_for(self.stop(), timeout=5.0)
                except asyncio.TimeoutError:
                    logging.warning("Timeout global (5.0s) en self.stop() durante apagado por señal.")
                finally:
                    loop.stop()

            task = loop.create_task(_async_shutdown())
            self._add_background_task(task)

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
            try:
                loop.run_until_complete(asyncio.wait_for(self.stop(), timeout=3.0))
            except (asyncio.TimeoutError, Exception):
                pass

            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            if pending:
                for task in pending:
                    task.cancel()
                try:
                    loop.run_until_complete(
                        asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=2.0)
                    )
                except (asyncio.TimeoutError, Exception):
                    pass

            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass

            loop.close()
