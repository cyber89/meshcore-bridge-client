"""Administrative entry point for the serial adapter's SDK command gateway."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.admin_handler import AdminContext


async def run_sdk_command(ctx: AdminContext, mc: Any, command: str, *args: Any, **kwargs: Any) -> Any:
    if mc is None or not hasattr(mc, "commands") or not hasattr(mc.commands, command):
        raise NotImplementedError(f"Comando SDK no disponible: {command}")
    adapter = getattr(ctx, "serial_adapter", None)
    if adapter is not None and getattr(adapter, "mc", None) is mc and hasattr(adapter, "run_sdk_command"):
        return await adapter.run_sdk_command(command, *args, **kwargs)
    result = getattr(mc.commands, command)(*args, **kwargs)
    return await result if asyncio.iscoroutine(result) else result


def require_success(response: Any, command: str) -> Any:
    """Verifica confirmación positiva del firmware / SDK para un comando."""
    if response is None or response is False:
        raise RuntimeError(f"El firmware no confirmó el comando {command}")
    event_type = getattr(response, "type", None)
    event_name = str(getattr(event_type, "name", event_type) or "").upper()
    if event_name in ("ERROR", "ERR", "COMMAND_ERROR", "LOGIN_FAILED", "DISABLED"):
        raise RuntimeError(f"El firmware rechazó el comando {command} con evento {event_name}")
    if isinstance(response, dict):
        if response.get("success") is False or str(response.get("status", "")).upper() in ("ERROR", "FAILED", "DISABLED"):
            raise RuntimeError(f"El firmware rechazó el comando {command}")
    if hasattr(response, "is_ok") and not response.is_ok:
        raise RuntimeError(f"El firmware no confirmó el comando {command}")
    if hasattr(response, "is_error") and callable(response.is_error) and response.is_error():
        raise RuntimeError(f"El firmware reportó error en el comando {command}")
    return response
