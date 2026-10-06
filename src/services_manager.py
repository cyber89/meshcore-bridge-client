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
from collections.abc import Callable
from typing import Any

from src.external_mqtt_client import ExternalBridgeMQTTClient
from src.mqtt_client import AsyncBridgeMQTTClient, MQTTConfig
from src.services_config import (
    LocalMqttConfig,
    ServicesConfig,
    TcpServerConfig,
    load_services_config,
    save_services_config_async,
    update_services_config,
)
from src.tcp_companion_server import MeshCoreCompanionServer

logger = logging.getLogger("meshcore.services_manager")


class ServicesManager:
    """
    Fachada y gestor central de servicios de red de MeshCore Bridge.
    Permite alternar, configurar y recargar en caliente los servicios de comunicación
    sin reiniciar el proceso ni interrumpir el enlace serie del módem LoRa.
    """

    def __init__(
        self,
        bridge: Any,
        on_incoming_mqtt_message: Callable[[str, str], None] | None = None,
        on_incoming_external_downlink: Callable[[str, str], None] | None = None,
        config_override: ServicesConfig | None = None,
    ) -> None:
        self.bridge = bridge
        self.on_incoming_mqtt_message = on_incoming_mqtt_message
        self.on_incoming_external_downlink = on_incoming_external_downlink

        self.services_config: ServicesConfig = config_override or load_services_config()
        self.is_running = False
        self._loop: asyncio.AbstractEventLoop | None = None

        # 1. Instanciar Cliente MQTT Local
        self.local_mqtt = self._create_local_mqtt_client(self.services_config.local_mqtt)

        # 2. Instanciar Cliente MQTT Externo
        local_pk = self._get_local_pubkey()
        self.external_mqtt = ExternalBridgeMQTTClient(
            config_data=self.services_config.external_mqtt,
            local_pubkey=local_pk,
            on_downlink_message_callback=self.on_incoming_external_downlink,
        )

        # 3. Instanciar Servidor TCP Companion si está habilitado
        self.tcp_server: MeshCoreCompanionServer | None = None
        if self.services_config.tcp_server.enabled:
            self.tcp_server = self._create_tcp_server(self.services_config.tcp_server)

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

    def _create_local_mqtt_client(self, cfg: LocalMqttConfig) -> AsyncBridgeMQTTClient:
        """Crea una instancia de AsyncBridgeMQTTClient configurada a partir de LocalMqttConfig."""
        mqtt_cfg = MQTTConfig(
            broker=cfg.host or "127.0.0.1",
            port=cfg.port or 1883,
            username=cfg.username if (cfg.auth_enabled and cfg.username) else None,
            password=cfg.password if (cfg.auth_enabled and cfg.password) else None,
            keepalive=cfg.keepalive or 60,
            topic_prefix=cfg.topic_prefix or "meshcore",
            tls_enabled=cfg.tls_enabled,
            tls_ca_file=cfg.tls_ca_file,
            tls_cert_file=cfg.tls_cert_file,
            tls_key_file=cfg.tls_key_file,
        )
        return AsyncBridgeMQTTClient(
            config=mqtt_cfg,
            on_rx_message_callback=self.on_incoming_mqtt_message,
        )

    def _create_tcp_server(self, cfg: TcpServerConfig) -> MeshCoreCompanionServer:
        """Crea una instancia de MeshCoreCompanionServer a partir de TcpServerConfig."""
        return MeshCoreCompanionServer(
            bridge=self.bridge,
            host=cfg.host or "0.0.0.0",  # nosec B104
            port=cfg.port or 5000,
        )

    async def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Inicia todos los servicios de red habilitados en configuración."""
        self._loop = loop or asyncio.get_running_loop()
        self.is_running = True

        # Sincronizar clave local si ya está disponible
        local_pk = self._get_local_pubkey()
        if local_pk:
            self.set_local_pubkey(local_pk)

        # 1. Iniciar MQTT Local si está activo
        if self.services_config.local_mqtt.enabled:
            logger.info("Iniciando cliente MQTT Local...")
            self.local_mqtt.start(loop=self._loop)
        else:
            logger.info("Cliente MQTT Local deshabilitado por configuración (Modo Standalone / Reducido).")

        # 2. Iniciar MQTT Externo si está activo
        if self.services_config.external_mqtt.enabled:
            logger.info("Iniciando cliente MQTT Externo...")
            self.external_mqtt.start(loop=self._loop)
        else:
            logger.debug("Cliente MQTT Externo deshabilitado en configuración.")

        # 3. Iniciar Servidor TCP Companion si está activo
        if self.tcp_server is not None and self.services_config.tcp_server.enabled:
            logger.info(
                f"Iniciando Servidor TCP Companion en tcp://{self.services_config.tcp_server.host}:"
                f"{self.services_config.tcp_server.port}..."
            )
            try:
                await self.tcp_server.start()
            except Exception as e:
                logger.error(f"Error iniciando servidor TCP Companion: {e}")

    async def stop(self) -> None:
        """Detiene ordenadamente todos los servicios de red."""
        self.is_running = False

        # 1. Detener TCP Companion Server
        if self.tcp_server is not None:
            try:
                await self.tcp_server.stop()
            except Exception as e:
                logger.debug(f"Error deteniendo servidor TCP Companion: {e}")

        # 2. Detener MQTT Local en hilo para no bloquear el loop
        if self.local_mqtt is not None:
            try:
                await asyncio.to_thread(self.local_mqtt.stop)
            except Exception as e:
                logger.debug(f"Error deteniendo cliente MQTT local: {e}")

        # 3. Detener MQTT Externo en hilo
        if self.external_mqtt is not None:
            try:
                await asyncio.to_thread(self.external_mqtt.stop)
            except Exception as e:
                logger.debug(f"Error deteniendo cliente MQTT externo: {e}")

        logger.info("Todos los servicios de red han sido detenidos ordenadamente.")

    async def reload_services(self, new_config_or_updates: ServicesConfig | dict[str, Any]) -> dict[str, Any]:
        """
        Aplica una nueva configuración mediante diffing selectivo sin reiniciar el proceso principal.
        Solo reinicia los sockets que efectivamente hayan cambiado sus parámetros.
        """
        old_cfg = copy.deepcopy(self.services_config)
        if isinstance(new_config_or_updates, ServicesConfig):
            new_cfg = new_config_or_updates
        else:
            new_cfg = update_services_config(old_cfg, new_config_or_updates)

        reloaded: list[str] = []

        # ==================== 1. Diffing Local MQTT ====================
        old_loc = old_cfg.local_mqtt
        new_loc = new_cfg.local_mqtt
        if old_loc != new_loc:
            logger.info("Detectados cambios en configuración MQTT Local. Aplicando recarga...")
            # Detener cliente previo
            if self.local_mqtt is not None:
                await asyncio.to_thread(self.local_mqtt.stop)

            # Instanciar nuevo cliente
            self.local_mqtt = self._create_local_mqtt_client(new_loc)
            self._propagate_local_mqtt_reference()

            # Arrancar si está habilitado y el bridge está corriendo
            if new_loc.enabled and self.is_running:
                self.local_mqtt.start(loop=self._loop)
            reloaded.append("local_mqtt")

        # ==================== 2. Diffing External MQTT ====================
        old_ext = old_cfg.external_mqtt
        new_ext = new_cfg.external_mqtt
        if old_ext != new_ext:
            logger.info("Detectados cambios en configuración MQTT Externo. Aplicando recarga...")
            # Detener cliente previo
            if self.external_mqtt is not None:
                await asyncio.to_thread(self.external_mqtt.stop)

            # Instanciar nuevo cliente con clave pública local
            local_pk = self._get_local_pubkey()
            self.external_mqtt = ExternalBridgeMQTTClient(
                config_data=new_ext,
                local_pubkey=local_pk,
                on_downlink_message_callback=self.on_incoming_external_downlink,
            )
            self._propagate_external_mqtt_reference()

            # Arrancar si está habilitado y el bridge está corriendo
            if new_ext.enabled and self.is_running:
                self.external_mqtt.start(loop=self._loop)
            reloaded.append("external_mqtt")

        # ==================== 3. Diffing TCP Companion Server ====================
        old_tcp = old_cfg.tcp_server
        new_tcp = new_cfg.tcp_server
        if old_tcp != new_tcp:
            logger.info("Detectados cambios en Servidor TCP Companion. Aplicando recarga...")
            # Detener servidor previo si existía
            if self.tcp_server is not None:
                await self.tcp_server.stop()
                self.tcp_server = None

            # Si el nuevo está habilitado, crearlo e iniciarlo
            if new_tcp.enabled:
                self.tcp_server = self._create_tcp_server(new_tcp)
                if self.is_running:
                    try:
                        await self.tcp_server.start()
                    except Exception as e:
                        logger.error(f"Error al reactivar Servidor TCP Companion: {e}")
            if hasattr(self.bridge, "tcp_server"):
                self.bridge.tcp_server = self.tcp_server
            reloaded.append("tcp_server")

        # ==================== 4. Persistencia Atómica en Disco ====================
        self.services_config = new_cfg
        await save_services_config_async(self.services_config)

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
        if admin is not None and hasattr(admin, "ctx"):
            admin.ctx.mqtt = self.local_mqtt

        health = getattr(self.bridge, "health_reporter", None)
        if health is not None and hasattr(health, "ctx"):
            health.ctx.mqtt = self.local_mqtt

    def _propagate_external_mqtt_reference(self) -> None:
        """Actualiza la referencia de external_mqtt en BridgeCore y submódulos dependientes."""
        if hasattr(self.bridge, "external_mqtt"):
            self.bridge.external_mqtt = self.external_mqtt

        router = getattr(self.bridge, "rx_router", None)
        if router is not None and hasattr(router, "_ctx"):
            if hasattr(router._ctx, "external_mqtt"):
                router._ctx.external_mqtt = self.external_mqtt
