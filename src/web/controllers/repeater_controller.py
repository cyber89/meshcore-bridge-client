"""
Repeater and admin commands REST controller.
Handles /api/admin/command, /api/admin/repeater, and /api/repeater/remote/*.
"""

from __future__ import annotations

import time
from typing import Any

from src.protocol_types import redact_sensitive_mapping
from src.web.controllers.base import BaseController, problem_details


class RepeaterController(BaseController):
    """Controlador para administración remota de repetidores, login, telemetría y diagnósticos."""

    def _remote_failure(self, result: Any) -> tuple[int, dict[str, Any]] | None:
        """Keep dispatch distinct from a remote confirmation, including partial details."""
        if isinstance(result, dict) and result.get("status") == "dispatched" and not result.get("error"):
            return None
        failure = self.command_failure(result)
        if failure is not None and isinstance(result, dict):
            failure[1]["data"] = redact_sensitive_mapping(result)
        return failure

    async def execute_admin_command(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Ejecuta un comando de administración directa."""
        action = req_body.get("action")
        res = await self.ctx.bridge.handle_admin(req_body)
        failure = self._remote_failure(res)
        if failure:
            return failure
        self.ctx.log_system_event("INFO", f"Comando admin ejecutado: {action}", source="admin")
        out_msg = ""
        if isinstance(res, dict):
            out_msg = str(res.get("result") or res.get("message") or "")
        return 200, {"status": "ok", "result": res, "response": out_msg, "message": out_msg}

    async def execute_repeater_command(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Enruta un comando hacia un repetidor remoto."""
        target_node = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
        action = str(req_body.get("action", req_body.get("command", "stats-radio")))
        if not target_node:
            return problem_details(400, "Bad Request", "Se requiere 'target_node'", "missing_target_node")

        cmd_data = {
            "target_node": target_node,
            "action": action,
            "params": req_body.get("params", {}),
            "password": req_body.get("password", ""),
            "request_id": req_body.get("request_id", f"web_rep_{int(time.time())}"),
        }
        res = await self.ctx.bridge.handle_admin(cmd_data)
        failure = self._remote_failure(res)
        if failure:
            return failure

        self.ctx.log_system_event("INFO", f"Comando RF a repetidor {target_node}: {action}", source="repeater_admin")
        return 200, {"status": "ok", "data": res}

    async def login(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Autentica sesión administrativa con un repetidor remoto."""
        target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
        raw_pwd = req_body.get("password")
        pwd = str(raw_pwd) if raw_pwd is not None else ""
        if not target:
            return problem_details(400, "Bad Request", "Se requiere 'target_node'", "missing_target_node")
        if len(pwd) == 0:
            return problem_details(400, "Bad Request", "La contraseña de administración no puede estar vacía", "empty_password")

        cmd = {"action": "login", "target_node": target, "password": pwd}
        res = await self.ctx.bridge.handle_admin(cmd)
        if isinstance(res, dict) and res.get("authenticated") is False:
            return problem_details(401, "Unauthorized", "Autenticación no confirmada por el repetidor", "auth_failed", {"data": res})
        failure = self.command_failure(res)
        if failure:
            return failure
        if res.get("status") == "error" or not res.get("authenticated", False):
            msg = res.get("message", "Contraseña incorrecta o sin respuesta del repetidor")
            self.ctx.log_system_event("WARN", f"Fallo de autenticación con repetidor {target}: {msg}", source="repeater_admin")
            return problem_details(401, "Unauthorized", msg, "auth_failed", {"data": res})

        self.ctx.log_system_event("INFO", f"Autenticación exitosa con repetidor {target}", source="repeater_admin")
        return 200, {"status": "ok", "data": res}

    async def logout(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Cierra sesión con un repetidor remoto."""
        target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
        if not target:
            return problem_details(400, "Bad Request", "Se requiere 'target_node'", "missing_target_node")

        cmd = {"action": "logout", "target_node": target}
        res = await self.ctx.bridge.handle_admin(cmd)
        failure = self._remote_failure(res)
        if failure:
            return failure

        self.ctx.log_system_event("INFO", f"Sesión cerrada en repetidor {target}", source="repeater_admin")
        return 200, {"status": "ok", "data": res}

    async def set_remote_config(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Aplica configuración remota en un repetidor."""
        target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
        pwd = str(req_body.get("password", "")) if req_body.get("password") is not None else ""
        params = req_body.get("params", {})
        if not target:
            return problem_details(400, "Bad Request", "Se requiere 'target_node'", "missing_target_node")

        cmd = {
            "action": "remote_repeater_set_config",
            "target_node": target,
            "password": pwd,
            "params": params,
        }
        res = await self.ctx.bridge.handle_admin(cmd)
        failure = self._remote_failure(res)
        if failure:
            return failure

        self.ctx.log_system_event("INFO", f"Configuración remota despachada a repetidor {target}", source="repeater_admin")
        return 200, {"status": "ok", "data": res}

    async def execute_remote_action(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Ejecuta una acción administrativa en un repetidor (reboot, set freq, etc.)."""
        target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
        pwd = str(req_body.get("password", "")) if req_body.get("password") is not None else ""
        action_name = str(req_body.get("action", "")).strip()
        if not target or not action_name:
            return problem_details(400, "Bad Request", "Se requieren 'target_node' y 'action'", "missing_fields")

        cmd = {
            "action": action_name,
            "target_node": target,
            "password": pwd,
            "params": req_body.get("params", {}),
        }
        res = await self.ctx.bridge.handle_admin(cmd)
        failure = self._remote_failure(res)
        if failure:
            return failure

        self.ctx.log_system_event("INFO", f"Acción remota '{action_name}' despachada a repetidor {target}", source="repeater_admin")
        return 200, {"status": "ok", "data": res}

    async def ping_zero(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Envía un ping directo de 0 saltos para medir RTT y verificar enlace."""
        target = str(req_body.get("target_node", req_body.get("repeater", req_body.get("target", "")))).strip()
        if not target:
            return problem_details(400, "Bad Request", "Se requiere 'target_node'", "missing_target_node")

        cmd = {
            "action": "ping_zero",
            "target_node": target,
        }
        res = await self.ctx.bridge.handle_admin(cmd)
        failure = self._remote_failure(res)
        if failure:
            return failure

        self.ctx.log_system_event("INFO", f"🎯 Ping Zero (0 saltos) enviado a {target} - RTT: {res.get('rtt_ms')} ms", source="repeater_admin")
        return 200, {"status": "ok", "data": res}

    async def traceroute(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Inicia una traza de ruta multi-salto hacia un nodo remoto."""
        target = str(req_body.get("target_node", req_body.get("target", req_body.get("repeater", req_body.get("to", ""))))).strip()
        if not target:
            return problem_details(400, "Bad Request", "Se requiere 'target_node'", "missing_target_node")

        cmd = {
            "action": "traceroute",
            "target_node": target,
        }
        res = await self.ctx.bridge.handle_admin(cmd)
        failure = self._remote_failure(res)
        if failure:
            return failure

        self.ctx.log_system_event("INFO", f"🗺️ Traceroute completado hacia {target} ({res.get('hop_count', 0)} saltos)", source="admin")
        return 200, {"status": "ok", "data": res}

    async def get_neighbours(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Consulta binaria de la tabla de vecinos zero-hop de un repetidor remoto."""
        target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
        if not target:
            return problem_details(400, "Bad Request", "Se requiere 'target_node'", "missing_target_node")
        cmd = {
            "action": "req_neighbours",
            "target_node": target,
            "count": req_body.get("count", 255),
            "offset": req_body.get("offset", 0),
            "password": req_body.get("password", ""),
        }
        res = await self.ctx.bridge.handle_admin(cmd)
        failure = self._remote_failure(res)
        if failure:
            return failure
        self.ctx.log_system_event("INFO", f"Vecinos consultados para repetidor {target}", source="repeater_admin")
        return 200, {"status": "ok", "data": res}

    async def get_owner(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Consulta anónima de la información de propietario de un repetidor remoto."""
        target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
        if not target:
            return problem_details(400, "Bad Request", "Se requiere 'target_node'", "missing_target_node")
        cmd = {"action": "req_owner", "target_node": target, "password": req_body.get("password", "")}
        res = await self.ctx.bridge.handle_admin(cmd)
        failure = self._remote_failure(res)
        if failure:
            return failure
        return 200, {"status": "ok", "data": res}

    async def get_regions(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Consulta de regiones configuradas en un repetidor remoto."""
        target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
        if not target:
            return problem_details(400, "Bad Request", "Se requiere 'target_node'", "missing_target_node")
        cmd = {"action": "req_regions", "target_node": target, "password": req_body.get("password", "")}
        res = await self.ctx.bridge.handle_admin(cmd)
        failure = self._remote_failure(res)
        if failure:
            return failure
        return 200, {"status": "ok", "data": res}

    async def get_clock(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Consulta de reloj RTC y estado básico de un repetidor remoto."""
        target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
        if not target:
            return problem_details(400, "Bad Request", "Se requiere 'target_node'", "missing_target_node")
        cmd = {"action": "req_clock", "target_node": target, "password": req_body.get("password", "")}
        res = await self.ctx.bridge.handle_admin(cmd)
        failure = self._remote_failure(res)
        if failure:
            return failure
        return 200, {"status": "ok", "data": res}

    async def get_acl(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Consulta de tabla de control de acceso (ACL) de un repetidor remoto."""
        target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
        if not target:
            return problem_details(400, "Bad Request", "Se requiere 'target_node'", "missing_target_node")
        cmd = {"action": "req_acl", "target_node": target, "password": req_body.get("password", "")}
        res = await self.ctx.bridge.handle_admin(cmd)
        failure = self._remote_failure(res)
        if failure:
            return failure
        return 200, {"status": "ok", "data": res}

