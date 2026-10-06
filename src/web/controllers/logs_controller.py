"""
Logs, messages and telemetry REST controller.
Handles /api/messages, /api/telemetry, /api/system/logs, /api/diagnostics/report*, /api/logs/*.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

from src.diagnostics import DiagnosticManager
from src.web.controllers.base import BaseController, problem_details


class LogsController(BaseController):
    """Controlador para consulta de historial de mensajes, telemetría y logs de diagnóstico."""

    async def route_logs(self, raw_path: str, clean_path: str) -> tuple[int, dict[str, Any]]:
        """Enruta consultas de logs, telemetría e informes diagnósticos."""
        limit = 100
        offset = 0
        query = parse_qs(urlsplit(raw_path).query)
        raw_limit = query.get("limit", [""])[0]
        raw_offset = query.get("offset", [""])[0]
        if raw_limit.isdigit():
            limit = int(raw_limit)
        if raw_offset.isdigit():
            offset = int(raw_offset)

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
            return await self._handle_diagnostics_report()

        if clean_path in ("/api/logs/download", "/api/logs/raw"):
            return await self._handle_raw_logs_download()

        return problem_details(404, "Not Found", "Registro no encontrado", "log_not_found")

    def _handle_system_logs(self, raw_path: str, limit: int) -> tuple[int, dict[str, Any]]:
        query = parse_qs(urlsplit(raw_path).query)
        return self.get_system_logs(query.get("level", [""])[0] or None, query.get("search", [""])[0] or None, limit)

    def get_system_logs(self, level: str | None = None, search: str | None = None, limit: int = 100) -> tuple[int, dict[str, Any]]:
        """Single reader used by HTTP and the legacy SystemController facade."""

        diag = getattr(self.ctx.bridge, "diagnostics", None)
        records: list[dict[str, Any]] = []
        if isinstance(diag, DiagnosticManager) and diag.log_handler is not None:
            total_logs = len(diag.log_handler.buffer)
            records = diag.log_handler.get_logs(level=level, search=search, limit=limit)
            counters = {
                "errors": diag.log_handler.error_count,
                "warnings": diag.log_handler.warn_count,
                "info": diag.log_handler.info_count,
                "debug": diag.log_handler.debug_count,
            }
            curr_lvl = diag.get_current_log_level()
        else:
            total_logs = len(self.ctx.system_logs)
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
            "total_logs": total_logs,
        }

    async def _handle_diagnostics_report(self) -> tuple[int, dict[str, Any]]:
        diag = getattr(self.ctx.bridge, "diagnostics", None)
        if isinstance(diag, DiagnosticManager):
            import asyncio
            md_text = await asyncio.to_thread(diag.generate_markdown_report)
        else:
            md_text = "# Reporte de Diagnóstico no disponible"
        return 200, {"status": "ok", "markdown": md_text, "text": md_text}

    async def _handle_raw_logs_download(self) -> tuple[int, dict[str, Any]]:
        diag = getattr(self.ctx.bridge, "diagnostics", None)
        if isinstance(diag, DiagnosticManager):
            if hasattr(diag, "get_raw_log_tail_async"):
                tail = await diag.get_raw_log_tail_async(lines=2000)
            else:
                import asyncio
                tail = await asyncio.to_thread(diag.get_raw_log_tail, 2000)
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
