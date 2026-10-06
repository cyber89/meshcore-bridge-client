"""
ServicesController: Controlador REST para la administración y diagnóstico de Servicios de Red.
Gestiona endpoints para configuración de MQTT local/externo, Servidor TCP Companion,
CRUD de presets de conexión y pruebas efímeras de conectividad.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import asdict
from typing import Any

from src.external_mqtt_client import ExternalBridgeMQTTClient
from src.services_config import (
    MASKED_PASSWORD,
    SYSTEM_PRESETS,
    ExternalMqttConfig,
    MqttPreset,
    save_services_config_async,
    to_redacted_dict,
)
from src.web.controllers.base import BaseController, problem_details

logger = logging.getLogger("meshcore.controllers.services")


class ServicesController(BaseController):
    """Controlador REST para gestión de servicios de red y presets MQTT."""

    async def get_services_config(self) -> tuple[int, dict[str, Any]]:
        """Devuelve la configuración consolidada de servicios de red con credenciales enmascaradas."""
        cfg = getattr(self.ctx.bridge, "services_config", None)
        if cfg is None:
            from src.services_config import load_services_config
            cfg = load_services_config()

        data = to_redacted_dict(cfg)
        mgr = getattr(self.ctx.bridge, "services_manager", None)
        if mgr and getattr(mgr, "external_mqtt", None):
            data["external_mqtt_connected"] = bool(getattr(mgr.external_mqtt, "is_connected", False))
        else:
            data["external_mqtt_connected"] = False
        return 200, {"status": "ok", "data": data}

    async def set_services_config(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Actualiza y recarga en caliente la configuración de servicios de red."""
        if not isinstance(body, dict):
            return problem_details(
                400, "Bad Request", "El cuerpo de la solicitud debe ser un objeto JSON válido.", "invalid_json"
            )

        # Validación de External MQTT si está presente
        ext = body.get("external_mqtt")
        if isinstance(ext, dict) and ext.get("enabled"):
            host = str(ext.get("host") or "").strip()
            if not host:
                return problem_details(
                    422, "Unprocessable Entity", "El host del broker MQTT externo es obligatorio cuando está habilitado.", "invalid_host"
                )
            port = ext.get("port")
            if port is not None:
                try:
                    p_val = int(port)
                    if not (1 <= p_val <= 65535):
                        raise ValueError()
                except (ValueError, TypeError):
                    return problem_details(
                        422, "Unprocessable Entity", "El puerto del broker MQTT externo debe ser un número entre 1 y 65535.", "invalid_port"
                    )

            transport = ext.get("transport")
            if transport and transport not in ("tcp", "websockets"):
                return problem_details(
                    422, "Unprocessable Entity", "El tipo de transporte debe ser 'tcp' o 'websockets'.", "invalid_transport"
                )

            auth_type = ext.get("auth_type")
            if auth_type and auth_type not in ("anonymous", "user_pass", "token"):
                return problem_details(
                    422, "Unprocessable Entity", "El tipo de autenticación debe ser 'anonymous', 'user_pass' o 'token'.", "invalid_auth_type"
                )

            privacy = ext.get("location_privacy")
            if privacy and privacy not in ("exact", "fuzzed", "hidden"):
                return problem_details(
                    422, "Unprocessable Entity", "La privacidad GPS debe ser 'exact', 'fuzzed' o 'hidden'.", "invalid_location_privacy"
                )

        # Validación de Local MQTT si está presente
        loc = body.get("local_mqtt")
        if isinstance(loc, dict) and loc.get("enabled"):
            port = loc.get("port")
            if port is not None:
                try:
                    p_val = int(port)
                    if not (1 <= p_val <= 65535):
                        raise ValueError()
                except (ValueError, TypeError):
                    return problem_details(
                        422, "Unprocessable Entity", "El puerto del broker MQTT local debe ser un número entre 1 y 65535.", "invalid_port"
                    )

        # Validación de TCP Server si está presente
        tcp = body.get("tcp_server")
        if isinstance(tcp, dict) and tcp.get("enabled"):
            port = tcp.get("port")
            if port is not None:
                try:
                    p_val = int(port)
                    if not (1024 <= p_val <= 65535):
                        raise ValueError()
                except (ValueError, TypeError):
                    return problem_details(
                        422, "Unprocessable Entity", "El puerto del Servidor TCP debe ser un número entre 1024 y 65535.", "invalid_port"
                    )

        # Aplicar recarga a través de BridgeCore
        try:
            if hasattr(self.ctx.bridge, "reload_services"):
                reload_res = await self.ctx.bridge.reload_services(body)
                reloaded = reload_res.get("reloaded", [])
            else:
                reloaded = []

            cfg = getattr(self.ctx.bridge, "services_config", None)
            data = to_redacted_dict(cfg) if cfg else {}

            self.ctx.log_system_event(
                "INFO",
                f"Configuración de servicios de red actualizada. Recargados: {reloaded or ['ninguno']}",
                source="services_mgr",
            )
            return 200, {
                "status": "ok",
                "message": "Configuración de servicios de red actualizada correctamente.",
                "reloaded": reloaded,
                "data": data,
            }
        except Exception as e:
            logger.error(f"Error actualizando servicios de red: {e}", exc_info=True)
            return problem_details(
                500, "Internal Server Error", f"Error al recargar servicios: {e}", "reload_failed"
            )

    async def save_preset(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Guarda un nuevo perfil personalizado de conexión MQTT o actualiza uno existente."""
        if not isinstance(body, dict):
            return problem_details(
                400, "Bad Request", "El cuerpo de la solicitud debe ser un objeto JSON válido.", "invalid_json"
            )

        name = str(body.get("name") or "").strip()
        if not name:
            return problem_details(
                422, "Unprocessable Entity", "El nombre del preset es obligatorio.", "missing_name"
            )

        host = str(body.get("host") or "").strip()
        if not host:
            return problem_details(
                422, "Unprocessable Entity", "El host del broker es obligatorio para guardar un preset.", "missing_host"
            )

        port = body.get("port", 1883)
        try:
            port_val = int(port)
            if not (1 <= port_val <= 65535):
                raise ValueError()
        except (ValueError, TypeError):
            return problem_details(
                422, "Unprocessable Entity", "El puerto debe ser un entero entre 1 y 65535.", "invalid_port"
            )

        preset_id = str(body.get("id") or "").strip()
        # Verificar que no sea un preset del sistema
        system_ids = {p.id for p in SYSTEM_PRESETS}
        if preset_id and preset_id in system_ids:
            return problem_details(
                400, "Bad Request", "No se puede sobreescribir un preset del sistema.", "system_preset_protected"
            )

        if not preset_id:
            # Generar ID limpio a partir del nombre o UUID
            clean_slug = re.sub(r"[^a-zA-Z0-9_]+", "_", name.lower()).strip("_")
            preset_id = f"custom_{clean_slug[:20]}_{uuid.uuid4().hex[:6]}"

        cfg = getattr(self.ctx.bridge, "services_config", None)
        if cfg is None:
            return problem_details(500, "Internal Server Error", "Servicio no inicializado.", "bridge_unavailable")

        # Preservar contraseña previa si se envía enmascarada
        existing = next((p for p in cfg.custom_presets if p.id == preset_id), None)
        password = str(body.get("password") or "")
        token = str(body.get("token") or "")
        if existing:
            if password == MASKED_PASSWORD:
                password = existing.password
            if token == MASKED_PASSWORD:
                token = existing.token

        preset = MqttPreset(
            id=preset_id,
            name=name,
            description=str(body.get("description") or ""),
            host=host,
            port=port_val,
            transport=str(body.get("transport") or "tcp"),
            tls_enabled=bool(body.get("tls_enabled", False)),
            tls_verify=bool(body.get("tls_verify", True)),
            auth_type=str(body.get("auth_type") or "anonymous"),
            username=str(body.get("username") or ""),
            password=password,
            token=token,
            downlink_enabled=bool(body.get("downlink_enabled", False)),
            location_privacy=str(body.get("location_privacy") or "fuzzed"),
            topic_mode=str(body.get("topic_mode") or "standard"),
            topic_prefix=str(body.get("topic_prefix") or "meshcore/remote"),
            region_iata=str(body.get("region_iata") or "XXX").upper(),
            payload_format=str(body.get("payload_format") or "json_canonical"),
            filter_observer_mode=bool(body.get("filter_observer_mode", False)),
            filter_public=bool(body.get("filter_public", True)),
            filter_channels=bool(body.get("filter_channels", True)),
            filter_direct=bool(body.get("filter_direct", False)),
            filter_telemetry=bool(body.get("filter_telemetry", True)),
            filter_nodes=bool(body.get("filter_nodes", True)),
            filter_raw=bool(body.get("filter_raw", False)),
            keepalive=int(body.get("keepalive") or 60),
            qos=int(body.get("qos") or 0),
            is_system=False,
        )

        # Reemplazar o añadir a la lista
        new_presets = [p for p in cfg.custom_presets if p.id != preset_id]
        new_presets.append(preset)
        cfg.custom_presets = new_presets

        await save_services_config_async(cfg)

        preset_dict = asdict(preset)
        preset_dict["has_password"] = bool(preset.password)
        preset_dict["password"] = MASKED_PASSWORD if preset.password else ""
        preset_dict["has_token"] = bool(preset.token)
        preset_dict["token"] = MASKED_PASSWORD if preset.token else ""

        self.ctx.log_system_event(
            "INFO", f"Preset personalizado '{name}' guardado correctamente.", source="services_mgr"
        )
        return 200, {
            "status": "ok",
            "message": f"Preset '{name}' guardado exitosamente.",
            "preset": preset_dict,
        }

    async def delete_preset(self, preset_id: str) -> tuple[int, dict[str, Any]]:
        """Elimina un preset personalizado existente."""
        clean_id = (preset_id or "").strip()
        system_ids = {p.id for p in SYSTEM_PRESETS}
        if clean_id in system_ids:
            return problem_details(
                400, "Bad Request", "No se puede eliminar un perfil predefinido del sistema.", "system_preset_protected"
            )

        cfg = getattr(self.ctx.bridge, "services_config", None)
        if cfg is None:
            return problem_details(500, "Internal Server Error", "Servicio no inicializado.", "bridge_unavailable")

        target = next((p for p in cfg.custom_presets if p.id == clean_id), None)
        if not target:
            return problem_details(
                404, "Not Found", f"Preset '{clean_id}' no encontrado.", "preset_not_found"
            )

        cfg.custom_presets = [p for p in cfg.custom_presets if p.id != clean_id]
        await save_services_config_async(cfg)

        self.ctx.log_system_event(
            "INFO", f"Preset personalizado '{target.name}' eliminado.", source="services_mgr"
        )
        return 200, {
            "status": "ok",
            "message": f"Preset '{target.name}' eliminado correctamente.",
        }

    async def test_external_mqtt(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Ejecuta una prueba efímera de conexión hacia el broker MQTT externo indicado."""
        if not isinstance(body, dict):
            return problem_details(
                400, "Bad Request", "El cuerpo de la solicitud debe ser un objeto JSON válido.", "invalid_json"
            )

        host = str(body.get("host") or "").strip()
        if not host:
            return problem_details(
                422, "Unprocessable Entity", "El host es obligatorio para realizar la prueba de conexión.", "missing_host"
            )

        port = body.get("port", 1883)
        try:
            port_val = int(port)
            if not (1 <= port_val <= 65535):
                raise ValueError()
        except (ValueError, TypeError):
            return problem_details(
                422, "Unprocessable Entity", "Puerto inválido.", "invalid_port"
            )

        cfg = getattr(self.ctx.bridge, "services_config", None)
        cur_ext = cfg.external_mqtt if cfg else None

        password = str(body.get("password") or "")
        token = str(body.get("token") or "")
        if password == MASKED_PASSWORD and cur_ext:
            password = cur_ext.password
        if token == MASKED_PASSWORD and cur_ext:
            token = cur_ext.token

        test_cfg = ExternalMqttConfig(
            enabled=True,
            host=host,
            port=port_val,
            transport=str(body.get("transport") or "tcp"),
            tls_enabled=bool(body.get("tls_enabled", False)),
            tls_verify=bool(body.get("tls_verify", True)),
            auth_type=str(body.get("auth_type") or "anonymous"),
            username=str(body.get("username") or ""),
            password=password,
            token=token,
        )

        timeout = float(body.get("timeout") or 5.0)
        timeout = max(1.0, min(10.0, timeout))

        test_result = await ExternalBridgeMQTTClient.test_connection(test_cfg, timeout=timeout)
        return 200, {
            "status": "ok" if test_result.get("ok") else "error",
            "data": test_result,
        }
