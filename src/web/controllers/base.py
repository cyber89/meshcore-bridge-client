"""
Base classes, context and RFC 7807 problem details generator for REST controllers.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ApiContext:
    """Contexto de dependencias inyectado a los controladores REST."""

    bridge: Any
    recent_messages: deque[dict[str, Any]]
    system_logs: deque[dict[str, Any]]
    log_system_event: Callable[..., None]
    broadcast_ws: Callable[[dict[str, Any]], Any] | None = None
    start_time: float = 0.0
    packet_buffer: Any = None
    recent_telemetry: deque[dict[str, Any]] | None = None


def problem_details(
    status: int,
    title: str,
    detail: str,
    error_code: str = "",
    extra: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    """
    Genera una respuesta de error estandarizada conforme a RFC 7807 (Problem Details for HTTP APIs),
    preservando campos de retrocompatibilidad ('error', 'message', 'status').
    """
    payload: dict[str, Any] = {
        "type": f"urn:meshcore:error:{error_code or status}",
        "title": title,
        "status": status,
        "detail": detail,
        "error": error_code or title,
        "message": detail,
        "timestamp": time.time(),
    }
    if extra:
        payload.update(extra)
    return status, payload


class BaseController:
    """Clase base para todos los controladores REST."""

    def __init__(self, ctx: ApiContext) -> None:
        self.ctx = ctx

    @staticmethod
    def command_failure(result: Any) -> tuple[int, dict[str, Any]] | None:
        """Map Companion refusals before claiming success or committing local state."""
        if result is None or result is False:
            return problem_details(503, "Service Unavailable", "El transceptor no confirmó la operación", "command_unconfirmed")
        if isinstance(result, dict):
            status = str(result.get("status", "")).upper()
            if status in {"OK", "SUCCESS", "SENT", "DELETED", "CLEARED"} and not result.get("error"):
                return None
            if status in {"ERROR", "FAILED", "NOT_SUPPORTED", "LOCAL_ONLY", "LOCAL_DELETED"} or result.get("error"):
                raw_code = result.get("code", 503 if status.startswith(("NOT_SUPPORTED", "LOCAL_")) else 400)
                code = raw_code if isinstance(raw_code, int) and not isinstance(raw_code, bool) and 400 <= raw_code <= 599 else 400
                return problem_details(code, "Command Failed", "El transceptor rechazó la operación", "command_failed")
            # Read results/legacy administrator results can omit a status field.
            if not status:
                return None
            return problem_details(503, "Service Unavailable", "Respuesta de operación no confirmada", "command_unconfirmed")
        event_type = getattr(result, "type", None)
        if str(getattr(event_type, "name", event_type)).upper() in {"ERROR", "DISABLED"}:
            return problem_details(400, "Command Failed", "El transceptor rechazó la operación", "command_failed")
        is_error = getattr(result, "is_error", None)
        if callable(is_error) and is_error():
            return problem_details(400, "Command Failed", "El transceptor rechazó la operación", "command_failed")
        return None

    async def serial_mutation(self, method: str, *args: Any) -> tuple[int, dict[str, Any]] | None:
        """Execute one explicit serial mutation and preserve exceptions as HTTP failures."""
        adapter = getattr(self.ctx.bridge, "serial_adapter", None)
        operation = getattr(adapter, method, None)
        if not callable(operation):
            return problem_details(503, "Service Unavailable", "Operación no disponible en el transceptor", "serial_unavailable")
        try:
            return self.command_failure(await operation(*args))
        except (ValueError, TypeError):
            return problem_details(422, "Unprocessable Entity", "Parámetros rechazados por el transceptor", "invalid_serial_parameters")
        except Exception:
            logging.warning("Operación serial %s falló", method, exc_info=True)
            return problem_details(503, "Service Unavailable", "Fallo de comunicación con el transceptor", "serial_operation_failed")


def firmware_name_valid(value: Any) -> bool:
    """Companion names occupy 32-byte C strings, including the terminator."""
    return isinstance(value, str) and len(value.encode("utf-8")) <= 31 and not any(ord(char) < 0x20 for char in value)
