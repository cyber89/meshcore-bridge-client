"""
Web API Router and REST Controller for MeshCore Web Client.
Procesa solicitudes HTTP REST para mensajería, gestión de contactos, canales cifrados,
telemetría y administración remota de repetidores.
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
        self.recent_messages: collections.deque[dict[str, Any]] = collections.deque(maxlen=100)
        self.recent_telemetry: collections.deque[dict[str, Any]] = collections.deque(maxlen=100)
        self.recent_rf_logs: collections.deque[dict[str, Any]] = collections.deque(maxlen=100)

    def record_incoming_event(self, event_data: dict[str, Any]) -> None:
        """Almacena eventos recientes para consulta del cliente web."""
        ev_type = str(event_data.get("event_type", ""))
        if "log" in ev_type or "rf_log" in ev_type:
            self.recent_rf_logs.append(event_data)
        elif "telemetry" in ev_type or "temperature_c" in event_data or "battery_pct" in event_data or "battery" in event_data:
            self.recent_telemetry.append(event_data)
        else:
            self.recent_messages.append(event_data)

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
                }
                return 200, status_data

            # 2. GET /api/nodes
            if method == "GET" and clean_path == "/api/nodes":
                nodes = self.bridge.node_registry.list_nodes()
                return 200, {"count": len(nodes), "nodes": nodes}

            # 3. GET /api/contacts
            if method == "GET" and clean_path == "/api/contacts":
                contacts = self.bridge.node_registry.list_nodes()
                return 200, {"contacts": contacts}

            # 4. POST /api/contacts
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
                return 200, {"status": "ok", "contact": contact.to_dict()}

            # 5. GET /api/channels
            if method == "GET" and clean_path == "/api/channels":
                return 200, {"channels": list(self.channels.values())}

            # 6. POST /api/channels
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
                return 200, {"status": "ok", "channel": self.channels[idx]}

            # 7. POST /api/tx (Transmisión RF)
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
                return 200, {"status": "ok", "result": res}

            # 8. POST /api/admin/command (Administración local)
            if method == "POST" and clean_path == "/api/admin/command":
                res = await self.bridge.handle_admin(req_body)
                return 200, {"status": "ok", "result": res}

            # 9. POST /api/admin/repeater (Comandos a repetidores remotos)
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
                return 200, {"status": "ok", "result": res}

            # 10. GET /api/messages
            if method == "GET" and clean_path == "/api/messages":
                return 200, {"messages": list(self.recent_messages)}

            # 11. GET /api/telemetry
            if method == "GET" and clean_path == "/api/telemetry":
                return 200, {"telemetry": list(self.recent_telemetry)}

            # 12. GET /api/logs
            if method == "GET" and clean_path == "/api/logs":
                return 200, {"logs": list(self.recent_rf_logs)}

            return 404, {"error": f"Ruta no encontrada: {method} {clean_path}"}

        except Exception as e:
            logging.error(f"Error procesando solicitud REST {method} {clean_path}: {e}", exc_info=True)
            return 500, {"error": str(e)}
