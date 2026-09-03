"""
System and diagnostics REST controller.
Handles /api/status, /api/health, /api/system/logs, and /api/preflight.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from src.web.controllers.base import ApiContext, BaseController, problem_details


class SystemController(BaseController):
    """Controlador para métricas de salud, logs del sistema y diagnósticos preflight."""

    def _collect_health(self) -> dict[str, Any]:
        """Recolecta diagnóstico de salud de subsistemas con resiliencia y fallback."""
        if hasattr(self.ctx.bridge, "get_health") and callable(self.ctx.bridge.get_health):
            try:
                res = self.ctx.bridge.get_health()
                if isinstance(res, dict):
                    return res
            except Exception:
                pass
        diag = getattr(self.ctx.bridge, "diagnostics", None)
        if diag and hasattr(diag, "collect_health_snapshot"):
            try:
                res = diag.collect_health_snapshot()
                if isinstance(res, dict):
                    return res
            except Exception:
                pass
        serial_adapter = getattr(self.ctx.bridge, "serial_adapter", None)
        is_ser_ok = getattr(serial_adapter, "is_connected", False) if serial_adapter else False
        return {
            "status": "healthy" if is_ser_ok else "degraded",
            "timestamp": time.time(),
            "uptime_seconds": int(time.time() - getattr(self.ctx.bridge, "start_time", self.ctx.start_time)),
            "subsystems": {
                "serial_companion": {
                    "connected": is_ser_ok,
                    "port": getattr(serial_adapter, "port", "none") if serial_adapter else "none",
                },
                "mqtt_broker": {
                    "connected": getattr(getattr(self.ctx.bridge, "mqtt", None), "is_connected", False),
                },
            },
        }

    async def get_status(self) -> tuple[int, dict[str, Any]]:
        """Devuelve el estado general del bridge y métricas de salud."""
        health = self._collect_health()
        uptime_sec = int(time.time() - getattr(self.ctx.bridge, "start_time", self.ctx.start_time))
        days = uptime_sec // 86400
        hours = (uptime_sec % 86400) // 3600
        mins = (uptime_sec % 3600) // 60
        secs = uptime_sec % 60
        uptime_str = f"{days}d {hours}h {mins}m {secs}s" if days > 0 else f"{hours}h {mins}m {secs}s"

        return 200, {
            "status": "ok",
            "uptime_seconds": uptime_sec,
            "uptime_str": uptime_str,
            "health": health,
            "rx_count": getattr(self.ctx.bridge, "rx_count", 0),
            "tx_count": getattr(self.ctx.bridge, "tx_count", 0),
            "error_count": getattr(self.ctx.bridge, "err_count", 0),
            "timestamp": time.time(),
        }

    async def get_health(self) -> tuple[int, dict[str, Any]]:
        """Devuelve diagnóstico de salud específico de subsistemas."""
        return 200, {
            "status": "ok",
            "data": self._collect_health(),
        }

    async def get_logs(self, query: str = "", level: str = "", limit: int = 200) -> tuple[int, dict[str, Any]]:
        """Filtra y devuelve los registros de actividad del sistema."""
        logs = list(self.ctx.system_logs)

        if level:
            level_clean = level.strip().upper()
            logs = [entry for entry in logs if str(entry.get("level", "")).upper() == level_clean]

        if query:
            q_clean = query.strip().lower()
            logs = [entry for entry in logs if q_clean in str(entry.get("message", "")).lower()]

        if limit > 0:
            logs = logs[-limit:]

        return 200, {
            "status": "ok",
            "data": logs,
            "count": len(logs),
            "total_logs": len(self.ctx.system_logs),
        }

    async def clear_logs(self) -> tuple[int, dict[str, Any]]:
        """Limpia el buffer de registros del sistema."""
        self.ctx.system_logs.clear()
        self.ctx.log_system_event("INFO", "Buffer de logs del sistema limpiado por el usuario", source="web_admin")
        return 200, {
            "status": "ok",
            "message": "Logs limpiados con éxito",
        }

    async def run_preflight(self) -> tuple[int, dict[str, Any]]:
        """Ejecuta la suite de verificación preflight."""
        if hasattr(self.ctx.bridge, "preflight_checker") and hasattr(self.ctx.bridge.preflight_checker, "run_all"):
            report = await self.ctx.bridge.preflight_checker.run_all()
            return 200, {"status": "ok", "data": report}

        from src.preflight import PreflightChecker
        checker = PreflightChecker()
        report = await checker.run_all()
        return 200, {"status": "ok", "data": report}
