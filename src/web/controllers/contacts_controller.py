"""
Contacts REST controller.
Handles /api/contacts, /api/contacts/sync, /api/contacts/share, export, and import.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.parse
from typing import Any

from src.contact_manager import NodeContactUpdate
from src.web.controllers.base import BaseController, problem_details


class ContactsController(BaseController):
    """Controlador para libreta de contactos (clientes LoRa) y sincronización con el firmware."""

    async def _save_registry_async(self) -> None:
        """Persiste el registro de nodos en un thread pool sin bloquear el event loop."""
        reg = getattr(self.ctx.bridge, "node_registry", None)
        if reg:
            if hasattr(reg, "save_to_file_async"):
                await reg.save_to_file_async()
            elif hasattr(reg, "save_to_file"):
                await asyncio.to_thread(reg.save_to_file)

    async def handle_contacts_route(
        self,
        path: str,
        method: str,
        req_body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        """Maneja todas las rutas asociadas a /api/contacts."""
        if path == "/api/contacts/sync" and method == "POST":
            return await self._sync_contacts()

        if path == "/api/contacts/share" and method == "POST":
            return await self._share_contact(req_body)

        if path == "/api/contacts/export" and method in ("GET", "POST"):
            return await self._export_contact(req_body)

        if path == "/api/contacts/import" and method == "POST":
            return await self._import_contact(req_body)

        if method == "GET":
            nodes = self.ctx.bridge.node_registry.list_client_contacts()
            return 200, {"status": "ok", "data": nodes, "count": len(nodes)}

        if method == "POST":
            return await self._create_or_update_contact(req_body)

        path_pubkey = ""
        if path.startswith("/api/contacts/"):
            sub = path.removeprefix("/api/contacts/").strip()
            if sub and "/" not in sub and sub not in ("sync", "share", "export", "import", "discovered", "accept"):
                path_pubkey = sub

        if method == "DELETE":
            return await self._delete_contact(req_body, path_pubkey=path_pubkey)

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido para /api/contacts", "method_not_allowed")

    async def _sync_contacts(self) -> tuple[int, dict[str, Any]]:
        """Sincroniza los contactos almacenados en el firmware con el registro del bridge."""
        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        imported_count = 0
        if ser and hasattr(ser, "sync_all_contacts"):
            try:
                imported = await ser.sync_all_contacts()
                now_cur = time.time()
                for c in imported:
                    pk = str(c.get("public_key", "")).strip()
                    if pk:
                        last_adv = c.get("last_advert")
                        valid_last_seen = None
                        if isinstance(last_adv, (int, float)) and 1_000_000_000 < last_adv <= now_cur:
                            valid_last_seen = float(last_adv)
                        self.ctx.bridge.node_registry.add_or_update(
                            pk,
                            NodeContactUpdate(
                                name=c.get("name"),
                                alias=c.get("alias"),
                                role=c.get("role", "CLIENT"),
                                last_seen=valid_last_seen,
                                last_advert=float(last_adv) if isinstance(last_adv, (int, float)) and last_adv > 0 else None,
                                latitude=c.get("latitude") if c.get("latitude") is not None else (c.get("lat") if c.get("lat") is not None else c.get("adv_lat")),
                                longitude=c.get("longitude") if c.get("longitude") is not None else (c.get("lon") if c.get("lon") is not None else c.get("adv_lon")),
                            ),
                        )
                        imported_count += 1
                await self._save_registry_async()
            except Exception as e:
                logging.warning(f"Error sincronizando contactos con el nodo: {e}")

        nodes = self.ctx.bridge.node_registry.list_client_contacts()
        return 200, {"status": "ok", "imported": imported_count, "data": nodes, "count": len(nodes)}

    async def _share_contact(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Comparte un contacto con los nodos de la malla."""
        pubkey = str(req_body.get("public_key", req_body.get("key", ""))).strip()
        if not pubkey:
            return problem_details(400, "Bad Request", "Se requiere 'public_key'", "missing_public_key")

        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        res = await ser.share_contact(pubkey) if ser and hasattr(ser, "share_contact") else None
        self.ctx.log_system_event("INFO", f"Contacto compartido con la malla: {pubkey}", source="contacts")
        return 200, {"status": "ok", "result": res}

    async def _export_contact(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Exporta los datos de un contacto en URI oficial de MeshCore (meshcore://contact/add?name=...&public_key=...&type=...)."""
        pubkey = str(req_body.get("public_key") or req_body.get("pubkey") or req_body.get("key") or "").strip()
        if not pubkey:
            return problem_details(400, "Bad Request", "Se requiere 'public_key' para exportar", "missing_public_key")

        name = ""
        role = "CLIENT"

        # 1. Buscar en el registro de nodos
        node = None
        if hasattr(self.ctx.bridge, "node_registry"):
            reg = self.ctx.bridge.node_registry
            if hasattr(reg, "get"):
                node = reg.get(pubkey)
            elif hasattr(reg, "get_by_key_or_prefix"):
                node = reg.get_by_key_or_prefix(pubkey)
            if not node and hasattr(reg, "is_local_key") and reg.is_local_key(pubkey):
                local_ident = getattr(reg, "local_identity", None)
                if local_ident:
                    name = getattr(local_ident, "name", "") or getattr(local_ident, "node_name", "")
                role = "CLIENT"

        if node:
            name = str(getattr(node, "name", "") or getattr(node, "alias", "") or "").strip()
            role = str(getattr(node, "role", "CLIENT") or "CLIENT").strip().upper()

        if not name:
            name = str(req_body.get("name") or req_body.get("alias") or f"Node_{pubkey[:6]}").strip()

        # Mapeo numérico oficial MeshCore FirmwareAdvertType:
        # 1: CHAT / CLIENT, 2: REPEATER, 3: ROOM, 4: SENSOR
        type_map = {
            "CLIENT": 1,
            "CHAT": 1,
            "USER": 1,
            "REPEATER": 2,
            "ROUTER": 2,
            "ROOM": 3,
            "SENSOR": 4,
        }
        type_num = type_map.get(role, 1)

        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        res = await ser.export_contact(pubkey) if ser and hasattr(ser, "export_contact") else None

        encoded_name = urllib.parse.quote(name)
        canonical_uri = f"meshcore://contact/add?name={encoded_name}&public_key={pubkey}&type={type_num}"
        message_tag = f"<{pubkey}:{type_num}:{name}>"

        contact_data = {
            "type": "contact",
            "name": name,
            "public_key": pubkey,
            "role": role,
            "contact_type": type_num,
            "uri": canonical_uri,
            "message_tag": message_tag,
            "raw_hex": res,
        }

        return 200, {
            "status": "ok",
            "uri": canonical_uri,
            "qr_uri": canonical_uri,
            "message_tag": message_tag,
            "data": contact_data,
            "result": res,
        }

    async def _import_contact(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Importa contactos desde URI canónica (meshcore://contact/add?...), formato de mensaje (<pubkey:type:name>), JSON estructurado o volcado hexadecimal."""
        raw_payload = str(req_body.get("data") or req_body.get("payload") or req_body.get("uri") or "").strip()
        contacts_to_add: list[dict[str, Any]] = []

        # 1. Si req_body ya tiene campos directos de contacto
        if "public_key" in req_body or "pubkey" in req_body or "key" in req_body:
            contacts_to_add.append(req_body)
        elif isinstance(req_body.get("contacts"), list):
            contacts_to_add.extend(c for c in req_body["contacts"] if isinstance(c, dict))

        # 2. Parseo de string si viene en raw_payload
        if raw_payload and not contacts_to_add:
            type_map_rev = {"1": "CLIENT", "2": "REPEATER", "3": "ROOM", "4": "SENSOR"}

            # Caso 2a: Formato de mensaje MeshCore <pubkey:type:name>
            m_single = re.match(r"^<([0-9a-fA-F]{64}):([0-9]+):([^>]+)>$", raw_payload)
            if m_single:
                pk = m_single.group(1).lower()
                raw_type = m_single.group(2)
                nm = m_single.group(3).strip()
                rl = type_map_rev.get(raw_type, "CLIENT")
                contacts_to_add.append({"public_key": pk, "name": nm, "alias": nm, "role": rl})
            else:
                matches = re.findall(r"<([0-9a-fA-F]{64}):([0-9]+):([^>]+)>", raw_payload)
                if matches:
                    for m_pk, m_type, m_name in matches:
                        rl = type_map_rev.get(m_type, "CLIENT")
                        contacts_to_add.append({"public_key": m_pk.lower(), "name": m_name.strip(), "alias": m_name.strip(), "role": rl})

            # Caso 2b: URI meshcore://contact o meshcore://node
            if not contacts_to_add and raw_payload.startswith("meshcore://"):
                try:
                    parsed_uri = urllib.parse.urlparse(raw_payload)
                    # Si es canal, alertar
                    if "channel" in parsed_uri.netloc.lower() or "channel" in parsed_uri.path.lower():
                        return problem_details(400, "Bad Request", "El contenido corresponde a un canal, no a un contacto. Usa la sección Canales para importarlo.", "channel_payload_in_contacts")

                    qs = urllib.parse.parse_qs(parsed_uri.query)
                    pk = (qs.get("public_key") or qs.get("pubkey") or qs.get("key") or [""])[0].strip()
                    nm = (qs.get("name") or qs.get("alias") or [""])[0].strip()
                    raw_type = (qs.get("type") or [""])[0].strip()
                    rl = (qs.get("role") or [""])[0].strip().upper()
                    if not rl and raw_type:
                        rl = type_map_rev.get(raw_type, "CLIENT")
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
                        contacts_to_add.append(c_entry)
                except Exception as e:
                    logging.warning(f"Error parseando URI meshcore: {e}")

            # Caso 2b: JSON string
            elif raw_payload.startswith("{") or raw_payload.startswith("["):
                try:
                    loaded = json.loads(raw_payload)
                    if isinstance(loaded, dict):
                        if "type" in loaded and loaded.get("type") == "channel":
                            return problem_details(400, "Bad Request", "El contenido corresponde a un canal, no a un contacto", "channel_payload_in_contacts")
                        contacts_to_add.append(loaded)
                    elif isinstance(loaded, list):
                        contacts_to_add.extend(c for c in loaded if isinstance(c, dict))
                except Exception as e:
                    logging.warning(f"Error deserializando JSON de contacto: {e}")

            # Caso 2c: Volcado binario hexadecimal (legado)
            if not contacts_to_add:
                try:
                    bin_data = bytes.fromhex(raw_payload)
                    # Intentar si el binario decodifica como texto UTF-8 JSON o URI
                    try:
                        utf8_text = bin_data.decode("utf-8").strip()
                        if utf8_text.startswith("{") or utf8_text.startswith("["):
                            loaded = json.loads(utf8_text)
                            if isinstance(loaded, dict):
                                contacts_to_add.append(loaded)
                            elif isinstance(loaded, list):
                                contacts_to_add.extend(c for c in loaded if isinstance(c, dict))
                        elif utf8_text.startswith("meshcore://"):
                            parsed_uri = urllib.parse.urlparse(utf8_text)
                            if "channel" in parsed_uri.netloc.lower() or "channel" in parsed_uri.path.lower():
                                return problem_details(400, "Bad Request", "El contenido corresponde a un canal, no a un contacto", "channel_payload_in_contacts")
                            qs = urllib.parse.parse_qs(parsed_uri.query)
                            pk = (qs.get("public_key") or qs.get("pubkey") or qs.get("key") or [""])[0].strip()
                            nm = (qs.get("name") or qs.get("alias") or [""])[0].strip()
                            raw_type = (qs.get("type") or [""])[0].strip()
                            rl = (qs.get("role") or [""])[0].strip().upper()
                            if not rl and raw_type:
                                type_map_rev = {"1": "CLIENT", "2": "REPEATER", "3": "ROOM", "4": "SENSOR"}
                                rl = type_map_rev.get(raw_type, "CLIENT")
                            if not rl:
                                rl = "CLIENT"
                            if pk:
                                contacts_to_add.append({"public_key": pk, "name": nm, "alias": nm, "role": rl})
                    except Exception:
                        pass

                    # Si es binario crudo del firmware
                    if not contacts_to_add:
                        ser = getattr(self.ctx.bridge, "serial_adapter", None)
                        res = await ser.import_contact(bin_data) if ser and hasattr(ser, "import_contact") else None
                        self.ctx.log_system_event("INFO", "Contacto binario importado hacia el firmware", source="contacts")
                        return 200, {"status": "ok", "result": res}
                except ValueError:
                    return problem_details(400, "Bad Request", "Formato de datos no reconocido (no es URI, JSON ni hexadecimal válido)", "invalid_hex_data")

        if not contacts_to_add:
            return problem_details(400, "Bad Request", "No se detectaron contactos válidos para importar", "no_valid_contacts")

        imported_records: list[dict[str, Any]] = []
        ser = getattr(self.ctx.bridge, "serial_adapter", None)

        for c_dict in contacts_to_add:
            pubkey = str(c_dict.get("public_key") or c_dict.get("pubkey") or c_dict.get("key") or "").strip()
            if not pubkey:
                continue

            # Regla 1.1: Prohibido agregar transceptor local a contactos
            if hasattr(self.ctx.bridge, "node_registry") and self.ctx.bridge.node_registry.is_local_key(pubkey):
                continue

            name = str(c_dict.get("name") or "").strip()
            alias = str(c_dict.get("alias") or name or f"Node_{pubkey[:6]}").strip()
            role = str(c_dict.get("role") or "CLIENT").strip().upper()

            # Regla 1.1: Prohibido agregar repetidores a libreta de contactos
            if role in ("REPEATER", "ROUTER"):
                continue

            is_fav = c_dict.get("is_favorite")
            is_favorite_val = bool(is_fav) if is_fav is not None else None

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

            contact = self.ctx.bridge.node_registry.add_or_update(
                pubkey,
                NodeContactUpdate(
                    name=name or alias,
                    alias=alias,
                    role=role,
                    is_favorite=is_favorite_val,
                    latitude=lat_val,
                    longitude=lon_val,
                    adv_lat=lat_val,
                    adv_lon=lon_val,
                ),
            )
            imported_records.append(contact.to_dict())

            # Enviar al transceptor serial si está activo
            if ser and hasattr(ser, "add_contact"):
                try:
                    await ser.add_contact({"public_key": pubkey, "name": name or alias, "role": role})
                except Exception as e:
                    logging.debug(f"Error sincronizando contacto importado con serial: {e}")

        if imported_records:
            await self._save_registry_async()

            if self.ctx.broadcast_ws:
                self.ctx.broadcast_ws({"type": "contacts_updated", "data": self.ctx.bridge.node_registry.list_nodes()})

            self.ctx.log_system_event("INFO", f"Se importaron {len(imported_records)} contactos exitosamente", source="contacts")
            return 201, {"status": "ok", "imported": len(imported_records), "data": imported_records}

        return problem_details(400, "Bad Request", "Ningún contacto válido pudo ser agregado (verifique que no sean nodos repetidores o la estación base local)", "import_rejected")

    async def _create_or_update_contact(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Crea o actualiza un contacto en la libreta del bridge."""
        pubkey = str(req_body.get("public_key", req_body.get("key", ""))).strip()
        name = str(req_body.get("name", "")).strip()
        alias = str(req_body.get("alias", "")).strip()
        role = str(req_body.get("role", "CLIENT")).strip()
        if not pubkey:
            return problem_details(400, "Bad Request", "Se requiere 'public_key'", "missing_public_key")

        if hasattr(self.ctx.bridge, "node_registry") and self.ctx.bridge.node_registry.is_local_key(pubkey):
            return problem_details(400, "Bad Request", "No se permite agregar la estación base local a la libreta de contactos", "cannot_add_local_station")

        if role.upper() in ("REPEATER", "ROUTER"):
            return problem_details(400, "Bad Request", "Los repetidores son nodos de infraestructura y no pueden agregarse a contactos", "repeater_contact_forbidden")

        is_new_contact = hasattr(self.ctx.bridge, "node_registry") and self.ctx.bridge.node_registry.get_node(pubkey) is None
        is_fav = req_body.get("is_favorite")
        is_favorite_val = bool(is_fav) if is_fav is not None else None

        raw_lat = req_body.get("latitude") if req_body.get("latitude") is not None else (req_body.get("lat") if req_body.get("lat") is not None else req_body.get("adv_lat"))
        raw_lon = req_body.get("longitude") if req_body.get("longitude") is not None else (req_body.get("lon") if req_body.get("lon") is not None else req_body.get("adv_lon"))
        lat_val = None
        lon_val = None
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

        contact = self.ctx.bridge.node_registry.add_or_update(
            pubkey,
            NodeContactUpdate(
                name=name or f"Node_{pubkey[:6]}",
                alias=alias,
                role=role,
                is_favorite=is_favorite_val,
                latitude=lat_val,
                longitude=lon_val,
                adv_lat=lat_val,
                adv_lon=lon_val,
            ),
        )
        await self._save_registry_async()

        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        if ser and hasattr(ser, "add_contact"):
            try:
                await ser.add_contact({"public_key": pubkey, "name": name or alias, "role": role})
            except Exception as e:
                logging.debug(f"Error enviando contacto al transceptor serial: {e}")

        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({"type": "contacts_updated", "data": self.ctx.bridge.node_registry.list_nodes()})

        self.ctx.log_system_event("INFO", f"Contacto guardado: {pubkey} ({alias or name})", source="contacts")
        status_code = 201 if is_new_contact else 200
        return status_code, {"status": "ok", "data": contact.to_dict()}

    async def _delete_contact(self, req_body: dict[str, Any], path_pubkey: str = "") -> tuple[int, dict[str, Any]]:
        """Elimina un contacto de la libreta."""
        pubkey = str(req_body.get("public_key", req_body.get("key", path_pubkey))).strip().lower()

        if hasattr(self.ctx.bridge, "node_registry") and self.ctx.bridge.node_registry.is_local_key(pubkey):
            return problem_details(400, "Bad Request", "No se permite eliminar la estación base local", "cannot_delete_local_station")

        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        if ser and hasattr(ser, "remove_contact"):
            try:
                await ser.remove_contact(pubkey)
            except Exception as e:
                logging.debug(f"Error eliminando contacto del transceptor serial: {e}")

        if pubkey and self.ctx.bridge.node_registry.remove_node(pubkey):
            await self._save_registry_async()
            if self.ctx.broadcast_ws:
                self.ctx.broadcast_ws({"type": "contacts_updated", "data": self.ctx.bridge.node_registry.list_nodes()})
            return 204, {}

        return problem_details(404, "Not Found", "Contacto no encontrado", "contact_not_found")
