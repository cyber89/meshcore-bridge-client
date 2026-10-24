"""
Channel Service for MeshCore Bridge (ADR 0020 / F3.1).
Owns channel configuration table, locks, persistence, hardware synchronization,
and separation of public snapshots from internal cryptographic secrets.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.shared_utils import derive_channel_secret
from src.storage_validation import validate_channels_document


def firmware_name_valid(name: str) -> bool:
    """Valida longitud UTF-8 (<=31 bytes) y ausencia de caracteres de control."""
    if not isinstance(name, str):
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        return False
    return len(name.strip().encode("utf-8")) <= 31


class ChannelService:
    """
    Servicio de aplicación para gestión y persistencia de canales LoRa.
    Opera de forma autónoma con o sin servidor web (soporte headless total).
    """

    def __init__(
        self,
        channels_file: str | Path | None = None,
        database: Any | None = None,
        serial_adapter_provider: Callable[[], Any] | None = None,
    ) -> None:
        self.channels_file = str(channels_file or "data/channels.json")
        self.database = database
        self.serial_adapter_provider = serial_adapter_provider
        self._channels: dict[int, dict[str, Any]] = {}
        self._deleted_channels: set[int] = set()
        self._dirty: bool = False
        self._mutation_lock = asyncio.Lock()
        self._save_lock = threading.Lock()
        self._write_task: asyncio.Task[None] | None = None
        self._load_channels()

    @property
    def channels(self) -> dict[int, dict[str, Any]]:
        """Devuelve el diccionario de canales internos."""
        return self._channels

    def _load_channels(self) -> None:
        """Carga la tabla de canales desde SQLite o JSON fallback."""
        if self.database is not None:
            data = self.database.read_document("channels", self.channels_file, validator=validate_channels_document)
            if isinstance(data, list):
                self._channels = {int(c.get("index", i)): c for i, c in enumerate(data)}
            elif isinstance(data, dict):
                self._channels = {int(k): v for k, v in data.items() if str(k).isdigit()}
        elif os.path.exists(self.channels_file):
            try:
                with open(self.channels_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._channels = {int(c.get("index", i)): c for i, c in enumerate(data)}
                    elif isinstance(data, dict):
                        self._channels = {int(k): v for k, v in data.items() if str(k).isdigit()}
            except Exception as error:
                logging.warning("Channel load failed: %s", type(error).__name__)

        if 0 not in self._channels:
            self._channels[0] = {
                "index": 0,
                "name": "Public / Broadcast",
                "psk": "",
                "is_public": True,
            }

    def _save_channels_sync(self, force: bool = False) -> None:
        """Persiste atómicamente la tabla de canales si hay cambios."""
        with self._save_lock:
            if not force and not self._dirty:
                return

            if self.database is not None:
                self.database.write_document("channels", list(self._channels.values()))
                self._dirty = False
                return

            target_dir = os.path.dirname(self.channels_file) or "."
            os.makedirs(target_dir, exist_ok=True)
            tmp_path = f"{self.channels_file}_{os.getpid()}_{time.time_ns()}.tmp"
            try:
                channels_data = list(self._channels.values())
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(channels_data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.channels_file)
                self._dirty = False
            except Exception as error:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                logging.error("Channel persistence failed: %s", type(error).__name__)
                raise

    async def wait_for_pending_write(self) -> None:
        """Join an owned writer without letting an old failure poison new work."""
        task = self._write_task
        if task is None:
            return
        try:
            await asyncio.shield(task)
        except Exception:
            # The original save caller receives the failure. A later operation
            # must be able to read state or retry after storage recovers.
            logging.warning("Previous channel write failed; a later operation may retry")
        finally:
            if task.done() and self._write_task is task:
                self._write_task = None

    @staticmethod
    def _observe_write(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            logging.error("Channel persistence failed: %s", type(task.exception()).__name__)

    async def save_channels_async(self, force: bool = False) -> None:
        """Keep writes owned through cancellation and surface this save's error."""
        await self.wait_for_pending_write()
        task = asyncio.create_task(
            asyncio.to_thread(self._save_channels_sync, force),
            name="ChannelsPersistence",
        )
        self._write_task = task
        task.add_done_callback(self._observe_write)
        try:
            await asyncio.shield(task)
        finally:
            if task.done() and self._write_task is task:
                self._write_task = None

    def mask_channel(self, ch: dict[str, Any]) -> dict[str, Any]:
        """Enmascara la PSK para vistas públicas/REST/WebSocket."""
        c_dict = dict(ch)
        ch_idx = int(c_dict.get("index", 0))
        raw_psk = str(c_dict.get("psk") or "").strip()
        is_ch0 = (ch_idx == 0)
        has_psk = bool(raw_psk) and not is_ch0
        c_dict["has_psk"] = has_psk
        c_dict["is_encrypted"] = not is_ch0 and (has_psk or str(c_dict.get("name") or "").startswith("#"))
        c_dict["is_public"] = is_ch0
        if has_psk and not is_ch0:
            c_dict["psk"] = "••••••••"
        else:
            c_dict["psk"] = ""
        return c_dict

    def get_masked_channels(self) -> list[dict[str, Any]]:
        """Devuelve todos los canales con secretos enmascarados."""
        channels_list = list(self._channels.values())
        channels_list.sort(key=lambda c: int(c.get("index", 0)))
        return [self.mask_channel(c) for c in channels_list]

    def get_channel(self, index: int, masked: bool = True) -> dict[str, Any] | None:
        """Devuelve un canal específico por índice."""
        ch = self._channels.get(index)
        if ch is None:
            return None
        return self.mask_channel(ch) if masked else dict(ch)

    def get_channel_secret_for_export(self, index: int) -> tuple[str, str]:
        """
        Devuelve (nombre, secret_hex) para exportación oficial URI de MeshCore.
        Lanza ValueError si el canal no existe, es el 0, o tiene clave inválida.
        """
        if index == 0:
            raise ValueError("El canal público 0 no requiere exportación")
        if index not in self._channels:
            raise KeyError(f"Canal {index} no encontrado")
        ch = self._channels[index]
        name = str(ch.get("name") or f"Canal {index}").strip()
        raw_psk = str(ch.get("psk") or "").strip()
        if not re.fullmatch(r"[a-fA-F0-9]{0,64}", raw_psk):
            raise ValueError("The stored channel key is unavailable or invalid")
        secret = derive_channel_secret(name, raw_psk).hex()
        return name, secret

    def max_channels(self) -> int:
        """Capacidad máxima anunciada por el transceptor serial o fallback clásico (8)."""
        if self.serial_adapter_provider:
            ser = self.serial_adapter_provider()
            info = getattr(ser, "self_info", None) if ser else None
            if isinstance(info, dict):
                try:
                    val = int(info.get("max_channels", 8))
                    if val > 0:
                        return val
                except (TypeError, ValueError):
                    pass
        return 8

    async def sync_from_radio(self, node_channels: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """
        Sincroniza canales desde hardware serial.
        Si node_channels es provisto, usa esos datos; en otro caso consulta al serial_adapter.
        """
        async with self._mutation_lock:
            await self.wait_for_pending_write()
            if node_channels is None:
                if not self.serial_adapter_provider:
                    raise ConnectionError("Transceptor serial no configurado")
                ser = self.serial_adapter_provider()
                if not ser or not hasattr(ser, "get_channels"):
                    raise ConnectionError("Transceptor serial no disponible")
                node_channels = await ser.get_channels()

            if node_channels is not None:
                for ch in node_channels:
                    idx = int(ch.get("index", 0))
                    if idx in self._deleted_channels:
                        if idx in self._channels:
                            del self._channels[idx]
                            self._dirty = True
                        continue

                    ch_name = str(ch.get("name") or "").strip()
                    raw_psk = str(ch.get("psk") or "").strip()
                    is_empty_slot = (not ch_name and (not raw_psk or raw_psk == "0" * 32 or raw_psk == "00" * 16))
                    if idx > 0 and is_empty_slot:
                        if idx in self._channels:
                            del self._channels[idx]
                            self._dirty = True
                        continue

                    if self._channels.get(idx) != ch:
                        self._channels[idx] = ch
                        self._dirty = True

                await self.save_channels_async()

            return self.get_masked_channels()

    async def set_channel(
        self,
        index: int,
        name: str,
        psk: str,
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Crea o actualiza un canal en la tabla interna y en el hardware."""
        max_ch = self.max_channels()
        if index < 0 or index >= max_ch:
            raise ValueError(f"El índice de canal debe estar entre 0 y {max_ch - 1}")

        if not firmware_name_valid(name):
            raise ValueError("El nombre debe caber en 31 bytes UTF-8 sin caracteres de control")

        async with self._mutation_lock:
            await self.wait_for_pending_write()
            if index in self._channels and not overwrite:
                raise FileExistsError(f"El canal {index} ya existe")

            clean_name = name.strip()
            clean_psk = psk.strip()
            if clean_psk == "••••••••" and index in self._channels:
                clean_psk = str(self._channels[index].get("psk", ""))

            # Mutación de hardware si el adaptador serial está disponible
            if self.serial_adapter_provider:
                ser = self.serial_adapter_provider()
                if ser and hasattr(ser, "set_channel") and callable(ser.set_channel):
                    res = await ser.set_channel(index, clean_name, clean_psk)
                    if isinstance(res, dict) and res.get("status") == "error":
                        raise RuntimeError(f"Error en hardware: {res.get('message', 'Fallo al configurar canal')}")

            self._channels[index] = {
                "index": index,
                "name": clean_name,
                "psk": clean_psk,
                "is_public": (index == 0),
            }
            self._deleted_channels.discard(index)
            self._dirty = True
            await self.save_channels_async()

            return self.mask_channel(self._channels[index])

    async def delete_channel(self, index: int) -> bool:
        """Elimina un canal secundario (1..N)."""
        if index == 0:
            raise ValueError("No se puede eliminar el canal público 0")

        async with self._mutation_lock:
            await self.wait_for_pending_write()
            if index not in self._channels:
                raise KeyError(f"Canal {index} no encontrado")

            if self.serial_adapter_provider:
                ser = self.serial_adapter_provider()
                if ser and hasattr(ser, "delete_channel") and callable(ser.delete_channel):
                    await ser.delete_channel(index)
                elif ser and hasattr(ser, "set_channel") and callable(ser.set_channel):
                    await ser.set_channel(index, "", "00" * 16)

            self._deleted_channels.add(index)
            del self._channels[index]
            self._dirty = True
            await self.save_channels_async()
            return True

    def update_from_system_event(self, channel_idx: int, channel_name: str, channel_hash: str) -> None:
        """Actualización limpia invocada desde SystemHandler sin acceder a estructuras internas."""
        if channel_idx not in self._channels:
            self._channels[channel_idx] = {
                "index": channel_idx,
                "name": channel_name,
                "channel_hash": channel_hash,
            }
        else:
            self._channels[channel_idx]["name"] = channel_name
            self._channels[channel_idx]["channel_hash"] = channel_hash
