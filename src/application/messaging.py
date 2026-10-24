"""
Application Service for Messaging and Chat (MessageService).
Encapsulates domain validations, rate limiting dispatch, and durable history queries
independently of Web REST (FastAPI) or MQTT transports.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from src.contact_manager import NodeRegistry, PacketRecord
from src.rate_limiter import TxPriority, TxRateLimiter
from src.shared_utils import classify_device_role
from src.station_database import StationDatabase
from src.target_resolver import TargetResolver

logger = logging.getLogger("meshcore.application.messaging")


class RateLimiterProtocol(Protocol):
    async def submit(
        self,
        payload: Any,
        priority: TxPriority = TxPriority.NORMAL,
        target: str | None = None,
        channel_idx: int = 0,
        request_id: str | None = None,
    ) -> Any: ...
    def get_queue_depth(self) -> int: ...


@dataclass(frozen=True, slots=True)
class ValidationResult:
    is_valid: bool
    error: str | None = None
    error_code: str | None = None
    http_code: int = 200
    is_broadcast: bool = False
    clean_target: str = "broadcast"
    clean_text: str = ""
    channel_idx: int = 0


@dataclass(frozen=True, slots=True)
class MessageSendResult:
    status: str  # "sent", "queued", "error", "conflict", "timeout", "rate_limited"
    data: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    http_code: int = 200
    request_id: str | None = None


class MessageService:
    """Servicio de aplicación para mensajería de chat e historial de la estación."""

    def __init__(
        self,
        node_registry: NodeRegistry | None = None,
        rate_limiter: TxRateLimiter | RateLimiterProtocol | None = None,
        database: StationDatabase | None = None,
        log_system_event: Any | None = None,
        mc_provider: Callable[[], Any] | None = None,
    ) -> None:
        self.node_registry = node_registry if node_registry is not None else NodeRegistry()
        self.rate_limiter = rate_limiter
        self.database = database
        self._log_event = log_system_event
        self._mc_provider = mc_provider

    def validate_tx_request(
        self,
        text: Any,
        target: Any,
        channel_idx: Any = 0,
    ) -> ValidationResult:
        """Valida las reglas invariantes de dominio y formato para envío de mensajes."""
        if not isinstance(text, str):
            return ValidationResult(
                is_valid=False,
                error="El campo 'text' debe ser texto",
                error_code="invalid_text_field",
                http_code=422,
            )
        clean_text = text.strip()
        if not clean_text:
            return ValidationResult(
                is_valid=False,
                error="El campo 'text' no puede estar vacío",
                error_code="missing_text_field",
                http_code=400,
            )

        if target is None:
            return ValidationResult(
                is_valid=False,
                error="El campo de destino ('to'/'target') no puede ser nulo",
                error_code="null_target_destination",
                http_code=422,
            )
        if not isinstance(target, str):
            return ValidationResult(
                is_valid=False,
                error="El destino debe ser texto",
                error_code="invalid_target_destination",
                http_code=422,
            )
        clean_target = target.strip()
        if not clean_target:
            return ValidationResult(
                is_valid=False,
                error="El campo de destino ('to'/'target') no puede ser una cadena vacía. Especifique 'broadcast' para difusión general o una clave pública válida.",
                error_code="empty_target_destination",
                http_code=422,
            )

        try:
            if isinstance(channel_idx, bool) or not isinstance(channel_idx, (str, int)):
                raise ValueError("Channel index must be an integer")
            if isinstance(channel_idx, str) and re.fullmatch(r"[+-]?[0-9]+", channel_idx.strip()) is None:
                raise ValueError("Channel index must be an integer")
            ch_val = int(channel_idx)
            if ch_val < 0 or ch_val > 255:
                raise ValueError("Channel index out of bounds")
        except (ValueError, TypeError):
            return ValidationResult(
                is_valid=False,
                error="El índice de canal debe ser un entero válido (0-255)",
                error_code="invalid_channel_index",
                http_code=400,
            )

        is_broadcast = (
            clean_target.lower() in ("broadcast", "public", "0xffff", "*", "")
            or clean_target.lower().startswith("channel")
        )

        if not is_broadcast:
            resolved_role = ""
            try:
                resolved = TargetResolver(
                    mc_provider=self._mc_provider, node_registry=self.node_registry,
                ).resolve(clean_target, raise_on_not_found=True)
                key = resolved.get("public_key", "") if isinstance(resolved, dict) else getattr(resolved, "public_key", resolved)
                if isinstance(resolved, dict):
                    advert_type = resolved.get("adv_type", resolved.get("type"))
                    resolved_role = (classify_device_role(int(advert_type)) if advert_type is not None
                                     else str(resolved.get("role", "")).upper())
                else:
                    resolved_role = str(getattr(resolved, "role", "")).upper()
                clean_target = str(key).lower().strip()
                if re.fullmatch(r"[0-9a-f]{64}", clean_target) is None:
                    raise ValueError("A complete public key is required")
            except (ValueError, TypeError):
                return ValidationResult(
                    is_valid=False, error="Destino desconocido, incompleto o ambiguo",
                    error_code="invalid_target_destination", http_code=422,
                )
            # Regla 1.2: Prohibido enviar chat a la propia estación local
            if self.node_registry.is_local_key(clean_target):
                return ValidationResult(
                    is_valid=False,
                    error="No se permite enviar mensajes de chat a la estación base local",
                    error_code="tx_to_local_forbidden",
                    http_code=400,
                    is_broadcast=False,
                    clean_target=clean_target,
                    clean_text=clean_text,
                    channel_idx=ch_val,
                )

            # Regla 1.1: Prohibido enviar chat hacia repetidores de infraestructura
            dest_node = self.node_registry.get_by_key_or_prefix(clean_target)
            if (resolved_role in ("REPEATER", "ROUTER") or
                (dest_node and dest_node.role in ("REPEATER", "ROUTER")) or self.node_registry.is_repeater_key(clean_target)):
                return ValidationResult(
                    is_valid=False,
                    error="Los repetidores son nodos de infraestructura y no procesan mensajes de chat",
                    error_code="tx_to_repeater_forbidden",
                    http_code=400,
                    is_broadcast=False,
                    clean_target=clean_target,
                    clean_text=clean_text,
                    channel_idx=ch_val,
                )

        return ValidationResult(
            is_valid=True,
            is_broadcast=is_broadcast,
            clean_target=clean_target,
            clean_text=clean_text,
            channel_idx=ch_val,
        )

    async def submit_chat(
        self,
        text: Any,
        target: Any,
        channel_idx: Any = 0,
        priority: TxPriority = TxPriority.NORMAL,
        request_id: str | None = None,
        timeout: float = 30.0,
    ) -> MessageSendResult:
        """Valida y encola un mensaje de chat hacia el limitador de tasa de radio (TxRateLimiter)."""
        validation = self.validate_tx_request(text=text, target=target, channel_idx=channel_idx)
        if not validation.is_valid:
            return MessageSendResult(
                status="error",
                error=validation.error,
                error_code=validation.error_code,
                http_code=validation.http_code,
                request_id=request_id,
            )

        rate_limiter = self.rate_limiter
        if not rate_limiter or not hasattr(rate_limiter, "submit"):
            return MessageSendResult(
                status="error",
                error="La cola de transmisión no está disponible",
                error_code="tx_submission_failed",
                http_code=503,
                request_id=request_id,
            )

        req_id = request_id or f"msg_{int(time.time() * 1000)}"
        target_arg = validation.clean_target if not validation.is_broadcast else None

        try:
            submit_res = rate_limiter.submit(
                payload=validation.clean_text,
                priority=priority,
                target=target_arg,
                channel_idx=validation.channel_idx,
                request_id=req_id,
            )
            future = await submit_res if asyncio.iscoroutine(submit_res) else submit_res

            if not (asyncio.isfuture(future) or asyncio.iscoroutine(future)):
                return MessageSendResult(
                    status="error",
                    error="La cola no confirmó la admisión de la transmisión",
                    error_code="tx_submission_failed",
                    http_code=503,
                    request_id=req_id,
                )

            async with asyncio.timeout(timeout):
                res = await future

        except TimeoutError:
            err_msg = f"Timeout esperando turno de transmisión en cola de Airtime LoRa ({timeout:.0f}s)"
            if callable(self._log_event):
                self._log_event("ERROR", f"Fallo en TX hacia {validation.clean_target}: {err_msg}", source="mesh_tx")
            return MessageSendResult(
                status="timeout",
                error=err_msg,
                error_code="tx_timeout",
                http_code=408,
                request_id=req_id,
            )
        except Exception as ex:
            err_msg = str(ex) or "Fallo en cola de transmisión LoRa"
            is_full = isinstance(ex, asyncio.QueueFull) or "Full" in err_msg or "RateLimit" in err_msg
            if callable(self._log_event):
                self._log_event("ERROR", f"Fallo en TX hacia {validation.clean_target}: {err_msg}", source="mesh_tx")
            return MessageSendResult(
                status="rate_limited" if is_full else "error",
                error=err_msg,
                error_code="tx_submission_failed",
                http_code=429 if is_full else 503,
                request_id=req_id,
            )

        if isinstance(res, dict) and res.get("status") == "error":
            err_msg = str(res.get("error") or "Error en transmisión por radio LoRa")
            if callable(self._log_event):
                self._log_event("ERROR", f"Fallo en TX hacia {validation.clean_target}: {err_msg}", source="mesh_tx")
            return MessageSendResult(
                status="error",
                error=err_msg,
                error_code="tx_transmission_failed",
                http_code=400,
                data=res,
                request_id=req_id,
            )

        # Si el envío fue directo (no broadcast), registrar métrica de transmisión en el nodo
        if target_arg and not validation.is_broadcast:
            self.node_registry.record_packet(PacketRecord(public_key=str(target_arg), is_rx=False))

        if callable(self._log_event):
            self._log_event("INFO", f"Transmisión TX enviada a {validation.clean_target} (Ch {validation.channel_idx})", source="mesh_tx")

        return MessageSendResult(
            status="sent",
            data=res if isinstance(res, dict) else {"status": "sent", "request_id": req_id},
            http_code=200,
            request_id=req_id,
        )

    async def get_history(
        self,
        feed_key: str | None = None,
        limit: int = 100,
        before: int | None = None,
    ) -> dict[str, Any]:
        """Lee el historial durable de mensajes desde la base de datos SQLite."""
        if self.database is None:
            raise RuntimeError("Station database is unavailable")
        return await asyncio.to_thread(self.database.history, feed_key, limit, before)

    async def get_conversations(self) -> dict[str, Any]:
        """Lee el resumen de conversaciones activas de la estación."""
        if self.database is None:
            raise RuntimeError("Station database is unavailable")
        conversations = await asyncio.to_thread(self.database.conversations)
        page = await asyncio.to_thread(self.database.history, None, 1)
        return {"conversations": conversations, "station_id": page["station_id"]}

    async def import_messages(
        self,
        messages: list[dict[str, Any]],
        station_id: str | None = None,
    ) -> dict[str, Any]:
        """Importa un lote acotado de mensajes preservando la identidad de estación."""
        if self.database is None:
            raise RuntimeError("Station database is unavailable")
        if not isinstance(messages, list) or not 1 <= len(messages) <= 200 or any(not isinstance(item, dict) for item in messages):
            raise ValueError("Import requires between 1 and 200 message objects")
        if station_id is not None and not isinstance(station_id, str):
            raise ValueError("Invalid station identity")
        return await asyncio.to_thread(self.database.import_messages, messages, station_id=station_id)

    async def get_recent_messages(self, limit: int = 200) -> list[dict[str, Any]]:
        """Lee los mensajes más recientes para visualización en la interfaz web."""
        if self.database is not None:
            page = await asyncio.to_thread(self.database.history, None, limit)
            return list(page.get("messages", []))
        return []
