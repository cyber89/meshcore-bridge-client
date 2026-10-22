"""
Capability Registry and 5-Level Runtime Optionality (ADR 0024 / F4).
Tracks package availability, configuration intent, instantiation, runtime startup,
and operational readiness across core, web, companion, and MQTT services.
"""

from __future__ import annotations

import importlib.util
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.integrations.mqtt.topics import MqttTopics

logger = logging.getLogger("meshcore.capabilities")


class CapabilityName(StrEnum):
    """Nombres canónicos de capacidades de MeshCore Bridge."""
    CORE = "core"
    WEB = "web"
    COMPANION = "companion"
    LOCAL_MQTT = "local_mqtt"
    EXTERNAL_MQTT = "external_mqtt"


class CapabilityState(StrEnum):
    """Estados normalizados de ciclo de vida en 5 niveles."""
    NOT_INSTALLED = "not_installed"
    DISABLED = "disabled"
    STARTING = "starting"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    """Reporte estructurado del estado de una capacidad en los 5 niveles."""
    name: str
    installed: bool
    configured: bool
    instantiated: bool
    started: bool
    operational: bool
    state: str
    essential: bool
    error: str | None = None
    error_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "installed": self.installed,
            "configured": self.configured,
            "instantiated": self.instantiated,
            "started": self.started,
            "operational": self.operational,
            "state": self.state,
            "essential": self.essential,
            "error": self.error,
            "error_code": self.error_code,
            "details": dict(self.details),
        }

    @property
    def is_installed(self) -> bool:
        return self.installed

    @property
    def is_active(self) -> bool:
        return bool(self.configured and self.installed)


class CapabilityRegistry:
    """
    Registro centralizado de capacidades y salud modular de la estación.
    Distingue la liveness del proceso de la readiness de cada subsistema.
    """

    def __init__(self, services_config: Any | None = None, web_enabled: bool = True) -> None:
        self._start_time = time.time()
        self._reports: dict[str, CapabilityReport] = {}

        # 1. Core (Radio, Módem LoRa, SQLite stdlib) - Esencial
        self._reports[CapabilityName.CORE] = CapabilityReport(
            name=CapabilityName.CORE,
            installed=True,
            configured=True,
            instantiated=True,
            started=False,
            operational=False,
            state=CapabilityState.STARTING,
            essential=True,
        )

        # 2. Web (FastAPI, Uvicorn, ASGI, REST, WS, SPA) - Opcional
        web_installed = self.is_web_installed()
        self._reports[CapabilityName.WEB] = CapabilityReport(
            name=CapabilityName.WEB,
            installed=web_installed,
            configured=bool(web_enabled),
            instantiated=False,
            started=False,
            operational=False,
            state=(
                CapabilityState.DISABLED
                if not web_enabled
                else (CapabilityState.STARTING if web_installed else CapabilityState.NOT_INSTALLED)
            ),
            essential=False,
            error=None if (not web_enabled or web_installed) else "Dependencias web (FastAPI/Uvicorn) no instaladas",
            error_code=None if (not web_enabled or web_installed) else "web_dependencies_missing",
        )

        # 3. Companion (TCP Companion Server - stdlib asyncio) - Opcional
        tcp_cfg = getattr(services_config, "tcp_server", None)
        tcp_enabled = bool(getattr(tcp_cfg, "enabled", False))
        self._reports[CapabilityName.COMPANION] = CapabilityReport(
            name=CapabilityName.COMPANION,
            installed=True,
            configured=tcp_enabled,
            instantiated=False,
            started=False,
            operational=False,
            state=CapabilityState.STARTING if tcp_enabled else CapabilityState.DISABLED,
            essential=False,
        )

        # 4. Local MQTT (paho-mqtt) - Opcional
        mqtt_installed = self.is_mqtt_installed()
        loc_cfg = getattr(services_config, "local_mqtt", None)
        loc_enabled = bool(getattr(loc_cfg, "enabled", False))
        self._reports[CapabilityName.LOCAL_MQTT] = CapabilityReport(
            name=CapabilityName.LOCAL_MQTT,
            installed=mqtt_installed,
            configured=loc_enabled,
            instantiated=False,
            started=False,
            operational=False,
            state=(
                CapabilityState.DISABLED
                if not loc_enabled
                else (CapabilityState.STARTING if mqtt_installed else CapabilityState.NOT_INSTALLED)
            ),
            essential=False,
            error=None if (not loc_enabled or mqtt_installed) else "Librería paho-mqtt no instalada",
            error_code=None if (not loc_enabled or mqtt_installed) else "mqtt_dependency_missing",
        )

        # 5. External MQTT (paho-mqtt) - Opcional
        ext_cfg = getattr(services_config, "external_mqtt", None)
        ext_enabled = bool(getattr(ext_cfg, "enabled", False))
        self._reports[CapabilityName.EXTERNAL_MQTT] = CapabilityReport(
            name=CapabilityName.EXTERNAL_MQTT,
            installed=mqtt_installed,
            configured=ext_enabled,
            instantiated=False,
            started=False,
            operational=False,
            state=(
                CapabilityState.DISABLED
                if not ext_enabled
                else (CapabilityState.STARTING if mqtt_installed else CapabilityState.NOT_INSTALLED)
            ),
            essential=False,
            error=None if (not ext_enabled or mqtt_installed) else "Librería paho-mqtt no instalada",
            error_code=None if (not ext_enabled or mqtt_installed) else "mqtt_dependency_missing",
        )

    @staticmethod
    def is_module_installed(module_name: str) -> bool:
        """Verifica si un módulo Python está instalado sin forzar su importación completa."""
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, ValueError, AttributeError):
            return False

    @classmethod
    def is_web_installed(cls) -> bool:
        return (
            cls.is_module_installed("fastapi")
            and cls.is_module_installed("uvicorn")
            and cls.is_module_installed("starlette")
        )

    @classmethod
    def is_mqtt_installed(cls) -> bool:
        return cls.is_module_installed("paho.mqtt")

    def update_capability(
        self,
        name: str | CapabilityName,
        *,
        configured: bool | None = None,
        instantiated: bool | None = None,
        started: bool | None = None,
        operational: bool | None = None,
        state: str | CapabilityState | None = None,
        error: str | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> CapabilityReport:
        """Actualiza el estado de una capacidad de forma determinista."""
        key = str(name)
        current = self._reports.get(key)
        if current is None:
            installed = self.is_mqtt_installed() if "mqtt" in key else (self.is_web_installed() if key == "web" else True)
            current = CapabilityReport(
                name=key,
                installed=installed,
                configured=bool(configured),
                instantiated=bool(instantiated),
                started=bool(started),
                operational=bool(operational),
                state=str(state or CapabilityState.STARTING),
                essential=key == CapabilityName.CORE,
            )

        new_installed = current.installed
        new_configured = current.configured if configured is None else configured
        new_instantiated = current.instantiated if instantiated is None else instantiated
        new_started = current.started if started is None else started
        new_operational = current.operational if operational is None else operational

        # Derivación determinista de estado si no se especifica explícitamente
        derived_state: str
        if state is not None:
            derived_state = str(state)
        elif not new_installed and new_configured:
            derived_state = CapabilityState.NOT_INSTALLED
        elif not new_configured:
            derived_state = CapabilityState.DISABLED
        elif new_operational:
            derived_state = CapabilityState.AVAILABLE
        elif error is not None:
            derived_state = CapabilityState.FAILED if current.essential else CapabilityState.DEGRADED
        elif new_started:
            derived_state = CapabilityState.STARTING
        else:
            derived_state = current.state

        new_details = dict(current.details)
        if details:
            new_details.update(details)

        updated = CapabilityReport(
            name=key,
            installed=new_installed,
            configured=new_configured,
            instantiated=new_instantiated,
            started=new_started,
            operational=new_operational,
            state=derived_state,
            essential=current.essential,
            error=error if error is not None else (None if derived_state == CapabilityState.AVAILABLE else current.error),
            error_code=error_code if error_code is not None else (None if derived_state == CapabilityState.AVAILABLE else current.error_code),
            details=new_details,
        )
        self._reports[key] = updated
        return updated

    def set_operational(self, name: str | CapabilityName, operational: bool = True, details: dict[str, Any] | None = None) -> None:
        state = CapabilityState.AVAILABLE if operational else CapabilityState.DEGRADED
        self.update_capability(name, operational=operational, state=state, error=None, error_code=None, details=details)

    def set_failed(self, name: str | CapabilityName, error: str, error_code: str | None = None) -> None:
        self.update_capability(name, operational=False, state=CapabilityState.FAILED, error=error, error_code=error_code)

    def set_disabled(self, name: str | CapabilityName) -> None:
        self.update_capability(name, configured=False, operational=False, state=CapabilityState.DISABLED, error=None)

    def get_report(self, name: str | CapabilityName) -> CapabilityReport:
        key = str(name)
        report = self._reports.get(key)
        if report is not None:
            return report
        return CapabilityReport(
            name=key,
            installed=False,
            configured=False,
            instantiated=False,
            started=False,
            operational=False,
            state=CapabilityState.NOT_INSTALLED,
            essential=False,
        )

    def is_healthy(self) -> bool:
        """Determina la salud global: el Core DEBE estar disponible; opcionales degradados no derriban la estación."""
        core = self.get_report(CapabilityName.CORE)
        if not core.operational and core.state != CapabilityState.AVAILABLE:
            return False
        return True

    def get_liveness(self) -> dict[str, Any]:
        """Reporte de liveness del proceso (proceso vivo y bucle respondiendo)."""
        return {
            "alive": True,
            "uptime_seconds": int(time.time() - self._start_time),
            "timestamp": time.time(),
        }

    def get_readiness(self) -> dict[str, Any]:
        """Reporte de readiness por capacidad."""
        core = self.get_report(CapabilityName.CORE)
        web = self.get_report(CapabilityName.WEB)
        loc_mqtt = self.get_report(CapabilityName.LOCAL_MQTT)
        return {
            "ready": bool(core.operational),
            "core_ready": bool(core.operational),
            "web_ready": bool(web.operational or not web.configured),
            "mqtt_ready": bool(loc_mqtt.operational or not loc_mqtt.configured),
            "overall_healthy": self.is_healthy(),
        }

    def to_dict(self) -> dict[str, Any]:
        """Snapshot completo serializable para REST y WebSockets."""
        return {
            "healthy": self.is_healthy(),
            "liveness": self.get_liveness(),
            "readiness": self.get_readiness(),
            "capabilities": {k: r.to_dict() for k, r in self._reports.items()},
        }


    @property
    def core(self) -> CapabilityHandle:
        return CapabilityHandle(self, CapabilityName.CORE)

    @property
    def web(self) -> CapabilityHandle:
        return CapabilityHandle(self, CapabilityName.WEB)

    @property
    def companion(self) -> CapabilityHandle:
        return CapabilityHandle(self, CapabilityName.COMPANION)

    @property
    def mqtt_local(self) -> CapabilityHandle:
        return CapabilityHandle(self, CapabilityName.LOCAL_MQTT)

    @property
    def mqtt_external(self) -> CapabilityHandle:
        return CapabilityHandle(self, CapabilityName.EXTERNAL_MQTT)


class CapabilityHandle:
    """Acceso y mutación ergonómica para una capacidad específica del registro."""

    def __init__(self, registry: CapabilityRegistry, name: CapabilityName | str) -> None:
        self._registry = registry
        self._name = str(name)

    @property
    def report(self) -> CapabilityReport:
        return self._registry.get_report(self._name)

    @property
    def is_installed(self) -> bool:
        return self.report.installed

    @property
    def is_active(self) -> bool:
        return bool(self.report.configured and self.report.installed)

    @property
    def operational(self) -> bool:
        return self.report.operational

    def mark_configured(self, configured: bool) -> None:
        self._registry.update_capability(self._name, configured=configured)

    def mark_instantiated(self, instance: Any = None) -> None:
        self._registry.update_capability(self._name, instantiated=True)

    def mark_started(self) -> None:
        self._registry.update_capability(self._name, started=True)

    def mark_operational(self, details: dict[str, Any] | None = None) -> None:
        self._registry.set_operational(self._name, operational=True, details=details)

    def mark_stopped(self) -> None:
        self._registry.update_capability(self._name, started=False, operational=False)

    def mark_failed(self, error: Exception | str, error_code: str | None = None) -> None:
        err_msg = str(error) if isinstance(error, Exception) else error
        self._registry.set_failed(self._name, error=err_msg, error_code=error_code)

    def to_dict(self) -> dict[str, Any]:
        return self.report.to_dict()


class StableMqttPort:
    """
    Puerto estable y desacoplado para publicación y estado MQTT.
    Permite a los consumidores (RxEventRouter, AdminCommandHandler, MqttInboundDispatcher)
    publicar tráfico de forma determinista sin acoplarse a referencias efímeras de clientes
    ni requerir reescritura de atributos privados `_ctx.mqtt` durante hot-reload.
    """

    def __init__(self, client_provider: Callable[[], Any | None]) -> None:
        self._provider = client_provider
        self._default_topics = MqttTopics()

    @property
    def client(self) -> Any | None:
        if callable(self._provider):
            return self._provider()
        return None

    @property
    def is_connected(self) -> bool:
        c = self.client
        return bool(c and getattr(c, "is_connected", False))

    @property
    def topics(self) -> MqttTopics:
        c = self.client
        if c and hasattr(c, "topics") and isinstance(c.topics, MqttTopics):
            return c.topics
        return self._default_topics

    @property
    def topic_prefix(self) -> str:
        return self.topics.prefix

    @property
    def topic_tx_status(self) -> str:
        return self.topics.tx_status

    @property
    def topic_admin_stat(self) -> str:
        return self.topics.admin_status

    @property
    def topic_admin_status(self) -> str:
        return self.topics.admin_status

    @property
    def topic_health(self) -> str:
        return self.topics.health

    @property
    def topic_alert(self) -> str:
        return self.topics.alert

    def publish_safe(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> bool:
        """Publica de forma segura a través del cliente activo actual."""
        c = self.client
        if c is not None and hasattr(c, "publish_safe"):
            try:
                return bool(c.publish_safe(topic, payload, qos=qos, retain=retain))
            except Exception as e:
                logger.debug("Error publicando en puerto estable MQTT: %s", type(e).__name__)
                return False
        return False

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> Any:
        c = self.client
        if c is not None and hasattr(c, "publish"):
            return c.publish(topic, payload, qos=qos, retain=retain)
        return None
