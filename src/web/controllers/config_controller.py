"""
Configuration REST controller.
Handles /api/node/config, /api/node/settings, /api/node/advert, and /api/node/reboot.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from src.web.controllers.base import BaseController, problem_details


class ConfigController(BaseController):
    """Controlador para lectura y actualización de configuración del nodo local y módem LoRa."""

    async def get_device_config(self, refresh: bool = False) -> tuple[int, dict[str, Any]]:
        """Obtiene la configuración completa del nodo local consolidada con métricas en tiempo real."""
        admin = getattr(self.ctx.bridge, "admin_handler", None)
        if refresh and admin and hasattr(admin, "fetch_device_config"):
            try:
                local_cfg = await admin.fetch_device_config(force=True)
            except Exception:
                local_cfg = admin.get_local_config()
        elif admin and hasattr(admin, "get_local_config"):
            local_cfg = admin.get_local_config()
        else:
            local_cfg = {}

        if not isinstance(local_cfg, dict):
            local_cfg = {}

        bridge_uptime_sec = int(time.time() - getattr(self.ctx.bridge, "start_time", self.ctx.start_time))
        b_days = bridge_uptime_sec // 86400
        b_hours = (bridge_uptime_sec % 86400) // 3600
        b_mins = (bridge_uptime_sec % 3600) // 60
        bridge_uptime_str = f"{b_days}d {b_hours}h {b_mins}m" if b_days > 0 else (f"{b_hours}h {b_mins}m" if b_hours > 0 else f"{b_mins}m")

        # Proyectar el uptime del transceptor físico obtenido de get_stats_core
        dev_uptime = local_cfg.get("device_uptime") or local_cfg.get("uptime_secs")
        dev_sampled = local_cfg.get("device_uptime_sampled_at")
        if dev_uptime is not None and dev_sampled is not None:
            dev_uptime_sec = int(dev_uptime + (time.time() - dev_sampled))
            d_days = dev_uptime_sec // 86400
            d_hours = (dev_uptime_sec % 86400) // 3600
            d_mins = (dev_uptime_sec % 3600) // 60
            dev_uptime_str = f"{d_days}d {d_hours}h {d_mins}m" if d_days > 0 else (f"{d_hours}h {d_mins}m" if d_hours > 0 else f"{d_mins}m")
            uptime_sec = dev_uptime_sec
            uptime_str = dev_uptime_str
        else:
            dev_uptime_sec = None
            uptime_sec = bridge_uptime_sec
            uptime_str = bridge_uptime_str

        # Proyectar el reloj del transceptor físico obtenido de get_time
        dev_epoch = local_cfg.get("device_epoch_time")
        dev_time_sampled = local_cfg.get("device_time_sampled_at")
        if dev_epoch is not None and dev_time_sampled is not None:
            projected_dev_epoch = int(dev_epoch + (time.time() - dev_time_sampled))
            local_cfg["device_epoch_time"] = projected_dev_epoch
            local_cfg["device_time_drift"] = local_cfg.get("device_time_drift", int(dev_epoch - dev_time_sampled))

        limiter = getattr(self.ctx.bridge, "rate_limiter", None)
        airtime_stats = limiter.airtime_tracker.get_stats() if (limiter and hasattr(limiter, "airtime_tracker")) else {}

        rx_val = getattr(self.ctx.bridge, "rx_count", 0)
        tx_val = getattr(self.ctx.bridge, "tx_count", 0)
        err_tx = getattr(self.ctx.bridge, "tx_error_count", 0)
        err_gen = getattr(self.ctx.bridge, "err_count", 0)
        serial_adapter = getattr(self.ctx.bridge, "serial_adapter", None)
        is_ser_ok = bool(serial_adapter.is_hardware_alive()) if serial_adapter and hasattr(serial_adapter, "is_hardware_alive") else bool(getattr(serial_adapter, "is_connected", False))
        serial_port = getattr(serial_adapter, "port", "none") if serial_adapter else "none"

        local_cfg.update({
            "uptime": uptime_sec,
            "uptime_str": uptime_str,
            "device_uptime": dev_uptime_sec,
            "bridge_uptime": bridge_uptime_sec,
            "airtime_ms": airtime_stats.get("hourly_used_ms", 0),
            "duty_cycle_pct": airtime_stats.get("hourly_duty_cycle_pct", 0.0),
            "hourly_limit_pct": airtime_stats.get("hourly_limit_pct", 1.0),
            "warn_threshold_pct": airtime_stats.get("warn_threshold_pct", 80.0),
            "is_warning": airtime_stats.get("is_warning", False),
            "is_critical": airtime_stats.get("is_critical", False),
            "status_level": airtime_stats.get("status_level", "normal"),
            "channel_stats": airtime_stats.get("channel_stats", {}),
            "airtime": airtime_stats,
            "tx_count": int(tx_val) if isinstance(tx_val, (int, float)) else 0,
            "rx_count": int(rx_val) if isinstance(rx_val, (int, float)) else 0,
            "duplicate_packets": getattr(self.ctx.bridge, "dup_count", 0),
            "packet_errors": (int(err_tx) if isinstance(err_tx, (int, float)) else 0) + (int(err_gen) if isinstance(err_gen, (int, float)) else 0),
            "noise_floor_dbm": local_cfg.get("noise_floor_dbm", -118),
            "clock": datetime.now().strftime("%I:%M:%S %p"),
            "serial_connected": is_ser_ok,
            "radio_connected": is_ser_ok,
            "serial_port": serial_port,
        })
        return 200, {"status": "ok", "data": local_cfg}

    async def set_local_config(self, params: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Aplica cambios en los parámetros del transceptor o configuración de red."""
        limiter = getattr(self.ctx.bridge, "rate_limiter", None)
        if limiter and hasattr(limiter, "airtime_tracker"):
            if "duty_cycle_limit_pct" in params:
                try:
                    limiter.airtime_tracker.duty_cycle_limit_pct = float(params["duty_cycle_limit_pct"])
                except (ValueError, TypeError):
                    pass
            if "warn_threshold_pct" in params:
                try:
                    limiter.airtime_tracker.warn_threshold_pct = float(params["warn_threshold_pct"])
                except (ValueError, TypeError):
                    pass

        cmd = {"action": "set_local_config", "params": params}
        res = await self.ctx.bridge.handle_admin(cmd)
        self.ctx.log_system_event("INFO", f"Configuración de nodo local actualizada: {list(params.keys())}", source="admin")
        if self.ctx.broadcast_ws and isinstance(res, dict) and "config" in res:
            self.ctx.broadcast_ws({
                "type": "self_info",
                "data": res["config"],
                "timestamp": int(time.time()),
            })
        return 200, {"status": "ok", "data": res}

    async def broadcast_advert(self, flood: bool = False) -> tuple[int, dict[str, Any]]:
        """Emite un paquete de anuncio (advert) por radio LoRa."""
        admin = getattr(self.ctx.bridge, "admin_handler", None)
        if admin and hasattr(admin, "broadcast_advert"):
            res = await admin.broadcast_advert(flood=flood)
            mode_str = "Flood Routed (toda la malla)" if flood else "Hop 0 (vecindario directo)"
            self.ctx.log_system_event("INFO", f"📢 Anuncio Advert emitido ({mode_str})", source="admin")
            return 200, {"status": "ok", "data": res}

        return problem_details(400, "Bad Request", "Admin handler no disponible", "admin_handler_unavailable")

    async def sync_clock(self, epoch_ts: int | None = None) -> tuple[int, dict[str, Any]]:
        """Sincroniza el reloj RTC de hardware del microcontrolador con la hora del host."""
        admin = getattr(self.ctx.bridge, "admin_handler", None)
        if admin and hasattr(admin, "sync_device_clock"):
            res = await admin.sync_device_clock(epoch_ts=epoch_ts)
        else:
            now_ts = int(epoch_ts if epoch_ts is not None else time.time())
            now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
            res = {"status": "ok", "clock": now_str, "epoch": now_ts, "message": "Hora del host registrada"}

        self.ctx.log_system_event("INFO", f"Reloj RTC sincronizado: {res.get('clock')}", source="admin")
        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({
                "type": "clock_synced",
                "clock": res.get("clock"),
                "epoch": res.get("epoch"),
                "timestamp": int(time.time()),
            })
        return 200, {"status": "ok", "data": res}

    async def clear_stats(self) -> tuple[int, dict[str, Any]]:
        """Restablece los contadores de paquetes, duplicados y estadísticas de radio a cero."""
        admin = getattr(self.ctx.bridge, "admin_handler", None)
        if admin and hasattr(admin, "clear_device_stats"):
            res = await admin.clear_device_stats()
        else:
            res = {"status": "ok", "message": "Estadísticas restablecidas"}

        if hasattr(self.ctx.bridge, "rx_count"):
            self.ctx.bridge.rx_count = 0
        if hasattr(self.ctx.bridge, "tx_count"):
            self.ctx.bridge.tx_count = 0
        if hasattr(self.ctx.bridge, "dup_count"):
            self.ctx.bridge.dup_count = 0
        if hasattr(self.ctx.bridge, "err_count"):
            self.ctx.bridge.err_count = 0
        if hasattr(self.ctx.bridge, "tx_error_count"):
            self.ctx.bridge.tx_error_count = 0

        self.ctx.log_system_event("INFO", "Estadísticas y contadores de paquetes locales restablecidos a cero", source="admin")
        if self.ctx.broadcast_ws:
            self.ctx.broadcast_ws({
                "type": "metrics_reset",
                "timestamp": int(time.time()),
            })
        return 200, {"status": "ok", "data": res}

    async def refresh_hardware_config(self) -> tuple[int, dict[str, Any]]:
        """Fuerza la consulta completa y en tiempo real al hardware físico sobre el enlace serial."""
        code, resp = await self.get_device_config(refresh=True)
        if code == 200 and self.ctx.broadcast_ws and "data" in resp:
            self.ctx.broadcast_ws({
                "type": "self_info",
                "data": resp["data"],
                "timestamp": int(time.time()),
            })
        return code, resp

    async def reconnect_serial(self) -> tuple[int, dict[str, Any]]:
        """Cierra y reabre de forma segura la conexión USB/Serial con el transceptor."""
        serial_adapter = getattr(self.ctx.bridge, "serial_adapter", None)
        if serial_adapter and hasattr(serial_adapter, "reconnect"):
            try:
                await serial_adapter.reconnect()
                self.ctx.log_system_event("INFO", "Reconexión de puerto serial completada", source="serial")
                return 200, {"status": "ok", "message": "Puerto serial reconectado exitosamente"}
            except Exception as e:
                self.ctx.log_system_event("ERROR", f"Fallo al reconectar puerto serial: {e}", source="serial")
                return 500, {"status": "error", "message": f"Error reconectando: {e}"}

        # Fallback a comando admin
        res = await self.ctx.bridge.handle_admin({"action": "reconnect_serial"})
        return 200, {"status": "ok", "data": res}

    async def reboot_local(self) -> tuple[int, dict[str, Any]]:
        """Solicita reinicio de hardware del nodo local."""
        cmd = {"action": "reboot_local"}
        res = await self.ctx.bridge.handle_admin(cmd)
        self.ctx.log_system_event("WARN", "Reinicio de hardware de nodo local solicitado", source="admin")
        return 200, {"status": "ok", "data": res}

    async def get_custom_vars(self) -> tuple[int, dict[str, Any]]:
        """Obtiene el diccionario de variables personalizadas."""
        admin = getattr(self.ctx.bridge, "admin_handler", None)
        if admin and hasattr(admin, "get_custom_vars"):
            vars_dict = await admin.get_custom_vars()
        else:
            vars_dict = {}
        return 200, {"status": "ok", "custom_vars": vars_dict, "data": vars_dict}

    async def set_custom_vars(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Crea o actualiza variables personalizadas en el nodo local conforme a un esquema estricto.

        Formatos válidos:
        1. Formato clave-valor: {"key": "<nombre>", "value": "<valor>"}
        2. Formato por lote: {"vars": {"<nombre>": "<valor>", ...}}
        """
        if not isinstance(body, dict):
            return problem_details(400, "Bad Request", "El cuerpo de la solicitud debe ser un objeto JSON", "invalid_json_body")

        admin = getattr(self.ctx.bridge, "admin_handler", None)
        if not admin:
            return problem_details(503, "Service Unavailable", "Admin handler no disponible", "admin_unavailable")

        pairs: dict[str, str] = {}
        if "key" in body:
            k = str(body["key"]).strip()
            if not k:
                return problem_details(422, "Unprocessable Entity", "El campo 'key' no puede estar vacío", "empty_key")
            val = body.get("value", body.get("val", ""))
            pairs[k] = str(val) if val is not None else ""
        elif "vars" in body:
            raw_vars = body["vars"]
            if not isinstance(raw_vars, dict) or not raw_vars:
                return problem_details(422, "Unprocessable Entity", "El campo 'vars' debe ser un objeto JSON no vacío con pares clave-valor", "invalid_vars_object")
            for k, v in raw_vars.items():
                k_str = str(k).strip()
                if not k_str:
                    return problem_details(422, "Unprocessable Entity", "Las claves en 'vars' no pueden estar vacías", "empty_key_in_vars")
                pairs[k_str] = str(v) if v is not None else ""
        else:
            return problem_details(
                400,
                "Bad Request",
                "Esquema JSON no válido. Debe proporcionar {'key': 'nombre', 'value': 'valor'} o {'vars': {'nombre': 'valor'}}",
                "invalid_schema",
            )

        for k, v in pairs.items():
            await admin.set_custom_var(k, v)

        fresh_vars = await admin.get_custom_vars()
        self.ctx.log_system_event("INFO", f"Variables custom actualizadas: {list(pairs.keys())}", source="admin")
        return 200, {"status": "ok", "custom_vars": fresh_vars, "data": fresh_vars}

    async def delete_custom_var(self, key: str) -> tuple[int, dict[str, Any]]:
        """Elimina una variable personalizada."""
        clean_key = str(key).strip() if key else ""
        if not clean_key:
            return problem_details(400, "Bad Request", "Se requiere el parámetro 'key' no vacío para eliminar", "missing_key")

        admin = getattr(self.ctx.bridge, "admin_handler", None)
        if not admin:
            return problem_details(503, "Service Unavailable", "Admin handler no disponible", "admin_unavailable")
        res = await admin.delete_custom_var(clean_key)
        self.ctx.log_system_event("INFO", f"Variable custom '{clean_key}' eliminada", source="admin")
        return 200, {"status": "ok", "custom_vars": res.get("custom_vars", {}), "data": res.get("custom_vars", {})}

    async def get_path_hash_mode(self) -> tuple[int, dict[str, Any]]:
        """Obtiene el modo actual de compresión path hash."""
        admin = getattr(self.ctx.bridge, "admin_handler", None)
        mode = await admin.get_path_hash_mode() if admin and hasattr(admin, "get_path_hash_mode") else 0
        return 200, {"status": "ok", "path_hash_mode": mode, "data": {"path_hash_mode": mode}}

    async def set_path_hash_mode(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Configura el modo de compresión path hash (0, 1, 2)."""
        admin = getattr(self.ctx.bridge, "admin_handler", None)
        if not admin:
            return problem_details(503, "Service Unavailable", "Admin handler no disponible", "admin_unavailable")
        raw_mode = body.get("mode", body.get("path_hash_mode", 0))
        mode = int(raw_mode) if str(raw_mode).isdigit() else 0
        res = await admin.set_path_hash_mode(mode)
        self.ctx.log_system_event("INFO", f"Path Hash Mode configurado a {mode}", source="admin")
        return 200, {"status": "ok", "path_hash_mode": mode, "data": res}

    async def get_autoadd_config(self) -> tuple[int, dict[str, Any]]:
        """Obtiene la configuración de auto-adición de contactos."""
        admin = getattr(self.ctx.bridge, "admin_handler", None)
        cfg = await admin.get_autoadd_config() if admin and hasattr(admin, "get_autoadd_config") else {}
        return 200, {"status": "ok", "autoadd_config": cfg, "data": cfg}

    async def set_autoadd_config(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Aplica la directiva de auto-adición de contactos."""
        admin = getattr(self.ctx.bridge, "admin_handler", None)
        if not admin:
            return problem_details(503, "Service Unavailable", "Admin handler no disponible", "admin_unavailable")
        flags = int(body.get("flags", body.get("config", body.get("autoadd", 0))))
        max_hops = body.get("max_hops")
        res = await admin.set_autoadd_config(flags, int(max_hops) if max_hops is not None else None)
        self.ctx.log_system_event("INFO", f"AutoAdd config actualizado (flags={flags})", source="admin")
        return 200, {"status": "ok", "data": res}

    async def get_flood_scope(self) -> tuple[int, dict[str, Any]]:
        """Obtiene el ámbito de inundación de transporte."""
        admin = getattr(self.ctx.bridge, "admin_handler", None)
        fs = await admin.get_flood_scope() if admin and hasattr(admin, "get_flood_scope") else {}
        return 200, {"status": "ok", "flood_scope": fs, "data": fs}

    async def set_flood_scope(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Ajusta o reinicia el ámbito de inundación de transporte."""
        admin = getattr(self.ctx.bridge, "admin_handler", None)
        if not admin:
            return problem_details(503, "Service Unavailable", "Admin handler no disponible", "admin_unavailable")
        scope = body.get("scope", body.get("scope_name"))
        res = await admin.set_flood_scope(str(scope) if scope else None)
        self.ctx.log_system_event("INFO", f"Flood Scope actualizado a '{scope or 'Global'}'", source="admin")
        return 200, {"status": "ok", "data": res}

