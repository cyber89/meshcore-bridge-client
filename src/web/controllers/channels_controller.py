"""
Channels REST controller.
Handles /api/channels and /api/channels/sync.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from typing import Any

from src.web.controllers.base import ApiContext, BaseController, problem_details


class ChannelsController(BaseController):
    """Controlador para configuración y sincronización de canales LoRa."""

    def __init__(self, ctx: ApiContext, channels_file: str | None = None) -> None:
        super().__init__(ctx)
        self.channels_file: str = str(
            channels_file
            or os.getenv("CHANNELS_STORAGE_PATH")
            or os.getenv("CHANNELS_JSON_PATH")
            or "data/channels.json"
        )
        self.channels: dict[int, dict[str, Any]] = {}
        self._deleted_channels: set[int] = set()
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
                "name": "Public / Broadcast",
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

        if path == "/api/channels/export" and method in ("GET", "POST"):
            return await self._export_channel(req_body)

        if method == "GET":
            return await self._get_channels(sync_serial=False)

        if method == "POST":
            return await self._create_or_update_channel(req_body)

        if method == "DELETE":
            return await self._delete_channel(req_body)

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido para /api/channels", "method_not_allowed")

    async def _sync_from_serial(self) -> None:
        """Sincroniza la tabla de canales desde el hardware serial si está disponible."""
        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        if ser and hasattr(ser, "get_channels"):
            try:
                node_channels = await ser.get_channels()
                if node_channels is not None:
                    for ch in node_channels:
                        idx = int(ch.get("index", 0))
                        # Si el canal fue eliminado explícitamente por el usuario, nunca resucitarlo
                        if idx in self._deleted_channels:
                            if idx in self.channels:
                                del self.channels[idx]
                            continue

                        ch_name = str(ch.get("name") or "").strip()
                        raw_psk = str(ch.get("psk") or "").strip()
                        # Un canal con nombre vacío y clave vacía o de ceros se considera slot libre/borrado
                        is_empty_slot = (not ch_name and (not raw_psk or raw_psk == "0" * 32 or raw_psk == "00" * 16))
                        if idx > 0 and is_empty_slot:
                            if idx in self.channels:
                                del self.channels[idx]
                            continue

                        self.channels[idx] = ch
                    self._save_channels()
            except Exception as e:
                logging.debug(f"Fallo sincronizando canales del nodo serial: {e}")

    async def _sync_channels(self) -> tuple[int, dict[str, Any]]:
        """Sincroniza los canales desde el hardware serial y retorna la lista enmascarada."""
        await self._sync_from_serial()
        masked_list = self._get_masked_channels_list()
        return 200, {"status": "ok", "data": masked_list, "count": len(masked_list)}

    def _get_masked_channels_list(self) -> list[dict[str, Any]]:
        """Devuelve una lista ordenada de canales con PSK enmascarado por seguridad."""
        channels_list = list(self.channels.values())
        channels_list.sort(key=lambda c: int(c.get("index", 0)))
        masked_list = []
        for ch in channels_list:
            c_dict = dict(ch)
            raw_psk = str(c_dict.get("psk") or "").strip()
            has_psk = bool(raw_psk)
            c_dict["has_psk"] = has_psk
            c_dict["is_encrypted"] = has_psk and (int(c_dict.get("index", 0)) != 0)
            if has_psk:
                c_dict["psk"] = "••••••••"
            else:
                c_dict["psk"] = ""
            masked_list.append(c_dict)
        return masked_list

    def _mask_channel(self, ch: dict[str, Any]) -> dict[str, Any]:
        """Enmascara la PSK de un único canal."""
        c_dict = dict(ch)
        raw_psk = str(c_dict.get("psk") or "").strip()
        has_psk = bool(raw_psk)
        c_dict["has_psk"] = has_psk
        c_dict["is_encrypted"] = has_psk and (int(c_dict.get("index", 0)) != 0)
        if has_psk:
            c_dict["psk"] = "••••••••"
        else:
            c_dict["psk"] = ""
        return c_dict

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

        # Si es canal 0 (público) o canal abierto sin clave, usar la clave canónica oficial de MeshCore
        # SSoT: reference/meshcore/docs/qr_codes.md y companion_protocol.md
        public_secret = "8b3387e9c5cdea6ac9e5edbaa115cd72"
        secret = raw_psk if (raw_psk and raw_psk != "••••••••") else public_secret

        encoded_name = urllib.parse.quote(name)
        canonical_uri = f"meshcore://channel/add?name={encoded_name}&secret={secret}"
        if idx > 0:
            canonical_uri += f"&index={idx}"

        channel_data = {
            "type": "channel",
            "index": idx,
            "name": name,
            "secret": secret,
            "is_encrypted": bool(raw_psk and raw_psk != "••••••••" and idx != 0),
            "is_public": (idx == 0),
        }

        return 200, {
            "status": "ok",
            "uri": canonical_uri,
            "qr_uri": canonical_uri,
            "data": channel_data,
        }

    async def _create_or_update_channel(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Crea o actualiza un canal en el rango 0..7."""
        try:
            idx = int(req_body.get("index", 1))
        except (ValueError, TypeError):
            return problem_details(400, "Bad Request", "Índice de canal inválido", "invalid_channel_index")

        if idx < 0 or idx > 7:
            return problem_details(400, "Bad Request", "El índice de canal debe estar entre 0 y 7", "channel_index_out_of_bounds")

        overwrite = bool(req_body.get("overwrite", False))
        if idx in self.channels and not overwrite:
            return problem_details(
                409,
                "Conflict",
                f"El canal {idx} ya existe. No se permite duplicar ni sobrescribir sin confirmación explícita (overwrite=true).",
                "channel_already_exists",
            )

        name = str(req_body.get("name", f"Canal {idx}")).strip()
        psk = str(req_body.get("psk", "")).strip()
        if psk == "••••••••" and idx in self.channels:
            psk = str(self.channels[idx].get("psk", ""))
        self.channels[idx] = {"index": idx, "name": name, "psk": psk, "is_public": (idx == 0)}
        self._deleted_channels.discard(idx)
        self._save_channels()

        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        if ser and hasattr(ser, "set_channel"):
            try:
                await ser.set_channel(idx, name, psk)
            except Exception as e:
                logging.debug(f"Error despachando canal al transceptor serial: {e}")

        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({"type": "channels_updated", "data": self._get_masked_channels_list()})

        self.ctx.log_system_event("INFO", f"Canal {idx} configurado: {name}", source="channels")
        return 200, {"status": "ok", "data": self._mask_channel(self.channels[idx])}

    async def _delete_channel(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Elimina un canal secundario (1..7) tanto del bridge como del transceptor físico."""
        try:
            idx = int(req_body.get("index", 0))
        except (ValueError, TypeError):
            return problem_details(400, "Bad Request", "Índice de canal inválido", "invalid_channel_index")

        if idx == 0:
            return problem_details(400, "Bad Request", "No se puede eliminar el canal público 0", "cannot_delete_public_channel")

        self._deleted_channels.add(idx)
        if idx in self.channels:
            del self.channels[idx]
        self._save_channels()

        # Enviar orden de vaciado de slot al transceptor serial si está activo
        ser = getattr(self.ctx.bridge, "serial_adapter", None)
        if ser:
            try:
                if hasattr(ser, "delete_channel"):
                    await ser.delete_channel(idx)
                elif hasattr(ser, "set_channel"):
                    await ser.set_channel(idx, "", "00" * 16)
            except Exception as e:
                logging.warning(f"Error borrando canal {idx} en el transceptor serial: {e}")

        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({"type": "channels_updated", "data": self._get_masked_channels_list()})

        self.ctx.log_system_event("INFO", f"Canal {idx} eliminado del sistema", source="channels")
        return 200, {"status": "ok", "message": f"Canal {idx} eliminado"}
