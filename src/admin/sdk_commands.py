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
    event_type = getattr(response, "type", None)
    event_name = str(getattr(event_type, "name", event_type) or "").upper()
    if response is None or event_name in ("ERROR", "ERR", "COMMAND_ERROR", "LOGIN_FAILED"):
        raise RuntimeError(f"El firmware no confirmó el comando {command}")
    return response
