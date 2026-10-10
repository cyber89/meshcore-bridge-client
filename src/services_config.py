"""
Módulo de Configuración Dinámica y Persistencia Atómica para Servicios de Red de MeshCore Bridge.
Gestiona el almacenamiento desacoplado de `.env` en `data/services_config.json`, migración transparente,
presets comunitarios y enmascaramiento seguro de credenciales.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger("meshcore.services_config")

DEFAULT_CONFIG_PATH = Path(getattr(config, "DATA_DIR", "data")) / "services_config.json"
MASKED_PASSWORD = "••••••••"


@dataclass(slots=True)
class MqttPreset:
    """Perfil predefinido o personalizado de conexión a broker MQTT externo."""
    id: str
    name: str
    description: str = ""
    host: str = ""
    port: int = 1883
    transport: str = "tcp"  # "tcp" o "websockets"
    tls_enabled: bool = False
    tls_verify: bool = True
    auth_type: str = "anonymous"  # "anonymous", "user_pass", "token"
    username: str = ""
    password: str = ""
    token: str = ""
    downlink_enabled: bool = False
    location_privacy: str = "fuzzed"  # "exact", "fuzzed", "hidden"
    topic_mode: str = "standard"  # "standard", "hierarchical", "custom"
    topic_prefix: str = "meshcore/remote"
    region_iata: str = "XXX"
    payload_format: str = "json_canonical"  # "json_canonical", "analyzer_packet"
    filter_observer_mode: bool = False
    filter_public: bool = True
    filter_channels: bool = True
    filter_direct: bool = False
    filter_telemetry: bool = True
    filter_nodes: bool = True
    filter_raw: bool = False
    keepalive: int = 60
    qos: int = 0
    is_system: bool = False


# Presets canónicos del ecosistema MeshCore / LetsMesh
SYSTEM_PRESETS: list[MqttPreset] = [
    MqttPreset(
        id="letsmesh_us",
        name="LetsMesh.net (US Analyzer)",
        description="Servidor de análisis y telemetría de red de LetsMesh (Nodo US-East)",
        host="mqtt-us-v1.letsmesh.net",
        port=443,
        transport="websockets",
        tls_enabled=True,
        tls_verify=True,
        auth_type="token",
        topic_mode="hierarchical",
        topic_prefix="meshcore",
        payload_format="analyzer_packet",
        filter_observer_mode=True,
        filter_public=False,
        filter_channels=False,
        filter_direct=False,
        filter_telemetry=True,
        filter_nodes=True,
        filter_raw=True,
        location_privacy="fuzzed",
        is_system=True,
    ),
    MqttPreset(
        id="letsmesh_eu",
        name="LetsMesh.net (EU Analyzer)",
        description="Servidor de análisis y telemetría de red de LetsMesh (Nodo Europa)",
        host="mqtt-eu-v1.letsmesh.net",
        port=443,
        transport="websockets",
        tls_enabled=True,
        tls_verify=True,
        auth_type="token",
        topic_mode="hierarchical",
        topic_prefix="meshcore",
        payload_format="analyzer_packet",
        filter_observer_mode=True,
        filter_public=False,
        filter_channels=False,
        filter_direct=False,
        filter_telemetry=True,
        filter_nodes=True,
        filter_raw=True,
        location_privacy="fuzzed",
        is_system=True,
    ),
    MqttPreset(
        id="meshmapper",
        name="MeshMapper.net",
        description="Cartografía y mapeo global de cobertura de nodos LoRa",
        host="mqtt.meshmapper.net",
        port=443,
        transport="websockets",
        tls_enabled=True,
        tls_verify=True,
        auth_type="token",
        topic_mode="hierarchical",
        topic_prefix="meshcore",
        payload_format="analyzer_packet",
        filter_observer_mode=True,
        filter_public=False,
        filter_channels=False,
        filter_direct=False,
        filter_telemetry=True,
        filter_nodes=True,
        filter_raw=False,
        location_privacy="fuzzed",
        is_system=True,
    ),
    MqttPreset(
        id="chimesh",
        name="ChiMesh.org (Chicagoland Mesh)",
        description="Broker regional comunitario de Chicagoland Mesh",
        host="mqtt.chimesh.org",
        port=443,
        transport="websockets",
        tls_enabled=True,
        tls_verify=True,
        auth_type="token",
        topic_mode="hierarchical",
        topic_prefix="meshcore",
        payload_format="analyzer_packet",
        filter_observer_mode=False,
        filter_public=True,
        filter_channels=True,
        filter_direct=False,
        filter_telemetry=True,
        filter_nodes=True,
        location_privacy="fuzzed",
        is_system=True,
    ),
    MqttPreset(
        id="homeassistant",
        name="Home Assistant (Mosquitto Local)",
        description="Integración típica para domótica local en red LAN (puerto estándar 1883)",
        host="192.168.1.100",
        port=1883,
        transport="tcp",
        tls_enabled=False,
        tls_verify=True,
        auth_type="user_pass",
        topic_mode="standard",
        topic_prefix="meshcore/home",
        payload_format="json_canonical",
        filter_observer_mode=False,
        filter_public=True,
        filter_channels=True,
        filter_direct=False,
        filter_telemetry=True,
        filter_nodes=True,
        location_privacy="exact",
        is_system=True,
    ),
]


@dataclass(slots=True)
class ExternalMqttConfig:
    """Configuración del broker MQTT externo / upstream."""
    enabled: bool = False
    host: str = ""
    port: int = 1883
    transport: str = "tcp"
    tls_enabled: bool = False
    tls_verify: bool = True
    auth_type: str = "anonymous"
    username: str = ""
    password: str = ""
    token: str = ""
    downlink_enabled: bool = False
    location_privacy: str = "fuzzed"
    topic_mode: str = "standard"
    topic_prefix: str = "meshcore/remote"
    region_iata: str = "XXX"
    payload_format: str = "json_canonical"
    keepalive: int = 60
    qos: int = 0
    filter_observer_mode: bool = False
    filter_public: bool = True
    filter_channels: bool = True
    filter_direct: bool = False
    filter_telemetry: bool = True
    filter_nodes: bool = True
    filter_raw: bool = False
    selected_preset_id: str = "custom"


@dataclass(slots=True)
class LocalMqttConfig:
    """Configuración del broker MQTT local (n8n & automatización interna)."""
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 1883
    auth_enabled: bool = False
    username: str = ""
    password: str = ""
    tls_enabled: bool = False
    tls_ca_file: str | None = None
    tls_cert_file: str | None = None
    tls_key_file: str | None = None
    topic_prefix: str = "meshcore"
    keepalive: int = 60


@dataclass(slots=True)
class TcpServerConfig:
    """Configuración del Servidor TCP Companion (App Móvil Oficial MeshCore & CLI)."""
    enabled: bool = True
    host: str = "0.0.0.0"  # nosec B104
    port: int = 5000
    max_clients: int = 8
    allowed_ips: str = ""


@dataclass(slots=True)
class ServicesConfig:
    """Contenedor raíz consolidado de todos los servicios de red."""
    version: int = 1
    external_mqtt: ExternalMqttConfig = field(default_factory=ExternalMqttConfig)
    local_mqtt: LocalMqttConfig = field(default_factory=LocalMqttConfig)
    tcp_server: TcpServerConfig = field(default_factory=TcpServerConfig)
    custom_presets: list[MqttPreset] = field(default_factory=list)


def _bootstrap_from_env() -> ServicesConfig:
    """Inicializa la configuración a partir de las variables existentes en config.py (.env)."""
    local_cfg = LocalMqttConfig(
        enabled=True,
        host=getattr(config, "MQTT_BROKER", "127.0.0.1"),
        port=int(getattr(config, "MQTT_PORT", 1883)),
        auth_enabled=bool(getattr(config, "MQTT_USER", "")),
        username=str(getattr(config, "MQTT_USER", "") or ""),
        password=str(getattr(config, "MQTT_PASSWORD", "") or ""),
        tls_enabled=bool(getattr(config, "MQTT_TLS", False)),
        tls_ca_file=getattr(config, "MQTT_TLS_CA_FILE", None),
        tls_cert_file=getattr(config, "MQTT_TLS_CERT_FILE", None),
        tls_key_file=getattr(config, "MQTT_TLS_KEY_FILE", None),
        topic_prefix=str(getattr(config, "TOPIC_PREFIX", "meshcore")),
        keepalive=int(getattr(config, "MQTT_KEEPALIVE", 60)),
    )

    tcp_cfg = TcpServerConfig(
        enabled=bool(getattr(config, "TCP_SERVER_ENABLED", True)),
        host=str(getattr(config, "TCP_SERVER_HOST", "0.0.0.0")),  # nosec B104
        port=int(getattr(config, "TCP_SERVER_PORT", 5000)),
        max_clients=int(getattr(config, "MAX_COMPANION_CLIENTS", 8)),
        allowed_ips=str(getattr(config, "COMPANION_ALLOWED_IPS", "") or ""),
    )

    return ServicesConfig(
        version=1,
        external_mqtt=ExternalMqttConfig(),
        local_mqtt=local_cfg,
        tcp_server=tcp_cfg,
        custom_presets=[],
    )


def _atomic_write_json(file_path: Path, data: dict[str, Any]) -> None:
    """Escribe un archivo JSON de forma atómica garantizando fsync en disco."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(
        dir=str(file_path.parent),
        prefix=f"{file_path.stem}_tmp_",
        suffix=".json",
    )
    try:
        with open(temp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, str(file_path))
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise


def load_services_config(file_path: Path | None = None) -> ServicesConfig:
    """Carga la configuración desde JSON con migración automática y fallback a .env."""
    path = file_path or DEFAULT_CONFIG_PATH
    if not path.is_file():
        logger.info(f"Archivo de servicios {path} no encontrado. Creando snapshot inicial desde .env...")
        initial_cfg = _bootstrap_from_env()
        try:
            save_services_config(initial_cfg, path)
        except Exception as e:
            logger.warning(f"No se pudo guardar el snapshot inicial en {path}: {e}")
        return initial_cfg

    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("El archivo JSON no contiene un objeto válido")

        ext_dict = raw.get("external_mqtt", {})
        loc_dict = raw.get("local_mqtt", {})
        tcp_dict = raw.get("tcp_server", {})
        raw_custom = raw.get("custom_presets", [])

        custom_presets: list[MqttPreset] = []
        if isinstance(raw_custom, list):
            for p in raw_custom:
                if isinstance(p, dict) and "id" in p and "name" in p:
                    # Excluir claves no pertenecientes al dataclass
                    valid_keys = MqttPreset.__dataclass_fields__.keys()
                    clean_p = {k: v for k, v in p.items() if k in valid_keys and k != "is_system"}
                    custom_presets.append(MqttPreset(is_system=False, **clean_p))

        # Reconstruir dataclasses con tolerancia a campos faltantes
        ext_fields = ExternalMqttConfig.__dataclass_fields__.keys()
        clean_ext = {k: ext_dict[k] for k in ext_fields if k in ext_dict}

        loc_fields = LocalMqttConfig.__dataclass_fields__.keys()
        clean_loc = {k: loc_dict[k] for k in loc_fields if k in loc_dict}

        tcp_fields = TcpServerConfig.__dataclass_fields__.keys()
        clean_tcp = {k: tcp_dict[k] for k in tcp_fields if k in tcp_dict}

        return ServicesConfig(
            version=int(raw.get("version", 1)),
            external_mqtt=ExternalMqttConfig(**clean_ext),
            local_mqtt=LocalMqttConfig(**clean_loc),
            tcp_server=TcpServerConfig(**clean_tcp),
            custom_presets=custom_presets,
        )
    except Exception as e:
        logger.error(f"Error cargando {path}: {e}. Usando valores de arranque desde .env...")
        return _bootstrap_from_env()


def save_services_config(cfg: ServicesConfig, file_path: Path | None = None) -> None:
    """Persiste atómicamente la configuración en disco en formato JSON."""
    path = file_path or DEFAULT_CONFIG_PATH
    data = asdict(cfg)
    _atomic_write_json(path, data)
    logger.info(f"Configuración de servicios persistida atómicamente en {path}")


async def save_services_config_async(cfg: ServicesConfig, file_path: Path | None = None) -> None:
    """Versión asíncrona no bloqueante de guardado atómico usando asyncio.to_thread."""
    path = file_path or DEFAULT_CONFIG_PATH
    await asyncio.to_thread(save_services_config, cfg, path)


def to_redacted_dict(cfg: ServicesConfig) -> dict[str, Any]:
    """Serializa la configuración para la API REST enmascarando contraseñas y tokens sensibles."""
    d = asdict(cfg)

    # Redactar contraseñas
    ext = d.get("external_mqtt", {})
    ext["has_password"] = bool(ext.get("password"))
    ext["password"] = MASKED_PASSWORD if ext.get("password") else ""
    ext["has_token"] = bool(ext.get("token"))
    ext["token"] = MASKED_PASSWORD if ext.get("token") else ""

    loc = d.get("local_mqtt", {})
    loc["has_password"] = bool(loc.get("password"))
    loc["password"] = MASKED_PASSWORD if loc.get("password") else ""

    # Incluir lista combinada de presets: presets del sistema + presets del usuario
    all_presets = [asdict(p) for p in SYSTEM_PRESETS]
    redacted_custom_presets: list[dict[str, Any]] = []
    for p in d.get("custom_presets", []):
        p_copy = dict(p)
        p_copy["has_password"] = bool(p_copy.get("password"))
        p_copy["password"] = MASKED_PASSWORD if p_copy.get("password") else ""
        p_copy["has_token"] = bool(p_copy.get("token"))
        p_copy["token"] = MASKED_PASSWORD if p_copy.get("token") else ""
        p_copy["is_system"] = False
        redacted_custom_presets.append(p_copy)
        all_presets.append(p_copy)

    # Both public views must use the redacted projection. asdict() made a deep
    # copy, so replacing this list never changes persisted/runtime credentials.
    d["custom_presets"] = redacted_custom_presets
    d["all_presets"] = all_presets
    return d


def update_services_config(
    current: ServicesConfig,
    updates: dict[str, Any],
) -> ServicesConfig:
    """Aplica mutaciones validadas preservando contraseñas existentes si se reciben enmascaradas."""
    new_cfg = copy.deepcopy(current)

    if "external_mqtt" in updates and isinstance(updates["external_mqtt"], dict):
        ext_in = updates["external_mqtt"]
        cur_ext = new_cfg.external_mqtt
        for k, v in ext_in.items():
            if not hasattr(cur_ext, k):
                continue
            if k == "password":
                # Preservar contraseña previa si se envía vacía o enmascarada
                if v and v != MASKED_PASSWORD:
                    cur_ext.password = str(v)
            elif k == "token":
                if v and v != MASKED_PASSWORD:
                    cur_ext.token = str(v)
            elif k in ("port", "keepalive", "qos"):
                try:
                    setattr(cur_ext, k, int(v))
                except (ValueError, TypeError):
                    pass
            elif k in (
                "enabled", "tls_enabled", "tls_verify", "downlink_enabled",
                "filter_observer_mode", "filter_public", "filter_channels",
                "filter_direct", "filter_telemetry", "filter_nodes", "filter_raw",
            ):
                setattr(cur_ext, k, bool(v))
            else:
                setattr(cur_ext, k, str(v) if v is not None else "")

    if "local_mqtt" in updates and isinstance(updates["local_mqtt"], dict):
        loc_in = updates["local_mqtt"]
        cur_loc = new_cfg.local_mqtt
        for k, v in loc_in.items():
            if not hasattr(cur_loc, k):
                continue
            if k == "password":
                if v and v != MASKED_PASSWORD:
                    cur_loc.password = str(v)
            elif k in ("port", "keepalive"):
                try:
                    setattr(cur_loc, k, int(v))
                except (ValueError, TypeError):
                    pass
            elif k in ("enabled", "auth_enabled", "tls_enabled"):
                setattr(cur_loc, k, bool(v))
            else:
                setattr(cur_loc, k, str(v) if v is not None else "")

    if "tcp_server" in updates and isinstance(updates["tcp_server"], dict):
        tcp_in = updates["tcp_server"]
        cur_tcp = new_cfg.tcp_server
        for k, v in tcp_in.items():
            if not hasattr(cur_tcp, k):
                continue
            if k in ("port", "max_clients"):
                try:
                    setattr(cur_tcp, k, int(v))
                except (ValueError, TypeError):
                    pass
            elif k == "enabled":
                setattr(cur_tcp, k, bool(v))
            else:
                setattr(cur_tcp, k, str(v) if v is not None else "")

    return new_cfg
