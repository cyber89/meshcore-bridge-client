"""
ServicesController: Controlador REST para la administración y diagnóstico de Servicios de Red.
Gestiona endpoints para configuración de MQTT local/externo, Servidor TCP Companion,
CRUD de presets de conexión y pruebas efímeras de conectividad.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

import config
from src.companion_connection import companion_connection_snapshot, normalize_companion_port
from src.external_mqtt_client import ExternalBridgeMQTTClient
from src.services_config import (
    MASKED_PASSWORD,
    SYSTEM_PRESETS,
    ExternalMqttConfig,
    MqttPreset,
    ServicesConfig,
    save_services_config_async,
    to_redacted_dict,
    validate_services_config,
)
from src.web.controllers.base import ApiContext, BaseController, problem_details

logger = logging.getLogger("meshcore.controllers.services")


class ServicesController(BaseController):
    """Controlador REST para gestión de servicios de red y presets MQTT."""

    def __init__(self, ctx: ApiContext) -> None:
        super().__init__(ctx)
        self._mutation_lock = asyncio.Lock()
        self._configuration_write_task: asyncio.Task[None] | None = None

    @asynccontextmanager
    async def _configuration_guard(self) -> AsyncIterator[None]:
        manager = getattr(self.ctx.bridge, "services_manager", None)
        guard = getattr(manager, "configuration_guard", None)
        if callable(guard):
            async with guard():
                yield
        else:
            # Lightweight consumers retain the same cancellation-safe writer
            # ordering without constructing any network service manager.
            async with self._mutation_lock:
                try:
                    await self._await_configuration_write()
                except Exception:
                    # The owned result callback reports the previous failure.
                    # This request can retry persistence with a new snapshot.
                    pass
                yield

    async def _await_configuration_write(self) -> None:
        task = self._configuration_write_task
        if task is None:
            return
        try:
            await asyncio.shield(task)
        finally:
            if task.done() and self._configuration_write_task is task:
                self._configuration_write_task = None

    @staticmethod
    def _observe_configuration_write(task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                logger.error("Preset persistence failed: %s", type(error).__name__)

    async def _persist_configuration(self, cfg: ServicesConfig) -> None:
        """Called only under the guard protecting this configuration snapshot."""
        manager = getattr(self.ctx.bridge, "services_manager", None)
        persist = getattr(manager, "persist_configuration", None)
        if callable(persist):
            await persist(cfg)
            return
        await self._await_configuration_write()
        snapshot = copy.deepcopy(cfg)
        self._configuration_write_task = asyncio.create_task(
            save_services_config_async(snapshot), name="PresetConfigurationPersistence"
        )
        self._configuration_write_task.add_done_callback(self._observe_configuration_write)
        await self._await_configuration_write()

    async def _commit_presets(self, current: ServicesConfig, candidate: ServicesConfig) -> None:
        """Publish a validated snapshot only after its owned disk write commits."""
        validate_services_config(candidate)

        async def commit() -> None:
            await self._persist_configuration(candidate)
            current.custom_presets = candidate.custom_presets

        transaction = asyncio.create_task(commit(), name="PresetConfigurationCommit")
        cancelled = False
        while not transaction.done():
            try:
                await asyncio.shield(transaction)
            except asyncio.CancelledError:
                cancelled = True
        transaction.result()
        if cancelled:
            raise asyncio.CancelledError

    async def get_services_config(self) -> tuple[int, dict[str, Any]]:
        """Devuelve la configuración consolidada de servicios de red con credenciales enmascaradas."""
        cfg = getattr(self.ctx.bridge, "services_config", None)
        if cfg is None:
            from src.services_config import load_services_config
            cfg = load_services_config()

        data = to_redacted_dict(cfg)
        data["companion_connection"] = self._companion_connection(cfg)
        mgr = getattr(self.ctx.bridge, "services_manager", None)
        if mgr and getattr(mgr, "external_mqtt", None):
            data["external_mqtt_connected"] = bool(getattr(mgr.external_mqtt, "is_connected", False))
        else:
            data["external_mqtt_connected"] = False
        caps = getattr(self.ctx.bridge, "capabilities", None)
        if caps is not None:
            self._refresh_runtime_capabilities()
            data["capabilities"] = caps.to_dict()
        return 200, {"status": "ok", "data": data}

    def _refresh_runtime_capabilities(self) -> None:
        refresh_core = getattr(self.ctx.bridge, "refresh_core_capability", None)
        if callable(refresh_core):
            refresh_core()
        manager = getattr(self.ctx.bridge, "services_manager", None)
        refresh_network = getattr(manager, "refresh_capabilities", None)
        if callable(refresh_network):
            refresh_network()

    async def get_capabilities(self) -> tuple[int, dict[str, Any]]:
        """Devuelve el inventario dinámico de capacidades de runtime y su estado de opcionalidad."""
        self._refresh_runtime_capabilities()
        caps = getattr(self.ctx.bridge, "capabilities", None)
        if caps is not None:
            return 200, {"status": "ok", "data": caps.to_dict()}
        from src.capabilities import CapabilityRegistry
        fallback = CapabilityRegistry(web_enabled=True)
        return 200, {"status": "ok", "data": fallback.to_dict()}

    def _companion_connection(self, cfg: ServicesConfig) -> dict[str, str | bool]:
        adapter = getattr(self.ctx.bridge, "serial_adapter", None)
        return companion_connection_snapshot(
            cfg.companion_port,
            config.SERIAL_PORT,
            str(getattr(adapter, "port", "")),
            getattr(self.ctx.bridge, "_companion_startup_port", None),
        )

    async def set_services_config(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Actualiza y recarga en caliente la configuración de servicios de red."""
        # reload_services owns the manager lock itself. Never hold that same
        # lock here while invoking it; this lock also supports legacy consumers.
        async with self._mutation_lock:
            try:
                await self._await_configuration_write()
            except Exception:
                pass  # Previous owned write failure was reported by its callback.
            return await self._set_services_config(body)

    async def _set_services_config(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if not isinstance(body, dict):
            return problem_details(
                400, "Bad Request", "El cuerpo de la solicitud debe ser un objeto JSON válido.", "invalid_json"
            )

        if "companion_port" in body:
            try:
                endpoint = normalize_companion_port(body["companion_port"])
            except ValueError:
                return problem_details(
                    422, "Unprocessable Entity",
                    "Companion requiere AUTO, un puerto COM, una ruta absoluta o tcp://host:puerto (1..65535), sin credenciales ni IPv6.",
                    "invalid_companion_port",
                )
            body = {**body, "companion_port": endpoint}

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

            tp = str(ext.get("topic_prefix") or "").strip().strip("/")
            if tp and any(ch in tp for ch in "+#"):
                return problem_details(
                    422, "Unprocessable Entity", "El prefijo del topic MQTT no puede contener caracteres comodín (+ o #).", "invalid_topic_prefix"
                )
            iata = str(ext.get("region_iata") or "").strip().upper()
            if iata and not re.match(r"^[A-Z]{3}$", iata):
                return problem_details(
                    422, "Unprocessable Entity", "El código de región IATA debe contener exactamente 3 letras mayúsculas.", "invalid_region_iata"
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
            if cfg is not None:
                data["companion_connection"] = self._companion_connection(cfg)

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
        except ValueError:
            return problem_details(
                422, "Unprocessable Entity", "Configuración de servicios inválida.", "invalid_services_config"
            )
        except Exception as e:
            logger.error("Services configuration reload failed: %s", type(e).__name__)
            return problem_details(
                500, "Internal Server Error", "Error al recargar servicios de red.", "reload_failed"
            )

    async def save_preset(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Guarda un nuevo perfil personalizado de conexión MQTT o actualiza uno existente."""
        async with self._configuration_guard():
            return await self._save_preset(body)

    async def _save_preset(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
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
            if isinstance(port, (bool, float)):
                raise ValueError()
            port_val = int(port)
            if not (1 <= port_val <= 65535):
                raise ValueError()
        except (ValueError, TypeError):
            return problem_details(
                422, "Unprocessable Entity", "El puerto debe ser un entero entre 1 y 65535.", "invalid_port"
            )
        try:
            raw_keepalive = body.get("keepalive", 60)
            raw_qos = body.get("qos", 0)
            if isinstance(raw_keepalive, (bool, float)) or isinstance(raw_qos, (bool, float)):
                raise ValueError()
            keepalive = int(raw_keepalive)
            qos = int(raw_qos)
        except (ValueError, TypeError):
            return problem_details(
                422, "Unprocessable Entity", "Keepalive y QoS deben ser enteros válidos.", "invalid_preset_number"
            )

        topic_prefix = str(body.get("topic_prefix") or "meshcore/remote").strip().strip("/")
        if any(ch in topic_prefix for ch in "+#"):
            return problem_details(
                422, "Unprocessable Entity", "El prefijo del topic MQTT no puede contener caracteres comodín (+ o #).", "invalid_topic_prefix"
            )
        region_iata = str(body.get("region_iata") or "XXX").strip().upper()
        if not re.match(r"^[A-Z]{3}$", region_iata):
            return problem_details(
                422, "Unprocessable Entity", "El código de región IATA debe contener exactamente 3 letras mayúsculas.", "invalid_region_iata"
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
            tls_ca_file=str(body.get("tls_ca_file") or "").strip() or None,
            auth_type=str(body.get("auth_type") or "anonymous"),
            username=str(body.get("username") or ""),
            password=password,
            token=token,
            downlink_enabled=bool(body.get("downlink_enabled", False)),
            location_privacy=str(body.get("location_privacy") or "fuzzed"),
            topic_mode=str(body.get("topic_mode") or "standard"),
            topic_prefix=topic_prefix,
            region_iata=region_iata,
            payload_format=str(body.get("payload_format") or "json_canonical"),
            filter_observer_mode=bool(body.get("filter_observer_mode", False)),
            filter_public=bool(body.get("filter_public", True)),
            filter_channels=bool(body.get("filter_channels", True)),
            filter_direct=bool(body.get("filter_direct", False)),
            filter_telemetry=bool(body.get("filter_telemetry", True)),
            filter_nodes=bool(body.get("filter_nodes", True)),
            filter_raw=bool(body.get("filter_raw", False)),
            keepalive=keepalive,
            qos=qos,
            is_system=False,
        )

        # Reemplazar o añadir a la lista
        new_presets = [p for p in cfg.custom_presets if p.id != preset_id]
        new_presets.append(preset)
        candidate = copy.deepcopy(cfg)
        candidate.custom_presets = new_presets
        try:
            await self._commit_presets(cfg, candidate)
        except ValueError:
            return problem_details(422, "Unprocessable Entity", "Configuración del preset inválida.", "invalid_preset")
        except Exception as error:
            logger.error("Preset commit failed: %s", type(error).__name__)
            return problem_details(503, "Service Unavailable", "No se pudo guardar el preset.", "preset_persistence_failed")

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
        async with self._configuration_guard():
            return await self._delete_preset(preset_id)

    async def _delete_preset(self, preset_id: str) -> tuple[int, dict[str, Any]]:
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

        candidate = copy.deepcopy(cfg)
        candidate.custom_presets = [p for p in cfg.custom_presets if p.id != clean_id]
        try:
            await self._commit_presets(cfg, candidate)
        except Exception as error:
            logger.error("Preset deletion commit failed: %s", type(error).__name__)
            return problem_details(503, "Service Unavailable", "No se pudo eliminar el preset.", "preset_persistence_failed")

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

        if host.lower() in ("169.254.169.254", "metadata.google.internal", "instance-data"):
            return problem_details(
                422, "Unprocessable Entity", "Host no permitido para pruebas de conectividad.", "disallowed_host"
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

        import ipaddress
        import socket
        try:
            loop = asyncio.get_running_loop()
            addr_info = await loop.getaddrinfo(host, port_val, proto=socket.IPPROTO_TCP)
            for _, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
                        ip = ip.ipv4_mapped
                    if ip.is_link_local or ip.is_unspecified or ip.is_multicast:
                        return problem_details(
                            422, "Unprocessable Entity", "Host no permitido para pruebas de conectividad.", "disallowed_host"
                        )
                except ValueError:
                    pass
        except socket.gaierror:
            return problem_details(
                422, "Unprocessable Entity", "No se pudo resolver el host especificado.", "unresolved_host"
            )

        raw_ca = str(body.get("tls_ca_file") or "").strip()
        tls_ca_file: str | None = None
        if raw_ca:
            import os
            if ".." in raw_ca or not os.path.isabs(raw_ca) or not os.path.isfile(raw_ca) or os.path.islink(raw_ca):
                return problem_details(
                    422, "Unprocessable Entity", "tls_ca_file debe ser una ruta absoluta válida sin transversales (..) ni enlaces simbólicos.", "invalid_tls_ca_file"
                )
            tls_ca_file = raw_ca

        cfg = getattr(self.ctx.bridge, "services_config", None)
        cur_ext = cfg.external_mqtt if cfg else None

        password = str(body.get("password") or "")
        token = str(body.get("token") or "")
        tls_enabled = bool(body.get("tls_enabled", False))

        preset_id = str(body.get("preset_id") or "").strip()
        matched_source: Any = None
        if cur_ext and host == cur_ext.host and port_val == cur_ext.port and tls_enabled == cur_ext.tls_enabled:
            matched_source = cur_ext
        elif preset_id and cfg:
            preset = next((p for p in cfg.custom_presets if p.id == preset_id), None)
            if preset and host == preset.host and port_val == preset.port and tls_enabled == preset.tls_enabled:
                matched_source = preset

        if password == MASKED_PASSWORD:
            if matched_source and getattr(matched_source, "password", ""):
                password = matched_source.password
            else:
                return problem_details(
                    422,
                    "Unprocessable Entity",
                    "No se pueden usar credenciales enmascaradas con un host o puerto diferente al configurado.",
                    "masked_credentials_host_mismatch",
                )

        if token == MASKED_PASSWORD:
            if matched_source and getattr(matched_source, "token", ""):
                token = matched_source.token
            else:
                return problem_details(
                    422,
                    "Unprocessable Entity",
                    "No se pueden usar credenciales enmascaradas con un host o puerto diferente al configurado.",
                    "masked_credentials_host_mismatch",
                )

        test_cfg = ExternalMqttConfig(
            enabled=True,
            host=host,
            port=port_val,
            transport=str(body.get("transport") or "tcp"),
            tls_enabled=tls_enabled,
            tls_verify=bool(body.get("tls_verify", True)),
            tls_ca_file=tls_ca_file,
            auth_type=str(body.get("auth_type") or "anonymous"),
            username=str(body.get("username") or ""),
            password=password,
            token=token,
        )

        try:
            timeout = float(body.get("timeout") or 5.0)
            timeout = max(1.0, min(10.0, timeout))
            test_result = await ExternalBridgeMQTTClient.test_connection(test_cfg, timeout=timeout)
        except (ValueError, TypeError):
            return problem_details(
                422, "Unprocessable Entity", "Configuración de servicios inválida.", "invalid_services_config"
            )
        if isinstance(test_result, dict) and "error" in test_result:
            test_result["error"] = str(test_result["error"]).split("\n")[0][:200]
        return 200, {
            "status": "ok" if test_result.get("ok") else "error",
            "data": test_result,
        }
