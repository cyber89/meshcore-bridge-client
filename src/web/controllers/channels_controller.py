"""
Channels REST controller.
Handles /api/channels and /api/channels/sync.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.parse
from typing import Any

from src.application.channels import ChannelService
from src.shared_utils import derive_channel_secret
from src.web.controllers.base import (
    ApiContext,
    BaseController,
    firmware_name_valid,
    problem_details,
)


class ChannelsController(BaseController):
    """Controlador para configuración y sincronización de canales LoRa."""

    def __init__(self, ctx: ApiContext, channels_file: str | None = None) -> None:
        super().__init__(ctx)
        bridge_path = getattr(ctx.bridge, "channels_storage_path", None)
        if not isinstance(bridge_path, (str, os.PathLike)):
            bridge_path = None
        self.channels_file: str = str(
            channels_file
            or bridge_path
            or os.getenv("CHANNELS_STORAGE_PATH")
            or os.getenv("CHANNELS_JSON_PATH")
            or "data/channels.json"
        )
        self.database = getattr(ctx.bridge, "database", None)
        cs = getattr(ctx.bridge, "channel_service", None)
        self.channel_service: ChannelService = (
            cs if isinstance(cs, ChannelService)
            else ChannelService(
                channels_file=self.channels_file,
                database=self.database,
                serial_adapter_provider=lambda: getattr(self.ctx.bridge, "serial_adapter", None),
            )
        )

    @property
    def channels(self) -> dict[int, dict[str, Any]]:
        return self.channel_service.channels

    @channels.setter
    def channels(self, val: dict[int, dict[str, Any]]) -> None:
        self.channel_service._channels = dict(val)

    @property
    def _deleted_channels(self) -> set[int]:
        return self.channel_service._deleted_channels

    @property
    def _dirty(self) -> bool:
        return self.channel_service._dirty

    @_dirty.setter
    def _dirty(self, val: bool) -> None:
        self.channel_service._dirty = val

    @property
    def _mutation_lock(self) -> asyncio.Lock:
        return self.channel_service._mutation_lock

    @property
    def _write_task(self) -> asyncio.Task[None] | None:
        return self.channel_service._write_task

    def _load_channels(self) -> None:
        self.channel_service._load_channels()

    def _save_channels(self, force: bool = False) -> None:
        self.channel_service._save_channels_sync(force)

    async def _save_channels_async(self, force: bool = False) -> None:
        await self.channel_service.save_channels_async(force)

    @staticmethod
    def _observe_write(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            logging.error("Channel persistence failed: %s", type(task.exception()).__name__)

    async def handle_channels_route(
        self, path: str, method: str, req_body: dict[str, Any]
    ) -> tuple[int, dict[str, Any]]:
        # sync_from_radio owns the same service lock. Do not acquire it twice.
        if path == "/api/channels/sync":
            return await self._handle_channels_route(path, method, req_body)
        async with self._mutation_lock:
            await self.channel_service.wait_for_pending_write()
            return await self._handle_channels_route(path, method, req_body)

    async def _handle_channels_route(
        self,
        path: str,
        method: str,
        req_body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        """Enruta solicitudes hacia /api/channels y /api/channels/sync."""
        if path == "/api/channels/sync":
            if method == "POST":
                return await self._sync_channels()
            return problem_details(405, "Method Not Allowed", "Sincronización requiere POST", "method_not_allowed")

        if path == "/api/channels/export":
            if method in ("GET", "POST"):
                return await self._export_channel(req_body)
            return problem_details(405, "Method Not Allowed", "Exportación requiere GET o POST", "method_not_allowed")

        if path != "/api/channels":
            return problem_details(404, "Not Found", "Ruta de canales desconocida", "route_not_found")

        if method == "GET":
            return await self._get_channels(sync_serial=False)

        if method == "POST":
            return await self._create_or_update_channel(req_body)

        if method == "DELETE":
            return await self._delete_channel(req_body)

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido para /api/channels", "method_not_allowed")

    async def _sync_from_serial(self) -> None:
        """Sincroniza la tabla de canales desde el hardware serial si está disponible."""
        await self.channel_service.sync_from_radio()

    async def _sync_channels(self) -> tuple[int, dict[str, Any]]:
        """Sincroniza los canales desde el hardware serial y retorna la lista enmascarada."""
        try:
            await self._sync_from_serial()
        except ConnectionError:
            return problem_details(503, "Service Unavailable", "No se pudo sincronizar canales", "sync_failed")
        except Exception:
            return problem_details(503, "Service Unavailable", "Fallo sincronizando canales del transceptor", "sync_failed")
        masked_list = self._get_masked_channels_list()
        return 200, {"status": "ok", "data": masked_list, "count": len(masked_list)}

    def _get_masked_channels_list(self) -> list[dict[str, Any]]:
        """Devuelve una lista ordenada de canales con PSK enmascarado delegando en ChannelService."""
        return self.channel_service.get_masked_channels()

    def _mask_channel(self, ch: dict[str, Any]) -> dict[str, Any]:
        """Enmascara la PSK de un único canal delegando en ChannelService."""
        return self.channel_service.mask_channel(ch)

    async def _get_channels(self, sync_serial: bool = True) -> tuple[int, dict[str, Any]]:
        """Devuelve los canales configurados con PSK enmascarada."""
        if sync_serial:
            await self._sync_from_serial()
        masked_list = self._get_masked_channels_list()
        return 200, {"status": "ok", "data": masked_list, "count": len(masked_list)}

    async def _export_channel(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Exporta un canal en formato URI oficial de MeshCore (meshcore://channel/add?name=...&secret=...)."""
        try:
            idx = int(req_body.get("index", 0))
        except (ValueError, TypeError):
            return problem_details(400, "Bad Request", "Índice de canal inválido", "invalid_channel_index")

        if idx == 0:
            return problem_details(
                400,
                "Bad Request",
                "El canal público 0 está preconfigurado por defecto en MeshCore y no requiere exportación",
                "cannot_export_public_channel",
            )

        if idx not in self.channels:
            return problem_details(404, "Not Found", f"Canal {idx} no encontrado", "channel_not_found")

        ch = self.channels[idx]
        name = str(ch.get("name") or (f"Canal {idx}" if idx > 0 else "Public / Broadcast")).strip()
        raw_psk = str(ch.get("psk") or "").strip()

        # Export the same key used by set_channel, including named hash channels
        # and legacy tokens. Never replace a missing private key with Public's key.
        if not re.fullmatch(r"[a-fA-F0-9]{0,64}", raw_psk):
            return problem_details(
                422,
                "Unprocessable Entity",
                "The stored channel key is unavailable or invalid; reconfigure this channel before exporting it",
                "channel_secret_unavailable",
            )
        secret = derive_channel_secret(name, raw_psk).hex()

        encoded_name = urllib.parse.quote(name)
        canonical_uri = f"meshcore://channel/add?name={encoded_name}&secret={secret}"
        if idx > 0:
            canonical_uri += f"&index={idx}"

        channel_data = {
            "type": "channel",
            "index": idx,
            "name": name,
            "secret": secret,
            "is_encrypted": bool(raw_psk or name.startswith("#")),
            "is_public": (idx == 0),
        }

        return 200, {
            "status": "ok",
            "uri": canonical_uri,
            "qr_uri": canonical_uri,
            "data": channel_data,
        }

    def _max_channels(self) -> int:
        """Capacidad anunciada por el transceptor; fallback compatible con Companion clásico."""
        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        info = getattr(ser, "self_info", None) if ser else None
        if isinstance(info, dict):
            try:
                value = int(info.get("max_channels", 8))
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass
        return 8

    async def _create_or_update_channel(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Crea o actualiza un canal dentro de la capacidad anunciada por el dispositivo."""
        raw_idx = req_body.get("index", 1)
        if isinstance(raw_idx, bool) or isinstance(raw_idx, float):
            return problem_details(422, "Unprocessable Entity", "El índice de canal debe ser un número entero", "invalid_channel_index")
        try:
            if isinstance(raw_idx, str):
                s = raw_idx.strip()
                if not s.isdigit() and not (s.startswith("-") and s[1:].isdigit()):
                    raise ValueError("Not an integer string")
            idx = int(raw_idx)
        except (ValueError, TypeError):
            return problem_details(422, "Unprocessable Entity", "Índice de canal inválido", "invalid_channel_index")

        max_channels = self._max_channels()
        if idx < 0 or idx >= max_channels:
            return problem_details(
                400,
                "Bad Request",
                f"El índice de canal debe estar entre 0 y {max_channels - 1}",
                "channel_index_out_of_bounds",
            )

        from src.shared_utils import to_bool
        overwrite = to_bool(req_body.get("overwrite", False))
        if idx in self.channels and not overwrite:
            return problem_details(
                409,
                "Conflict",
                f"El canal {idx} ya existe. No se permite duplicar ni sobrescribir sin confirmación explícita (overwrite=true).",
                "channel_already_exists",
            )

        is_new_channel = idx not in self.channels
        raw_name = req_body.get("name", f"Canal {idx}")
        if not firmware_name_valid(raw_name):
            return problem_details(422, "Unprocessable Entity", "El nombre debe caber en 31 bytes UTF-8 sin caracteres de control", "invalid_channel_name")
        name = raw_name.strip()
        psk = str(req_body.get("psk", "")).strip()
        if psk == "••••••••" and idx in self.channels:
            psk = str(self.channels[idx].get("psk", ""))
        elif psk == "••••••••":
            return problem_details(422, "Unprocessable Entity", "Placeholder de PSK inválido para un canal nuevo", "invalid_psk")
        if psk and not re.fullmatch(r"[a-fA-F0-9]{32}", psk):
            return problem_details(422, "Unprocessable Entity", "La clave PSK debe contener exactamente 32 caracteres hexadecimales (16 bytes)", "invalid_psk")
        failure = await self.serial_mutation("set_channel", idx, name, psk)
        if failure:
            return failure
        self.channels[idx] = {"index": idx, "name": name, "psk": psk, "is_public": (idx == 0)}
        self._deleted_channels.discard(idx)
        self._dirty = True
        await self._save_channels_async()

        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({"type": "channels_updated", "data": self._get_masked_channels_list()})

        self.ctx.log_system_event("INFO", f"Canal {idx} configurado: {name}", source="channels")
        status_code = 201 if is_new_channel else 200
        return status_code, {"status": "ok", "data": self._mask_channel(self.channels[idx])}

    async def _delete_channel(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Elimina un canal secundario (1..7) tanto del bridge como del transceptor físico."""
        raw_idx = req_body.get("index", 0)
        if isinstance(raw_idx, bool) or isinstance(raw_idx, float):
            return problem_details(422, "Unprocessable Entity", "El índice de canal debe ser un número entero", "invalid_channel_index")
        try:
            if isinstance(raw_idx, str):
                s = raw_idx.strip()
                if not s.isdigit() and not (s.startswith("-") and s[1:].isdigit()):
                    raise ValueError("Not an integer string")
            idx = int(raw_idx)
        except (ValueError, TypeError):
            return problem_details(422, "Unprocessable Entity", "Índice de canal inválido", "invalid_channel_index")

        if idx == 0:
            return problem_details(400, "Bad Request", "No se puede eliminar el canal público 0", "cannot_delete_public_channel")

        if idx not in self.channels:
            return problem_details(404, "Not Found", f"Canal {idx} no encontrado", "channel_not_found")

        # Enviar orden de vaciado de slot al transceptor serial si está activo
        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        failure = await self.serial_mutation("delete_channel", idx) if callable(getattr(ser, "delete_channel", None)) else await self.serial_mutation("set_channel", idx, "", "00" * 16)
        if failure:
            return failure
        self._deleted_channels.add(idx)
        del self.channels[idx]
        self._dirty = True
        await self._save_channels_async()

        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({"type": "channels_updated", "data": self._get_masked_channels_list()})

        self.ctx.log_system_event("INFO", f"Canal {idx} eliminado del sistema", source="channels")
        return 204, {}
