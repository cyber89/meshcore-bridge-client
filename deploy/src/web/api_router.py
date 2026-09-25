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
from src.event_utils import extract_sender_from_payload
from src.sensor_decoder import extract_telemetry_fields
from src.shared_utils import to_bool
from src.web.controllers import (
    ApiContext,
    ChannelsController,
    ConfigController,
    ContactsController,
    LogsController,
    NodesController,
    PacketsController,
    RepeaterController,
    SystemController,
    TxController,
    problem_details,
)
from src.web.map_tile_service import MapTileService


# Mapeo canónico de alias y retrocompatibilidad de rutas REST
ROUTE_ALIASES: dict[str, str] = {
    # Ping directo / repetidor
    "/api/node/ping": "/api/node/ping_zero",
    "/api/nodes/ping": "/api/node/ping_zero",
    "/api/nodes/ping_zero": "/api/node/ping_zero",
    "/api/ping_zero": "/api/node/ping_zero",
    # Traceroute
    "/api/trace": "/api/traceroute",
    "/api/node/traceroute": "/api/repeater/traceroute",
    "/api/node/trace": "/api/repeater/traceroute",
    "/api/nodes/traceroute": "/api/repeater/traceroute",
    "/api/nodes/trace": "/api/repeater/traceroute",
    # Analytics / Métricas
    "/api/link_quality": "/api/lqi",
    "/api/metrics/analytics": "/api/analytics",
    "/api/metrics/reset": "/api/analytics/reset",
    # Repetidor / Administración remota
    "/api/repeater/neighbours": "/api/repeater/remote/neighbours",
    "/api/repeater/neighbors": "/api/repeater/remote/neighbours",
    "/api/repeater/remote/neighbors": "/api/repeater/remote/neighbours",
    "/api/repeater/owner": "/api/repeater/remote/owner",
    "/api/repeater/regions": "/api/repeater/remote/regions",
    "/api/repeater/clock": "/api/repeater/remote/clock",
    "/api/repeater/acl": "/api/repeater/remote/acl",
    "/api/repeater/logout": "/api/repeater/remote/logout",
    "/api/admin/command": "/api/admin",
    # Configuración de hardware / nodo local
    "/api/node/settings": "/api/config",
    "/api/node/config": "/api/config",
    "/api/node/custom_vars": "/api/config/custom_vars",
    "/api/node/path_hash_mode": "/api/config/path_hash_mode",
    "/api/node/autoadd": "/api/config/autoadd",
    "/api/node/flood_scope": "/api/config/flood_scope",
    "/api/node/config/radio": "/api/config/radio",
    "/api/node/config/identity": "/api/config/identity",
    "/api/config/advert": "/api/node/advert",
    "/api/config/reboot": "/api/node/reboot",
    "/api/node/sync-clock": "/api/config/sync-clock",
    "/api/config/sync_clock": "/api/config/sync-clock",
    "/api/node/clear-stats": "/api/config/clear-stats",
    "/api/config/clear_stats": "/api/config/clear-stats",
    "/api/node/refresh": "/api/config/refresh",
    "/api/node/reconnect": "/api/config/reconnect",
    "/api/config/reconnect-serial": "/api/config/reconnect",
    # Mapas
    "/api/map/refresh": "/api/map/reload",
}


def _safe_int(val: Any, default: int, min_val: int = 0, max_val: int = 100000) -> int:
    """Convierte de forma segura cualquier entrada a entero acotado."""
    try:
        res = int(val)
        return max(min_val, min(max_val, res))
    except (ValueError, TypeError):
        return default


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
            packet_buffer=getattr(bridge, "packet_buffer", None),
            recent_telemetry=self.recent_telemetry,
        )

        # Controladores especializados por dominio (Modular REST Architecture)
        self.system_ctrl = SystemController(self.api_ctx)
        self.nodes_ctrl = NodesController(self.api_ctx)
        self.contacts_ctrl = ContactsController(self.api_ctx)
        self.channels_ctrl = ChannelsController(self.api_ctx)
        self.tx_ctrl = TxController(self.api_ctx)
        self.repeater_ctrl = RepeaterController(self.api_ctx)
        self.config_ctrl = ConfigController(self.api_ctx)
        self.packets_ctrl = PacketsController(self.api_ctx)
        self.logs_ctrl = LogsController(self.api_ctx)

        # Referencia compartida de canales para retrocompatibilidad
        self.channels: dict[int, dict[str, Any]] = self.channels_ctrl.channels
        self._background_tasks: set[asyncio.Task[Any]] = set()

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
                task = asyncio.create_task(res)
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

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
        if ev_type in (
            "system_log", "metrics_update", "status", "rf_packet", "trace_data",
            "log_data", "rx_log_data", "ping", "pong"
        ):
            return

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
                contact = self.bridge.node_registry.get_by_key_or_prefix(canonical_sender) if hasattr(self.bridge, "node_registry") else None
                is_local = (contact.is_local if contact else False) or (
                    hasattr(self.bridge, "node_registry") and self.bridge.node_registry.is_local_key(canonical_sender)
                )
                if not is_local:
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
        # Saneamiento y consolidación de alias a rutas canónicas (Recomendación A2)
        clean_path = ROUTE_ALIASES.get(clean_path, clean_path)
        req_body = dict(body) if body else {}
        if "?" in path:
            try:
                import urllib.parse
                parsed_qs = urllib.parse.parse_qs(path.split("?", 1)[1], keep_blank_values=True)
                for k, v in parsed_qs.items():
                    if k not in req_body:
                        req_body[k] = v[0] if len(v) == 1 else v
            except Exception:
                pass

        try:
            if clean_path in (
                "/api/status",
                "/api/health",
                "/api/preflight",
                "/api/diagnostics",
                "/api/diagnostics/report.md",
                "/api/diagnostics/report",
                "/api/diagnostics/export",
            ) or clean_path.startswith("/api/system/logs"):
                return await self._dispatch_system(method, path, clean_path, req_body)

            if (
                clean_path in (
                    "/api/nodes", "/api/lqi",
                    "/api/analytics", "/api/analytics/reset",
                    "/api/rf/heatmap", "/api/airtime/stats", "/api/rf/noise",
                )
                or clean_path.startswith("/api/analytics/")
            ):
                return await self._dispatch_nodes(method, path, clean_path, req_body)

            if clean_path.startswith("/api/contacts"):
                return await self._dispatch_contacts(method, clean_path, req_body)

            if clean_path.startswith("/api/channels"):
                return await self._dispatch_channels(method, clean_path, req_body)

            if clean_path in ("/api/tx", "/api/messages/recent"):
                return await self._dispatch_tx(method, clean_path, req_body)

            if (
                clean_path in (
                    "/api/node/ping_zero",
                    "/api/repeater/ping_zero",
                    "/api/traceroute",
                    "/api/repeater/traceroute",
                )
                or clean_path.startswith(("/api/admin", "/api/repeater", "/api/traceroute"))
            ):
                return await self._dispatch_repeater(method, clean_path, req_body)

            if clean_path.startswith(("/api/node", "/api/config")):
                return await self._dispatch_config(method, path, clean_path, req_body)

            if clean_path.startswith("/api/packets"):
                return await self._dispatch_packets(method, path, clean_path, req_body)

            if clean_path.startswith("/api/map") or clean_path in (
                "/api/messages",
                "/api/telemetry",
                "/api/logs",
                "/api/logs/download",
                "/api/logs/raw",
            ):
                return await self._dispatch_misc(method, path, clean_path, req_body)

            return problem_details(404, "Not Found", f"Ruta no encontrada: {method} {clean_path}", "route_not_found")

        except Exception as e:
            logging.error(f"Error procesando solicitud REST {method} {clean_path}: {e}", exc_info=True)
            self.log_system_event("ERROR", f"Fallo en API {method} {clean_path}: {e}", source="api")
            return problem_details(500, "Internal Server Error", str(e), "internal_server_error")

    async def _dispatch_system(self, method: str, raw_path: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de salud, estado y logs al SystemController."""
        if clean_path == "/api/status" and method == "GET":
            return await self.system_ctrl.get_status()
        if clean_path in ("/api/health", "/api/diagnostics") and method == "GET":
            return await self.system_ctrl.get_health()
        if clean_path in ("/api/diagnostics/report.md", "/api/diagnostics/report") and method == "GET":
            diag = getattr(self.bridge, "diagnostics", None)
            from src.diagnostics import DiagnosticManager

            if isinstance(diag, DiagnosticManager):
                md_text = diag.generate_markdown_report()
            else:
                md_text = "# Reporte de Diagnóstico no disponible"
            return 200, {"status": "ok", "markdown": md_text, "text": md_text}
        if clean_path == "/api/diagnostics/export" and method == "GET":
            diag = getattr(self.bridge, "diagnostics", None)
            from src.diagnostics import DiagnosticManager

            if isinstance(diag, DiagnosticManager):
                return 200, {"status": "ok", "data": diag.generate_full_diagnostic_bundle()}
            return 200, {"status": "error", "message": "No diagnostics"}
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
                return await self._route_logs(raw_path, clean_path)

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

    async def _dispatch_packets(self, method: str, raw_path: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de inspección y exportación de paquetes LoRa al PacketsController."""
        if clean_path == "/api/packets/export" and method == "GET":
            export_fmt = "json"
            if "?" in raw_path:
                for part in raw_path.split("?", 1)[1].split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        if k.lower() == "format":
                            export_fmt = v.lower()
            return await self.packets_ctrl.export_packets(export_fmt)

        if clean_path == "/api/packets":
            if method == "DELETE":
                return await self.packets_ctrl.clear_packets()
            if method == "GET":
                limit = _safe_int(req_body.get("limit", 100), default=100, min_val=1, max_val=500)
                offset = _safe_int(req_body.get("offset", 0), default=0, min_val=0, max_val=100000)
                direction = ""
                p_type = ""
                if "?" in raw_path:
                    for part in raw_path.split("?", 1)[1].split("&"):
                        if "=" in part:
                            k, v = part.split("=", 1)
                            if k.lower() == "limit":
                                limit = _safe_int(v, default=limit, min_val=1, max_val=500)
                            elif k.lower() == "offset":
                                offset = _safe_int(v, default=offset, min_val=0, max_val=100000)
                            elif k.lower() == "direction":
                                direction = v
                            elif k.lower() == "type":
                                p_type = v
                return await self.packets_ctrl.get_packets(limit, offset, direction, p_type)

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

    async def _dispatch_nodes(self, method: str, raw_path: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de directorio de nodos y analítica al NodesController."""
        if clean_path == "/api/nodes" and method == "GET":
            limit = _safe_int(req_body.get("limit", 100), default=100, min_val=1, max_val=500)
            offset = _safe_int(req_body.get("offset", 0), default=0, min_val=0, max_val=100000)
            if "?" in raw_path:
                for part in raw_path.split("?", 1)[1].split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        if k.lower() == "limit":
                            limit = _safe_int(v, default=limit, min_val=1, max_val=500)
                        elif k.lower() == "offset":
                            offset = _safe_int(v, default=offset, min_val=0, max_val=100000)
            return await self.nodes_ctrl.list_nodes(limit, offset)

        if clean_path == "/api/lqi" and method == "GET":
            return await self.nodes_ctrl.get_lqi()
        if clean_path == "/api/analytics/reset" and method in ("POST", "DELETE"):
            return await self.nodes_ctrl.reset_metrics()
        if clean_path == "/api/analytics" and method == "GET":
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
        if clean_path == "/api/messages/recent" and method == "GET":
            return await self.tx_ctrl.get_recent_messages()
        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

    async def _dispatch_repeater(self, method: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de gestión de repetidores y comandos remotos."""
        if clean_path == "/api/admin" and method == "POST":
            return await self.repeater_ctrl.execute_admin_command(req_body)
        if clean_path == "/api/admin/repeater" and method == "POST":
            return await self.repeater_ctrl.execute_repeater_command(req_body)
        if clean_path == "/api/repeater/remote/login" and method == "POST":
            return await self.repeater_ctrl.login(req_body)
        if clean_path == "/api/repeater/remote/logout" and method == "POST":
            return await self.repeater_ctrl.logout(req_body)
        if clean_path == "/api/repeater/remote/config" and method == "POST":
            return await self.repeater_ctrl.set_remote_config(req_body)
        if clean_path == "/api/repeater/remote/action" and method == "POST":
            return await self.repeater_ctrl.execute_remote_action(req_body)
        if clean_path == "/api/repeater/remote/neighbours" and method == "POST":
            return await self.repeater_ctrl.get_neighbours(req_body)
        if clean_path == "/api/repeater/remote/owner" and method == "POST":
            return await self.repeater_ctrl.get_owner(req_body)
        if clean_path == "/api/repeater/remote/regions" and method == "POST":
            return await self.repeater_ctrl.get_regions(req_body)
        if clean_path == "/api/repeater/remote/clock" and method == "POST":
            return await self.repeater_ctrl.get_clock(req_body)
        if clean_path == "/api/repeater/remote/acl" and method == "POST":
            return await self.repeater_ctrl.get_acl(req_body)
        if clean_path in ("/api/repeater/ping_zero", "/api/node/ping_zero") and method == "POST":
            return await self.repeater_ctrl.ping_zero(req_body)
        if clean_path in ("/api/traceroute", "/api/repeater/traceroute") and method == "POST":
            return await self.repeater_ctrl.traceroute(req_body)

        return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

    async def _dispatch_config(self, method: str, raw_path: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha rutas de configuración de nodo local y módem LoRa."""
        force_refresh = "refresh=true" in raw_path.lower()
        if clean_path == "/api/config":
            if method == "GET":
                return await self.config_ctrl.get_device_config(refresh=force_refresh)
            if method == "POST":
                return await self.config_ctrl.set_local_config(req_body)
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/config/custom_vars":
            if method == "GET":
                return await self.config_ctrl.get_custom_vars()
            if method == "POST":
                return await self.config_ctrl.set_custom_vars(req_body)
            if method == "DELETE":
                k_del = str(req_body.get("key", ""))
                if not k_del and "?" in raw_path:
                    for part in raw_path.split("?", 1)[1].split("&"):
                        if "=" in part and part.split("=", 1)[0].lower() == "key":
                            k_del = part.split("=", 1)[1]
                return await self.config_ctrl.delete_custom_var(k_del)
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/config/path_hash_mode":
            if method == "GET":
                return await self.config_ctrl.get_path_hash_mode()
            if method == "POST":
                return await self.config_ctrl.set_path_hash_mode(req_body)
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/config/autoadd":
            if method == "GET":
                return await self.config_ctrl.get_autoadd_config()
            if method == "POST":
                return await self.config_ctrl.set_autoadd_config(req_body)
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/config/flood_scope":
            if method == "GET":
                return await self.config_ctrl.get_flood_scope()
            if method == "POST":
                return await self.config_ctrl.set_flood_scope(req_body)
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/config/radio":
            if method == "POST":
                return await self.config_ctrl.set_local_config(req_body)
            if method == "GET":
                return await self.config_ctrl.get_device_config(refresh=force_refresh)
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/config/identity":
            if method == "POST":
                return await self.config_ctrl.set_local_config(req_body)
            if method == "GET":
                return await self.config_ctrl.get_device_config()
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/node/advert":
            if method == "POST":
                flood = to_bool(req_body.get("flood", False))
                return await self.config_ctrl.broadcast_advert(flood)
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/node/reboot":
            if method == "POST":
                return await self.config_ctrl.reboot_local()
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/config/sync-clock":
            if method == "POST":
                raw_epoch = req_body.get("epoch", req_body.get("timestamp"))
                epoch_ts = int(raw_epoch) if raw_epoch is not None else None
                return await self.config_ctrl.sync_clock(epoch_ts=epoch_ts)
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/config/clear-stats":
            if method == "POST":
                return await self.config_ctrl.clear_stats()
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/config/refresh":
            if method in ("POST", "GET"):
                return await self.config_ctrl.refresh_hardware_config()
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        if clean_path == "/api/config/reconnect":
            if method == "POST":
                return await self.config_ctrl.reconnect_serial()
            return problem_details(405, "Method Not Allowed", f"Método {method} no permitido", "method_not_allowed")

        return problem_details(404, "Not Found", f"Ruta no encontrada: {method} {clean_path}", "route_not_found")

    async def _dispatch_misc(self, method: str, raw_path: str, clean_path: str, req_body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Despacha servicios de mapas y visualización de diagnósticos históricos."""
        if clean_path == "/api/map/status" and method == "GET":
            return 200, {"status": "ok", "data": self.map_tile_service.get_status()}

        if clean_path == "/api/map/reload" and method in ("GET", "POST"):
            try:
                self.map_tile_service.reload_mbtiles()
            except Exception as e:
                logging.warning("Error recargando mosaicos de mapas: %s", e)
            return 200, {
                "status": "ok",
                "message": "Archivos MBTiles reindexados correctamente",
                "data": self.map_tile_service.get_status(),
            }

        if clean_path in (
            "/api/messages",
            "/api/telemetry",
            "/api/logs",
            "/api/logs/download",
            "/api/logs/raw",
        ) and method == "GET":
            return await self._route_logs(raw_path, clean_path)

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

    async def _route_logs(self, raw_path: str, clean_path: str) -> tuple[int, dict[str, Any]]:
        return await self.logs_ctrl.route_logs(raw_path, clean_path)
