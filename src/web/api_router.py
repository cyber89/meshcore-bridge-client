"""
Web API Router and REST Controller for MeshCore Web Client.
Procesa solicitudes HTTP REST para mensajería, gestión de contactos, canales cifrados,
telemetría, sniffer de paquetes RF, métricas analíticas avanzadas y consola de logs.
"""

from __future__ import annotations

import collections
import logging
import time
from datetime import datetime
from typing import Any

from src.contact_manager import NodeContactUpdate, PacketRecord


class WebAPIRouter:
    """Enrutador modular de API REST para el cliente web de MeshCore Bridge."""

    def __init__(self, bridge: Any) -> None:
        self.bridge = bridge
        self.channels: dict[int, dict[str, Any]] = {
            0: {"index": 0, "name": "Public / Broadcast", "psk": "", "is_public": True},
        }
        self.recent_messages: collections.deque[dict[str, Any]] = collections.deque(maxlen=200)
        self.recent_telemetry: collections.deque[dict[str, Any]] = collections.deque(maxlen=200)
        self.recent_rf_logs: collections.deque[dict[str, Any]] = collections.deque(maxlen=300)
        self.recent_system_logs: collections.deque[dict[str, Any]] = collections.deque(maxlen=300)
        self.sniffer_active = False

    def log_system_event(self, level: str, message: str, source: str = "bridge") -> None:
        """Registra un evento interno en el búfer de logs del sistema."""
        now_ts = float(time.time())
        now_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        lvl_upper = level.upper()

        entry = {
            "timestamp": int(now_ts),
            "iso_time": now_iso,
            "level": lvl_upper,
            "source": source,
            "message": message,
        }
        self.recent_system_logs.append(entry)

        diag = getattr(self.bridge, "diagnostics", None)
        if diag and getattr(diag, "log_handler", None):
            from src.diagnostics import SystemLogRecord

            rec = SystemLogRecord(
                timestamp=now_ts,
                iso_time=now_iso,
                level=lvl_upper,
                logger_name=f"bridge.{source}",
                module=source,
                func_name="log_system_event",
                line_no=0,
                message=message,
                source=source,
            )
            diag.log_handler.buffer.append(rec)
            if lvl_upper in ("ERROR", "CRITICAL"):
                diag.log_handler.error_count += 1
            elif lvl_upper in ("WARNING", "WARN"):
                diag.log_handler.warn_count += 1
            elif lvl_upper == "INFO":
                diag.log_handler.info_count += 1
            else:
                diag.log_handler.debug_count += 1

    def record_incoming_event(self, event_data: dict[str, Any]) -> None:
        """Almacena eventos recientes para consulta del cliente web y actualiza métricas."""
        ev_type = str(event_data.get("event_type", ""))
        if ev_type in ("system_log", "metrics_update", "status"):
            return

        sender = str(event_data.get("sender", event_data.get("sender_id", ""))).strip().lower()
        metrics = event_data.get("metrics", {})
        rssi = metrics.get("rssi")
        snr = metrics.get("snr")

        if ev_type == "rf_log" or "sniffer" in ev_type:
            rf_entry = dict(event_data)
            rf_entry["iso_time"] = time.strftime("%H:%M:%S", time.localtime())
            self.recent_rf_logs.append(rf_entry)
            self.log_system_event("INFO", f"RF Sniffer interceptó trama de {rf_entry.get('byte_length', 0)} bytes", source="sniffer")

        elif ev_type in ("telemetry", "telemetry_recv") or "temperature_c" in event_data or "battery_pct" in event_data or "battery" in event_data:
            self.recent_telemetry.append(event_data)
            if sender and sender != "unknown":
                self.bridge.node_registry.record_packet(PacketRecord(public_key=sender, is_rx=True, rssi=rssi, snr=snr, telemetry=event_data))
            self.log_system_event("INFO", f"Telemetría ambiental recibida de nodo {sender}", source="telemetry")

        elif ev_type in ("public", "channel", "direct") or bool(event_data.get("text")):
            self.recent_messages.append(event_data)
            if sender and sender != "unknown":
                self.bridge.node_registry.record_packet(PacketRecord(public_key=sender, is_rx=True, rssi=rssi, snr=snr))
            self.log_system_event("INFO", f"Mensaje RX [{ev_type}] de {sender}: {str(event_data.get('text', ''))[:30]}", source="mesh_rx")

    async def handle_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Maneja una solicitud REST despachando al sub-manejador correspondiente."""
        clean_path = path.split("?")[0].rstrip("/")
        req_body = body or {}

        try:
            if method == "GET" and clean_path == "/api/status":
                return await self._route_status()

            if method == "GET" and clean_path == "/api/nodes":
                nodes = self.bridge.node_registry.list_nodes()
                return 200, {"status": "ok", "data": nodes, "count": len(nodes)}

            if method == "GET" and clean_path in ("/api/analytics", "/api/metrics/analytics"):
                return await self._route_analytics()

            if clean_path in ("/api/contacts", "/api/contacts/sync"):
                return await self._route_contacts(clean_path, method, req_body)

            if clean_path in ("/api/channels", "/api/channels/sync"):
                return await self._route_channels(clean_path, method, req_body)

            if method == "POST" and clean_path == "/api/tx":
                return await self._route_tx(req_body)

            if method == "POST" and clean_path == "/api/sniffer/control":
                return await self._route_sniffer(req_body)

            if method == "POST" and clean_path == "/api/admin/command":
                res = await self.bridge.handle_admin(req_body)
                self.log_system_event("INFO", f"Comando admin ejecutado: {req_body.get('action')}", source="admin")
                return 200, {"status": "ok", "result": res}

            if method == "POST" and clean_path == "/api/admin/repeater":
                return await self._route_admin_repeater(req_body)

            if method == "GET" and clean_path in ("/api/node/config", "/api/node/settings"):
                admin = getattr(self.bridge, "admin_handler", None)
                local_cfg = admin.get_local_config() if (admin and hasattr(admin, "get_local_config")) else {}

                # Consolidar métricas en tiempo real del bridge
                uptime_sec = int(time.time() - getattr(self.bridge, "start_time", time.time()))
                days = uptime_sec // 86400
                hours = (uptime_sec % 86400) // 3600
                mins = (uptime_sec % 3600) // 60
                secs = uptime_sec % 60
                uptime_str = f"{days}d {hours}h {mins}m {secs}s" if days > 0 else (f"{hours}h {mins}m {secs}s" if hours > 0 else f"{mins}m {secs}s")

                limiter = getattr(self.bridge, "rate_limiter", None)
                airtime_stats = limiter.airtime_tracker.get_stats() if (limiter and hasattr(limiter, "airtime_tracker")) else {}

                rx_val = getattr(self.bridge, "rx_count", 0)
                tx_val = getattr(self.bridge, "tx_count", 0)
                err_tx = getattr(self.bridge, "tx_error_count", 0)
                err_gen = getattr(self.bridge, "err_count", 0)

                local_cfg.update({
                    "uptime": uptime_sec,
                    "uptime_str": uptime_str,
                    "airtime_ms": airtime_stats.get("hourly_used_ms", 0),
                    "duty_cycle_pct": airtime_stats.get("hourly_duty_cycle_pct", 0.0),
                    "tx_count": int(tx_val) if isinstance(tx_val, (int, float)) else 0,
                    "rx_count": int(rx_val) if isinstance(rx_val, (int, float)) else 0,
                    "duplicate_packets": getattr(self.bridge, "dup_count", 0),
                    "packet_errors": (int(err_tx) if isinstance(err_tx, (int, float)) else 0) + (int(err_gen) if isinstance(err_gen, (int, float)) else 0),
                    "noise_floor_dbm": local_cfg.get("noise_floor_dbm", -118),
                    "clock": datetime.now().strftime("%I:%M:%S %p"),
                })
                return 200, {"status": "ok", "data": local_cfg}

            if method == "POST" and clean_path in ("/api/node/config", "/api/node/settings"):
                cmd = {"action": "set_local_config", "params": req_body}
                res = await self.bridge.handle_admin(cmd)
                self.log_system_event("INFO", f"Configuración de nodo local actualizada: {list(req_body.keys())}", source="admin")
                return 200, {"status": "ok", "data": res}

            if method == "POST" and clean_path == "/api/node/advert":
                flood = bool(req_body.get("flood", False))
                admin = getattr(self.bridge, "admin_handler", None)
                if admin and hasattr(admin, "broadcast_advert"):
                    res = await admin.broadcast_advert(flood=flood)
                    mode_str = "Flood Routed (toda la malla)" if flood else "Hop 0 (vecindario directo)"
                    self.log_system_event("INFO", f"📢 Anuncio Advert emitido ({mode_str})", source="admin")
                    return 200, {"status": "ok", "data": res}
                return 400, {"status": "error", "message": "Admin handler no disponible"}

            if method == "POST" and clean_path == "/api/node/reboot":
                cmd = {"action": "reboot_local"}
                res = await self.bridge.handle_admin(cmd)
                self.log_system_event("WARN", "Reinicio de hardware de nodo local solicitado", source="admin")
                return 200, {"status": "ok", "data": res}

            if method == "POST" and clean_path == "/api/repeater/remote/login":
                target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
                pwd = str(req_body.get("password", "")).strip()
                if not target:
                    return 400, {"status": "error", "message": "Se requiere 'target_node'"}
                if not pwd:
                    return 400, {"status": "error", "message": "La contraseña de administración no puede estar vacía"}
                cmd = {"action": "login", "target_node": target, "password": pwd}
                res = await self.bridge.handle_admin(cmd)
                if res.get("status") == "error":
                    return 400, res
                self.log_system_event("INFO", f"Intento de autenticación enviado a repetidor {target}", source="repeater_admin")
                return 200, {"status": "ok", "data": res}

            if method == "POST" and clean_path == "/api/repeater/remote/config":
                target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
                pwd = str(req_body.get("password", "")).strip()
                params = req_body.get("params", {})
                if not target:
                    return 400, {"status": "error", "message": "Se requiere 'target_node'"}
                cmd = {
                    "action": "remote_repeater_set_config",
                    "target_node": target,
                    "password": pwd,
                    "params": params,
                }
                res = await self.bridge.handle_admin(cmd)
                if res.get("status") == "error":
                    return 400, res
                self.log_system_event("INFO", f"Configuración remota despachada a repetidor {target}", source="repeater_admin")
                return 200, {"status": "ok", "data": res}

            if method == "POST" and clean_path == "/api/repeater/remote/action":
                target = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
                pwd = str(req_body.get("password", "")).strip()
                action_name = str(req_body.get("action", "")).strip()
                if not target or not action_name:
                    return 400, {"status": "error", "message": "Se requieren 'target_node' y 'action'"}
                cmd = {
                    "action": action_name,
                    "target_node": target,
                    "password": pwd,
                    "params": req_body.get("params", {}),
                }
                res = await self.bridge.handle_admin(cmd)
                if res.get("status") == "error":
                    return 400, res
                self.log_system_event("INFO", f"Acción remota '{action_name}' despachada a repetidor {target}", source="repeater_admin")
                return 200, {"status": "ok", "data": res}

            if method == "POST" and clean_path in ("/api/repeater/ping_zero", "/api/node/ping_zero"):
                target = str(req_body.get("target_node", req_body.get("repeater", req_body.get("target", "")))).strip()
                pwd = str(req_body.get("password", "")).strip()
                if not target:
                    return 400, {"status": "error", "message": "Se requiere 'target_node'"}
                cmd = {
                    "action": "ping_zero",
                    "target_node": target,
                    "password": pwd,
                }
                res = await self.bridge.handle_admin(cmd)
                if res.get("status") == "error":
                    return 400, res
                self.log_system_event("INFO", f"🎯 Ping Zero (0 saltos) enviado a {target} - RTT: {res.get('rtt_ms')} ms", source="repeater_admin")
                return 200, {"status": "ok", "data": res}

            if method == "GET" and clean_path == "/api/airtime/stats":
                limiter = getattr(self.bridge, "rate_limiter", None)
                stats = (
                    limiter.airtime_tracker.get_stats()
                    if limiter and hasattr(limiter, "airtime_tracker")
                    else {
                        "hourly_used_ms": 0.0,
                        "hourly_budget_ms": 36000.0,
                        "hourly_duty_cycle_pct": 0.0,
                        "hourly_limit_pct": 1.0,
                        "hourly_packets": 0,
                        "daily_used_ms": 0.0,
                        "total_airtime_ms": 0.0,
                        "total_packets": 0,
                        "is_throttled": False,
                        "channel_stats": {},
                    }
                )
                return 200, {"status": "ok", "data": stats}

            if method == "GET" and clean_path == "/api/rf/heatmap":
                nodes = self.bridge.node_registry.list_nodes()
                heatmap_points = []
                for n in nodes:
                    lat = n.get("latitude")
                    lon = n.get("longitude")
                    if lat is not None and lon is not None and lat != 0.0 and lon != 0.0:
                        rssi = n.get("last_rssi")
                        snr = n.get("last_snr")
                        rssi_val = rssi if rssi is not None else -100
                        weight = max(0.1, min(1.0, round((rssi_val + 120.0) / 70.0, 2)))
                        heatmap_points.append({
                            "lat": lat,
                            "lon": lon,
                            "rssi": rssi,
                            "snr": snr,
                            "name": n.get("name") or n.get("alias") or n.get("public_key", "")[:8],
                            "role": n.get("role", "CLIENT"),
                            "weight": weight,
                            "noise_floor": n.get("noise_floor_dbm"),
                        })
                return 200, {"status": "ok", "data": {"points": heatmap_points, "count": len(heatmap_points)}}

            if method == "GET" and clean_path == "/api/rf/noise":
                nodes = self.bridge.node_registry.list_nodes()
                noise_matrix = []
                for n in nodes:
                    noise_matrix.append({
                        "pubkey": n.get("public_key"),
                        "name": n.get("name") or n.get("alias"),
                        "role": n.get("role"),
                        "noise_floor_dbm": n.get("noise_floor_dbm"),
                        "snr": n.get("last_snr"),
                        "rssi": n.get("last_rssi"),
                        "channel": n.get("channel", 0),
                        "freq": n.get("frequency", 915.0),
                    })
                return 200, {"status": "ok", "data": {"matrix": noise_matrix}}

            if method == "GET" and clean_path == "/api/contacts/discovered":
                discovered = self.bridge.node_registry.list_discovered()
                return 200, {"status": "ok", "data": {"discovered": discovered, "count": len(discovered)}}

            if method == "POST" and clean_path == "/api/contacts/accept":
                pubkey = str(req_body.get("public_key", req_body.get("target_node", ""))).strip()
                if not pubkey:
                    return 400, {"status": "error", "message": "Se requiere 'public_key'"}
                success = self.bridge.node_registry.accept_discovered_contact(pubkey)
                return 200, {"status": "ok" if success else "error", "accepted": success}

            if method == "POST" and clean_path == "/api/traceroute":
                target = str(req_body.get("target_node", req_body.get("target", ""))).strip()
                path = req_body.get("path", [])
                if not target:
                    return 400, {"status": "error", "message": "Se requiere 'target_node'"}
                cmd = {
                    "action": "traceroute",
                    "target_node": target,
                    "path": path,
                }
                res = await self.bridge.handle_admin(cmd)
                self.log_system_event("INFO", f"🗺️ Traceroute ejecutado hacia {target} - Saltos: {res.get('total_hops', 0)}", source="repeater_admin")
                return 200, {"status": "ok", "data": res}

            if method == "GET" and clean_path == "/api/ha/status":
                ha = getattr(self.bridge, "ha_discovery", None)
                enabled = getattr(ha, "enabled", False) if ha else False
                count = len(getattr(ha, "_discovered_entities", set())) if ha else 0
                return 200, {"status": "ok", "data": {"enabled": enabled, "discovered_nodes": count}}

            if method == "POST" and clean_path == "/api/ha/publish":
                published = await self._trigger_ha_publish()
                return 200, {"status": "ok", "data": {"published_entities": published}}

            if method == "GET" and clean_path == "/api/preflight":
                report = self._run_preflight_diagnostics()
                return 200, {"status": "ok", "data": report}

            if method == "GET" and clean_path == "/api/diagnostics":
                diag = getattr(self.bridge, "diagnostics", None)
                data = diag.collect_health_snapshot() if diag else {}
                return 200, {"status": "ok", "data": data}

            if method == "GET" and clean_path == "/api/diagnostics/export":
                diag = getattr(self.bridge, "diagnostics", None)
                data = diag.generate_full_diagnostic_bundle() if diag else {}
                return 200, {"status": "ok", "data": data}

            if method == "GET" and clean_path == "/api/system/logs/level":
                diag = getattr(self.bridge, "diagnostics", None)
                lvl = diag.get_current_log_level() if diag else "INFO"
                return 200, {"status": "ok", "level": lvl}

            if method == "POST" and clean_path == "/api/system/logs/level":
                diag = getattr(self.bridge, "diagnostics", None)
                target_lvl = req_body.get("level", "INFO")
                if diag:
                    new_lvl = diag.set_log_level(str(target_lvl))
                    return 200, {"status": "ok", "level": new_lvl}
                return 400, {"status": "error", "message": "Diagnostic manager no disponible"}

            if method == "DELETE" and clean_path == "/api/system/logs":
                diag = getattr(self.bridge, "diagnostics", None)
                if diag and diag.log_handler:
                    diag.log_handler.clear()
                self.recent_system_logs.clear()
                return 200, {"status": "ok", "message": "Logs del sistema limpiados"}

            if method == "POST" and clean_path == "/api/trace":
                return await self._route_trace(req_body)

            if method == "GET" and clean_path in (
                "/api/messages",
                "/api/telemetry",
                "/api/logs",
                "/api/sniffer/logs",
                "/api/sniffer/packets",
                "/api/system/logs",
                "/api/diagnostics/report.md",
                "/api/diagnostics/report",
                "/api/logs/download",
                "/api/logs/raw",
            ):
                return self._route_logs(path, clean_path)

            return 404, {"status": "error", "message": f"Ruta no encontrada: {method} {clean_path}"}

        except Exception as e:
            logging.error(f"Error procesando solicitud REST {method} {clean_path}: {e}", exc_info=True)
            self.log_system_event("ERROR", f"Fallo en API {method} {clean_path}: {e}", source="api")
            return 500, {"status": "error", "message": str(e)}

    async def _route_status(self) -> tuple[int, dict[str, Any]]:
        rx_val = getattr(self.bridge, "rx_count", 0)
        total_rx = int(rx_val) if isinstance(rx_val, (int, float)) else 0
        tx_val = getattr(self.bridge, "tx_count", 0)
        total_tx = int(tx_val) if isinstance(tx_val, (int, float)) else 0
        err_tx = getattr(self.bridge, "tx_error_count", 0)
        err_gen = getattr(self.bridge, "err_count", 0)
        total_err = (int(err_tx) if isinstance(err_tx, (int, float)) else 0) + (int(err_gen) if isinstance(err_gen, (int, float)) else 0)
        total_pkts = total_rx + total_tx
        error_rate = round((total_err / total_pkts * 100.0), 1) if total_pkts > 0 else 0.0
        node_cnt = self.bridge.node_registry.get_count() if hasattr(self.bridge, "node_registry") and hasattr(self.bridge.node_registry, "get_count") else 0
        q_depth = self.bridge.rate_limiter.get_queue_depth() if hasattr(self.bridge, "rate_limiter") and hasattr(self.bridge.rate_limiter, "get_queue_depth") else 0

        tcp_server = getattr(self.bridge, "tcp_server", None)
        tcp_info = {
            "enabled": getattr(tcp_server, "is_running", False) if tcp_server else False,
            "host": getattr(tcp_server, "host", "0.0.0.0") if tcp_server else "0.0.0.0",  # nosec B104
            "port": getattr(tcp_server, "port", 5000) if tcp_server else 5000,
            "connected_clients": getattr(tcp_server, "connected_clients_count", 0) if tcp_server else 0,
        }

        local_cfg = self.bridge.admin_handler.get_local_config() if hasattr(self.bridge, "admin_handler") else {}

        status_data = {
            "bridge_status": "online" if getattr(self.bridge, "running", True) else "offline",
            "uptime_seconds": int(time.time() - getattr(self.bridge, "start_time", time.time())),
            "serial_connected": getattr(self.bridge.serial_adapter, "is_connected", False),
            "mqtt_connected": getattr(self.bridge.mqtt, "is_connected", False),
            "tcp_companion": tcp_info,
            "local_node_pubkey": local_cfg.get("public_key"),
            "local_node_name": local_cfg.get("name"),
            "known_mesh_nodes": node_cnt,
            "node_count": node_cnt,
            "total_rx_packets": total_rx,
            "rx_count": total_rx,
            "total_tx_packets": total_tx,
            "tx_count": total_tx,
            "total_tx_errors": total_err,
            "error_rate": error_rate,
            "tx_queue_depth": q_depth,
            "queue_depth": q_depth,
            "offline_buffer_pending": await self.bridge.store_and_forward.count(),
            "sniffer_active": self.sniffer_active,
        }
        return 200, {"status": "ok", "data": status_data}

    async def _route_analytics(self) -> tuple[int, dict[str, Any]]:
        analytics = self.bridge.node_registry.get_analytics_summary()
        analytics["queue_depth"] = self.bridge.rate_limiter.get_queue_depth()
        analytics["offline_buffer_size"] = await self.bridge.store_and_forward.count()
        return 200, {"status": "ok", "data": analytics}

    async def _route_contacts(self, path: str, method: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if path == "/api/contacts/sync" and method in ("POST", "GET"):
            ser = getattr(self.bridge, "serial_adapter", None)
            imported_count = 0
            if ser and hasattr(ser, "sync_all_contacts"):
                try:
                    imported = await ser.sync_all_contacts()
                    for c in imported:
                        pk = str(c.get("public_key", "")).strip()
                        if pk:
                            self.bridge.node_registry.add_or_update(
                                pk,
                                NodeContactUpdate(
                                    name=c.get("name"),
                                    alias=c.get("alias"),
                                    role=c.get("role", "CLIENT"),
                                ),
                            )
                            imported_count += 1
                except Exception as e:
                    logging.warning(f"Error sincronizando contactos con el nodo: {e}")
            nodes = self.bridge.node_registry.list_nodes()
            return 200, {"status": "ok", "imported": imported_count, "data": nodes, "count": len(nodes)}

        if method == "GET":
            nodes = self.bridge.node_registry.list_nodes()
            return 200, {"status": "ok", "data": nodes, "count": len(nodes)}

        if method == "POST":
            pubkey = str(req_body.get("public_key", req_body.get("key", ""))).strip()
            name = str(req_body.get("name", "")).strip()
            alias = str(req_body.get("alias", "")).strip()
            role = str(req_body.get("role", "CLIENT")).strip()
            if not pubkey:
                return 400, {"status": "error", "message": "Se requiere 'public_key'"}

            contact = self.bridge.node_registry.add_or_update(
                pubkey,
                NodeContactUpdate(name=name or f"Node_{pubkey[:6]}", alias=alias, role=role),
            )
            # Sincronizar hacia el transceptor serial
            ser = getattr(self.bridge, "serial_adapter", None)
            if ser and hasattr(ser, "add_contact"):
                try:
                    await ser.add_contact({"public_key": pubkey, "name": name or alias, "role": role})
                except Exception as e:
                    logging.debug(f"Error enviando contacto al transceptor serial: {e}")

            # Notificar a los clientes WebSocket en tiempo real
            web = getattr(self.bridge, "web_server", None)
            if web:
                web.broadcast_event({"type": "contacts_updated", "data": self.bridge.node_registry.list_nodes()})

            self.log_system_event("INFO", f"Contacto guardado: {pubkey} ({alias or name})", source="contacts")
            return 200, {"status": "ok", "data": contact.to_dict()}

        if method == "DELETE":
            pubkey = str(req_body.get("public_key", req_body.get("key", ""))).strip().lower()
            ser = getattr(self.bridge, "serial_adapter", None)
            if ser and hasattr(ser, "remove_contact"):
                try:
                    await ser.remove_contact(pubkey)
                except Exception as e:
                    logging.debug(f"Error eliminando contacto del transceptor serial: {e}")

            if pubkey and pubkey in self.bridge.node_registry._nodes_by_key:
                del self.bridge.node_registry._nodes_by_key[pubkey]
                web = getattr(self.bridge, "web_server", None)
                if web:
                    web.broadcast_event({"type": "contacts_updated", "data": self.bridge.node_registry.list_nodes()})
                return 200, {"status": "ok", "message": f"Contacto {pubkey} eliminado"}
            return 404, {"status": "error", "message": "Contacto no encontrado"}

        return 405, {"status": "error", "message": "Método no permitido para /api/contacts"}

    async def _route_channels(self, path: str, method: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if path == "/api/channels/sync" and method in ("POST", "GET"):
            ser = getattr(self.bridge, "serial_adapter", None)
            if ser and hasattr(ser, "get_channels"):
                try:
                    node_channels = await ser.get_channels()
                    for ch in node_channels:
                        idx = int(ch.get("index", 0))
                        self.channels[idx] = ch
                except Exception as e:
                    logging.debug(f"Fallo sincronizando canales del nodo serial: {e}")
            channels = list(self.channels.values())
            channels.sort(key=lambda c: int(c.get("index", 0)))
            return 200, {"status": "ok", "data": channels, "count": len(channels)}

        if method == "GET":
            ser = getattr(self.bridge, "serial_adapter", None)
            if ser and hasattr(ser, "get_channels"):
                try:
                    node_channels = await ser.get_channels()
                    for ch in node_channels:
                        idx = int(ch.get("index", 0))
                        self.channels[idx] = ch
                except Exception as e:
                    logging.debug(f"Fallo sincronizando canales del nodo serial: {e}")

            channels = list(self.channels.values())
            channels.sort(key=lambda c: int(c.get("index", 0)))
            return 200, {"status": "ok", "data": channels, "count": len(channels)}

        if method == "POST":
            try:
                idx = int(req_body.get("index", 1))
            except ValueError:
                return 400, {"status": "error", "message": "Índice de canal inválido"}
            if idx < 0 or idx > 7:
                return 400, {"status": "error", "message": "El índice de canal debe estar entre 0 y 7"}

            name = str(req_body.get("name", f"Canal {idx}")).strip()
            psk = str(req_body.get("psk", "")).strip()
            self.channels[idx] = {"index": idx, "name": name, "psk": psk, "is_public": (idx == 0)}

            # Sincronizar con el hardware serial si está conectado
            ser = getattr(self.bridge, "serial_adapter", None)
            if ser and hasattr(ser, "set_channel"):
                try:
                    await ser.set_channel(idx, name, psk)
                except Exception as e:
                    logging.debug(f"Error despachando canal al transceptor serial: {e}")

            web = getattr(self.bridge, "web_server", None)
            if web:
                web.broadcast_event({"type": "channels_updated", "data": list(self.channels.values())})

            self.log_system_event("INFO", f"Canal {idx} configurado: {name}", source="channels")
            return 200, {"status": "ok", "data": self.channels[idx]}

        if method == "DELETE":
            try:
                idx = int(req_body.get("index", 0))
            except ValueError:
                return 400, {"status": "error", "message": "Índice de canal inválido"}
            if idx == 0:
                return 400, {"status": "error", "message": "No se puede eliminar el canal público 0"}
            if idx in self.channels:
                del self.channels[idx]
                ser = getattr(self.bridge, "serial_adapter", None)
                if ser and hasattr(ser, "set_channel"):
                    try:
                        await ser.set_channel(idx, "", "")
                    except Exception as e:
                        logging.debug(f"Error limpiando canal en transceptor serial: {e}")
                web = getattr(self.bridge, "web_server", None)
                if web:
                    web.broadcast_event({"type": "channels_updated", "data": list(self.channels.values())})
                return 200, {"status": "ok", "message": f"Canal {idx} eliminado"}
            return 404, {"status": "error", "message": "Canal no encontrado"}

        return 405, {"status": "error", "message": "Método no permitido para /api/channels"}

    async def _route_tx(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        text = str(req_body.get("text", "")).strip()
        if not text:
            return 400, {"status": "error", "message": "El campo 'text' no puede estar vacío"}

        target = req_body.get("to", req_body.get("target", "broadcast"))
        try:
            ch_idx = int(req_body.get("channel_index", req_body.get("channel_idx", 0)))
        except ValueError:
            return 400, {"status": "error", "message": "Invalid channel index"}
        req_id = req_body.get("request_id", f"web_{int(time.time() * 1000)}")

        tx_item = {"to": target, "channel_index": ch_idx, "text": text, "request_id": req_id}
        res = await self.bridge._execute_tx(tx_item)
        if target != "broadcast":
            self.bridge.node_registry.record_packet(PacketRecord(public_key=target, is_rx=False))
        self.log_system_event("INFO", f"Transmisión TX enviada a {target} (Ch {ch_idx})", source="mesh_tx")
        return 200, {"status": "ok", "data": res}

    async def _route_sniffer(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        action = str(req_body.get("action", "start")).lower().strip()
        self.sniffer_active = (action == "start")
        cmd_data = {
            "target_node": req_body.get("target_node", "local"),
            "action": f"log {action}",
            "request_id": f"web_sniff_{int(time.time())}",
        }
        res = await self.bridge.handle_admin(cmd_data)
        self.log_system_event("INFO", f"Control de Sniffer RF: {action.upper()}", source="sniffer")
        return 200, {"status": "ok", "data": {"sniffer_active": self.sniffer_active, "result": res}}

    async def _route_admin_repeater(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        target_node = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
        action = str(req_body.get("action", req_body.get("command", "stats-radio")))
        if not target_node:
            return 400, {"status": "error", "message": "Se requiere 'target_node'"}

        cmd_data = {
            "target_node": target_node,
            "action": action,
            "params": req_body.get("params", {}),
            "request_id": req_body.get("request_id", f"web_rep_{int(time.time())}"),
        }
        res = await self.bridge.handle_admin(cmd_data)
        self.log_system_event("INFO", f"Comando RF a repetidor {target_node}: {action}", source="repeater_admin")
        return 200, {"status": "ok", "data": res}

    def _route_logs(self, raw_path: str, clean_path: str) -> tuple[int, dict[str, Any]]:
        if clean_path == "/api/messages":
            return 200, {"status": "ok", "data": list(self.recent_messages), "count": len(self.recent_messages)}
        if clean_path == "/api/telemetry":
            return 200, {"status": "ok", "data": list(self.recent_telemetry), "count": len(self.recent_telemetry)}
        if clean_path in ("/api/logs", "/api/sniffer/logs", "/api/sniffer/packets"):
            return 200, {"status": "ok", "data": list(self.recent_rf_logs), "count": len(self.recent_rf_logs)}
        if clean_path == "/api/system/logs":
            level = None
            search = None
            limit = 100
            if "?" in raw_path:
                query_str = raw_path.split("?", 1)[1]
                for part in query_str.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        k_lower = k.lower()
                        if k_lower == "level":
                            level = v
                        elif k_lower == "search":
                            search = v
                        elif k_lower == "limit" and v.isdigit():
                            limit = int(v)

            diag = getattr(self.bridge, "diagnostics", None)
            from src.diagnostics import DiagnosticManager

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
                records = list(self.recent_system_logs)
                if level:
                    target_lvl = level.strip().upper()
                    records = [r for r in records if r.get("level") == target_lvl]
                if search:
                    search_low = search.strip().lower()
                    records = [r for r in records if search_low in str(r.get("message", "")).lower()]
                if limit and len(records) > limit:
                    records = records[-limit:]
                counters = {
                    "errors": sum(1 for r in self.recent_system_logs if r.get("level") in ("ERROR", "CRITICAL")),
                    "warnings": sum(1 for r in self.recent_system_logs if r.get("level") in ("WARNING", "WARN")),
                    "info": sum(1 for r in self.recent_system_logs if r.get("level") == "INFO"),
                    "debug": sum(1 for r in self.recent_system_logs if r.get("level") == "DEBUG"),
                }
                curr_lvl = "INFO"

            return 200, {
                "status": "ok",
                "data": records,
                "count": len(records),
                "counters": counters,
                "current_level": curr_lvl,
            }

        if clean_path in ("/api/diagnostics/report.md", "/api/diagnostics/report"):
            diag = getattr(self.bridge, "diagnostics", None)
            from src.diagnostics import DiagnosticManager

            if isinstance(diag, DiagnosticManager):
                md_text = diag.generate_markdown_report()
            else:
                md_text = "# Reporte de Diagnóstico no disponible"
            return 200, {"status": "ok", "markdown": md_text, "text": md_text}

        if clean_path in ("/api/logs/download", "/api/logs/raw"):
            diag = getattr(self.bridge, "diagnostics", None)
            from src.diagnostics import DiagnosticManager

            if isinstance(diag, DiagnosticManager):
                tail = diag.get_raw_log_tail(lines=500)
                log_file = diag.get_raw_log_path()
            else:
                tail = "\n".join(f"[{r.get('iso_time')}] [{r.get('level')}] {r.get('message')}" for r in self.recent_system_logs)
                log_file = None
            return 200, {
                "status": "ok",
                "raw_logs": tail,
                "log_file": log_file,
                "line_count": len(tail.splitlines()),
            }

        return 404, {"status": "error", "message": "Registro no encontrado"}

    async def _trigger_ha_publish(self) -> int:
        ha = getattr(self.bridge, "ha_discovery", None)
        if not ha:
            return 0
        total: int = ha.publish_discovery_for_bridge(self.bridge.mqtt.publish_safe)
        for node in self.bridge.node_registry.list_nodes():
            total += int(ha.publish_discovery_for_node(node, self.bridge.mqtt.publish_safe))
        self.log_system_event("INFO", f"Home Assistant Discovery anunciado ({total} entidades)", source="ha")
        return int(total)

    def _run_preflight_diagnostics(self) -> dict[str, Any]:
        checker = getattr(self.bridge, "preflight", None)
        if checker and hasattr(checker, "run_all"):
            import config
            res = checker.run_all(
                mqtt_host=config.MQTT_BROKER,
                mqtt_port=config.MQTT_PORT,
                db_path=config.SQLITE_DB_PATH,
                serial_port=getattr(self.bridge.serial_adapter, "port", config.SERIAL_PORT),
            )
            if isinstance(res, dict):
                return res
        return {"status": "OK", "checks": []}

    async def _route_trace(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        target = str(req_body.get("to", req_body.get("target", ""))).strip()
        if not target:
            return 400, {"status": "error", "message": "Se requiere 'to' (nodo objetivo)"}

        auth_code = int(req_body.get("auth_code", 0))
        cmd_data = {
            "target_node": target,
            "action": "trace",
            "params": {"auth_code": auth_code, "path": req_body.get("path", "")},
            "request_id": f"web_trace_{int(time.time())}",
        }
        res = await self.bridge.handle_admin(cmd_data)
        self.log_system_event("INFO", f"Traceroute iniciado hacia {target}", source="trace")
        return 200, {"status": "ok", "data": res}
