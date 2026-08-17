"""
Web API Router and REST Controller for MeshCore Web Client.
Procesa solicitudes HTTP REST para mensajería, gestión de contactos, canales cifrados,
telemetría, sniffer de paquetes RF, métricas analíticas avanzadas y consola de logs.
"""

from __future__ import annotations

import collections
import logging
import time
from typing import Any


class WebAPIRouter:
    """Enrutador de API REST para el cliente web de MeshCore Bridge."""

    def __init__(self, bridge: Any) -> None:
        self.bridge = bridge
        self.channels: dict[int, dict[str, Any]] = {
            0: {"index": 0, "name": "Public / Broadcast", "psk": "", "is_public": True},
            1: {"index": 1, "name": "Canal Secundario 1", "psk": "AES128_SECRET_1", "is_public": False},
            2: {"index": 2, "name": "Canal Emergencia", "psk": "AES128_SECRET_EMERGENCY", "is_public": False},
        }
        self.recent_messages: collections.deque[dict[str, Any]] = collections.deque(maxlen=200)
        self.recent_telemetry: collections.deque[dict[str, Any]] = collections.deque(maxlen=200)
        self.recent_rf_logs: collections.deque[dict[str, Any]] = collections.deque(maxlen=300)
        self.recent_system_logs: collections.deque[dict[str, Any]] = collections.deque(maxlen=300)
        self.sniffer_active = False

    def log_system_event(self, level: str, message: str, source: str = "bridge") -> None:
        """Registra un evento interno en el búfer de logs del sistema."""
        entry = {
            "timestamp": int(time.time()),
            "iso_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "level": level.upper(),
            "source": source,
            "message": message,
        }
        self.recent_system_logs.append(entry)

    def record_incoming_event(self, event_data: dict[str, Any]) -> None:
        """Almacena eventos recientes para consulta del cliente web y actualiza métricas."""
        ev_type = str(event_data.get("event_type", ""))
        sender = str(event_data.get("sender", event_data.get("sender_id", ""))).strip().lower()
        metrics = event_data.get("metrics", {})
        rssi = metrics.get("rssi")
        snr = metrics.get("snr")

        if "log" in ev_type or "rf_log" in ev_type:
            # Enriquecer log de sniffer si es trama binaria
            rf_entry = dict(event_data)
            rf_entry["iso_time"] = time.strftime("%H:%M:%S", time.localtime())
            self.recent_rf_logs.append(rf_entry)
            self.log_system_event("INFO", f"RF Sniffer interceptó trama de {rf_entry.get('byte_length', 0)} bytes", source="sniffer")

        elif "telemetry" in ev_type or "temperature_c" in event_data or "battery_pct" in event_data or "battery" in event_data:
            self.recent_telemetry.append(event_data)
            if sender:
                self.bridge.node_registry.record_packet(
                    public_key=sender,
                    is_rx=True,
                    rssi=rssi,
                    snr=snr,
                    telemetry=event_data,
                )
            self.log_system_event("INFO", f"Telemetría ambiental recibida de nodo {sender}", source="telemetry")

        else:
            self.recent_messages.append(event_data)
            if sender:
                self.bridge.node_registry.record_packet(
                    public_key=sender,
                    is_rx=True,
                    rssi=rssi,
                    snr=snr,
                )
            self.log_system_event("INFO", f"Mensaje RX [{ev_type}] de {sender}: {event_data.get('text', '')[:30]}", source="mesh_rx")

    async def handle_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Maneja una solicitud REST y retorna (status_code, json_dict)."""
        clean_path = path.split("?")[0].rstrip("/")
        req_body = body or {}

        try:
            # 1. GET /api/status
            if method == "GET" and clean_path == "/api/status":
                status_data = {
                    "bridge_status": "online" if getattr(self.bridge, "running", True) else "offline",
                    "uptime_seconds": int(time.time() - getattr(self.bridge, "start_time", time.time())),
                    "serial_connected": getattr(self.bridge.serial_adapter, "is_connected", False),
                    "mqtt_connected": getattr(self.bridge.mqtt, "is_connected", False),
                    "known_mesh_nodes": self.bridge.node_registry.get_count(),
                    "total_rx_packets": getattr(self.bridge, "rx_count", 0),
                    "total_tx_packets": getattr(self.bridge, "tx_count", 0),
                    "total_tx_errors": getattr(self.bridge, "tx_error_count", 0),
                    "tx_queue_depth": self.bridge.rate_limiter.get_queue_depth(),
                    "offline_buffer_pending": self.bridge.store_and_forward.get_size(),
                    "sniffer_active": self.sniffer_active,
                }
                return 200, status_data

            # 2. GET /api/nodes
            if method == "GET" and clean_path == "/api/nodes":
                nodes = self.bridge.node_registry.list_nodes()
                return 200, {"count": len(nodes), "nodes": nodes}

            # 3. GET /api/analytics (Métricas Avanzadas: Top Nodos, Top Clientes, Top Errores)
            if method == "GET" and clean_path in ("/api/analytics", "/api/metrics/analytics"):
                analytics = self.bridge.node_registry.get_analytics_summary()
                analytics["queue_depth"] = self.bridge.rate_limiter.get_queue_depth()
                analytics["offline_buffer_size"] = self.bridge.store_and_forward.get_size()
                return 200, analytics

            # 4. GET /api/contacts
            if method == "GET" and clean_path == "/api/contacts":
                contacts = self.bridge.node_registry.list_nodes()
                return 200, {"contacts": contacts}

            # 5. POST /api/contacts
            if method == "POST" and clean_path == "/api/contacts":
                pubkey = str(req_body.get("public_key", req_body.get("key", ""))).strip()
                name = str(req_body.get("name", "")).strip()
                alias = str(req_body.get("alias", "")).strip()
                if not pubkey:
                    return 400, {"error": "Se requiere 'public_key'"}

                contact = self.bridge.node_registry.add_or_update(
                    public_key=pubkey,
                    name=name or f"Node_{pubkey[:6]}",
                    alias=alias,
                )
                self.log_system_event("INFO", f"Contacto guardado: {pubkey} ({alias or name})", source="contacts")
                return 200, {"status": "ok", "contact": contact.to_dict()}

            # 6. GET /api/channels
            if method == "GET" and clean_path == "/api/channels":
                return 200, {"channels": list(self.channels.values())}

            # 7. POST /api/channels
            if method == "POST" and clean_path == "/api/channels":
                idx = int(req_body.get("index", 1))
                name = str(req_body.get("name", f"Canal {idx}"))
                psk = str(req_body.get("psk", ""))
                self.channels[idx] = {
                    "index": idx,
                    "name": name,
                    "psk": psk,
                    "is_public": (idx == 0),
                }
                self.log_system_event("INFO", f"Canal {idx} actualizado: {name}", source="channels")
                return 200, {"status": "ok", "channel": self.channels[idx]}

            # 8. POST /api/tx (Transmisión RF)
            if method == "POST" and clean_path == "/api/tx":
                text = str(req_body.get("text", "")).strip()
                if not text:
                    return 400, {"error": "El campo 'text' no puede estar vacío"}

                target = req_body.get("to", req_body.get("target", "broadcast"))
                ch_idx = int(req_body.get("channel_index", req_body.get("channel_idx", 0)))
                req_id = req_body.get("request_id", f"web_{int(time.time() * 1000)}")

                tx_item = {
                    "to": target,
                    "channel_index": ch_idx,
                    "text": text,
                    "request_id": req_id,
                }
                res = await self.bridge._execute_tx(tx_item)
                if target != "broadcast":
                    self.bridge.node_registry.record_packet(public_key=target, is_rx=False)
                self.log_system_event("INFO", f"Transmisión TX enviada a {target} (Ch {ch_idx})", source="mesh_tx")
                return 200, {"status": "ok", "result": res}

            # 9. POST /api/sniffer/control (Control de Sniffer de Paquetes)
            if method == "POST" and clean_path == "/api/sniffer/control":
                action = str(req_body.get("action", "start")).lower().strip()
                self.sniffer_active = (action == "start")
                cmd_data = {
                    "target_node": req_body.get("target_node", "local"),
                    "action": f"log {action}",
                    "request_id": f"web_sniff_{int(time.time())}",
                }
                res = await self.bridge.handle_admin(cmd_data)
                self.log_system_event("INFO", f"Control de Sniffer RF: {action.upper()}", source="sniffer")
                return 200, {"status": "ok", "sniffer_active": self.sniffer_active, "result": res}

            # 10. POST /api/admin/command (Administración local)
            if method == "POST" and clean_path == "/api/admin/command":
                res = await self.bridge.handle_admin(req_body)
                self.log_system_event("INFO", f"Comando admin ejecutado: {req_body.get('action')}", source="admin")
                return 200, {"status": "ok", "result": res}

            # 11. POST /api/admin/repeater (Comandos a repetidores remotos)
            if method == "POST" and clean_path == "/api/admin/repeater":
                target_node = str(req_body.get("target_node", req_body.get("repeater", ""))).strip()
                action = str(req_body.get("action", req_body.get("command", "stats-radio")))
                if not target_node:
                    return 400, {"error": "Se requiere 'target_node'"}

                cmd_data = {
                    "target_node": target_node,
                    "action": action,
                    "params": req_body.get("params", {}),
                    "request_id": req_body.get("request_id", f"web_rep_{int(time.time())}"),
                }
                res = await self.bridge.handle_admin(cmd_data)
                self.log_system_event("INFO", f"Comando RF a repetidor {target_node}: {action}", source="repeater_admin")
                return 200, {"status": "ok", "result": res}

            # 12. GET /api/messages
            if method == "GET" and clean_path == "/api/messages":
                return 200, {"messages": list(self.recent_messages)}

            # 13. GET /api/telemetry
            if method == "GET" and clean_path == "/api/telemetry":
                return 200, {"telemetry": list(self.recent_telemetry)}

            # 14. GET /api/logs / /api/sniffer/logs (Sniffer RF)
            if method == "GET" and clean_path in ("/api/logs", "/api/sniffer/logs"):
                return 200, {"count": len(self.recent_rf_logs), "logs": list(self.recent_rf_logs)}

            # 15. GET /api/system/logs (Logs del Sistema)
            if method == "GET" and clean_path == "/api/system/logs":
                return 200, {"count": len(self.recent_system_logs), "system_logs": list(self.recent_system_logs)}

            return 404, {"error": f"Ruta no encontrada: {method} {clean_path}"}

        except Exception as e:
            logging.error(f"Error procesando solicitud REST {method} {clean_path}: {e}", exc_info=True)
            self.log_system_event("ERROR", f"Fallo en API {method} {clean_path}: {e}", source="api")
            return 500, {"error": str(e)}
