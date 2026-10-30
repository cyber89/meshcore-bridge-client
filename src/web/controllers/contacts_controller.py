"""
Contacts REST controller.
Handles /api/contacts, /api/contacts/sync, /api/contacts/share, export, and import.
Delegates domain logic, hardware synchronization, and persistence to ContactService.
"""

from __future__ import annotations

import re
from typing import Any

from src.application.contacts import ContactOperationResult, ContactService
from src.web.controllers.base import (
    ApiContext,
    BaseController,
    problem_details,
)


class ContactsController(BaseController):
    """Controlador REST para la libreta de contactos (clientes LoRa) y sincronización con el firmware."""

    def __init__(self, ctx: ApiContext) -> None:
        super().__init__(ctx)
        cs = getattr(ctx.bridge, "contact_service", None)
        self.contact_service: ContactService = (
            cs if isinstance(cs, ContactService)
            else ContactService(
                node_registry=getattr(ctx.bridge, "node_registry", None),
                serial_adapter_provider=lambda: getattr(self.ctx.bridge, "serial_adapter", None),
                database=getattr(ctx.bridge, "database", None),
                log_system_event=ctx.log_system_event,
            )
        )

    def _contact_validation(self, pubkey: str, name: str, role: str) -> tuple[int, dict[str, Any]] | None:
        """Valida un contacto usando ContactService y devuelve un problem_details si es inválido."""
        val: ContactOperationResult = self.contact_service.validate_contact(pubkey, name, role)
        if not val.success:
            title = "Unprocessable Entity" if val.http_code == 422 else "Bad Request"
            return problem_details(val.http_code, title, val.error or "Error de validación", val.error_code or "validation_error")
        return None

    async def _save_registry_async(self) -> bool:
        """Persiste el registro de nodos delegando a ContactService."""
        return await self.contact_service._save_registry_async()

    async def handle_contacts_route(
        self,
        path: str,
        method: str,
        req_body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        """Maneja todas las rutas asociadas a /api/contacts."""
        resource_methods = {
            "/api/contacts": {"GET", "POST", "DELETE"},
            "/api/contacts/sync": {"POST"},
            "/api/contacts/share": {"POST"},
            "/api/contacts/export": {"GET", "POST"},
            "/api/contacts/import": {"POST"},
        }
        path_pubkey = ""
        if path not in resource_methods:
            match = re.fullmatch(r"/api/contacts/([0-9a-fA-F]{64})", path)
            if not match:
                return problem_details(404, "Not Found", "Ruta de contactos desconocida", "route_not_found")
            path_pubkey = match.group(1).lower()
            if method != "DELETE":
                return problem_details(405, "Method Not Allowed", "Contacto individual admite DELETE", "method_not_allowed")
        elif method not in resource_methods[path]:
            return problem_details(405, "Method Not Allowed", "Método no permitido para este recurso", "method_not_allowed")

        if path == "/api/contacts/sync" and method == "POST":
            return await self._sync_contacts()

        if path == "/api/contacts/share" and method == "POST":
            return await self._share_contact(req_body)

        if path == "/api/contacts/export" and method in ("GET", "POST"):
            return await self._export_contact(req_body)

        if path == "/api/contacts/import" and method == "POST":
            return await self._import_contact(req_body)

        if method == "GET":
            nodes = self.contact_service.list_contacts()
            return 200, {"status": "ok", "data": nodes, "count": len(nodes)}

        if method == "POST":
            return await self._create_or_update_contact(req_body)

        if method == "DELETE":
            return await self._delete_contact(req_body, path_pubkey=path_pubkey)

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido para /api/contacts", "method_not_allowed")

    async def _sync_contacts(self) -> tuple[int, dict[str, Any]]:
        """Sincroniza los contactos almacenados en el firmware con el registro del bridge."""
        res = await self.contact_service.sync_from_radio()
        if not res.success:
            return problem_details(
                res.http_code,
                "Service Unavailable",
                res.error or "Fallo sincronizando contactos con el nodo",
                res.error_code or "sync_failed",
            )

        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({"type": "contacts_updated", "data": self.ctx.bridge.node_registry.list_nodes()})

        nodes = self.contact_service.list_contacts()
        return 200, {"status": "ok", "imported": res.data.get("imported", 0), "data": nodes, "count": len(nodes)}

    async def _share_contact(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Comparte un contacto con los nodos de la malla."""
        pubkey = str(req_body.get("public_key", req_body.get("key", ""))).strip()
        if not pubkey:
            return problem_details(400, "Bad Request", "Se requiere 'public_key'", "missing_public_key")

        res = await self.contact_service.share_contact(pubkey)
        if not res.success:
            return problem_details(
                res.http_code,
                "Bad Request" if res.http_code == 400 else "Service Unavailable",
                res.error or "Error al compartir contacto",
                res.error_code or "share_failed",
            )
        return 200, {"status": "ok", "result": res.data}

    async def _export_contact(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Exporta los datos de un contacto en formato canónico de MeshCore."""
        pubkey = str(req_body.get("public_key") or req_body.get("pubkey") or req_body.get("key") or "").strip()
        if not pubkey:
            return problem_details(400, "Bad Request", "Se requiere 'public_key' para exportar", "missing_public_key")

        res = await self.contact_service.export_contact(pubkey)
        if not res.success:
            title = "Unprocessable Entity" if res.http_code == 422 else "Bad Request"
            return problem_details(res.http_code, title, res.error or "Error al exportar contacto", res.error_code or "export_failed")

        return 200, res.data

    async def _import_contact(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Importa contactos desde URI, tags, JSON estructurado o volcado hexadecimal."""
        res = await self.contact_service.import_contact_payload(req_body, sync_to_hardware=True)
        if not res.success:
            title = (
                "Unprocessable Entity"
                if res.http_code == 422
                else ("Service Unavailable" if res.http_code >= 500 else "Bad Request")
            )
            return problem_details(res.http_code, title, res.error or "Error al importar contactos", res.error_code or "import_failed")

        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({"type": "contacts_updated", "data": self.ctx.bridge.node_registry.list_nodes()})

        return res.http_code, res.data

    async def _create_or_update_contact(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Crea o actualiza un contacto en la libreta del bridge."""
        pubkey = str(req_body.get("public_key", req_body.get("key", ""))).strip()
        name = str(req_body.get("name", "")).strip()
        alias = str(req_body.get("alias", "")).strip()
        role = str(req_body.get("role", "CLIENT")).strip()
        if not pubkey:
            return problem_details(400, "Bad Request", "Se requiere 'public_key'", "missing_public_key")

        from src.shared_utils import to_bool
        is_fav = req_body.get("is_favorite")
        is_favorite_val = to_bool(is_fav) if is_fav is not None else None

        raw_lat = req_body.get("latitude") if req_body.get("latitude") is not None else (req_body.get("lat") if req_body.get("lat") is not None else req_body.get("adv_lat"))
        raw_lon = req_body.get("longitude") if req_body.get("longitude") is not None else (req_body.get("lon") if req_body.get("lon") is not None else req_body.get("adv_lon"))
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

        res = await self.contact_service.create_or_update_contact(
            pubkey=pubkey,
            name=name,
            alias=alias or None,
            role=role,
            is_favorite=is_favorite_val,
            latitude=lat_val,
            longitude=lon_val,
            sync_to_hardware=True,
        )
        if not res.success:
            title = (
                "Unprocessable Entity"
                if res.http_code == 422
                else ("Service Unavailable" if res.http_code >= 500 else "Bad Request")
            )
            return problem_details(res.http_code, title, res.error or "Error al crear o actualizar contacto", res.error_code or "contact_error")

        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({"type": "contacts_updated", "data": self.ctx.bridge.node_registry.list_nodes()})

        return res.http_code, {"status": "ok", "data": res.data}

    async def _delete_contact(self, req_body: dict[str, Any], path_pubkey: str = "") -> tuple[int, dict[str, Any]]:
        """Elimina un contacto de la libreta."""
        raw_key = path_pubkey or req_body.get("public_key") or req_body.get("key") or ""
        pubkey = str(raw_key).strip().lower()
        if not pubkey:
            return problem_details(400, "Bad Request", "Se requiere 'public_key'", "missing_public_key")

        res = await self.contact_service.delete_contact(pubkey=pubkey, sync_to_hardware=True)
        if not res.success:
            title = (
                "Not Found"
                if res.http_code == 404
                else ("Unprocessable Entity" if res.http_code == 422 else ("Bad Request" if res.http_code == 400 else "Service Unavailable"))
            )
            return problem_details(res.http_code, title, res.error or "Error al eliminar contacto", res.error_code or "contact_error")

        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({"type": "contacts_updated", "data": self.ctx.bridge.node_registry.list_nodes()})

        return res.http_code, {}

    # Compatibilidad estática hacia métodos auxiliares
    @staticmethod
    def _parse_contacts_from_tags(raw_payload: str) -> list[dict[str, Any]]:
        return ContactService.parse_contacts_from_tags(raw_payload)

    @staticmethod
    def _parse_contacts_from_uri(raw_payload: str) -> tuple[list[dict[str, Any]], tuple[int, dict[str, Any]] | None]:
        contacts, err = ContactService.parse_contacts_from_uri(raw_payload)
        if err:
            return [], problem_details(err.http_code, "Bad Request", err.error or "Error", err.error_code or "error")
        return contacts, None

    @staticmethod
    def _parse_contacts_from_json(raw_payload: str) -> tuple[list[dict[str, Any]], tuple[int, dict[str, Any]] | None]:
        contacts, err = ContactService.parse_contacts_from_json(raw_payload)
        if err:
            return [], problem_details(err.http_code, "Bad Request", err.error or "Error", err.error_code or "error")
        return contacts, None

    @classmethod
    def _parse_contacts_from_hex(cls, raw_payload: str) -> tuple[list[dict[str, Any]], bytes | None, tuple[int, dict[str, Any]] | None]:
        contacts, bin_data, err = ContactService.parse_contacts_from_hex(raw_payload)
        if err:
            return [], None, problem_details(err.http_code, "Bad Request", err.error or "Error", err.error_code or "error")
        return contacts, bin_data, None
