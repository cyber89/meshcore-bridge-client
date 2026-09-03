"""
Contacts REST controller.
Handles /api/contacts, /api/contacts/sync, /api/contacts/share, export, and import.
"""

from __future__ import annotations

import logging
from typing import Any

from src.contact_manager import NodeContactUpdate
from src.web.controllers.base import ApiContext, BaseController, problem_details


class ContactsController(BaseController):
    """Controlador para libreta de contactos (clientes LoRa) y sincronización con el firmware."""

    async def handle_contacts_route(
        self,
        path: str,
        method: str,
        req_body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        """Maneja todas las rutas asociadas a /api/contacts."""
        if path == "/api/contacts/sync" and method in ("POST", "GET"):
            return await self._sync_contacts()

        if path == "/api/contacts/share" and method == "POST":
            return await self._share_contact(req_body)

        if path == "/api/contacts/export" and method in ("GET", "POST"):
            return await self._export_contact(req_body)

        if path == "/api/contacts/import" and method == "POST":
            return await self._import_contact(req_body)

        if method == "GET":
            nodes = self.ctx.bridge.node_registry.list_nodes()
            return 200, {"status": "ok", "data": nodes, "count": len(nodes)}

        if method == "POST":
            return await self._create_or_update_contact(req_body)

        if method == "DELETE":
            return await self._delete_contact(req_body)

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido para /api/contacts", "method_not_allowed")

    async def _sync_contacts(self) -> tuple[int, dict[str, Any]]:
        """Sincroniza los contactos almacenados en el firmware con el registro del bridge."""
        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        imported_count = 0
        if ser and hasattr(ser, "sync_all_contacts"):
            try:
                imported = await ser.sync_all_contacts()
                for c in imported:
                    pk = str(c.get("public_key", "")).strip()
                    if pk:
                        self.ctx.bridge.node_registry.add_or_update(
                            pk,
                            NodeContactUpdate(
                                name=c.get("name"),
                                alias=c.get("alias"),
                                role=c.get("role", "CLIENT"),
                            ),
                        )
                        imported_count += 1
                if hasattr(self.ctx.bridge.node_registry, "save_to_file"):
                    self.ctx.bridge.node_registry.save_to_file()
            except Exception as e:
                logging.warning(f"Error sincronizando contactos con el nodo: {e}")

        nodes = self.ctx.bridge.node_registry.list_nodes()
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
        """Exporta los datos binarios de un contacto para respaldo."""
        pubkey = str(req_body.get("public_key", req_body.get("key", ""))).strip()
        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        res = await ser.export_contact(pubkey) if ser and hasattr(ser, "export_contact") else None
        return 200, {"status": "ok", "result": res}

    async def _import_contact(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Importa un contacto desde un volcado hexadecimal."""
        hex_data = str(req_body.get("data", "")).strip()
        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        try:
            bin_data = bytes.fromhex(hex_data) if hex_data else b""
        except ValueError:
            return problem_details(400, "Bad Request", "Formato hexadecimal inválido en 'data'", "invalid_hex_data")

        res = await ser.import_contact(bin_data) if ser and hasattr(ser, "import_contact") else None
        self.ctx.log_system_event("INFO", "Contacto importado vía API", source="contacts")
        return 200, {"status": "ok", "result": res}

    async def _create_or_update_contact(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Crea o actualiza un contacto en la libreta del bridge."""
        pubkey = str(req_body.get("public_key", req_body.get("key", ""))).strip()
        name = str(req_body.get("name", "")).strip()
        alias = str(req_body.get("alias", "")).strip()
        role = str(req_body.get("role", "CLIENT")).strip()
        if not pubkey:
            return problem_details(400, "Bad Request", "Se requiere 'public_key'", "missing_public_key")

        contact = self.ctx.bridge.node_registry.add_or_update(
            pubkey,
            NodeContactUpdate(name=name or f"Node_{pubkey[:6]}", alias=alias, role=role),
        )
        if hasattr(self.ctx.bridge.node_registry, "save_to_file"):
            self.ctx.bridge.node_registry.save_to_file()

        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        if ser and hasattr(ser, "add_contact"):
            try:
                await ser.add_contact({"public_key": pubkey, "name": name or alias, "role": role})
            except Exception as e:
                logging.debug(f"Error enviando contacto al transceptor serial: {e}")

        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({"type": "contacts_updated", "data": self.ctx.bridge.node_registry.list_nodes()})

        self.ctx.log_system_event("INFO", f"Contacto guardado: {pubkey} ({alias or name})", source="contacts")
        return 200, {"status": "ok", "data": contact.to_dict()}

    async def _delete_contact(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Elimina un contacto de la libreta."""
        pubkey = str(req_body.get("public_key", req_body.get("key", ""))).strip().lower()
        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        if ser and hasattr(ser, "remove_contact"):
            try:
                await ser.remove_contact(pubkey)
            except Exception as e:
                logging.debug(f"Error eliminando contacto del transceptor serial: {e}")

        if pubkey and pubkey in self.ctx.bridge.node_registry._nodes_by_key:
            del self.ctx.bridge.node_registry._nodes_by_key[pubkey]
            if hasattr(self.ctx.bridge.node_registry, "save_to_file"):
                self.ctx.bridge.node_registry.save_to_file()
            if self.ctx.broadcast_ws:
                self.ctx.broadcast_ws({"type": "contacts_updated", "data": self.ctx.bridge.node_registry.list_nodes()})
            return 200, {"status": "ok", "message": f"Contacto {pubkey} eliminado"}

        return problem_details(404, "Not Found", "Contacto no encontrado", "contact_not_found")
