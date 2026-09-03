"""
Web API Router and Dispatcher for MeshCore Bridge Web Interface.
Gestiona el enrutamiento y procesamiento de peticiones REST para canales, contactos,
telemetría, métricas analíticas avanzadas y consola de logs delegando en controladores modulares.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import time
from pathlib import Path
from typing import Any

from src.contact_manager import PacketRecord, is_valid_node_key
from src.sensor_decoder import extract_telemetry_fields
from src.web.controllers import (
    ApiContext,
    ChannelsController,
    ConfigController,
    ContactsController,
    NodesController,
    RepeaterController,
    SystemController,
    TxController,
    problem_details,
)
from src.web.map_tile_service import MapTileService


class WebAPIRouter:
    """Enrutador modular de API REST para el cliente web de MeshCore Bridge."""

    def __init__(self, bridge: Any) -> None:
        self.bridge = bridge
        self.recent_messages: collections.deque[dict[str, Any]] = collections.deque(maxlen=200)
        self.recent_telemetry: collections.deque[dict[str, Any]] = collections.deque(maxlen=200)
        self.recent_system_logs: collections.deque[dict[str, Any]] = collections.deque(maxlen=300)
        self.map_tile_service = MapTileService()

        # Inyección de dependencias mediante ApiContext
        self.api_ctx = ApiContext(
            bridge=self.bridge,
            recent_messages=self.recent_messages,
            system_logs=self.recent_system_logs,
            log_system_event=self.log_system_event,
            broadcast_ws=self._notify_web_clients,
            start_time=getattr(bridge, "start_time", time.time()),
        )

        # Controladores especializados por dominio (Modular REST Architecture)
        self.system_ctrl = SystemController(self.api_ctx)
        self.nodes_ctrl = NodesController(self.api_ctx)
        self.contacts_ctrl = ContactsController(self.api_ctx)
        self.channels_ctrl = ChannelsController(self.api_ctx)
        self.tx_ctrl = TxController(self.api_ctx)
        self.repeater_ctrl = RepeaterController(self.api_ctx)
        self.config_ctrl = ConfigController(self.api_ctx)

        # Referencia compartida de canales para retrocompatibilidad
        self.channels: dict[int, dict[str, Any]] = self.channels_ctrl.channels

    def _get_storage_path(self) -> Path:
        """Obtiene la ruta persistente del archivo JSON de canales."""
        return Path(self.channels_ctrl.channels_file)

    def _load_channels(self) -> None:
        """Carga la configuración persistida de canales delegando al controlador."""
        self.channels_ctrl._load_channels()
        self.channels = self.channels_ctrl.channels

    def _save_channels(self) -> bool:
        """Persiste la configuración de canales delegando al controlador."""
        try:
            self.channels_ctrl._save_channels()
            return True
        except Exception:
            return False

    def _notify_web_clients(self, event: dict[str, Any]) -> None:
        """Emite eventos en tiempo real a clientes WebSocket manejando corutinas y mocks síncronos."""
        web = getattr(self.bridge, "web_server", None)
        if web and hasattr(web, "broadcast_event"):
            res = web.broadcast_event(event)
            if asyncio.iscoroutine(res):
                asyncio.create_task(res)

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
        if diag and hasattr(diag, "log_handler") and diag.log_handler:
            if lvl_upper in ("ERROR", "CRITICAL"):
                diag.log_handler.error_count += 1
            elif lvl_upper in ("WARNING", "WARN"):
                diag.log_handler.warn_count += 1
            elif lvl_upper == "INFO":
                diag.log_handler.info_count += 1
            else:
                diag.log_handler.debug_count += 1

    def record_incoming_event(self, ev_type_or_data: str | dict[str, Any], event_data: dict[str, Any] | None = None) -> None:
        """Registra eventos en los buffers circulares en memoria para clientes web."""
        if isinstance(ev_type_or_data, dict):
            data = ev_type_or_data
            ev_type = str(data.get("event_type", data.get("type", "")))
        else:
            ev_type = str(ev_type_or_data)
            data = event_data or {}

        if not data or not isinstance(data, dict):
            return
        if ev_type in ("system_log", "metrics_update", "status"):
            return

        from src.event_utils import extract_sender_from_payload
        sender_raw, sender_name = extract_sender_from_payload(data)

        node_info = None
        if hasattr(self.bridge, "node_registry") and self.bridge.node_registry:
            if sender_raw:
                node_info = self.bridge.node_registry.get_by_key_or_prefix(sender_raw)
            if not node_info and sender_name:
                node_info = self.bridge.node_registry.find_by_name(sender_name)

        if node_info:
            node_label = node_info.alias or node_info.name or (node_info.public_key[:8] if node_info.public_key else "desconocido")
            pk_short = node_info.public_key[:8] if node_info.public_key else ""
            sender_id_str = f"nodo '{node_label}' ({pk_short})" if pk_short and pk_short != node_label else f"nodo '{node_label}'"
            canonical_sender = node_info.public_key
        elif sender_name and sender_raw:
            sender_id_str = f"nodo '{sender_name}' ({sender_raw[:8]})"
            canonical_sender = sender_raw
        elif sender_name:
            sender_id_str = f"nodo '{sender_name}'"
            canonical_sender = sender_name
        elif sender_raw:
            sender_id_str = f"nodo [{sender_raw[:8]}]"
            canonical_sender = sender_raw
        elif ev_type in ("self_info", "battery", "device_info"):
            sender_id_str = "Estación Base Local"
            canonical_sender = getattr(self.bridge.node_registry, "get_local_pubkey", lambda: "")() if hasattr(self.bridge, "node_registry") else ""
        else:
            sender_id_str = "nodo anónimo"
            canonical_sender = ""

        rssi = data.get("rssi", data.get("RSSI", data.get("last_rssi")))
        snr = data.get("snr", data.get("SNR", data.get("last_snr")))

        extracted_telem = extract_telemetry_fields(data)

        if (
            ev_type in ("telemetry", "telemetry_recv", "telemetry_response", "stats_core", "stats_radio", "stats_packets", "battery", "battery_info", "device_info", "repeater_telemetry")
            or any(k in data for k in ("temperature_c", "battery_pct", "battery", "battery_mv", "voltage_v", "voltage", "temp", "uptime_secs", "uptime", "lpp"))
            or bool(extracted_telem)
        ):
            self.recent_telemetry.append(data)
            if canonical_sender and is_valid_node_key(canonical_sender):
                self.bridge.node_registry.record_packet(PacketRecord(public_key=canonical_sender, is_rx=True, rssi=rssi, snr=snr, telemetry=data))

            readings = []
            if "temperature_c" in extracted_telem:
                readings.append(f"🌡️ {extracted_telem['temperature_c']}°C")
            if "humidity_pct" in extracted_telem:
                readings.append(f"💧 {extracted_telem['humidity_pct']}%")
            if "pressure_hpa" in extracted_telem:
                readings.append(f"🌀 {extracted_telem['pressure_hpa']} hPa")

            bat = extracted_telem.get("battery_pct")
            volt = extracted_telem.get("voltage_v")
            bat_mv = extracted_telem.get("battery_mv")
            if bat is not None and volt is not None:
                readings.append(f"🔋 {bat}% ({volt}V)")
            elif bat is not None:
                readings.append(f"🔋 {bat}%")
            elif volt is not None:
                readings.append(f"⚡ {volt}V")
            elif bat_mv is not None:
                readings.append(f"🔋 {bat_mv}mV")

            if "solar_v" in extracted_telem:
                readings.append(f"☀️ {extracted_telem['solar_v']}V")
            if "uptime" in extracted_telem:
                readings.append(f"⏱️ {extracted_telem['uptime']}")
            elif "uptime_secs" in extracted_telem:
                readings.append(f"⏱️ {extracted_telem['uptime_secs']}s")

            if "packet_errors" in extracted_telem:
                readings.append(f"⚠️ {extracted_telem['packet_errors']} err")
            if "queue_len" in extracted_telem:
                readings.append(f"📦 Cola: {extracted_telem['queue_len']}")

            if snr is not None:
                readings.append(f"📶 SNR {snr}dB")
            if rssi is not None:
                readings.append(f"📡 {rssi}dBm")

            detail_str = f" [{', '.join(readings)}]" if readings else ""
            self.log_system_event("INFO", f"Telemetría recibida de {sender_id_str}{detail_str}", source="telemetry")

        elif ev_type in ("public", "channel", "direct"):
            text_val = str(data.get("text", data.get("message", "")))
            raw_txt_type = data.get("txt_type", data.get("text_type", 0))
            try:
                txt_type = int(raw_txt_type) if raw_txt_type is not None else 0
            except (ValueError, TypeError):
                txt_type = 0

            from src.rx_router import is_common_chat_message
            if is_common_chat_message(text_val, txt_type=txt_type, event_type=ev_type):
                self.recent_messages.append(data)
                if canonical_sender and is_valid_node_key(canonical_sender):
                    self.bridge.node_registry.record_packet(PacketRecord(public_key=canonical_sender, is_rx=True, rssi=rssi, snr=snr))
                self.log_system_event("INFO", f"Mensaje RX [{ev_type}] de {sender_id_str}: {text_val[:30]}", source="mesh_rx")

    async def handle_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Maneja una solicitud REST despachando limpiamente a controladores modulares especializados."""
        clean_path = path.split("?")[0].rstrip("/")
        req_body = body or {}

        try:
            if clean_path in ("/api/status", "/api/health", "/api/preflight") or clean_path.startswith("/api/system/logs"):
                return await self._dispatch_system(method, path, clean_path, req_body)

            if clean_path in ("/api/nodes", "/api/lqi", "/api/link_quality", "/api/analytics", "/api/metrics/analytics", "/api/rf/heatmap", "/api/airtime/stats", "/api/rf/noise"):
                return await self._dispatch_nodes(method, path, clean_path, req_body)

            if clean_path.startswith("/api/contacts"):
                return await self._dispatch_contacts(method, clean_path, req_body)

            if clean_path.startswith("/api/channels"):
                return await self._dispatch_channels(method, clean_path, req_body)

            if clean_path in ("/api/tx", "/api/messages/recent", "/api/messages"):
                return await self._dispatch_tx(method, clean_path, req_body)

            if clean_path.startswith(("/api/admin", "/api/repeater", "/api/traceroute", "/api/trace")):
                return await self._dispatch_repeater(method, clean_path, req_body)

            if clean_path.startswith("/api/node"):
                return await self._dispatch_config(method, clean_path, req_body)

            if clean_path.startswith("/api/map") or clean_path in ("/api/logs", "/api/telemetry", "/api/diagnostics", "/api/diagnostics/report.md", "/api/diagnostics/report", "/api/logs/download", "/api/logs/raw"):
                return await self._dispatch_misc(method, path, clean_path, req_body)

            return problem_details(404, "Not Found", f"Ruta no encontrada: {method} {clean_path}", "route_not_found")

        except Exception as e:
            logging.error(f"Error procesando solicitud REST {method} {clean_path}: {e}", exc_info=True)
            self.log_system_event("ERROR", f"Fallo en API {method} {clean_path}: {e}", source="api")
            return problem_details(500, "Internal Server Error", str(e), "internal_server_error")

    async def _dispatch_system(self, method: str, raw_path: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de salud, estado y logs al SystemController."""
        if clean_path == "/api/status" and method == "GET":
            return await self._route_status()
        if clean_path == "/api/health" and method == "GET":
            return await self.system_ctrl.get_health()
        if clean_path == "/api/preflight" and method == "GET":
            return await self.system_ctrl.run_preflight()
        if clean_path == "/api/system/logs/level":
            if method == "GET":
                diag = getattr(self.bridge, "diagnostics", None)
                lvl = diag.get_current_log_level() if diag else "INFO"
                return 200, {"status": "ok", "level": lvl}
            if method == "POST":
                diag = getattr(self.bridge, "diagnostics", None)
                target_lvl = req_body.get("level", "INFO")
                if diag:
                    new_lvl = diag.set_log_level(str(target_lvl))
                    return 200, {"status": "ok", "level": new_lvl}
                return problem_details(400, "Bad Request", "Diagnostic manager no disponible", "diagnostic_unavailable")
        if clean_path == "/api/system/logs":
            if method == "DELETE":
                return await self.system_ctrl.clear_logs()
            if method == "GET":
                return self._route_logs(raw_path, clean_path)

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

    async def _dispatch_nodes(self, method: str, raw_path: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de directorio de nodos y analítica al NodesController."""
        if clean_path == "/api/nodes" and method == "GET":
            limit = int(req_body.get("limit", 100))
            offset = int(req_body.get("offset", 0))
            if "?" in raw_path:
                for part in raw_path.split("?", 1)[1].split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        if k.lower() == "limit" and v.isdigit():
                            limit = int(v)
                        elif k.lower() == "offset" and v.isdigit():
                            offset = int(v)
            return await self.nodes_ctrl.list_nodes(limit, offset)

        if clean_path in ("/api/lqi", "/api/link_quality") and method == "GET":
            return await self.nodes_ctrl.get_lqi()
        if clean_path in ("/api/analytics", "/api/metrics/analytics") and method == "GET":
            return await self.nodes_ctrl.get_analytics()
        if clean_path == "/api/rf/heatmap" and method == "GET":
            return await self.nodes_ctrl.get_rf_heatmap()
        if clean_path == "/api/airtime/stats" and method == "GET":
            return await self.nodes_ctrl.get_airtime_stats()
        if clean_path == "/api/rf/noise" and method == "GET":
            nodes = self.bridge.node_registry.list_nodes()
            matrix = [
                {
                    "pubkey": n.get("public_key"),
                    "name": n.get("name") or n.get("alias"),
                    "role": n.get("role"),
                    "noise_floor_dbm": n.get("noise_floor_dbm"),
                    "snr": n.get("last_snr"),
                    "rssi": n.get("last_rssi"),
                    "channel": n.get("channel", 0),
                    "freq": n.get("frequency", 915.0),
                }
                for n in nodes
            ]
            return 200, {"status": "ok", "data": {"matrix": matrix}}

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

    async def _dispatch_contacts(self, method: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de libreta de contactos al ContactsController."""
        if clean_path == "/api/contacts/discovered" and method == "GET":
            discovered = self.bridge.node_registry.list_discovered()
            return 200, {"status": "ok", "data": {"discovered": discovered, "count": len(discovered)}}

        if clean_path == "/api/contacts/accept" and method == "POST":
            pubkey = str(req_body.get("public_key", req_body.get("target_node", ""))).strip()
            if not pubkey:
                return problem_details(400, "Bad Request", "Se requiere 'public_key'", "missing_public_key")
            success = self.bridge.node_registry.accept_discovered_contact(pubkey)
            return 200, {"status": "ok" if success else "error", "accepted": success}

        return await self.contacts_ctrl.handle_contacts_route(clean_path, method, req_body)

    async def _dispatch_channels(self, method: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de canales al ChannelsController."""
        res = await self.channels_ctrl.handle_channels_route(clean_path, method, req_body)
        self.channels = self.channels_ctrl.channels
        return res

    async def _dispatch_tx(self, method: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de transmisión de mensajes al TxController."""
        if clean_path == "/api/tx" and method == "POST":
            return await self.tx_ctrl.send_tx(req_body)
        if clean_path in ("/api/messages/recent", "/api/messages") and method == "GET":
            return await self.tx_ctrl.get_recent_messages()
        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

    async def _dispatch_repeater(self, method: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de gestión de repetidores y comandos remotos."""
        if clean_path == "/api/admin/command" and method == "POST":
            return await self.repeater_ctrl.execute_admin_command(req_body)
        if clean_path == "/api/admin/repeater" and method == "POST":
            return await self.repeater_ctrl.execute_repeater_command(req_body)
        if clean_path == "/api/repeater/remote/login" and method == "POST":
            return await self.repeater_ctrl.login(req_body)
        if clean_path in ("/api/repeater/remote/logout", "/api/repeater/logout") and method == "POST":
            return await self.repeater_ctrl.logout(req_body)
        if clean_path == "/api/repeater/remote/config" and method == "POST":
            return await self.repeater_ctrl.set_remote_config(req_body)
        if clean_path == "/api/repeater/remote/action" and method == "POST":
            return await self.repeater_ctrl.execute_remote_action(req_body)
        if clean_path in ("/api/repeater/ping_zero", "/api/node/ping_zero") and method == "POST":
            return await self.repeater_ctrl.ping_zero(req_body)
        if clean_path in ("/api/traceroute", "/api/trace") and method == "POST":
            return await self.repeater_ctrl.traceroute(req_body)

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

    async def _dispatch_config(self, method: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de configuración de nodo local y módem LoRa."""
        if clean_path in ("/api/node/config", "/api/node/settings"):
            if method == "GET":
                return await self.config_ctrl.get_device_config()
            if method == "POST":
                return await self.config_ctrl.set_local_config(req_body)
        if clean_path == "/api/node/advert" and method == "POST":
            flood = bool(req_body.get("flood", False))
            return await self.config_ctrl.broadcast_advert(flood)
        if clean_path == "/api/node/reboot" and method == "POST":
            return await self.config_ctrl.reboot_local()

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

    async def _dispatch_misc(self, method: str, raw_path: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha servicios de mapas y visualización de diagnósticos históricos."""
        if clean_path == "/api/map/status" and method == "GET":
            return 200, {"status": "ok", "data": self.map_tile_service.get_status()}

        if clean_path in (
            "/api/messages",
            "/api/telemetry",
            "/api/logs",
            "/api/system/logs",
            "/api/diagnostics/report.md",
            "/api/diagnostics/report",
            "/api/logs/download",
            "/api/logs/raw",
        ) and method == "GET":
            return self._route_logs(raw_path, clean_path)

        return problem_details(404, "Not Found", "Recurso no encontrado", "not_found")

    # Retrocompatibilidad para llamadas internas o tests directos
    async def _route_status(self) -> tuple[int, dict[str, Any]]:
        return await self.config_ctrl.get_device_config()

    async def _route_analytics(self) -> tuple[int, dict[str, Any]]:
        return await self.nodes_ctrl.get_analytics()

    async def _route_contacts(self, path: str, method: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return await self.contacts_ctrl.handle_contacts_route(path, method, req_body)

    async def _route_channels(self, path: str, method: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return await self.channels_ctrl.handle_channels_route(path, method, req_body)

    async def _route_tx(self, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return await self.tx_ctrl.send_tx(req_body)

    def _route_logs(self, raw_path: str, clean_path: str) -> tuple[int, dict[str, Any]]:
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
            all_messages = list(self.recent_messages)
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
            all_telemetry = list(self.recent_telemetry)
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

        return problem_details(404, "Not Found", "Registro no encontrado", "log_not_found")
