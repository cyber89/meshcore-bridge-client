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
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

import config
from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.deduplicator import PacketDeduplicator
from src.diagnostics import DiagnosticManager, SystemLogHandler, setup_file_logging
from src.health_reporter import HealthContext, HealthReporter
from src.mqtt_dispatcher import MqttInboundContext, MqttInboundDispatcher
from src.packet_buffer import PacketBuffer
from src.preflight import PreflightChecker
from src.rate_limiter import (
    LoRaRadioConfig,
    TxItem,
    TxPriority,
    TxRateLimiter,
    estimate_lora_airtime_ms,
)
from src.repeater_manager import RepeaterManager
from src.rx_router import RxEventRouter, RxRouterContext
from src.serial_driver import (
    BaseSerialAdapter,
    MeshcoreSDKAdapter,
    SerialWatchdog,
)
from src.services_config import ServicesConfig
from src.services_manager import ServicesManager
from src.tcp_companion_server import MeshCoreCompanionServer
from src.web.server_protocol import WebServerProtocol


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
        **_kwargs: Any,
    ) -> None:
        self.running = True
        self._is_stopped = False
        self._cleanup_task: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._started = False
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
            logging.debug("No se pudo cargar NodeRegistry previo: %s", type(e).__name__)
        self.repeater_manager = RepeaterManager(storage_path=Path(config.DATA_DIR) / "repeater_cooldowns.json")
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
            cutoff_threshold_pct=getattr(config, "AIRTIME_CUTOFF_THRESHOLD_PCT", 35.0),
            cutoff_resume_pct=getattr(config, "AIRTIME_CUTOFF_RESUME_PCT", 30.0),
            cutoff_enabled=getattr(config, "AIRTIME_CUTOFF_ENABLED", True),
            on_cutoff_change_callback=self._on_airtime_cutoff_change,
        )
        self.repeater_manager.is_cutoff_active_callback = self.rate_limiter.is_cutoff_active
        self.services_manager = ServicesManager(
            bridge=self,
            on_incoming_mqtt_message=self._on_incoming_mqtt_message,
            on_incoming_external_downlink=self._on_incoming_external_downlink,
        )
        self.mqtt = self.services_manager.local_mqtt
        self.external_mqtt = self.services_manager.external_mqtt
        self.preflight = PreflightChecker()
        self._pending_acks: dict[str, dict[str, Any]] = {}

    def _prune_pending_acks(self) -> None:
        """Expire delivery correlations using the agreed 3600-second lifetime."""
        now = time.monotonic()
        pending = getattr(self, "_pending_acks", {})
        expired = [key for key, info in pending.items()
                   if now - info.get("registered_at", float("-inf")) >= 3600]
        for key in expired:
            pending.pop(key, None)

    def register_pending_ack(self, expected_ack: str, req_id: str, target: str = "") -> str:
        """Track at most 200 pending deliveries without replacing another request."""
        clean_ack = str(expected_ack).lower().strip()
        if clean_ack.startswith("0x"):
            clean_ack = clean_ack[2:]
        self._prune_pending_acks()
        if len(clean_ack) != 8 or any(char not in "0123456789abcdef" for char in clean_ack) or set(clean_ack) <= {"0"}:
            return "invalid_ack"
        previous = self._pending_acks.get(clean_ack)
        if previous:
            if previous.get("req_id") == req_id and previous.get("target") == target:
                return "registered"
            logging.warning("ACK delivery tracking unavailable: collision; request_id=%s", req_id)
            return "collision"
        if len(self._pending_acks) >= 200:
            logging.warning("ACK delivery tracking unavailable: capacity_exceeded; request_id=%s", req_id)
            return "capacity_exceeded"
        self._pending_acks[clean_ack] = {
            "req_id": req_id,
            "timestamp": time.time(),
            "registered_at": time.monotonic(),
            "target": target,
        }
        return "registered"

    def resolve_pending_ack(self, ack_code: str) -> dict[str, Any] | None:
        """Resuelve el msg_id y target asociados a un código ACK recibido."""
        clean_ack = str(ack_code).lower().strip()
        if clean_ack.startswith("0x"):
            clean_ack = clean_ack[2:]
        self._prune_pending_acks()
        if not clean_ack or set(clean_ack) <= {"0"}:
            return None
        return self._pending_acks.pop(clean_ack, None)

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
        if web is None or not getattr(self, "running", False) or not hasattr(web, "broadcast_event"):
            return

        self._schedule_background(lambda: web.broadcast_event(payload))

    def _schedule_background(self, factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        """Create and own tasks on their event loop, including callbacks from threads."""
        if not getattr(self, "running", False):
            return
        loop = getattr(self, "_custom_loop", None)
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if loop is None or not loop.is_running():
            loop = current_loop
        if loop is None or loop.is_closed():
            return

        def launch() -> None:
            if not getattr(self, "running", False):
                return
            try:
                router = getattr(self, "rx_router", None)
                if isinstance(router, RxEventRouter):
                    router._enqueue_work(factory)
                else:
                    self._add_background_task(asyncio.create_task(factory()))
            except Exception:
                logging.exception("No se pudo iniciar tarea background", extra={"skip_broadcast": True})

        if current_loop is loop:
            launch()
        else:
            try:
                loop.call_soon_threadsafe(launch)
            except RuntimeError:
                # The loop may have stopped between inspection and scheduling.
                return

    def _on_raw_companion_frame_rx(self, payload: bytes) -> None:
        """Difunde tramas binarias de la radio hacia clientes TCP Companion conectados (App Móvil / CLI)."""
        tcp_srv = getattr(self, "tcp_server", None)
        if tcp_srv is not None and getattr(self, "running", False):
            owner = tcp_srv.get_response_owner() if hasattr(tcp_srv, "get_response_owner") else None
            if payload and payload[0] < 0x80:
                if owner is None:
                    return
                if hasattr(tcp_srv, "note_response_received"):
                    tcp_srv.note_response_received(owner)
                self._schedule_background(lambda: tcp_srv.broadcast_companion_frame(payload, response_owner=owner))
            else:
                self._schedule_background(lambda: tcp_srv.broadcast_companion_frame(payload))

    async def handle_tcp_companion_command(self, payload: bytes, client_writer: Any, timeout: float = 30.0) -> bool:
        """Maneja comandos binarios enviados por apps móviles o CLI a través del socket TCP Companion."""
        if not payload:
            return False
        if payload[0] in (2, 3):
            # Companion text layout: type + attempt/channel + timestampLE,
            # then the six-byte destination prefix for direct messages.
            if len(payload) < (14 if payload[0] == 2 else 8):
                return False
            if payload[0] == 3 or payload[1] != 1:
                channel_idx = payload[2] if payload[0] == 3 else 0
                target = payload[7:13].hex() if payload[0] == 2 else None
                try:
                    future = await self.rate_limiter.submit(payload=payload, priority=TxPriority.NORMAL,
                                                           target=target, channel_idx=channel_idx)
                    async with asyncio.timeout(timeout):
                        result = await future
                    return isinstance(result, dict) and str(result.get("status", "")).lower() in ("sent", "ok", "success")
                except TimeoutError:
                    logging.warning("Timeout esperando confirmación de transmisión chat TCP en rate limiter", extra={"skip_broadcast": True})
                    return False
                except Exception:
                    logging.warning("No se pudo enviar chat TCP por la cola TX", extra={"skip_broadcast": True})
                    return False
        if hasattr(self.serial_adapter, "send_raw_companion_frame"):
            return bool(await self.serial_adapter.send_raw_companion_frame(payload))
        return False

    def _init_metrics_and_tasks(self) -> None:
        """Inicializa contadores y conjuntos de tareas en background."""
        self.rx_count = 0
        self.tx_count = 0
        self.tx_error_count = 0
        self.err_count = 0
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
        if hasattr(self, "node_registry") and hasattr(self.node_registry, "reset_analytics"):
            res = self.node_registry.reset_analytics()
        if hasattr(self, "packet_buffer") and getattr(self.packet_buffer, "metrics_aggregator", None):
            self.packet_buffer.metrics_aggregator.reset()
        return res

    def _add_background_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        """Registra una tarea asíncrona previniendo recolección prematura por GC."""
        self._background_tasks.add(task)
        task.add_done_callback(self._background_task_done)
        return task

    def _background_task_done(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logging.error("Error en tarea background: %s", error,
                          exc_info=(type(error), error, error.__traceback__),
                          extra={"skip_broadcast": True})

    def _get_lifecycle_lock(self) -> asyncio.Lock:
        lock = getattr(self, "_lifecycle_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            self._lifecycle_lock = lock
        return cast(asyncio.Lock, lock)

    async def _cleanup_loop(self) -> None:
        while self.running:
            await asyncio.sleep(60.0)
            self._prune_pending_acks()
            async with self._tasks_lock:
                self._background_tasks.difference_update([t for t in self._background_tasks if t.done()])
            try:
                if hasattr(self, "node_registry"):
                    if hasattr(self.node_registry, "cleanup_inactive"):
                        await asyncio.to_thread(self.node_registry.cleanup_inactive)
                    if hasattr(self.node_registry, "save_to_file"):
                        await asyncio.to_thread(self.node_registry.save_to_file)
            except Exception as e:
                logging.debug("Fallo en mantenimiento periódico de NodeRegistry: %s", type(e).__name__)

    def _create_web_server(self) -> WebServerProtocol | None:
        """Crea el servidor web asíncrono FastAPI ASGI si está habilitado por configuración."""
        if not getattr(config, "WEB_ENABLED", True):
            return None

        from src.web.api_router import WebAPIRouter
        from src.web.asgi_server import AsgiWebServer

        router = WebAPIRouter(bridge=self)
        return AsgiWebServer(
            router=router,
            host=getattr(config, "WEB_HOST", "0.0.0.0"),  # nosec B104
            port=getattr(config, "WEB_PORT", 8080),
            shutdown_budget_s=getattr(config, "SHUTDOWN_TIMEOUT", 1.5),
            owns_tile_service=True,
            on_failure=self._on_web_server_failure,
        )

    def _on_web_server_failure(self, error: Exception) -> None:
        """Observe web termination without initiating radio work or a restart."""
        logging.error(
            "Web subsystem terminated unexpectedly: %s",
            type(error).__name__,
            extra={"skip_broadcast": True},
        )

    def _create_tcp_server(self) -> MeshCoreCompanionServer | None:
        """Crea el servidor TCP Companion asíncrono si está habilitado por configuración."""
        if hasattr(self, "services_manager"):
            return self.services_manager.tcp_server
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
                register_task=self._add_background_task,
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
                register_task=self._add_background_task,
                external_mqtt=self.external_mqtt,
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

    @property
    def services_config(self) -> ServicesConfig:
        if hasattr(self, "services_manager"):
            return self.services_manager.services_config
        from src.services_config import load_services_config
        return load_services_config()

    async def reload_services(self, new_config: Any) -> dict[str, Any]:
        """Recarga en caliente la configuración de servicios de red."""
        if hasattr(self, "services_manager"):
            res = await self.services_manager.reload_services(new_config)
            self.mqtt = self.services_manager.local_mqtt
            self.external_mqtt = self.services_manager.external_mqtt
            self.tcp_server = self.services_manager.tcp_server
            return res
        return {"status": "error", "message": "ServicesManager no disponible"}

    def get_health(self) -> dict[str, Any]:
        """Devuelve un snapshot consolidado de la salud de todos los subsistemas del bridge."""
        if hasattr(self, "diagnostics") and hasattr(self.diagnostics, "collect_health_snapshot"):
            return self.diagnostics.collect_health_snapshot()
        serial_adapter = getattr(self, "serial_adapter", None)
        mqtt_client = getattr(self, "mqtt", None)
        is_ser_ok = getattr(serial_adapter, "is_connected", False) if serial_adapter else False
        loc_enabled = True
        if hasattr(self, "services_manager"):
            loc_enabled = self.services_manager.services_config.local_mqtt.enabled
        is_mqtt_connected = getattr(mqtt_client, "is_connected", False) if mqtt_client else False
        is_mqtt_ok = is_mqtt_connected if loc_enabled else True
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
                    "enabled": loc_enabled,
                    "connected": is_mqtt_connected,
                },
            },
        }

    def resolve_sender_name(self, prefix_or_key: str) -> str:
        # Primero consultar el registro dinámico local
        local_name = self.node_registry.resolve_name(prefix_or_key)
        if local_name and local_name != prefix_or_key:
            return local_name
        return self.serial_adapter.resolve_sender_name(prefix_or_key)

    def _create_serial_adapter(self) -> BaseSerialAdapter:
        """Select the official physical transport; memory framing is not a UART."""
        try:
            return MeshcoreSDKAdapter(
                port=config.SERIAL_PORT,
                baud_rate=config.BAUD_RATE,
                timeout_sec=config.SERIAL_TIMEOUT,
                node_registry=self.node_registry,
            )
        except Exception as error:
            raise RuntimeError("No se pudo inicializar el transporte SDK MeshCore") from error

    async def start(self) -> None:
        """Inicia todos los subsistemas del bridge de forma asíncrona."""
        async with self._get_lifecycle_lock():
            if getattr(self, "_started", False):
                return
            self._is_stopped = False
            self.running = True
            self._custom_loop = asyncio.get_running_loop()
            for name in ("mqtt_dispatcher", "rx_router"):
                component = getattr(self, name, None)
                if component is not None:
                    component._ctx.loop = self._custom_loop
            if hasattr(self, "log_handler") and self.log_handler not in logging.getLogger().handlers:
                logging.getLogger().addHandler(self.log_handler)
            sdk_logger = logging.getLogger("meshcore")
            sdk_logger.setLevel(max(logging.INFO, sdk_logger.getEffectiveLevel()))
            try:
                await self._start_subsystems()
            except BaseException:
                # Already inside the lifecycle lock; avoid re-entering public stop().
                await self._stop_subsystems()
                raise
            self._started = True

    async def _start_subsystems(self) -> None:
        self.running = True
        loop = self._custom_loop or asyncio.get_running_loop()
        manager = getattr(self, "repeater_manager", None)
        if manager is not None:
            await manager.load_state()
        dispatcher = getattr(self, "mqtt_dispatcher", None)
        if dispatcher is not None:
            dispatcher.start()

        # 0. Diagnósticos Preflight de arranque
        loc_cfg = self.services_config.local_mqtt
        tcp_cfg = self.services_config.tcp_server
        report = await asyncio.to_thread(self.preflight.run_all,
            mqtt_host=loc_cfg.host,
            mqtt_port=loc_cfg.port,
            serial_port=getattr(self.serial_adapter, "port", config.SERIAL_PORT),
            tcp_server_port=tcp_cfg.port,
            tcp_server_enabled=tcp_cfg.enabled,
            tcp_server_host=tcp_cfg.host,
            mqtt_enabled=loc_cfg.enabled,
        )
        logging.debug(f"Preflight Diagnostics: Estado {report['status']} ({len(report['checks'])} comprobaciones realizadas)")

        # Iniciar Rate Limiter y Cliente MQTT
        # Iniciar Rate Limiter y Servicios de Red (MQTT local, MQTT externo, TCP Companion)
        self.rate_limiter.start()
        if hasattr(self, "services_manager"):
            await self.services_manager.start(loop=loop)
            self.mqtt = self.services_manager.local_mqtt
            self.external_mqtt = self.services_manager.external_mqtt
            self.tcp_server = self.services_manager.tcp_server
        else:
            self.mqtt.start(loop=loop)
            if self.tcp_server:
                await self.tcp_server.start()

        # Conectar con hardware serial
        await self.serial_adapter.connect()
        self.watchdog.start()

        # Iniciar servidor web si está habilitado
        if self.web_server:
            await self.web_server.start()

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
        async with self._get_lifecycle_lock():
            await self._stop_subsystems()

    async def _stop_subsystems(self) -> None:
        if getattr(self, "_is_stopped", False):
            return
        self._started = False
        logging.info("Deteniendo MeshCore Bridge...")
        self.running = False
        dispatcher = getattr(self, "mqtt_dispatcher", None)
        if dispatcher is not None:
            try:
                async with asyncio.timeout(1.5):
                    await dispatcher.close()
            except Exception:
                logging.warning("MQTT ingress shutdown did not complete within existing shutdown bound")

        cleanup_task = self._cleanup_task
        if cleanup_task is not None and not cleanup_task.done():
            cleanup_task.cancel()
            try:
                async with asyncio.timeout(0.5):
                    await cleanup_task
            except (asyncio.CancelledError, TimeoutError, Exception):
                pass
            self._cleanup_task = None

        current_task = asyncio.current_task()
        owned = [task for task in self._background_tasks if task is not current_task]
        for task in owned:
            if not task.done():
                task.cancel()
        if owned:
            # Reuse the existing per-subsystem shutdown bound.
            try:
                async with asyncio.timeout(1.5):
                    await asyncio.gather(*owned, return_exceptions=True)
            except TimeoutError:
                logging.warning("Timeout al detener tareas background", extra={"skip_broadcast": True})
            self._background_tasks.difference_update(task for task in owned if task.done())

        # Detención resiliente: cada subsistema se cierra con timeout individual estricto (1.5s máx)
        stop_tcp = None
        tcp_srv = getattr(self, "tcp_server", None)
        if tcp_srv is not None:
            sm = getattr(self, "services_manager", None)
            if sm is None or getattr(sm, "tcp_server", None) is not tcp_srv:
                stop_tcp = tcp_srv.stop()

        for subsystem_name, coro in [
            ("services_manager", self.services_manager.stop() if getattr(self, "services_manager", None) else None),
            ("tcp_server", stop_tcp),
            ("web_server", self.web_server.stop() if self.web_server else None),
            ("health_reporter", self.health_reporter.stop()),
            ("watchdog", self.watchdog.stop()),
            ("rate_limiter", self.rate_limiter.stop()),
            ("serial_adapter", self.serial_adapter.disconnect()),
        ]:
            if coro is None:
                continue
            try:
                async with asyncio.timeout(1.5):
                    await coro
            except TimeoutError:
                logging.warning(f"Timeout (1.5s) al detener subsistema '{subsystem_name}'.")
            except Exception as e:
                logging.error("Error deteniendo %s: %s", subsystem_name, type(e).__name__)

        # Persistir libreta de contactos y métricas de nodos de forma no bloqueante
        try:
            if hasattr(self, "node_registry") and hasattr(self.node_registry, "save_to_file"):
                async with asyncio.timeout(1.0):
                    await asyncio.to_thread(self.node_registry.save_to_file, None, True)
        except (TimeoutError, Exception) as e:
            logging.debug("Error o timeout guardando NodeRegistry al detener: %s", type(e).__name__)

        sm_instance = getattr(self, "services_manager", None)
        if sm_instance is None or getattr(sm_instance, "local_mqtt", None) is not getattr(self, "mqtt", None):
            if hasattr(self, "mqtt") and self.mqtt is not None and hasattr(self.mqtt, "stop"):
                try:
                    async with asyncio.timeout(1.5):
                        await asyncio.to_thread(self.mqtt.stop)
                except (TimeoutError, Exception) as e:
                    logging.warning("Error o timeout deteniendo cliente MQTT: %s", type(e).__name__)

        if hasattr(self, "log_handler") and self.log_handler in logging.getLogger().handlers:
            logging.getLogger().removeHandler(self.log_handler)
        manager = getattr(self, "repeater_manager", None)
        if manager is not None:
            try:
                async with asyncio.timeout(1.5):
                    await manager.close()
            except Exception:
                logging.warning("Repeater cooldown persistence did not complete at shutdown")
        if hasattr(self, "_pending_acks"):
            self._pending_acks.clear()
        self._is_stopped = True
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
                logging.debug("Error en auto-importación de canales: %s", type(e).__name__)

        # 2. Sincronizar libreta de contactos desde el hardware
        if hasattr(self.serial_adapter, "sync_all_contacts"):
            try:
                imported_contacts = await self.serial_adapter.sync_all_contacts()
                if imported_contacts:
                    for c in imported_contacts:
                        pk = str(c.get("public_key", "")).strip()
                        if pk:
                            last_adv = c.get("last_advert")
                            self.node_registry.add_or_update(
                                pk,
                                NodeContactUpdate(
                                    name=c.get("name") or c.get("adv_name"),
                                    alias=c.get("alias"),
                                    role=c.get("role", "CLIENT"),
                                    auto_discovered=False,
                                    is_favorite=True,
                                    last_seen=None,
                                    last_advert=float(last_adv) if isinstance(last_adv, (int, float)) and last_adv > 0 else None,
                                    latitude=c.get("latitude"),
                                    longitude=c.get("longitude"),
                                    adv_lat=c.get("adv_lat") or c.get("latitude"),
                                    adv_lon=c.get("adv_lon") or c.get("longitude"),
                                    flags=c.get("flags"),
                                    out_path=c.get("out_path"),
                                    out_path_len=c.get("out_path_len"),
                                    out_path_hash_mode=c.get("out_path_hash_mode"),
                                ),
                            )

                    logging.info(f"Auto-importados {len(imported_contacts)} contactos desde el transceptor serial.")
            except Exception as e:
                logging.debug("Error en auto-importación de contactos: %s", type(e).__name__)

        # 3. Consultar y cachear configuración del dispositivo
        if hasattr(self.admin_handler, "fetch_device_config"):
            try:
                cfg = await self.admin_handler.fetch_device_config()
                if cfg and "public_key" in cfg:
                    local_pk = str(cfg["public_key"]).strip().lower()
                    self.node_registry.set_local_pubkey(local_pk)
                    if hasattr(self, "services_manager"):
                        self.services_manager.set_local_pubkey(local_pk)
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
                logging.debug("Error consultando parámetros de radio del nodo: %s", type(e).__name__)

    async def _reconnect_serial(self) -> None:
        """Rutina de reconexión segura invocada por el Watchdog con pausa de estabilización USB."""
        logging.info("Ejecutando reconexión de puerto serial con estabilización USB...")
        await self.serial_adapter.disconnect()
        # Pausa esencial de 1.5s para permitir que el kernel y el USB CDC liberen el endpoint
        await asyncio.sleep(1.5)
        success = await self.serial_adapter.connect()
        if success:
            logging.info("Reconexión de transceptor serial completada con éxito.")
        else:
            logging.warning("Intento de reconexión serial no completado. El Watchdog continuará intentando en background.")

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
        if self.node_registry.is_local_key(target_str):
            return "No se puede enviar mensajes de chat hacia el nodo local."
        if self.node_registry.is_repeater_key(target_str):
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
            if not self.serial_adapter or not self.serial_adapter.is_connected:
                raise ConnectionError("Puerto serial / MeshCore no conectado")

            target_arg = str(target) if not is_broadcast else None
            send_res = await self.serial_adapter.send_message(text=text, target=target_arg, channel_idx=ch_idx)
            if not isinstance(send_res, dict) or str(send_res.get("status", "")).lower() not in ("ok", "sent", "success"):
                raise RuntimeError("El transceptor no confirmó la transmisión")
            expected_ack_hex = send_res.get("expected_ack")
            res_obj = send_res.get("event")
            if res_obj is not None:
                ev_type = getattr(res_obj, "type", None)
                if str(getattr(ev_type, "name", ev_type)).upper() == "ERROR":
                    raise RuntimeError("El transceptor rechazó la transmisión")

        except Exception as e:
            async with self._tx_metrics_lock:
                self.tx_error_count += 1
                if hasattr(self, "packet_buffer") and getattr(self.packet_buffer, "metrics_aggregator", None):
                    self.packet_buffer.metrics_aggregator.record_error("timeouts")
            status_val = "error"
            logging.warning("Transmisión no confirmada: %s", type(e).__name__)
            error_detail = "No se confirmó la transmisión por radio"

        # Publicar ACK de transmisión
        ack_payload: dict[str, Any] = {
            "status": status_val,
            "request_id": req_id,
            "target": target,
            "channel_idx": ch_idx,
            "expected_ack": expected_ack_hex,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if error_detail:
            ack_payload["error"] = error_detail
        if status_val == "sent" and expected_ack_hex and req_id:
            ack_payload["delivery_tracking"] = self.register_pending_ack(expected_ack_hex, req_id, str(target))

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
        if not self.running or getattr(self, "_is_stopped", False):
            logging.debug("Descartando evento mesh recibido tras el apagado del bridge.")
            return
        self.rx_router.handle_event(event)

    # ================================================================
    # Despachador de Mensajes MQTT Entrantes (n8n -> Bridge)
    # ================================================================
    def _on_incoming_mqtt_message(self, topic: str, payload_str: str) -> None:
        """Enruta mensajes recibidos desde MQTT (TX o Admin) a la cola de eventos."""
        if not self.running or getattr(self, "_is_stopped", False):
            logging.debug("Descartando mensaje MQTT recibido tras el apagado del bridge.")
            return
        max_payload_size = getattr(config, "MQTT_MAX_PAYLOAD_BYTES", 128 * 1024)
        if len(payload_str.encode("utf-8")) > max_payload_size:
            logging.warning(
                f"Payload MQTT entrante excede el límite máximo permitido ({len(payload_str.encode('utf-8'))} > {max_payload_size} B). Descartando en {topic}."
            )
            return
        self.mqtt_dispatcher.handle_incoming(topic, payload_str)

    def _on_incoming_external_downlink(self, topic: str, payload_str: str) -> None:
        """Procesa mensajes recibidos desde el broker MQTT externo hacia la radio LoRa (Downlink con rate limit)."""
        if not self.running or getattr(self, "_is_stopped", False):
            return
        if not getattr(self, "services_manager", None):
            return
        cfg = getattr(self.services_manager, "services_config", None)
        if not cfg or not cfg.external_mqtt.enabled or not cfg.external_mqtt.downlink_enabled:
            logging.debug("Mensaje downlink externo ignorado: Downlink desactivado en configuración.")
            return
        if hasattr(self, "rate_limiter") and self.rate_limiter.is_cutoff_active():
            logging.warning("Mensaje downlink externo descartado: Corte de seguridad por saturación de airtime activo.")
            return

        # Procesar payload pasando por el dispatcher y la cola de rate limiting LoRa
        if hasattr(self, "mqtt_dispatcher"):
            self._schedule_background(lambda: self.mqtt_dispatcher._handle_tx_request(payload_str))

    def on_mqtt_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """Compatibilidad con suites de pruebas y callbacks directos de paho-mqtt."""
        try:
            topic = str(getattr(msg, "topic", ""))
            raw = getattr(msg, "payload", b"")
            max_payload_size = getattr(config, "MQTT_MAX_PAYLOAD_BYTES", 128 * 1024)
            if len(raw) > max_payload_size:
                logging.warning(
                    f"Payload MQTT entrante directo excede el límite permitido ({len(raw)} > {max_payload_size} B). Descartando en {topic}."
                )
                return
            payload_str = (
                raw.decode("utf-8", errors="replace").strip()
                if isinstance(raw, (bytes, bytearray))
                else str(raw).strip()
            )
            self._on_incoming_mqtt_message(topic, payload_str)
        except Exception as e:
            logging.error("Error procesando mensaje MQTT directo: %s", type(e).__name__)

    async def _execute_tx_transmission(self, item: TxItem) -> dict[str, Any]:
        """Callback real de emisión hacia el adaptador serial."""
        if isinstance(item.payload, bytes):
            if item.future is not None and item.future.cancelled():
                return {"status": "error", "error": "Solicitud TCP cancelada"}
            success = False
            try:
                success = bool(await self.serial_adapter.send_raw_companion_frame(item.payload))
            except Exception:
                logging.warning("Fallo en transmisión de chat Companion TCP", extra={"skip_broadcast": True})
            async with self._tx_metrics_lock:
                self.tx_count += 1
                if not success:
                    self.tx_error_count += 1
                    if hasattr(self, "packet_buffer") and getattr(self.packet_buffer, "metrics_aggregator", None):
                        self.packet_buffer.metrics_aggregator.record_error("timeouts")
            return {"status": "sent" if success else "error", "target": item.target, "channel_idx": item.channel_idx}
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
            self._schedule_background(lambda: ws_server.broadcast_event(payload))

        # 2. Publicar en tópico MQTT de alertas
        if getattr(self, "mqtt", None):
            try:
                alert_topic = getattr(config, "TOPIC_ALERT", f"{config.TOPIC_PREFIX}/bridge/alert")
                self.mqtt.publish_safe(alert_topic, json.dumps(payload), qos=1)
            except Exception as e:
                logging.debug("Error publicando duty_cycle_alert en MQTT: %s", type(e).__name__)

    def _on_airtime_cutoff_change(self, active: bool, channel_utilization: float) -> None:
        """Notifica transiciones del Airtime Cutoff dinámico a WebSockets y MQTT."""
        if active and hasattr(self, "packet_buffer") and getattr(self.packet_buffer, "metrics_aggregator", None):
            self.packet_buffer.metrics_aggregator.record_error("airtime_cutoff")

        payload = {
            "type": "airtime_cutoff_change",
            "event": "airtime_cutoff_change",
            "active": active,
            "channel_utilization_pct": channel_utilization,
            "threshold_pct": getattr(config, "AIRTIME_CUTOFF_THRESHOLD_PCT", 35.0),
            "resume_pct": getattr(config, "AIRTIME_CUTOFF_RESUME_PCT", 30.0),
            "timestamp": time.time(),
        }

        ws_server = self.web_server
        if ws_server is not None:
            self._schedule_background(lambda: ws_server.broadcast_event(payload))

        if getattr(self, "mqtt", None):
            try:
                alert_topic = getattr(config, "TOPIC_ALERT", f"{config.TOPIC_PREFIX}/bridge/alert")
                self.mqtt.publish_safe(alert_topic, json.dumps(payload), qos=1)
            except Exception as e:
                logging.debug("Error publicando airtime_cutoff_change en MQTT: %s", type(e).__name__)


    def run_forever(self) -> None:
        """Punto de entrada síncrono que corre el bucle asyncio con manejo de señales y apagado acotado."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        if getattr(config, "LOG_LEVEL", "INFO") == "DEBUG":
            loop.set_debug(True)
            logging.getLogger("asyncio").setLevel(logging.DEBUG)

        _shutdown_triggered = False
        shutdown_task: asyncio.Task[None] | None = None

        def _stop_task() -> None:
            nonlocal _shutdown_triggered, shutdown_task
            if _shutdown_triggered:
                return
            _shutdown_triggered = True

            async def _async_shutdown() -> None:
                try:
                    async with asyncio.timeout(5.0):
                        await self.stop()
                except TimeoutError:
                    logging.warning("Timeout global (5.0s) en self.stop() durante apagado por señal.")
                finally:
                    loop.stop()

            # Keep the shutdown controller outside the tasks it asks stop() to cancel.
            shutdown_task = loop.create_task(_async_shutdown(), name="BridgeShutdown")
            shutdown_task.add_done_callback(self._background_task_done)

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
            async def _final_stop() -> None:
                async with asyncio.timeout(3.0):
                    await self.stop()

            try:
                loop.run_until_complete(_final_stop())
            except (TimeoutError, Exception):
                pass

            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            if pending:
                for task in pending:
                    task.cancel()

                async def _cancel_pending() -> None:
                    async with asyncio.timeout(2.0):
                        await asyncio.gather(*pending, return_exceptions=True)

                try:
                    loop.run_until_complete(_cancel_pending())
                except (TimeoutError, Exception):
                    pass

            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass

            loop.close()
