"""
Base classes, context and RFC 7807 problem details generator for REST controllers.
"""

from __future__ import annotations

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
