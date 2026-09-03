"""
Channels REST controller.
Handles /api/channels and /api/channels/sync.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.web.controllers.base import ApiContext, BaseController, problem_details


class ChannelsController(BaseController):
    """Controlador para configuración y sincronización de canales LoRa."""

    def __init__(self, ctx: ApiContext, channels_file: str = "data/channels.json") -> None:
        super().__init__(ctx)
        self.channels_file = channels_file
        self.channels: dict[int, dict[str, Any]] = {}
        self._load_channels()

    def _load_channels(self) -> None:
        """Carga la tabla de canales desde disco o inicializa el canal público."""
        if os.path.exists(self.channels_file):
            try:
                with open(self.channels_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.channels = {int(c.get("index", i)): c for i, c in enumerate(data)}
                    elif isinstance(data, dict):
                        self.channels = {int(k): v for k, v in data.items() if str(k).isdigit()}
            except Exception as e:
                logging.warning(f"Error cargando canales desde {self.channels_file}: {e}")

        if 0 not in self.channels:
            self.channels[0] = {
                "index": 0,
                "name": "General",
                "psk": "",
                "is_public": True,
            }

    def _save_channels(self) -> None:
        """Persiste la tabla de canales a disco de forma atómica."""
        os.makedirs(os.path.dirname(self.channels_file) or ".", exist_ok=True)
        try:
            tmp_path = f"{self.channels_file}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(list(self.channels.values()), f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.channels_file)
        except Exception as e:
            logging.error(f"Error persistiendo canales en {self.channels_file}: {e}")

    async def handle_channels_route(
        self,
        path: str,
        method: str,
        req_body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        """Enruta solicitudes hacia /api/channels y /api/channels/sync."""
        if path == "/api/channels/sync" and method in ("POST", "GET"):
            return await self._sync_channels()

        if method == "GET":
            return await self._get_channels()

        if method == "POST":
            return await self._create_or_update_channel(req_body)

        if method == "DELETE":
            return await self._delete_channel(req_body)

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido para /api/channels", "method_not_allowed")

    async def _sync_channels(self) -> tuple[int, dict[str, Any]]:
        """Sincroniza los canales desde el hardware serial."""
        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        if ser and hasattr(ser, "get_channels"):
            try:
                node_channels = await ser.get_channels()
                if node_channels:
                    for ch in node_channels:
                        idx = int(ch.get("index", 0))
                        self.channels[idx] = ch
                    self._save_channels()
            except Exception as e:
                logging.debug(f"Fallo sincronizando canales del nodo serial: {e}")

        channels_list = list(self.channels.values())
        channels_list.sort(key=lambda c: int(c.get("index", 0)))
        return 200, {"status": "ok", "data": channels_list, "count": len(channels_list)}

    async def _get_channels(self) -> tuple[int, dict[str, Any]]:
        """Devuelve los canales configurados."""
        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        if ser and hasattr(ser, "get_channels"):
            try:
                node_channels = await ser.get_channels()
                if node_channels:
                    for ch in node_channels:
                        idx = int(ch.get("index", 0))
                        self.channels[idx] = ch
                    self._save_channels()
            except Exception as e:
                logging.debug(f"Fallo sincronizando canales del nodo serial: {e}")

        channels_list = list(self.channels.values())
        channels_list.sort(key=lambda c: int(c.get("index", 0)))
        return 200, {"status": "ok", "data": channels_list, "count": len(channels_list)}

    async def _create_or_update_channel(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Crea o actualiza un canal en el rango 0..7."""
        try:
            idx = int(req_body.get("index", 1))
        except (ValueError, TypeError):
            return problem_details(400, "Bad Request", "Índice de canal inválido", "invalid_channel_index")

        if idx < 0 or idx > 7:
            return problem_details(400, "Bad Request", "El índice de canal debe estar entre 0 y 7", "channel_index_out_of_bounds")

        name = str(req_body.get("name", f"Canal {idx}")).strip()
        psk = str(req_body.get("psk", "")).strip()
        self.channels[idx] = {"index": idx, "name": name, "psk": psk, "is_public": (idx == 0)}
        self._save_channels()

        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        if ser and hasattr(ser, "set_channel"):
            try:
                await ser.set_channel(idx, name, psk)
            except Exception as e:
                logging.debug(f"Error despachando canal al transceptor serial: {e}")

        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({"type": "channels_updated", "data": list(self.channels.values())})

        self.ctx.log_system_event("INFO", f"Canal {idx} configurado: {name}", source="channels")
        return 200, {"status": "ok", "data": self.channels[idx]}

    async def _delete_channel(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Elimina un canal secundario (1..7)."""
        try:
            idx = int(req_body.get("index", 0))
        except (ValueError, TypeError):
            return problem_details(400, "Bad Request", "Índice de canal inválido", "invalid_channel_index")

        if idx == 0:
            return problem_details(400, "Bad Request", "No se puede eliminar el canal público 0", "cannot_delete_public_channel")

        if idx in self.channels:
            del self.channels[idx]
            self._save_channels()
            if self.ctx.broadcast_ws:
                self.ctx.broadcast_ws({"type": "channels_updated", "data": list(self.channels.values())})
            return 200, {"status": "ok", "message": f"Canal {idx} eliminado"}

        return problem_details(404, "Not Found", f"Canal {idx} no encontrado", "channel_not_found")
