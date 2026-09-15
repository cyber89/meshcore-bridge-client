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

        uptime_sec = int(time.time() - getattr(self.ctx.bridge, "start_time", self.ctx.start_time))
        days = uptime_sec // 86400
        hours = (uptime_sec % 86400) // 3600
        mins = (uptime_sec % 3600) // 60
        secs = uptime_sec % 60
        uptime_str = f"{days}d {hours}h {mins}m {secs}s" if days > 0 else (f"{hours}h {mins}m {secs}s" if hours > 0 else f"{mins}m {secs}s")

        limiter = getattr(self.ctx.bridge, "rate_limiter", None)
        airtime_stats = limiter.airtime_tracker.get_stats() if (limiter and hasattr(limiter, "airtime_tracker")) else {}

        rx_val = getattr(self.ctx.bridge, "rx_count", 0)
        tx_val = getattr(self.ctx.bridge, "tx_count", 0)
        err_tx = getattr(self.ctx.bridge, "tx_error_count", 0)
        err_gen = getattr(self.ctx.bridge, "err_count", 0)
        last_snr = getattr(self.ctx.bridge, "last_rx_snr", None)
        last_rssi = getattr(self.ctx.bridge, "last_rx_rssi", None)

        if (last_snr is None or last_rssi is None) and hasattr(self.ctx.bridge, "node_registry") and hasattr(self.ctx.bridge.node_registry, "list_nodes"):
            remote_nodes = [
                n for n in self.ctx.bridge.node_registry.list_nodes()
                if not n.get("is_local") and str(n.get("role")).upper() != "LOCAL" and (n.get("last_snr") is not None or n.get("last_rssi") is not None)
            ]
            if remote_nodes:
                remote_nodes.sort(key=lambda x: float(x.get("last_seen") or 0.0), reverse=True)
                if last_snr is None and remote_nodes[0].get("last_snr") is not None:
                    last_snr = remote_nodes[0].get("last_snr")
                if last_rssi is None and remote_nodes[0].get("last_rssi") is not None:
                    last_rssi = remote_nodes[0].get("last_rssi")

        serial_adapter = getattr(self.ctx.bridge, "serial_adapter", None)
        is_ser_ok = getattr(serial_adapter, "is_connected", False) if serial_adapter else False
        serial_port = getattr(serial_adapter, "port", "none") if serial_adapter else "none"

        local_cfg.update({
            "uptime": uptime_sec,
            "uptime_str": uptime_str,
            "airtime_ms": airtime_stats.get("hourly_used_ms", 0),
            "duty_cycle_pct": airtime_stats.get("hourly_duty_cycle_pct", 0.0),
            "tx_count": int(tx_val) if isinstance(tx_val, (int, float)) else 0,
            "rx_count": int(rx_val) if isinstance(rx_val, (int, float)) else 0,
            "duplicate_packets": getattr(self.ctx.bridge, "dup_count", 0),
            "packet_errors": (int(err_tx) if isinstance(err_tx, (int, float)) else 0) + (int(err_gen) if isinstance(err_gen, (int, float)) else 0),
            "noise_floor_dbm": local_cfg.get("noise_floor_dbm", -118),
            "clock": datetime.now().strftime("%I:%M:%S %p"),
            "last_snr": last_snr,
            "last_rssi": last_rssi,
            "serial_connected": is_ser_ok,
            "radio_connected": is_ser_ok,
            "serial_port": serial_port,
        })
        return 200, {"status": "ok", "data": local_cfg}

    async def set_local_config(self, params: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Aplica cambios en los parámetros del transceptor o configuración de red."""
        cmd = {"action": "set_local_config", "params": params}
        res = await self.ctx.bridge.handle_admin(cmd)
        self.ctx.log_system_event("INFO", f"Configuración de nodo local actualizada: {list(params.keys())}", source="admin")
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
