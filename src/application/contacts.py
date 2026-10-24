"""
Application Service for Contact and Node Directory Management (ContactService).
Encapsulates contact validations, radio synchronization, import/export, and mesh sharing
independently of the Web REST layer (FastAPI / Starlette).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.application.channels import firmware_name_valid
from src.contact_manager import NodeContactUpdate, NodeRegistry, is_valid_node_key
from src.station_database import StationDatabase

logger = logging.getLogger("meshcore.application.contacts")

_CONTACT_TYPE_MAP_REV: dict[str, str] = {
    "1": "CLIENT",
    "2": "REPEATER",
    "3": "ROOM",
    "4": "SENSOR",
}
_ROLE_TYPE_MAP: dict[str, int] = {
    "CLIENT": 1,
    "CHAT": 1,
    "USER": 1,
    "REPEATER": 2,
    "ROUTER": 2,
    "ROOM": 3,
    "SENSOR": 4,
}


@dataclass(frozen=True, slots=True)
class ContactOperationResult:
    """Resultado estandarizado de operaciones de contacto."""

    success: bool
    data: Any = None
    error: str | None = None
    error_code: str | None = None
    http_code: int = 200


class ContactService:
    """Servicio de aplicación para gestión, validación y sincronización de contactos."""

    def __init__(
        self,
        node_registry: NodeRegistry | None = None,
        serial_adapter_provider: Callable[[], Any] | None = None,
        database: StationDatabase | None = None,
        log_system_event: Any | None = None,
    ) -> None:
        self.node_registry = node_registry if node_registry is not None else NodeRegistry()
        self._serial_provider = serial_adapter_provider
        self.database = database
        self._log_event = log_system_event
        self._mutation_lock = asyncio.Lock()

    @property
    def serial_adapter(self) -> Any | None:
        if callable(self._serial_provider):
            return self._serial_provider()
        return None

    @staticmethod
    def _check_hardware_result(res: Any) -> ContactOperationResult | None:
        """Verifica la respuesta del transceptor serial y mapea rechazos a resultados de error."""
        if res is None or res is False:
            return ContactOperationResult(
                success=False,
                error="El transceptor no confirmó la operación",
                error_code="command_unconfirmed",
                http_code=503,
            )
        if isinstance(res, dict):
            status = str(res.get("status", "")).upper()
            if status in {"OK", "SUCCESS", "SENT", "DELETED", "CLEARED"} and not res.get("error"):
                return None
            if status in {"ERROR", "FAILED", "PARTIAL", "NOT_SUPPORTED", "LOCAL_ONLY", "LOCAL_DELETED"} or res.get("error"):
                raw_code = res.get("code", 503 if status.startswith(("NOT_SUPPORTED", "LOCAL_")) else 400)
                code = raw_code if isinstance(raw_code, int) and not isinstance(raw_code, bool) and 400 <= raw_code <= 599 else 400
                err_code = "command_partial" if status == "PARTIAL" else "command_failed"
                return ContactOperationResult(
                    success=False,
                    error="El transceptor rechazó la operación",
                    error_code=err_code,
                    http_code=code,
                )
            if not status:
                return None
            return ContactOperationResult(
                success=False,
                error="Respuesta de operación no confirmada",
                error_code="command_unconfirmed",
                http_code=503,
            )
        event_type = getattr(res, "type", None)
        if str(getattr(event_type, "name", event_type)).upper() in {"ERROR", "DISABLED"}:
            return ContactOperationResult(
                success=False,
                error="El transceptor rechazó la operación",
                error_code="command_failed",
                http_code=400,
            )
        is_error = getattr(res, "is_error", None)
        if callable(is_error) and is_error():
            return ContactOperationResult(
                success=False,
                error="El transceptor rechazó la operación",
                error_code="command_failed",
                http_code=400,
            )
        return None

    def validate_contact(self, pubkey: str, name: str, role: str) -> ContactOperationResult:
        """Valida que un contacto cumpla las restricciones de protocolo e invariantes de dominio."""
        clean_pk = pubkey.strip().lower()
        if not is_valid_node_key(clean_pk) or len(clean_pk) != 64:
            return ContactOperationResult(
                success=False,
                error="Se requiere una clave pública hexadecimal válida de 32 bytes (64 caracteres)",
                error_code="invalid_public_key",
                http_code=422,
            )
        if not firmware_name_valid(name):
            return ContactOperationResult(
                success=False,
                error="El nombre debe caber en 31 bytes UTF-8 sin caracteres de control",
                error_code="invalid_contact_name",
                http_code=422,
            )

        # Regla Inmutable 1.2: Prohibido agregar la estación base local como contacto
        if self.node_registry.is_local_key(clean_pk):
            return ContactOperationResult(
                success=False,
                error="No se permite agregar la estación base local a la libreta de contactos",
                error_code="cannot_add_local_station",
                http_code=400,
            )

        # Regla Inmutable 1.1: Prohibido agregar repetidores a la libreta de contactos
        existing = self.node_registry.get_node(clean_pk)
        role_upper = role.strip().upper()
        if role_upper in {"REPEATER", "ROUTER", "LOCAL"} or (existing and existing.role in {"REPEATER", "ROUTER", "LOCAL"}):
            return ContactOperationResult(
                success=False,
                error="Los nodos de infraestructura (repetidores/routers) no pertenecen a la libreta de contactos",
                error_code="repeater_contact_forbidden",
                http_code=400,
            )

        if role_upper not in {"CLIENT", "CHAT", "NONE"}:
            return ContactOperationResult(
                success=False,
                error="La libreta de contactos sólo admite dispositivos cliente de mensajería (rol CLIENT). Los sensores, salas y repetidores se gestionan en Nodos/Telemetría.",
                error_code="invalid_contact_role",
                http_code=422,
            )

        return ContactOperationResult(success=True, http_code=200)

    def list_contacts(self) -> list[dict[str, Any]]:
        """Lista únicamente contactos cliente (excluye repetidores y nodo local)."""
        return self.node_registry.list_client_contacts()

    def get_contact(self, pubkey: str) -> dict[str, Any] | None:
        """Obtiene un contacto por clave pública."""
        node = self.node_registry.get_contact(pubkey.strip().lower())
        if node and node.role not in ("REPEATER", "ROUTER", "LOCAL"):
            return node.to_dict()
        return None

    async def _save_registry_async(self) -> bool:
        if hasattr(self.node_registry, "save_to_file_async"):
            return bool(await self.node_registry.save_to_file_async())
        elif hasattr(self.node_registry, "save_to_file"):
            return bool(await asyncio.to_thread(self.node_registry.save_to_file))
        return True

    async def create_or_update_contact(
        self,
        pubkey: str,
        name: str,
        alias: str | None = None,
        role: str = "CLIENT",
        is_favorite: bool | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        sync_to_hardware: bool = True,
    ) -> ContactOperationResult:
        """Crea o actualiza un contacto en el registro y opcionalmente en el hardware."""
        async with self._mutation_lock:
            clean_pk = pubkey.strip().lower()
            if not clean_pk:
                return ContactOperationResult(
                    success=False,
                    error="Se requiere 'public_key'",
                    error_code="missing_public_key",
                    http_code=400,
                )

            clean_name = name.strip()
            clean_alias = alias.strip() if alias else clean_name
            clean_role = role.strip().upper()
            if clean_role in {"CHAT", "NONE"}:
                clean_role = "CLIENT"

            validation = self.validate_contact(pubkey=clean_pk, name=clean_name or clean_alias or f"Node_{clean_pk[:6]}", role=clean_role)
            if not validation.success:
                return validation

            # Sincronización previa con hardware si fue solicitada
            ser = self.serial_adapter
            if sync_to_hardware and ser:
                type_val = _ROLE_TYPE_MAP.get(clean_role, 1)
                mutation_data: dict[str, Any] = {
                    "public_key": clean_pk,
                    "name": clean_name or clean_alias or f"Node_{clean_pk[:6]}",
                    "role": clean_role,
                    "type": type_val,
                    "latitude": latitude,
                    "longitude": longitude,
                    "adv_lat": latitude,
                    "adv_lon": longitude,
                }
                try:
                    if hasattr(ser, "add_contact"):
                        res = await ser.add_contact(mutation_data)
                        failure = self._check_hardware_result(res)
                        if failure:
                            return failure
                    elif hasattr(ser, "send_contact"):
                        await ser.send_contact(clean_pk, clean_name, type_val)
                except (ValueError, TypeError):
                    return ContactOperationResult(
                        success=False,
                        error="Parámetros rechazados por el transceptor",
                        error_code="invalid_serial_parameters",
                        http_code=422,
                    )
                except Exception as ex:
                    logger.warning("Fallo al enviar contacto al transceptor: %s", type(ex).__name__)
                    return ContactOperationResult(
                        success=False,
                        error="Fallo de comunicación con el transceptor",
                        error_code="serial_operation_failed",
                        http_code=503,
                    )

            is_new = self.node_registry.get_node(clean_pk) is None
            update = NodeContactUpdate(
                name=clean_name or f"Node_{clean_pk[:6]}",
                alias=clean_alias or clean_name,
                role=clean_role,
                is_favorite=is_favorite,
                latitude=latitude,
                longitude=longitude,
                adv_lat=latitude,
                adv_lon=longitude,
            )
            updated = self.node_registry.add_or_update(clean_pk, update)
            saved = await self._save_registry_async()
            if not saved:
                return ContactOperationResult(
                    success=False,
                    error="Error al persistir el contacto en disco",
                    error_code="persistence_failed",
                    http_code=500,
                )

            if callable(self._log_event):
                self._log_event("INFO", f"Contacto guardado: {clean_pk} ({clean_alias or clean_name})", source="contacts")

            status_code = 201 if is_new else 200
            return ContactOperationResult(
                success=True,
                data=updated.to_dict() if updated else {"public_key": clean_pk, "name": clean_name},
                http_code=status_code,
            )

    async def delete_contact(
        self,
        pubkey: str,
        sync_to_hardware: bool = True,
    ) -> ContactOperationResult:
        """Elimina un contacto del registro y del transceptor."""
        async with self._mutation_lock:
            clean_pk = pubkey.strip().lower()
            if not clean_pk:
                return ContactOperationResult(
                    success=False,
                    error="Se requiere 'public_key'",
                    error_code="missing_public_key",
                    http_code=400,
                )

            if not is_valid_node_key(clean_pk):
                return ContactOperationResult(
                    success=False,
                    error="Clave pública inválida",
                    error_code="invalid_public_key",
                    http_code=422,
                )

            if self.node_registry.is_local_key(clean_pk):
                return ContactOperationResult(
                    success=False,
                    error="No se permite eliminar la estación base local",
                    error_code="cannot_delete_local_station",
                    http_code=400,
                )

            if not self.node_registry.get_node(clean_pk):
                return ContactOperationResult(
                    success=False,
                    error="Contacto no encontrado",
                    error_code="contact_not_found",
                    http_code=404,
                )

            ser = self.serial_adapter
            if sync_to_hardware and ser:
                try:
                    if hasattr(ser, "remove_contact"):
                        res = await ser.remove_contact(clean_pk)
                        failure = self._check_hardware_result(res)
                        if failure:
                            return failure
                    elif hasattr(ser, "delete_contact"):
                        await ser.delete_contact(clean_pk)
                except (ValueError, TypeError):
                    return ContactOperationResult(
                        success=False,
                        error="Parámetros rechazados por el transceptor",
                        error_code="invalid_serial_parameters",
                        http_code=422,
                    )
                except Exception as ex:
                    logger.warning("Fallo al eliminar contacto del transceptor: %s", type(ex).__name__)
                    return ContactOperationResult(
                        success=False,
                        error="Fallo de comunicación con el transceptor",
                        error_code="serial_operation_failed",
                        http_code=503,
                    )

            deleted = False
            if hasattr(self.node_registry, "delete_contact"):
                deleted = bool(self.node_registry.delete_contact(clean_pk))
            elif hasattr(self.node_registry, "remove_node"):
                deleted = bool(self.node_registry.remove_node(clean_pk))

            if not deleted:
                return ContactOperationResult(
                    success=False,
                    error="Contacto no encontrado",
                    error_code="contact_not_found",
                    http_code=404,
                )

            saved = await self._save_registry_async()
            if not saved:
                return ContactOperationResult(
                    success=False,
                    error="Error al persistir eliminación en disco",
                    error_code="persistence_failed",
                    http_code=500,
                )

            if callable(self._log_event):
                self._log_event("INFO", f"Contacto eliminado: {clean_pk[:8]}...", source="contacts")

            return ContactOperationResult(
                success=True,
                data={"public_key": clean_pk, "deleted": True},
                http_code=204,
            )

    async def sync_from_radio(self) -> ContactOperationResult:
        """Sincroniza todos los contactos desde el transceptor serial hacia el registro."""
        async with self._mutation_lock:
            ser = self.serial_adapter
            if not ser or not hasattr(ser, "sync_all_contacts"):
                return ContactOperationResult(
                    success=False,
                    error="Transceptor no disponible para sincronización de contactos",
                    error_code="transceiver_offline",
                    http_code=503,
                )

            imported_count = 0
            try:
                imported = await ser.sync_all_contacts()
                for c in imported:
                    pk = str(c.get("public_key", "")).strip().lower()
                    if pk and is_valid_node_key(pk) and not self.node_registry.is_local_key(pk):
                        last_adv = c.get("last_advert")
                        eff_lat = c.get("latitude") if c.get("latitude") is not None else (c.get("lat") if c.get("lat") is not None else c.get("adv_lat"))
                        eff_lon = c.get("longitude") if c.get("longitude") is not None else (c.get("lon") if c.get("lon") is not None else c.get("adv_lon"))
                        self.node_registry.add_or_update(
                            pk,
                            NodeContactUpdate(
                                name=c.get("name"),
                                alias=c.get("alias"),
                                role=c.get("role", "CLIENT"),
                                last_seen=None,
                                last_advert=float(last_adv) if isinstance(last_adv, (int, float)) and last_adv > 0 else None,
                                latitude=eff_lat,
                                longitude=eff_lon,
                                adv_lat=c.get("adv_lat") or eff_lat,
                                adv_lon=c.get("adv_lon") or eff_lon,
                                flags=c.get("flags"),
                                out_path=c.get("out_path"),
                                out_path_len=c.get("out_path_len"),
                                out_path_hash_mode=c.get("out_path_hash_mode"),
                            ),
                        )
                        imported_count += 1
                await self._save_registry_async()
            except ConnectionError:
                return ContactOperationResult(
                    success=False,
                    error="No se pudo sincronizar contactos: Error de conexión serie",
                    error_code="sync_failed",
                    http_code=503,
                )
            except Exception as e:
                logger.error("Error sincronizando contactos con el nodo: %s", type(e).__name__)
                return ContactOperationResult(
                    success=False,
                    error=f"Fallo sincronizando contactos con el nodo: {type(e).__name__}",
                    error_code="sync_failed",
                    http_code=503,
                )

            contacts = self.list_contacts()
            return ContactOperationResult(
                success=True,
                data={"status": "ok", "imported": imported_count, "data": contacts, "count": len(contacts)},
                http_code=200,
            )

    async def share_contact(self, pubkey: str) -> ContactOperationResult:
        """Comparte un contacto con la malla LoRa a través del transceptor."""
        clean_pk = pubkey.strip().lower()
        if not clean_pk:
            return ContactOperationResult(
                success=False,
                error="Se requiere 'public_key'",
                error_code="missing_public_key",
                http_code=400,
            )

        ser = self.serial_adapter
        if not ser or not hasattr(ser, "share_contact"):
            return ContactOperationResult(
                success=False,
                error="El transceptor no soporta la función share_contact",
                error_code="operation_not_supported",
                http_code=503,
            )

        try:
            res = await ser.share_contact(clean_pk)
            failure = self._check_hardware_result(res)
            if failure:
                return failure
        except Exception as e:
            return ContactOperationResult(
                success=False,
                error=f"Error al compartir contacto: {type(e).__name__}",
                error_code="share_failed",
                http_code=503,
            )

        if callable(self._log_event):
            self._log_event("INFO", f"Contacto compartido con la malla: {clean_pk}", source="contacts")
        return ContactOperationResult(success=True, data=res, http_code=200)

    async def export_contact(self, pubkey: str) -> ContactOperationResult:
        """Exporta un contacto en URI oficial de MeshCore (meshcore://contact/add?...)."""
        clean_pk = pubkey.strip().lower()
        if not clean_pk:
            return ContactOperationResult(
                success=False,
                error="Se requiere 'public_key' para exportar",
                error_code="missing_public_key",
                http_code=400,
            )

        val = self.validate_contact(clean_pk, "Export", "CLIENT")
        if not val.success:
            return val

        name = ""
        role = "CLIENT"
        node = self.node_registry.get_node(clean_pk)
        if node:
            name = str(getattr(node, "name", "") or getattr(node, "alias", "") or "").strip()
            role = str(getattr(node, "role", "CLIENT") or "CLIENT").strip().upper()

        if not name:
            name = f"Node_{clean_pk[:6]}"

        type_num = _ROLE_TYPE_MAP.get(role, 1)

        ser = self.serial_adapter
        res = await ser.export_contact(clean_pk) if ser and hasattr(ser, "export_contact") else None

        raw_hex_str: str | None = None
        if isinstance(res, str):
            raw_hex_str = res
        elif isinstance(res, dict) and isinstance(res.get("raw_hex"), str):
            raw_hex_str = res["raw_hex"]
        elif isinstance(res, dict) and res.get("status") == "OK" and "response" in res:
            raw_hex_str = str(res["response"])

        encoded_name = urllib.parse.quote(name)
        canonical_uri = f"meshcore://contact/add?name={encoded_name}&public_key={clean_pk}&type={type_num}"
        message_tag = f"<{clean_pk}:{type_num}:{name}>"

        contact_data = {
            "type": "contact",
            "name": name,
            "public_key": clean_pk,
            "role": role,
            "contact_type": type_num,
            "uri": canonical_uri,
            "message_tag": message_tag,
            "raw_hex": raw_hex_str,
        }

        return ContactOperationResult(
            success=True,
            data={
                "status": "ok",
                "uri": canonical_uri,
                "qr_uri": canonical_uri,
                "message_tag": message_tag,
                "data": contact_data,
                "result": raw_hex_str,
            },
            http_code=200,
        )

    @staticmethod
    def parse_contacts_from_tags(raw_payload: str) -> list[dict[str, Any]]:
        """Extrae contactos en formato de mensaje MeshCore <pubkey:type:name>."""
        contacts: list[dict[str, Any]] = []
        m_single = re.match(r"^<([0-9a-fA-F]{64}):([0-9]+):([^>]+)>$", raw_payload)
        if m_single:
            pk = m_single.group(1).lower()
            raw_type = m_single.group(2)
            nm = m_single.group(3).strip()
            rl = _CONTACT_TYPE_MAP_REV.get(raw_type, "CLIENT")
            contacts.append({"public_key": pk, "name": nm, "alias": nm, "role": rl})
        else:
            matches = re.findall(r"<([0-9a-fA-F]{64}):([0-9]+):([^>]+)>", raw_payload)
            for m_pk, m_type, m_name in matches:
                rl = _CONTACT_TYPE_MAP_REV.get(m_type, "CLIENT")
                contacts.append({"public_key": m_pk.lower(), "name": m_name.strip(), "alias": m_name.strip(), "role": rl})
        return contacts

    @staticmethod
    def parse_contacts_from_uri(raw_payload: str) -> tuple[list[dict[str, Any]], ContactOperationResult | None]:
        """Extrae contactos desde URI meshcore://."""
        if not raw_payload.startswith("meshcore://"):
            return [], None
        try:
            parsed_uri = urllib.parse.urlparse(raw_payload)
            if "channel" in parsed_uri.netloc.lower() or "channel" in parsed_uri.path.lower():
                return [], ContactOperationResult(
                    success=False,
                    error="El contenido corresponde a un canal, no a un contacto. Usa la sección Canales para importarlo.",
                    error_code="channel_payload_in_contacts",
                    http_code=400,
                )

            qs = urllib.parse.parse_qs(parsed_uri.query)
            pk = (qs.get("public_key") or qs.get("pubkey") or qs.get("key") or [""])[0].strip().lower()
            nm = (qs.get("name") or qs.get("alias") or [""])[0].strip()
            raw_type = (qs.get("type") or [""])[0].strip()
            rl = (qs.get("role") or [""])[0].strip().upper()
            if not rl and raw_type:
                rl = _CONTACT_TYPE_MAP_REV.get(raw_type, "CLIENT")
            if not rl:
                rl = "CLIENT"
            lat_s = (qs.get("latitude") or qs.get("lat") or qs.get("adv_lat") or [""])[0].strip()
            lon_s = (qs.get("longitude") or qs.get("lon") or qs.get("adv_lon") or [""])[0].strip()
            c_entry: dict[str, Any] = {"public_key": pk, "name": nm, "alias": nm, "role": rl}
            if lat_s:
                try:
                    c_entry["latitude"] = float(lat_s)
                except (ValueError, TypeError):
                    pass
            if lon_s:
                try:
                    c_entry["longitude"] = float(lon_s)
                except (ValueError, TypeError):
                    pass
            if pk:
                return [c_entry], None
        except Exception as error:
            logger.warning("Contact URI parsing failed: %s", type(error).__name__)
        return [], None

    @staticmethod
    def parse_contacts_from_json(raw_payload: str) -> tuple[list[dict[str, Any]], ContactOperationResult | None]:
        """Extrae contactos desde cadena JSON."""
        if not (raw_payload.startswith("{") or raw_payload.startswith("[")):
            return [], None
        try:
            loaded = json.loads(raw_payload)
            if isinstance(loaded, dict):
                if loaded.get("type") == "channel":
                    return [], ContactOperationResult(
                        success=False,
                        error="El contenido corresponde a un canal, no a un contacto",
                        error_code="channel_payload_in_contacts",
                        http_code=400,
                    )
                return [loaded], None
            elif isinstance(loaded, list):
                return [c for c in loaded if isinstance(c, dict)], None
        except Exception as error:
            logger.warning("Contact JSON parsing failed: %s", type(error).__name__)
        return [], None

    @classmethod
    def parse_contacts_from_hex(cls, raw_payload: str) -> tuple[list[dict[str, Any]], bytes | None, ContactOperationResult | None]:
        """Extrae contactos desde volcado hexadecimal, decodificando UTF-8 o retornando bytes binarios para el firmware."""
        try:
            bin_data = bytes.fromhex(raw_payload)
        except ValueError:
            return [], None, ContactOperationResult(
                success=False,
                error="Formato de datos no reconocido (no es URI, JSON ni hexadecimal válido)",
                error_code="invalid_hex_data",
                http_code=400,
            )

        try:
            utf8_text = bin_data.decode("utf-8").strip()
            if utf8_text.startswith("{") or utf8_text.startswith("["):
                contacts, err = cls.parse_contacts_from_json(utf8_text)
                if err:
                    return [], None, err
                if contacts:
                    return contacts, None, None
            elif utf8_text.startswith("meshcore://"):
                contacts, err = cls.parse_contacts_from_uri(utf8_text)
                if err:
                    return [], None, err
                if contacts:
                    return contacts, None, None
        except Exception:
            pass

        return [], bin_data, None

    async def import_contact_payload(
        self,
        payload: str | dict[str, Any] | list[Any],
        sync_to_hardware: bool = True,
    ) -> ContactOperationResult:
        """Importa contactos desde URI, tags, JSON, volcado hexadecimal o dict/list estructurado."""
        from src.shared_utils import to_bool

        contacts_to_add: list[dict[str, Any]] = []
        raw_payload = ""

        if isinstance(payload, dict):
            if "public_key" in payload or "pubkey" in payload or "key" in payload:
                contacts_to_add.append(payload)
            elif isinstance(payload.get("contacts"), list):
                contacts_to_add.extend(c for c in payload["contacts"] if isinstance(c, dict))
            else:
                raw_payload = str(payload.get("data") or payload.get("payload") or payload.get("uri") or "").strip()
        elif isinstance(payload, list):
            contacts_to_add.extend(c for c in payload if isinstance(c, dict))
        elif isinstance(payload, str):
            raw_payload = payload.strip()

        if raw_payload and not contacts_to_add:
            contacts_to_add = self.parse_contacts_from_tags(raw_payload)

            if not contacts_to_add:
                uri_contacts, uri_err = self.parse_contacts_from_uri(raw_payload)
                if uri_err:
                    return uri_err
                contacts_to_add = uri_contacts

            if not contacts_to_add:
                json_contacts, json_err = self.parse_contacts_from_json(raw_payload)
                if json_err:
                    return json_err
                contacts_to_add = json_contacts

            if not contacts_to_add:
                hex_contacts, bin_data, hex_err = self.parse_contacts_from_hex(raw_payload)
                if hex_err:
                    return hex_err
                if hex_contacts:
                    contacts_to_add = hex_contacts
                elif bin_data:
                    ser = self.serial_adapter
                    if ser and hasattr(ser, "import_contact"):
                        try:
                            res = await ser.import_contact(bin_data)
                            failure = self._check_hardware_result(res)
                            if failure:
                                return failure
                            if callable(self._log_event):
                                self._log_event("INFO", "Contacto binario importado hacia el firmware", source="contacts")
                            return ContactOperationResult(success=True, data={"status": "ok", "result": res}, http_code=200)
                        except Exception as ex:
                            return ContactOperationResult(
                                success=False,
                                error=f"Error en transceptor al importar binario: {type(ex).__name__}",
                                error_code="serial_operation_failed",
                                http_code=503,
                            )
                    return ContactOperationResult(
                        success=False,
                        error="Transceptor no disponible para importar contacto binario",
                        error_code="serial_unavailable",
                        http_code=503,
                    )

        if not contacts_to_add:
            return ContactOperationResult(
                success=False,
                error="No se detectaron contactos válidos para importar",
                error_code="no_valid_contacts",
                http_code=400,
            )

        async with self._mutation_lock:
            # Validación previa de lote
            validated_batch: list[tuple[str, str, str, str, bool | None, float | None, float | None]] = []
            for c_dict in contacts_to_add:
                if not isinstance(c_dict, dict):
                    return ContactOperationResult(
                        success=False,
                        error="Cada contacto debe ser un objeto JSON",
                        error_code="invalid_contact_format",
                        http_code=422,
                    )
                pubkey = str(c_dict.get("public_key") or c_dict.get("pubkey") or c_dict.get("key") or "").strip().lower()
                if not pubkey or self.node_registry.is_local_key(pubkey):
                    continue

                role = str(c_dict.get("role") or "CLIENT").strip().upper()
                if role in ("REPEATER", "ROUTER", "LOCAL"):
                    continue

                name = str(c_dict.get("name") or "").strip()
                alias = str(c_dict.get("alias") or name or f"Node_{pubkey[:6]}").strip()

                val = self.validate_contact(pubkey, name or alias, role)
                if not val.success:
                    return val

                is_fav = c_dict.get("is_favorite")
                is_favorite_val = to_bool(is_fav) if is_fav is not None else None

                raw_lat = c_dict.get("latitude") if c_dict.get("latitude") is not None else (c_dict.get("lat") if c_dict.get("lat") is not None else c_dict.get("adv_lat"))
                raw_lon = c_dict.get("longitude") if c_dict.get("longitude") is not None else (c_dict.get("lon") if c_dict.get("lon") is not None else c_dict.get("adv_lon"))
                lat_val: float | None = None
                lon_val: float | None = None
                if raw_lat is not None:
                    try:
                        lat_val = float(raw_lat)
                    except (ValueError, TypeError):
                        pass
                if raw_lon is not None:
                    try:
                        lon_val = float(raw_lon)
                    except (ValueError, TypeError):
                        pass

                validated_batch.append((pubkey, name, alias, role, is_favorite_val, lat_val, lon_val))

            if not validated_batch:
                return ContactOperationResult(
                    success=False,
                    error="Ningún contacto válido pudo ser agregado (verifique que no sean nodos repetidores o la estación base local)",
                    error_code="import_rejected",
                    http_code=400,
                )

            # Persistencia y mutación de hardware
            imported_records: list[dict[str, Any]] = []
            ser = self.serial_adapter
            for pk, nm, al, rl, fav, lat, lon in validated_batch:
                if sync_to_hardware and ser and hasattr(ser, "add_contact"):
                    mutation_data: dict[str, Any] = {
                        "public_key": pk,
                        "name": nm or al,
                        "role": rl,
                        "type": _ROLE_TYPE_MAP.get(rl, 1),
                        "latitude": lat,
                        "longitude": lon,
                        "adv_lat": lat,
                        "adv_lon": lon,
                    }
                    try:
                        res = await ser.add_contact(mutation_data)
                        failure = self._check_hardware_result(res)
                        if failure:
                            if imported_records:
                                await self._save_registry_async()
                            return failure
                    except (ValueError, TypeError):
                        if imported_records:
                            await self._save_registry_async()
                        return ContactOperationResult(
                            success=False,
                            error="Parámetros rechazados por el transceptor",
                            error_code="invalid_serial_parameters",
                            http_code=422,
                        )
                    except Exception as ex:
                        if imported_records:
                            await self._save_registry_async()
                        return ContactOperationResult(
                            success=False,
                            error=f"Fallo de comunicación con el transceptor: {type(ex).__name__}",
                            error_code="serial_operation_failed",
                            http_code=503,
                        )

                contact = self.node_registry.add_or_update(
                    pk,
                    NodeContactUpdate(
                        name=nm or al,
                        alias=al,
                        role=rl,
                        is_favorite=fav,
                        latitude=lat,
                        longitude=lon,
                        adv_lat=lat,
                        adv_lon=lon,
                    ),
                )
                imported_records.append(contact.to_dict())

            saved = await self._save_registry_async()
            if not saved:
                return ContactOperationResult(
                    success=False,
                    error="Error al persistir contactos importados en disco",
                    error_code="persistence_failed",
                    http_code=500,
                )

            if callable(self._log_event):
                self._log_event("INFO", f"Se importaron {len(imported_records)} contactos exitosamente", source="contacts")

            return ContactOperationResult(
                success=True,
                data={"status": "ok", "imported": len(imported_records), "data": imported_records},
                http_code=201,
            )
