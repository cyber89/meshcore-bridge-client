"""
ServicesManager: Orquestador desacoplado de servicios de red de MeshCore Bridge.
Gestiona el ciclo de vida, arranque asíncrono, apagado ordenado y recarga en caliente (hot-reload)
de:
1. Cliente MQTT Local (n8n / automatización / Home Assistant).
2. Cliente MQTT Externo (LetsMesh / analizadores comunitarios / upstream).
3. Servidor TCP Companion (App Móvil Oficial MeshCore / CLI).
"""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from src.capabilities import CapabilityName, CapabilityRegistry, CapabilityState
from src.external_mqtt_client import ExternalBridgeMQTTClient
from src.mqtt_client import AsyncBridgeMQTTClient, DisabledMQTTClient, MQTTConfig
from src.services_config import (
    ExternalMqttConfig,
    LocalMqttConfig,
    ServicesConfig,
    TcpServerConfig,
    load_services_config,
    save_services_config_async,
    update_services_config,
    validate_services_config,
)
from src.tcp_companion_server import MeshCoreCompanionServer

logger = logging.getLogger("meshcore.services_manager")


class ServicesManager:
    """
    Fachada y gestor central de servicios de red de MeshCore Bridge.
    Permite alternar, configurar y recargar en caliente los servicios de comunicación
    sin reiniciar el proceso ni interrumpir el enlace serie del módem LoRa.
    """

    capabilities: CapabilityRegistry | None = None

    def __init__(
        self,
        bridge: Any,
        on_incoming_mqtt_message: Callable[[str, str], None] | None = None,
        on_incoming_external_downlink: Callable[[str, str], None] | None = None,
        config_override: ServicesConfig | None = None,
        capabilities: CapabilityRegistry | None = None,
    ) -> None:
        self.bridge = bridge
        self.on_incoming_mqtt_message = on_incoming_mqtt_message
        self.on_incoming_external_downlink = on_incoming_external_downlink

        self.database = getattr(bridge, "database", None)
        self._config_path = (
            Path(bridge.data_dir) / "services_config.json" if getattr(bridge, "_storage_overridden", False) else None
        )
        self.services_config: ServicesConfig = config_override or load_services_config(self._config_path, database=self.database)
        self.is_running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._configuration_write_task: asyncio.Task[None] | None = None
        self.capabilities: CapabilityRegistry | None = capabilities or getattr(bridge, "capabilities", None)

        # 1. Instanciar Cliente MQTT Local
        self.local_mqtt = self._create_local_mqtt_client(self.services_config.local_mqtt)
        if self.capabilities:
            if self.services_config.local_mqtt.enabled:
                self.capabilities.update_capability(
                    CapabilityName.LOCAL_MQTT,
                    configured=True,
                    instantiated=not isinstance(self.local_mqtt, DisabledMQTTClient),
                    state=CapabilityState.STARTING if not isinstance(self.local_mqtt, DisabledMQTTClient) else CapabilityState.NOT_INSTALLED,
                )
            else:
                self.capabilities.set_disabled(CapabilityName.LOCAL_MQTT)

        # 2. Instanciar Cliente MQTT Externo
        local_pk = self._get_local_pubkey()
        self.external_mqtt = self._create_external_mqtt_client(self.services_config.external_mqtt, local_pk)
        if self.capabilities:
            if self.services_config.external_mqtt.enabled:
                self.capabilities.update_capability(
                    CapabilityName.EXTERNAL_MQTT,
                    configured=True,
                    instantiated=bool(self.external_mqtt.config.enabled),
                    state=CapabilityState.STARTING if self.external_mqtt.config.enabled else CapabilityState.NOT_INSTALLED,
                )
            else:
                self.capabilities.set_disabled(CapabilityName.EXTERNAL_MQTT)

        # 3. Instanciar Servidor TCP Companion si está habilitado
        self.tcp_server: MeshCoreCompanionServer | None = None
        if self.services_config.tcp_server.enabled:
            self.tcp_server = self._create_tcp_server(self.services_config.tcp_server)
            if self.capabilities:
                self.capabilities.update_capability(
                    CapabilityName.COMPANION,
                    configured=True,
                    instantiated=True,
                    state=CapabilityState.STARTING,
                )
        else:
            if self.capabilities:
                self.capabilities.set_disabled(CapabilityName.COMPANION)

    def _get_local_pubkey(self) -> str:
        """Obtiene la clave pública del nodo local desde NodeRegistry o Bridge."""
        if hasattr(self.bridge, "node_registry") and hasattr(self.bridge.node_registry, "get_local_pubkey"):
            pk = self.bridge.node_registry.get_local_pubkey()
            if pk:
                return str(pk)
        return str(getattr(self.bridge, "local_pubkey", "") or "")

    def set_local_pubkey(self, pubkey: str) -> None:
        """Actualiza la clave pública local en los clientes que la requieran."""
        if self.external_mqtt is not None:
            self.external_mqtt.set_local_pubkey(pubkey)

    @staticmethod
    async def _finish_owned_transaction[T](transaction: asyncio.Task[T]) -> T:
        """Retain lifecycle ownership through any number of caller cancellations."""
        cancelled = False
        while not transaction.done():
            try:
                await asyncio.shield(transaction)
            except asyncio.CancelledError:
                cancelled = True
        result = transaction.result()
        if cancelled:
            raise asyncio.CancelledError
        return result

    async def synchronize_local_pubkey(self, pubkey: str) -> None:
        """Replace a changed gateway session under the service lifecycle lock."""
        async with self.configuration_guard():
            transaction = asyncio.create_task(self._synchronize_local_pubkey(pubkey), name="MqttGatewayIdentity")
            await self._finish_owned_transaction(transaction)

    async def _synchronize_local_pubkey(self, pubkey: str, *, start_client: bool = True) -> None:
        normalized = pubkey.lower().strip()
        previous = self.external_mqtt
        if previous.local_pubkey == normalized:
            return
        # Stop the old identity before constructing its replacement. A TLS or
        # start failure must leave the old gateway offline, never mislabeled.
        await asyncio.to_thread(previous.stop)
        replacement = self._create_external_mqtt_client(self.services_config.external_mqtt, normalized)
        try:
            if start_client and self.is_running and self.services_config.external_mqtt.enabled:
                replacement.start(loop=self._loop)
        except BaseException:
            try:
                await asyncio.to_thread(replacement.stop)
            except Exception as error:
                logger.error("MQTT identity candidate cleanup failed: %s", type(error).__name__)
            raise
        self.external_mqtt = replacement
        self._propagate_external_mqtt_reference()

    def _create_local_mqtt_client(self, cfg: LocalMqttConfig) -> AsyncBridgeMQTTClient:
        """Crea una instancia de AsyncBridgeMQTTClient configurada a partir de LocalMqttConfig."""
        mqtt_cfg = MQTTConfig(
            broker=cfg.host or "127.0.0.1",
            port=cfg.port or 1883,
            username=cfg.username if (cfg.auth_enabled and cfg.username) else None,
            password=cfg.password if (cfg.auth_enabled and cfg.password) else None,
            keepalive=cfg.keepalive,
            topic_prefix=cfg.topic_prefix or "meshcore",
            tls_enabled=cfg.tls_enabled,
            tls_ca_file=cfg.tls_ca_file,
            tls_cert_file=cfg.tls_cert_file,
            tls_key_file=cfg.tls_key_file,
        )
        if not cfg.enabled or not CapabilityRegistry.is_mqtt_installed():
            return DisabledMQTTClient(mqtt_cfg)
        return AsyncBridgeMQTTClient(
            config=mqtt_cfg,
            on_rx_message_callback=self.on_incoming_mqtt_message,
        )

    def _create_external_mqtt_client(self, cfg: ExternalMqttConfig, public_key: str) -> ExternalBridgeMQTTClient:
        effective = copy.deepcopy(cfg)
        if not CapabilityRegistry.is_mqtt_installed():
            effective.enabled = False
        return ExternalBridgeMQTTClient(
            config_data=effective, local_pubkey=public_key,
            on_downlink_message_callback=self.on_incoming_external_downlink,
        )

    def refresh_capabilities(self) -> None:
        """Read current network state on demand, without a new polling timer."""
        caps = self.capabilities
        if caps is None:
            return
        for name, cfg, client in (
            (CapabilityName.LOCAL_MQTT, self.services_config.local_mqtt, self.local_mqtt),
            (CapabilityName.EXTERNAL_MQTT, self.services_config.external_mqtt, self.external_mqtt),
        ):
            if not cfg.enabled:
                caps.set_disabled(name)
                continue
            installed = CapabilityRegistry.is_mqtt_installed()
            connected = bool(installed and self.is_running and getattr(client, "is_connected", False))
            caps.update_capability(
                name, configured=True, instantiated=installed,
                started=bool(installed and self.is_running), operational=connected,
                state=(CapabilityState.NOT_INSTALLED if not installed else
                       CapabilityState.AVAILABLE if connected else CapabilityState.STARTING),
            )
        tcp_cfg = self.services_config.tcp_server
        if not tcp_cfg.enabled:
            caps.set_disabled(CapabilityName.COMPANION)
        else:
            listening = bool(self.is_running and self.tcp_server is not None and self.tcp_server.running)
            caps.update_capability(
                CapabilityName.COMPANION, configured=True,
                instantiated=self.tcp_server is not None, started=listening, operational=listening,
                state=CapabilityState.AVAILABLE if listening else CapabilityState.STARTING,
            )

    def _create_tcp_server(self, cfg: TcpServerConfig) -> MeshCoreCompanionServer:
        """Crea una instancia de MeshCoreCompanionServer a partir de TcpServerConfig."""
        return MeshCoreCompanionServer(
            bridge=self.bridge,
            host=cfg.host or "127.0.0.1",
            port=cfg.port or 5000,
            max_clients=cfg.max_clients,
            allowed_ips=cfg.allowed_ips,
        )

    @asynccontextmanager
    async def configuration_guard(self) -> AsyncIterator[None]:
        """Own mutations after any previous, cancellation-shielded disk write.

        Callers holding this guard must not call start(), stop() or
        reload_services(), which acquire it themselves.
        """
        async with self._lifecycle_lock:
            try:
                await self._await_configuration_write()
            except Exception:
                # The writer's result callback already reports disk failures.
                # A failed old write must not prevent closing network services;
                # persist_configuration still raises errors to its own caller.
                pass
            yield

    async def _await_configuration_write(self) -> None:
        task = self._configuration_write_task
        if task is None:
            return
        try:
            await asyncio.shield(task)
        finally:
            # A cancelled waiter never cancels the writer or loses its owner.
            if task.done() and self._configuration_write_task is task:
                self._configuration_write_task = None

    @staticmethod
    def _observe_configuration_write(task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                logger.error("Services configuration persistence failed: %s", type(error).__name__)

    async def persist_configuration(self, config_snapshot: ServicesConfig | None = None) -> None:
        """Persist a private snapshot while the caller holds configuration_guard.

        Cancellation returns promptly to the caller. The next mutation waits
        for this owned writer, so an older file cannot replace a newer one.
        """
        await self._await_configuration_write()
        snapshot = copy.deepcopy(config_snapshot if config_snapshot is not None else self.services_config)
        self._configuration_write_task = asyncio.create_task(
            save_services_config_async(snapshot, getattr(self, "_config_path", None), database=self.database), name="ServicesConfigurationPersistence"
        )
        self._configuration_write_task.add_done_callback(self._observe_configuration_write)
        await self._await_configuration_write()

    async def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Inicia todos los servicios de red habilitados en configuración."""
        async with self.configuration_guard():
            await self._start_services(loop)

    async def _start_services(self, loop: asyncio.AbstractEventLoop | None) -> None:
        self._loop = loop or asyncio.get_running_loop()
        self.is_running = True

        # Sincronizar clave local si ya está disponible
        local_pk = self._get_local_pubkey()
        if local_pk:
            await self._synchronize_local_pubkey(local_pk, start_client=False)

        # 1. Iniciar MQTT Local si está activo
        if self.services_config.local_mqtt.enabled:
            logger.info("Iniciando cliente MQTT Local...")
            if self.local_mqtt is not None and not isinstance(self.local_mqtt, DisabledMQTTClient):
                self.local_mqtt.start(loop=self._loop)
                if self.capabilities:
                    self.capabilities.update_capability(
                        CapabilityName.LOCAL_MQTT,
                        started=True,
                        operational=bool(getattr(self.local_mqtt, "is_connected", False)),
                        state=CapabilityState.AVAILABLE if getattr(self.local_mqtt, "is_connected", False) else CapabilityState.STARTING,
                    )
        else:
            logger.info("Cliente MQTT Local deshabilitado por configuración (Modo Standalone / Reducido).")
            if self.capabilities:
                self.capabilities.set_disabled(CapabilityName.LOCAL_MQTT)

        # 2. Iniciar MQTT Externo si está activo
        if self.services_config.external_mqtt.enabled:
            logger.info("Iniciando cliente MQTT Externo...")
            if self.external_mqtt is not None and self.external_mqtt.config.enabled:
                self.external_mqtt.start(loop=self._loop)
                if self.capabilities:
                    self.capabilities.update_capability(
                        CapabilityName.EXTERNAL_MQTT,
                        started=True,
                        operational=bool(getattr(self.external_mqtt, "is_connected", False)),
                        state=CapabilityState.AVAILABLE if getattr(self.external_mqtt, "is_connected", False) else CapabilityState.STARTING,
                    )
        else:
            logger.debug("Cliente MQTT Externo deshabilitado en configuración.")
            if self.capabilities:
                self.capabilities.set_disabled(CapabilityName.EXTERNAL_MQTT)

        # 3. Iniciar Servidor TCP Companion si está activo
        if self.tcp_server is not None and self.services_config.tcp_server.enabled:
            logger.info(
                f"Iniciando Servidor TCP Companion en tcp://{self.services_config.tcp_server.host}:"
                f"{self.services_config.tcp_server.port}..."
            )
            try:
                await self.tcp_server.start()
                if self.capabilities:
                    self.capabilities.set_operational(
                        CapabilityName.COMPANION,
                        True,
                        {"host": self.services_config.tcp_server.host, "port": self.services_config.tcp_server.port},
                    )
            except Exception as e:
                logger.error("TCP Companion startup failed: %s", type(e).__name__)
                if self.capabilities:
                    self.capabilities.set_failed(CapabilityName.COMPANION, str(e), "tcp_companion_startup_failed")
                raise
        elif self.capabilities:
            self.capabilities.set_disabled(CapabilityName.COMPANION)

    async def stop(self) -> None:
        """Detiene ordenadamente todos los servicios de red."""
        async with self.configuration_guard():
            await self._stop_services()

    async def _stop_services(self) -> None:
        self.is_running = False

        # 1. Detener TCP Companion Server
        if self.tcp_server is not None:
            try:
                await self.tcp_server.stop()
            except Exception as e:
                logger.debug("TCP Companion shutdown failed: %s", type(e).__name__)

        # 2. Detener MQTT Local en hilo para no bloquear el loop
        if self.local_mqtt is not None:
            try:
                await asyncio.to_thread(self.local_mqtt.stop)
            except Exception as e:
                logger.debug("Local MQTT shutdown failed: %s", type(e).__name__)

        # 3. Detener MQTT Externo en hilo
        if self.external_mqtt is not None:
            try:
                await asyncio.to_thread(self.external_mqtt.stop)
            except Exception as e:
                logger.debug("External MQTT shutdown failed: %s", type(e).__name__)

        if self.capabilities:
            self.capabilities.update_capability(CapabilityName.LOCAL_MQTT, started=False, operational=False)
            self.capabilities.update_capability(CapabilityName.EXTERNAL_MQTT, started=False, operational=False)
            self.capabilities.update_capability(CapabilityName.COMPANION, started=False, operational=False)

        logger.info("Todos los servicios de red han sido detenidos ordenadamente.")

    async def reload_services(self, new_config_or_updates: ServicesConfig | dict[str, Any]) -> dict[str, Any]:
        """
        Aplica una nueva configuración mediante diffing selectivo sin reiniciar el proceso principal.
        Solo reinicia los sockets que efectivamente hayan cambiado sus parámetros.
        """
        async with self.configuration_guard():
            return await self._reload_services(new_config_or_updates)

    async def _reload_services(self, new_config_or_updates: ServicesConfig | dict[str, Any]) -> dict[str, Any]:
        """Keep lifecycle ownership until the transaction commits or rolls back."""
        transaction = asyncio.create_task(self._apply_reload(new_config_or_updates), name="ServicesReloadTransaction")
        return await self._finish_owned_transaction(transaction)

    async def _apply_reload(self, new_config_or_updates: ServicesConfig | dict[str, Any]) -> dict[str, Any]:
        """Compute and apply the diff while holding configuration ownership."""
        old_cfg = copy.deepcopy(self.services_config)
        if isinstance(new_config_or_updates, ServicesConfig):
            new_cfg = copy.deepcopy(new_config_or_updates)
        else:
            new_cfg = update_services_config(old_cfg, new_config_or_updates)

        validate_services_config(new_cfg)
        local_changed = old_cfg.local_mqtt != new_cfg.local_mqtt
        external_changed = old_cfg.external_mqtt != new_cfg.external_mqtt
        if hasattr(self, "bridge"):
            external_changed = external_changed or self.external_mqtt.local_pubkey != self._get_local_pubkey()
        tcp_changed = old_cfg.tcp_server != new_cfg.tcp_server
        if not any((local_changed, external_changed, tcp_changed)):
            await self.persist_configuration(new_cfg)
            self.services_config = new_cfg
            return {"status": "ok", "reloaded": [], "config": self.services_config}
        old_local, old_external, old_tcp = self.local_mqtt, self.external_mqtt, self.tcp_server
        # Constructors validate TLS and policies before any live service stops.
        candidate_local = self._create_local_mqtt_client(new_cfg.local_mqtt) if local_changed else old_local
        candidate_external = self._create_external_mqtt_client(
            new_cfg.external_mqtt, self._get_local_pubkey()
        ) if external_changed else old_external
        candidate_tcp = (
            self._create_tcp_server(new_cfg.tcp_server) if new_cfg.tcp_server.enabled else None
        ) if tcp_changed else old_tcp
        stopped_local = stopped_external = stopped_tcp = False
        try:
            # Binding fails before disrupting MQTT. Reusing the same address
            # requires releasing the old listener, which rollback reopens.
            if tcp_changed:
                if old_tcp is not None:
                    stopped_tcp = True
                    await old_tcp.stop()
                # Reply routing must point to the listener accepting commands
                # during preparation, before the configuration write commits.
                self.tcp_server = candidate_tcp
                if hasattr(self.bridge, "tcp_server"):
                    self.bridge.tcp_server = candidate_tcp
                if candidate_tcp is not None and self.is_running:
                    await candidate_tcp.start()
            if local_changed:
                stopped_local = True
                await asyncio.to_thread(old_local.stop)
                self.local_mqtt = candidate_local
                self._propagate_local_mqtt_reference()
                if new_cfg.local_mqtt.enabled and self.is_running:
                    candidate_local.start(loop=self._loop)
            if external_changed:
                stopped_external = True
                await asyncio.to_thread(old_external.stop)
                self.external_mqtt = candidate_external
                self._propagate_external_mqtt_reference()
                if new_cfg.external_mqtt.enabled and self.is_running:
                    candidate_external.start(loop=self._loop)
            await self.persist_configuration(new_cfg)
        except BaseException:
            for changed, candidate in ((local_changed, candidate_local), (external_changed, candidate_external)):
                if changed:
                    try:
                        await asyncio.to_thread(candidate.stop)
                    except Exception as error:
                        logger.error("MQTT candidate cleanup failed during rollback: %s", type(error).__name__)
            if tcp_changed and candidate_tcp is not None:
                try:
                    await candidate_tcp.stop()
                except Exception as error:
                    logger.error("TCP candidate cleanup failed during rollback: %s", type(error).__name__)
            self.tcp_server = old_tcp
            if hasattr(self.bridge, "tcp_server"):
                self.bridge.tcp_server = old_tcp
            self.local_mqtt, self.external_mqtt = old_local, old_external
            self._propagate_local_mqtt_reference()
            self._propagate_external_mqtt_reference()
            if self.is_running:
                for restart, previous in (
                    (stopped_local and old_cfg.local_mqtt.enabled, old_local),
                    (stopped_external and old_cfg.external_mqtt.enabled, old_external),
                ):
                    if restart:
                        try:
                            previous.start(loop=self._loop)
                        except Exception as error:
                            logger.error("Previous MQTT restart failed during rollback: %s", type(error).__name__)
                if stopped_tcp and old_tcp is not None:
                    try:
                        await old_tcp.start()
                    except Exception as error:
                        logger.error("Previous TCP restart failed during rollback: %s", type(error).__name__)
            raise

        self.local_mqtt, self.external_mqtt, self.tcp_server = candidate_local, candidate_external, candidate_tcp
        self.services_config = new_cfg
        self._propagate_local_mqtt_reference()
        self._propagate_external_mqtt_reference()
        if hasattr(self.bridge, "tcp_server"):
            self.bridge.tcp_server = self.tcp_server
        reloaded = [name for name, changed in (
            ("local_mqtt", local_changed), ("external_mqtt", external_changed), ("tcp_server", tcp_changed)
        ) if changed]

        caps = getattr(self, "capabilities", None)
        if caps:
            if self.services_config.local_mqtt.enabled:
                caps.update_capability(
                    CapabilityName.LOCAL_MQTT,
                    configured=True,
                    instantiated=self.local_mqtt is not None,
                    operational=bool(getattr(self.local_mqtt, "is_connected", False)),
                    state=CapabilityState.AVAILABLE if getattr(self.local_mqtt, "is_connected", False) else CapabilityState.STARTING,
                )
            else:
                caps.set_disabled(CapabilityName.LOCAL_MQTT)

            if self.services_config.external_mqtt.enabled:
                caps.update_capability(
                    CapabilityName.EXTERNAL_MQTT,
                    configured=True,
                    instantiated=self.external_mqtt is not None,
                    operational=bool(getattr(self.external_mqtt, "is_connected", False)),
                    state=CapabilityState.AVAILABLE if getattr(self.external_mqtt, "is_connected", False) else CapabilityState.STARTING,
                )
            else:
                caps.set_disabled(CapabilityName.EXTERNAL_MQTT)

            if self.services_config.tcp_server.enabled:
                caps.update_capability(
                    CapabilityName.COMPANION,
                    configured=True,
                    instantiated=self.tcp_server is not None,
                    operational=self.tcp_server is not None,
                    state=CapabilityState.AVAILABLE if self.tcp_server is not None else CapabilityState.STARTING,
                )
            else:
                caps.set_disabled(CapabilityName.COMPANION)

        self.refresh_capabilities()
        logger.info(f"Recarga de servicios completada. Componentes actualizados: {reloaded or ['ninguno']}")
        return {
            "status": "ok",
            "reloaded": reloaded,
            "config": self.services_config,
        }

    def _propagate_local_mqtt_reference(self) -> None:
        """Actualiza la referencia de local_mqtt en BridgeCore y submódulos dependientes."""
        if hasattr(self.bridge, "mqtt"):
            self.bridge.mqtt = self.local_mqtt

        dispatcher = getattr(self.bridge, "mqtt_dispatcher", None)
        if dispatcher is not None and hasattr(dispatcher, "_ctx"):
            dispatcher._ctx.mqtt = self.local_mqtt

        router = getattr(self.bridge, "rx_router", None)
        if router is not None and hasattr(router, "_ctx"):
            router._ctx.mqtt = self.local_mqtt

        admin = getattr(self.bridge, "admin_handler", None)
        if admin is not None and hasattr(admin, "_ctx"):
            admin._ctx.mqtt = self.local_mqtt

        health = getattr(self.bridge, "health_reporter", None)
        if health is not None and hasattr(health, "_ctx"):
            health._ctx.mqtt = self.local_mqtt

    def _propagate_external_mqtt_reference(self) -> None:
        """Actualiza la referencia de external_mqtt en BridgeCore y submódulos dependientes."""
        if hasattr(self.bridge, "external_mqtt"):
            self.bridge.external_mqtt = self.external_mqtt

        router = getattr(self.bridge, "rx_router", None)
        if router is not None and hasattr(router, "_ctx"):
            if hasattr(router._ctx, "external_mqtt"):
                router._ctx.external_mqtt = self.external_mqtt
