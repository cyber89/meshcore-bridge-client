"""
Logs, messages and telemetry REST controller.
Handles /api/messages, /api/telemetry, /api/system/logs, /api/diagnostics/report*, /api/logs/*.
"""

from __future__ import annotations

from typing import Any

from src.diagnostics import DiagnosticManager
from src.web.controllers.base import BaseController, problem_details


class LogsController(BaseController):
    """Controlador para consulta de historial de mensajes, telemetría y logs de diagnóstico."""

    def route_logs(self, raw_path: str, clean_path: str) -> tuple[int, dict[str, Any]]:
        """Enruta consultas de logs, telemetría e informes diagnósticos."""
        limit = 100
        offset = 0
        if "?" in raw_path:
            for part in raw_path.split("?", 1)[1].split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    if k.lower() == "limit" and v.isdigit():
                        limit = int(v)
                    elif k.lower() == "offset" and v.isdigit():
                        offset = int(v)

        if clean_path == "/api/messages":
            all_messages = list(self.ctx.recent_messages)
            msgs_page = all_messages[offset : offset + limit]
            return 200, {
                "status": "ok",
                "data": msgs_page,
                "count": len(msgs_page),
                "total_count": len(all_messages),
                "limit": limit,
                "offset": offset,
            }

        if clean_path == "/api/telemetry":
            telem_source = self.ctx.recent_telemetry if self.ctx.recent_telemetry is not None else []
            all_telemetry = list(telem_source)
            telem_page = all_telemetry[offset : offset + limit]
            return 200, {
                "status": "ok",
                "data": telem_page,
                "count": len(telem_page),
                "total_count": len(all_telemetry),
                "limit": limit,
                "offset": offset,
            }

        if clean_path == "/api/system/logs":
            return self._handle_system_logs(raw_path, limit)

        if clean_path in ("/api/diagnostics/report.md", "/api/diagnostics/report"):
            return self._handle_diagnostics_report()

        if clean_path in ("/api/logs/download", "/api/logs/raw"):
            return self._handle_raw_logs_download()

        return problem_details(404, "Not Found", "Registro no encontrado", "log_not_found")

    def _handle_system_logs(self, raw_path: str, limit: int) -> tuple[int, dict[str, Any]]:
        level = None
        search = None
        if "?" in raw_path:
            for part in raw_path.split("?", 1)[1].split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    if k.lower() == "level":
                        level = v
                    elif k.lower() == "search":
                        search = v

        diag = getattr(self.ctx.bridge, "diagnostics", None)
        records: list[dict[str, Any]] = []
        if isinstance(diag, DiagnosticManager) and diag.log_handler is not None:
            records = diag.log_handler.get_logs(level=level, search=search, limit=limit)
            counters = {
                "errors": diag.log_handler.error_count,
                "warnings": diag.log_handler.warn_count,
                "info": diag.log_handler.info_count,
                "debug": diag.log_handler.debug_count,
            }
            curr_lvl = diag.get_current_log_level()
        else:
            records = list(self.ctx.system_logs)
            if level:
                target_lvl = level.strip().upper()
                records = [r for r in records if r.get("level") == target_lvl]
            if search:
                search_low = search.strip().lower()
                records = [r for r in records if search_low in str(r.get("message", "")).lower()]
            if limit and len(records) > limit:
                records = records[-limit:]
            counters = {
                "errors": sum(1 for r in self.ctx.system_logs if r.get("level") in ("ERROR", "CRITICAL")),
                "warnings": sum(1 for r in self.ctx.system_logs if r.get("level") in ("WARNING", "WARN")),
                "info": sum(1 for r in self.ctx.system_logs if r.get("level") == "INFO"),
                "debug": sum(1 for r in self.ctx.system_logs if r.get("level") == "DEBUG"),
            }
            curr_lvl = "INFO"

        return 200, {
            "status": "ok",
            "data": records,
            "count": len(records),
            "counters": counters,
            "current_level": curr_lvl,
        }

    def _handle_diagnostics_report(self) -> tuple[int, dict[str, Any]]:
        diag = getattr(self.ctx.bridge, "diagnostics", None)
        if isinstance(diag, DiagnosticManager):
            md_text = diag.generate_markdown_report()
        else:
            md_text = "# Reporte de Diagnóstico no disponible"
        return 200, {"status": "ok", "markdown": md_text, "text": md_text}

    def _handle_raw_logs_download(self) -> tuple[int, dict[str, Any]]:
        diag = getattr(self.ctx.bridge, "diagnostics", None)
        if isinstance(diag, DiagnosticManager):
            tail = diag.get_raw_log_tail(lines=2000)
            log_file = diag.get_raw_log_path()
        else:
            tail = "\n".join(f"[{r.get('iso_time')}] [{r.get('level')}] {r.get('message')}" for r in self.ctx.system_logs)
            log_file = None
        return 200, {
            "status": "ok",
            "raw_logs": tail,
            "log_file": log_file,
            "line_count": len(tail.splitlines()),
        }
