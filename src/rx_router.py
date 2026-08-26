"""
RxEventRouter: Enrutamiento de eventos entrantes de la radio hacia MQTT, n8n y WebSocket.
Extraído de MeshCoreBridge para separar responsabilidades y facilitar pruebas unitarias.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import config
from src.contact_manager import NodeContactUpdate, NodeRegistry, PacketRecord, is_valid_node_key
from src.mqtt_client import AsyncBridgeMQTTClient
from src.protocol_types import MeshcoreFrame, OpCode, TextMessagePayload
from src.repeater_manager import RepeaterManager
from src.sensor_decoder import CayenneLPPDecoder
from src.deduplicator import PacketDeduplicator

_SENDER_PREFIX_RE = re.compile(r"^([a-zA-Z0-9_\-\.]{2,32}):\s*(.*)$", re.DOTALL)


def extract_sender_from_text(text: str) -> tuple[str | None, str]:
    """Extrae el nombre del remitente si el texto tiene el prefijo 'Nombre: Mensaje'."""
    if not text or not isinstance(text, str):
        return None, text
    m = _SENDER_PREFIX_RE.match(text.strip())
    if m:
        candidate_name = m.group(1).strip()
        actual_text = m.group(2).strip()
        if candidate_name.lower() not in ("http", "https", "ftp", "ws", "wss", "json", "data", "cmd", "r", "ack", "req", "res", "echo", "status"):
            return candidate_name, actual_text
    return None, text



@dataclass(slots=True)
class MeshMessageEvent:
    """Representa un mensaje de texto normalizado recibido por RF."""
    sender: str
    sender_name: str
    text: str
    channel_idx: int
    rssi: float | int | None = None
    snr: float | None = None
    txt_type: int = 0


def is_command_or_system_message(text: str, txt_type: int = 0) -> bool:
    """
    Determina si un mensaje recibido es una respuesta de comando CLI, anuncio,
    telemetría de repetidor o mensaje de control de firmware (NO es chat común).
    """
    if txt_type == 1:
        return True

    if not text or not isinstance(text, str):
        return True

    clean = text.strip()
    if not clean:
        return True

    clean_lower = clean.lower()

    # Normalizar si contiene prefijos de prompt como "-> ", "- > ", "> "
    if clean_lower.startswith(("->", "- >", ">")):
        clean_lower = clean_lower.lstrip("-> ").strip()

    if (
        clean_lower.startswith((
            "unknown command",
            "error: unknown command",
            "error unknown command",
            "invalid command",
            "cmd ",
            "login ",
            "auth ",
            "stats-",
            "stats ",
            "set ",
            "get ",
            "log ",
            "reboot",
            "logging off",
            "log erased",
            "eof",
            "welcome admin",
            "access denied",
            "bad pin",
            "wrong password",
            "incorrect password",
            "permission denied",
            "not logged in",
        ))
        or clean_lower in (
            "unknown command",
            "ok",
            "error",
            "success",
            "failed",
            "unauthorized",
            "advert",
            "[advert]",
            "beacon",
            "logging off",
            "log erased",
            "eof",
            "pong",
            "ping",
        )
    ):
        return True

    # Respuestas de bots reflejadas
    if clean.startswith(("[Eco ", "[Status ", "[ACK", "📡 ", "⛔ ", "📖 ", "⏰ ", "📅 ", "🏓 ")):
        return True

    return False


def is_common_chat_message(text: str, txt_type: int = 0, event_type: str = "") -> bool:
    """
    Valida si un mensaje corresponde a mensajería de chat común de usuario
    (canal público, canal privado o DM directo).
    """
    if txt_type not in (0, 2):  # 0: Plain text, 2: Signed text
        return False

    if event_type and event_type not in ("public", "channel", "direct", "CHANNEL_MSG", "DIRECT_MSG"):
        return False

    return not is_command_or_system_message(text, txt_type)


class BridgeCounters(Protocol):
    """Protocolo estructural para contadores de telemetría del bridge."""
    rx_count: int
    tx_count: int
    tx_error_count: int
    err_count: int


@dataclass(slots=True)
class RxRouterContext:
    """Dependencias requeridas por el enrutador de recepción."""
    mqtt: AsyncBridgeMQTTClient
    node_registry: NodeRegistry
    repeater_manager: RepeaterManager
    deduplicator: PacketDeduplicator
    serial_adapter: Any
    web_server: Any
    loop: asyncio.AbstractEventLoop | None
    background_tasks: set[asyncio.Task[Any]]
    counters: BridgeCounters
    admin_handler: Any = None


class RxEventRouter:
    """Enruta eventos de la red Mesh (RF/radio) hacia MQTT, n8n y WebSocket."""

    def __init__(self, ctx: RxRouterContext) -> None:
        self._ctx = ctx

    def handle_event(self, event: Any) -> None:
        """Procesa y enruta eventos de la red Mesh hacia MQTT y n8n."""
        self._ctx.counters.rx_count += 1
        self._ctx.serial_adapter.heartbeat()

        try:
            if isinstance(event, MeshcoreFrame):
                loop = self._ctx.loop or asyncio.get_event_loop()
                task = loop.create_task(self._dispatch_parsed_frame(event))
                self._ctx.background_tasks.add(task)
                task.add_done_callback(self._ctx.background_tasks.discard)
                return

            ev_type_str = str(getattr(event, "type", getattr(event, "event_type", "")))
            payload_obj = getattr(event, "payload", getattr(event, "data", event))

            if isinstance(payload_obj, dict):
                payload_dict = dict(payload_obj)
            elif hasattr(payload_obj, "__dict__"):
                payload_dict = {k: v for k, v in payload_obj.__dict__.items() if not k.startswith("_")}
            else:
                payload_dict = {"raw": str(payload_obj)}

            if payload_dict.get("is_outgoing") is True:
                return

            rssi = payload_dict.get("rssi", payload_dict.get("RSSI"))
            snr = payload_dict.get("snr", payload_dict.get("SNR"))
            sender_raw = str(payload_dict.get("sender", payload_dict.get("pubkey_prefix", payload_dict.get("public_key", "")))).strip()
            sender = self._ctx.node_registry.get_canonical_key(sender_raw) if is_valid_node_key(sender_raw) else ""
            sender_name = str(payload_dict.get("sender_name", payload_dict.get("adv_name", payload_dict.get("name", self._resolve_sender_name(sender))))) if sender else ""
            text = str(payload_dict.get("text", payload_dict.get("message", ""))).strip()
            channel_idx = int(payload_dict.get("channel_idx", payload_dict.get("channel", 0)))
            hops = int(payload_dict.get("hop_count", payload_dict.get("hops", 0)))

            # Extracción inteligente de nombre desde el cuerpo del texto si viene en formato 'Nombre: Mensaje'
            extracted_name, _ = extract_sender_from_text(text)
            if extracted_name:
                if not sender_name or sender_name.lower() in ("unknown", "anónimo", "anonimo", "") or sender_name == sender:
                    sender_name = extracted_name
                if not sender or not is_valid_node_key(sender):
                    found_c = self._ctx.node_registry.find_by_name(extracted_name)
                    if found_c and is_valid_node_key(found_c.public_key):
                        sender = found_c.public_key

            # Normalizar métricas de enlace RF de forma global

            is_local_sender = bool(sender and is_valid_node_key(sender) and self._ctx.node_registry.is_local_key(sender))
            effective_rssi = None if is_local_sender else (int(rssi) if isinstance(rssi, (int, float)) else None)
            effective_snr = None if is_local_sender else (float(snr) if isinstance(snr, (int, float)) else None)
            effective_hops = 0 if is_local_sender else hops

            # Actualizar directorio dinámico de nodos
            if sender and is_valid_node_key(sender):
                bat_pct = int(payload_dict["battery"]) if "battery" in payload_dict and isinstance(payload_dict["battery"], (int, float)) else None

                role_val = payload_dict.get("role")
                if not role_val:
                    raw_type = payload_dict.get("adv_type", payload_dict.get("type"))
                    if raw_type == 2 or raw_type == "REPEATER":
                        role_val = "REPEATER"
                    elif raw_type == 3 or raw_type == "ROOM":
                        role_val = "ROOM"
                    elif raw_type == 4 or raw_type == "SENSOR":
                        role_val = "SENSOR"
                    elif raw_type == 1 or raw_type == "CHAT" or raw_type == "CLIENT":
                        role_val = "CLIENT"

                def _get_coord(d: dict[str, Any], keys: tuple[str, ...]) -> float | None:
                    for k in keys:
                        if k in d and d[k] is not None:
                            try:
                                v = float(d[k])
                                if v != 0.0:
                                    return v
                            except (ValueError, TypeError):
                                pass
                    for sub in ("gps", "position", "pos", "location"):
                        if sub in d and isinstance(d[sub], dict):
                            res = _get_coord(d[sub], keys)
                            if res is not None:
                                return res
                    return None

                lat_val = _get_coord(payload_dict, ("lat", "latitude", "gps_lat"))
                lon_val = _get_coord(payload_dict, ("lon", "longitude", "gps_lon"))

                effective_role = "LOCAL" if is_local_sender else (role_val or "CLIENT")

                is_new, contact_info = self._ctx.node_registry.discover_node(
                    public_key=sender,
                    name=sender_name if sender_name and sender_name != sender else None,
                    role=effective_role,
                    rssi=effective_rssi,
                    snr=effective_snr,
                    hops=effective_hops,
                )

                if is_valid_node_key(contact_info.public_key):
                    if lat_val is not None or lon_val is not None or bat_pct is not None:
                        contact_info = self._ctx.node_registry.add_or_update(
                            sender,
                            NodeContactUpdate(
                                battery_pct=bat_pct,
                                latitude=lat_val,
                                longitude=lon_val,
                                is_local=is_local_sender,
                            ),
                        )

                    if not is_local_sender:
                        self._ctx.node_registry.record_packet(
                            PacketRecord(
                                public_key=sender,
                                is_rx=True,
                                rssi=effective_rssi,
                                snr=effective_snr,
                                hop_count=effective_hops,
                            )
                        )
                        if self._ctx.web_server:
                            self._ctx.web_server.broadcast_event({
                                "type": "contact_discovered" if is_new else "contact_updated",
                                "event_type": "contact_discovered" if is_new else "contact_updated",
                                "is_new": is_new,
                                "contact": contact_info.to_dict(),
                            })

            ev_upper = ev_type_str.upper()
            p_type_upper = str(payload_dict.get("type", "")).upper()
            ev_attrs = getattr(event, "attributes", {}) if hasattr(event, "attributes") and isinstance(event.attributes, dict) else {}

            # Caso Descubrimiento / Importación de Contacto (CONTACT, NEXT_CONTACT, CONTACTS, ADVERTISEMENT)
            if "CONTACT" in ev_upper or "ADVERT" in ev_upper or "ADVERTISEMENT" in ev_upper:
                c_items: list[dict[str, Any]] = []
                if isinstance(payload_obj, list):
                    c_items = [x for x in payload_obj if isinstance(x, dict)]
                elif isinstance(payload_obj, dict):
                    if "contacts" in payload_obj and isinstance(payload_obj["contacts"], list):
                        c_items = [x for x in payload_obj["contacts"] if isinstance(x, dict)]
                    else:
                        c_items = [payload_obj]

                for c_item in c_items:
                    c_pk = str(c_item.get("public_key", c_item.get("key", c_item.get("pubkey", "")))).strip().lower()
                    if not c_pk or not is_valid_node_key(c_pk):
                        continue

                    c_name = str(c_item.get("adv_name", c_item.get("name", c_item.get("alias", f"Node_{c_pk[:6]}")))).strip()
                    c_raw_type = c_item.get("type", c_item.get("adv_type", 1))
                    c_name_upper = c_name.upper()
                    if c_raw_type == 2 or c_name_upper.startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-")) or "REPEATER" in c_name_upper or "ROUTER" in c_name_upper:
                        c_role = "REPEATER"
                    elif c_raw_type == 3 or "ROOM" in c_name_upper or "BBS" in c_name_upper:
                        c_role = "ROOM"
                    elif c_raw_type == 4 or "SENSOR" in c_name_upper:
                        c_role = "SENSOR"
                    else:
                        c_role = "CLIENT"

                    c_lat = _get_coord(c_item, ("adv_lat", "lat", "latitude", "gps_lat"))
                    c_lon = _get_coord(c_item, ("adv_lon", "lon", "longitude", "gps_lon"))
                    c_bat = _safe_int(c_item.get("battery_pct", c_item.get("battery", c_item.get("batt"))))

                    is_c_new, c_contact_info = self._ctx.node_registry.discover_node(
                        public_key=c_pk,
                        name=c_name,
                        role=c_role,
                        rssi=effective_rssi,
                        snr=effective_snr,
                        hops=effective_hops,
                    )
                    self._ctx.node_registry.add_or_update(
                        c_pk,
                        NodeContactUpdate(
                            name=c_name,
                            alias=c_name,
                            role=c_role,
                            latitude=c_lat,
                            longitude=c_lon,
                            battery_pct=c_bat,
                            auto_discovered=False,
                            is_favorite=True,
                        ),
                    )
                    if self._ctx.web_server:
                        self._ctx.web_server.broadcast_event({
                            "type": "contact_discovered" if is_c_new else "contact_updated",
                            "event_type": "contact_discovered" if is_c_new else "contact_updated",
                            "is_new": is_c_new,
                            "contact": c_contact_info.to_dict(),
                        })

            # Caso ACK de Entrega E2E (Delivery Receipt)
            if "ACK" in ev_upper or "ACK" in p_type_upper or payload_dict.get("event_type") == "ack" or "code" in payload_dict or "code" in ev_attrs:
                raw_code = payload_dict.get("code", payload_dict.get("ack_code", ev_attrs.get("code", "")))
                if isinstance(raw_code, bytes):
                    ack_code = raw_code.hex().lower()
                elif isinstance(raw_code, int):
                    ack_code = hex(raw_code)[2:].lower()
                else:
                    ack_code = str(raw_code).strip().lower()

                trip_time = float(payload_dict.get("trip_time_ms", payload_dict.get("trip_time", payload_dict.get("rtt", 0.0))))
                ack_msg_id = str(payload_dict.get("msg_id", payload_dict.get("id", ""))).strip()

                admin = getattr(self._ctx, "admin_handler", None)
                if admin and hasattr(admin, "notify_ping_response"):
                    admin.notify_ping_response(
                        sender,
                        {
                            "trip_time": trip_time,
                            "rssi": effective_rssi,
                            "snr_there": effective_snr,
                            "snr_back": effective_snr,
                            "source": "ack",
                        },
                    )

                ack_evt_data = {
                    "type": "message_delivered",
                    "event_type": "message_delivered",
                    "msg_id": ack_msg_id,
                    "ack_code": ack_code,
                    "trip_time_ms": trip_time,
                    "recipient": sender,
                    "status": "delivered",
                    "rssi": effective_rssi,
                    "snr": effective_snr,
                }

                if self._ctx.web_server:
                    self._ctx.web_server.broadcast_event(ack_evt_data)

                self._ctx.mqtt.publish_safe(
                    config.TOPIC_TX_STATUS,
                    json.dumps(ack_evt_data),
                    qos=1,
                )
                return

            # Caso Trace Path / Traceroute
            if "TRACE" in ev_upper or "TRACE" in p_type_upper or payload_dict.get("event_type") == "trace":
                path_nodes = payload_dict.get("path", [])
                snr_there = path_nodes[0].get("snr") if path_nodes and isinstance(path_nodes[0], dict) else None
                snr_back = path_nodes[-1].get("snr") if path_nodes and isinstance(path_nodes[-1], dict) else None
                rssi_trace = payload_dict.get("rssi", payload_dict.get("RSSI", effective_rssi))
                tag = payload_dict.get("tag")

                admin = getattr(self._ctx, "admin_handler", None)
                if admin and hasattr(admin, "notify_ping_response"):
                    admin.notify_ping_response(
                        str(tag) if tag else sender,
                        {
                            "snr_there": snr_there,
                            "snr_back": snr_back,
                            "rssi": rssi_trace,
                            "tag": tag,
                            "source": "trace",
                        },
                    )

                if self._ctx.web_server:
                    self._ctx.web_server.broadcast_event({
                        "type": "trace_data",
                        "data": payload_dict,
                    })
                return

            raw_txt_type = payload_dict.get("txt_type", payload_dict.get("text_type", 0))
            try:
                txt_type = int(raw_txt_type)
            except (ValueError, TypeError):
                txt_type = 0

            # Caso Anuncio / Presencia (ADVERT / ADVERTISEMENT / NODE_ADVERT / NEW_CONTACT)
            is_advert = (
                "ADVERT" in ev_upper
                or "ADVERT" in p_type_upper
                or payload_dict.get("event_type") in ("advert", "node_advert", "node_discovered", "advertisement")
                or ev_upper in ("NEW_CONTACT", "CONTACT_UPDATE", "NODE_DISCOVERED")
            )
            if is_advert:
                if "event_type" not in payload_dict:
                    payload_dict["event_type"] = "advert"
                self._handle_mesh_telemetry_msg(payload_dict)
                return

            # Caso Telemetría explícita o estadísticas
            is_explicit_telem = (
                "TELEM" in ev_upper
                or "STATS" in ev_upper
                or payload_dict.get("event_type") in ("telemetry", "repeater_telemetry", "stats_radio", "stats_core")
                or "temperature_c" in payload_dict
                or "battery_mv" in payload_dict
                or "solar_mv" in payload_dict
            )
            if is_explicit_telem and not ("CONTACT" in ev_upper or "CHANNEL" in ev_upper or "DIRECT" in ev_upper):
                if "event_type" not in payload_dict:
                    payload_dict["event_type"] = "telemetry"
                self._handle_mesh_telemetry_msg(payload_dict)
                return

            is_direct = (
                "CONTACT" in ev_upper
                or "DIRECT" in ev_upper
                or "PRIV" in p_type_upper
                or payload_dict.get("event_type") == "direct"
            )
            is_channel = (
                "CHANNEL" in ev_upper
                or "CHAN" in p_type_upper
                or payload_dict.get("event_type") in ("public", "channel")
                or (bool(text) and not is_direct)
            )

            if is_direct and text:
                self._handle_mesh_direct_msg(MeshMessageEvent(sender, sender_name, text, channel_idx, effective_rssi, effective_snr, txt_type))
            elif is_channel and text:
                self._handle_mesh_channel_msg(MeshMessageEvent(sender, sender_name, text, channel_idx, effective_rssi, effective_snr, txt_type))
            else:
                if "event_type" not in payload_dict:
                    payload_dict["event_type"] = "telemetry"
                self._handle_mesh_telemetry_msg(payload_dict)

        except Exception as e:
            self._ctx.counters.err_count += 1
            logging.error(f"Error procesando evento de radio Mesh: {e}", exc_info=True)

    def _resolve_sender_name(self, prefix_or_key: str) -> str:
        # Primero consultar el registro dinámico local
        local_name = self._ctx.node_registry.resolve_name(prefix_or_key)
        if local_name and local_name != prefix_or_key:
            return local_name
        return str(self._ctx.serial_adapter.resolve_sender_name(prefix_or_key))

    def _handle_mesh_channel_msg(self, msg: MeshMessageEvent) -> None:
        # Analizar si el mensaje de canal contiene telemetría o respuestas de comandos
        extracted_telem = self._ctx.repeater_manager.parse_repeater_telemetry_or_response(msg.text)
        if extracted_telem:
            self._ctx.node_registry.add_or_update(
                msg.sender,
                NodeContactUpdate(
                    name=msg.sender_name,
                    role="REPEATER",
                    last_rssi=int(msg.rssi) if isinstance(msg.rssi, (int, float)) else extracted_telem.get("last_rssi"),
                    last_snr=float(msg.snr) if isinstance(msg.snr, (int, float)) else extracted_telem.get("last_snr"),
                    battery_pct=extracted_telem.get("battery_pct"),
                    voltage_v=extracted_telem.get("voltage_v"),
                    solar_v=extracted_telem.get("solar_v"),
                    latitude=extracted_telem.get("latitude"),
                    longitude=extracted_telem.get("longitude"),
                    altitude_m=extracted_telem.get("altitude_m"),
                    fixed_position=extracted_telem.get("fixed_position"),
                    uptime=extracted_telem.get("uptime"),
                    clock=extracted_telem.get("clock"),
                    airtime_ms=extracted_telem.get("airtime_ms"),
                    noise_floor_dbm=extracted_telem.get("noise_floor_dbm"),
                    packets_sent=extracted_telem.get("packets_sent"),
                    packets_recv=extracted_telem.get("packets_recv"),
                    duplicate_packets=extracted_telem.get("duplicate_packets"),
                    packet_errors=extracted_telem.get("packet_errors"),
                    queue_len=extracted_telem.get("queue_len"),
                    owner_name=extracted_telem.get("owner_name"),
                    owner_info=extracted_telem.get("owner_info"),
                    firmware_version=extracted_telem.get("firmware_version"),
                    hardware_board=extracted_telem.get("hardware_board"),
                    frequency=extracted_telem.get("frequency"),
                    tx_power=extracted_telem.get("tx_power"),
                    spreading_factor=extracted_telem.get("spreading_factor"),
                    bandwidth=extracted_telem.get("bandwidth"),
                    coding_rate=extracted_telem.get("coding_rate"),
                    repeat_enabled=extracted_telem.get("repeat_enabled"),
                    advert_interval=extracted_telem.get("advert_interval"),
                    hops=extracted_telem.get("hops"),
                ),
            )

        sender_contact = self._ctx.node_registry.get_contact(msg.sender)
        is_repeater_sender = (
            (sender_contact and sender_contact.role in ("REPEATER", "ROUTER"))
            or bool(extracted_telem)
            or (msg.sender_name and (
                msg.sender_name.upper().startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-"))
                or "REPEATER" in msg.sender_name.upper()
                or "ROUTER" in msg.sender_name.upper()
            ))
        )
        is_cmd_response = (
            msg.txt_type == 1
            or is_repeater_sender
            or is_command_or_system_message(msg.text, msg.txt_type)
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        if is_cmd_response:
            admin = getattr(self._ctx, "admin_handler", None)
            if admin:
                cmd_resp_payload = {
                    "rssi": msg.rssi,
                    "snr_there": msg.snr,
                    "snr_back": msg.snr,
                    "snr": msg.snr,
                    "text": msg.text,
                    "message": msg.text,
                    "channel_idx": msg.channel_idx,
                    "telemetry": extracted_telem,
                    "source": "repeater_response",
                }
                if hasattr(admin, "notify_command_response"):
                    admin.notify_command_response(msg.sender, cmd_resp_payload)
                elif hasattr(admin, "notify_ping_response"):
                    admin.notify_ping_response(msg.sender, cmd_resp_payload)

            # Es una respuesta de comando o telemetría: NO emitir como mensaje de canal de chat
            rep_payload = {
                "type": "repeater_response",
                "event_type": "repeater_response",
                "sender": msg.sender,
                "sender_name": msg.sender_name,
                "text": msg.text,
                "channel_idx": msg.channel_idx,
                "channel_index": msg.channel_idx,
                "telemetry": extracted_telem if extracted_telem else None,
                "rssi": msg.rssi,
                "snr": msg.snr,
                "timestamp": now_iso,
            }
            if extracted_telem:
                self._ctx.mqtt.publish_safe(config.TOPIC_RX_TELEMETRY, json.dumps({
                    "event_type": "repeater_telemetry",
                    "sender": msg.sender,
                    "sender_name": msg.sender_name,
                    "telemetry": extracted_telem,
                    "timestamp": now_iso,
                }), qos=0)
            self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, json.dumps(rep_payload, sort_keys=True), qos=0)
            if self._ctx.web_server:
                self._ctx.web_server.broadcast_event(rep_payload)
            return

        event_type = "public" if msg.channel_idx == 0 else "channel"
        evt_payload = {
            "event_type": event_type,
            "sender": msg.sender,
            "sender_name": msg.sender_name,
            "text": msg.text,
            "channel_idx": msg.channel_idx,
            "channel_index": msg.channel_idx,
            "txt_type": msg.txt_type,
            "rssi": msg.rssi,
            "snr": msg.snr,
            "metrics": {
                "rssi": msg.rssi,
                "snr": msg.snr,
            },
            "timestamp": now_iso,
        }
        evt_json = json.dumps(evt_payload, sort_keys=True)

        if msg.channel_idx == 0:
            self._ctx.mqtt.publish_safe(config.TOPIC_RX_PUBLIC, evt_json, qos=0)
        else:
            self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_CHANNEL}/ch_{msg.channel_idx}", evt_json, qos=0)

        self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)
        if self._ctx.web_server:
            self._ctx.web_server.broadcast_event(evt_payload)

    def _handle_mesh_direct_msg(self, msg: MeshMessageEvent) -> None:
        # Analizar si el mensaje de texto contiene telemetría o respuestas de comandos del repetidor
        extracted_telem = self._ctx.repeater_manager.parse_repeater_telemetry_or_response(msg.text)
        if extracted_telem:
            self._ctx.node_registry.add_or_update(
                msg.sender,
                NodeContactUpdate(
                    name=msg.sender_name,
                    role="REPEATER",
                    last_rssi=int(msg.rssi) if isinstance(msg.rssi, (int, float)) else extracted_telem.get("last_rssi"),
                    last_snr=float(msg.snr) if isinstance(msg.snr, (int, float)) else extracted_telem.get("last_snr"),
                    battery_pct=extracted_telem.get("battery_pct"),
                    voltage_v=extracted_telem.get("voltage_v"),
                    solar_v=extracted_telem.get("solar_v"),
                    latitude=extracted_telem.get("latitude"),
                    longitude=extracted_telem.get("longitude"),
                    altitude_m=extracted_telem.get("altitude_m"),
                    fixed_position=extracted_telem.get("fixed_position"),
                    uptime=extracted_telem.get("uptime"),
                    clock=extracted_telem.get("clock"),
                    airtime_ms=extracted_telem.get("airtime_ms"),
                    noise_floor_dbm=extracted_telem.get("noise_floor_dbm"),
                    packets_sent=extracted_telem.get("packets_sent"),
                    packets_recv=extracted_telem.get("packets_recv"),
                    duplicate_packets=extracted_telem.get("duplicate_packets"),
                    packet_errors=extracted_telem.get("packet_errors"),
                    queue_len=extracted_telem.get("queue_len"),
                    owner_name=extracted_telem.get("owner_name"),
                    owner_info=extracted_telem.get("owner_info"),
                    firmware_version=extracted_telem.get("firmware_version"),
                    hardware_board=extracted_telem.get("hardware_board"),
                    frequency=extracted_telem.get("frequency"),
                    tx_power=extracted_telem.get("tx_power"),
                    spreading_factor=extracted_telem.get("spreading_factor"),
                    bandwidth=extracted_telem.get("bandwidth"),
                    coding_rate=extracted_telem.get("coding_rate"),
                    repeat_enabled=extracted_telem.get("repeat_enabled"),
                    advert_interval=extracted_telem.get("advert_interval"),
                    hops=extracted_telem.get("hops"),
                ),
            )

        # Verificar si el emisor es un repetidor o si el texto es una respuesta de comando/diagnóstico
        sender_contact = self._ctx.node_registry.get_contact(msg.sender)
        is_repeater_sender = (
            (sender_contact and sender_contact.role in ("REPEATER", "ROUTER"))
            or bool(extracted_telem)
            or (msg.sender_name and (
                msg.sender_name.upper().startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-"))
                or "REPEATER" in msg.sender_name.upper()
                or "ROUTER" in msg.sender_name.upper()
            ))
        )
        is_cmd_response = (
            msg.txt_type == 1
            or is_repeater_sender
            or is_command_or_system_message(msg.text, msg.txt_type)
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        if is_cmd_response:
            admin = getattr(self._ctx, "admin_handler", None)
            if admin:
                cmd_resp_payload = {
                    "rssi": msg.rssi,
                    "snr_there": msg.snr,
                    "snr_back": msg.snr,
                    "snr": msg.snr,
                    "text": msg.text,
                    "message": msg.text,
                    "telemetry": extracted_telem,
                    "source": "repeater_response",
                }
                if hasattr(admin, "notify_command_response"):
                    admin.notify_command_response(msg.sender, cmd_resp_payload)
                elif hasattr(admin, "notify_ping_response"):
                    admin.notify_ping_response(msg.sender, cmd_resp_payload)

            # Es una respuesta de comando o telemetría de repetidor: NO emitir como chat directo de usuario
            rep_payload = {
                "type": "repeater_response",
                "event_type": "repeater_response",
                "sender": msg.sender,
                "sender_name": msg.sender_name,
                "text": msg.text,
                "telemetry": extracted_telem if extracted_telem else None,
                "rssi": msg.rssi,
                "snr": msg.snr,
                "timestamp": now_iso,
            }
            if extracted_telem:
                self._ctx.mqtt.publish_safe(config.TOPIC_RX_TELEMETRY, json.dumps({
                    "event_type": "repeater_telemetry",
                    "sender": msg.sender,
                    "sender_name": msg.sender_name,
                    "telemetry": extracted_telem,
                    "timestamp": now_iso,
                }), qos=0)
            self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, json.dumps(rep_payload, sort_keys=True), qos=0)
            if self._ctx.web_server:
                self._ctx.web_server.broadcast_event(rep_payload)
            return

        evt_payload = {
            "event_type": "direct",
            "sender": msg.sender,
            "sender_name": msg.sender_name,
            "text": msg.text,
            "channel_idx": msg.channel_idx,
            "txt_type": msg.txt_type,
            "rssi": msg.rssi,
            "snr": msg.snr,
            "metrics": {
                "rssi": msg.rssi,
                "snr": msg.snr,
            },
            "telemetry": extracted_telem if extracted_telem else None,
            "timestamp": now_iso,
        }
        evt_json = json.dumps(evt_payload, sort_keys=True)

        topic = f"{config.TOPIC_RX_DIRECT}/{msg.sender}"
        self._ctx.mqtt.publish_safe(topic, evt_json, qos=1)
        self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)

        if self._ctx.web_server:
            self._ctx.web_server.broadcast_event(evt_payload)

    def _handle_mesh_telemetry_msg(self, payload_dict: dict[str, Any]) -> None:
        if "raw_bytes" in payload_dict and isinstance(payload_dict["raw_bytes"], (bytes, bytearray)):
            raw_b = bytes(payload_dict["raw_bytes"])
            _readings, summary = CayenneLPPDecoder.decode(raw_b)
            payload_dict["raw_hex"] = raw_b.hex()
            payload_dict.pop("raw_bytes", None)
            payload_dict.update(summary)

        # Si el payload contiene texto de telemetría de repetidor
        raw_text_cand = payload_dict.get("text", payload_dict.get("raw_text", payload_dict.get("message", "")))
        if isinstance(raw_text_cand, str) and raw_text_cand.strip():
            extracted = self._ctx.repeater_manager.parse_repeater_telemetry_or_response(raw_text_cand)
            if extracted:
                payload_dict.update(extracted)
                sender = str(payload_dict.get("sender", payload_dict.get("public_key", "")))
                if sender:
                    self._ctx.node_registry.add_or_update(
                        sender,
                        NodeContactUpdate(
                            name=str(payload_dict.get("sender_name", self._resolve_sender_name(sender))),
                            role="REPEATER",
                            battery_pct=extracted.get("battery_pct"),
                            voltage_v=extracted.get("voltage_v"),
                            solar_v=extracted.get("solar_v"),
                            latitude=extracted.get("latitude"),
                            longitude=extracted.get("longitude"),
                            altitude_m=extracted.get("altitude_m"),
                            fixed_position=extracted.get("fixed_position"),
                            uptime=extracted.get("uptime"),
                            clock=extracted.get("clock"),
                            airtime_ms=extracted.get("airtime_ms"),
                            noise_floor_dbm=extracted.get("noise_floor_dbm"),
                            packets_sent=extracted.get("packets_sent"),
                            packets_recv=extracted.get("packets_recv"),
                            duplicate_packets=extracted.get("duplicate_packets"),
                            packet_errors=extracted.get("packet_errors"),
                            queue_len=extracted.get("queue_len"),
                            owner_name=extracted.get("owner_name"),
                            owner_info=extracted.get("owner_info"),
                            firmware_version=extracted.get("firmware_version"),
                            hardware_board=extracted.get("hardware_board"),
                            frequency=extracted.get("frequency"),
                            tx_power=extracted.get("tx_power"),
                            spreading_factor=extracted.get("spreading_factor"),
                            bandwidth=extracted.get("bandwidth"),
                            coding_rate=extracted.get("coding_rate"),
                            repeat_enabled=extracted.get("repeat_enabled"),
                            advert_interval=extracted.get("advert_interval"),
                            hops=extracted.get("hops"),
                        ),
                    )

        # Sanitizar cualquier otro campo bytes restante
        for k, v in list(payload_dict.items()):
            if isinstance(v, (bytes, bytearray)):
                payload_dict[k] = bytes(v).hex()

        payload_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
        evt_json = json.dumps(payload_dict, sort_keys=True)
        self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)
        if "battery" in payload_dict or "battery_pct" in payload_dict or "voltage" in payload_dict or "temperature" in payload_dict or "temperature_c" in payload_dict:
            self._ctx.mqtt.publish_safe(config.TOPIC_RX_TELEMETRY, evt_json, qos=0)
        if self._ctx.web_server:
            self._ctx.web_server.broadcast_event(payload_dict)

    async def _dispatch_parsed_frame(self, frame: MeshcoreFrame) -> None:
        """Enruta instancias de MeshcoreFrame validadas a MQTT."""
        mqtt_evt = frame.to_mqtt_event()
        evt_json = json.dumps(mqtt_evt)

        dedup_key = f"frame::{frame.header.src_node_id}::{frame.header.seq_num}::{int(frame.header.opcode)}"
        if await self._ctx.deduplicator.is_duplicate(dedup_key):
            return

        self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)

        if frame.header.opcode == OpCode.TELEMETRY:
            self._ctx.mqtt.publish_safe(config.TOPIC_RX_TELEMETRY, evt_json, qos=0)
        elif frame.header.opcode == OpCode.NODE_ADVERT:
            self._ctx.mqtt.publish_safe(config.TOPIC_RX_NODES, evt_json, qos=0)
        elif frame.header.opcode == OpCode.TEXT_MSG:
            if isinstance(frame.payload, TextMessagePayload):
                if not is_common_chat_message(frame.payload.text):
                    return
                if frame.payload.channel_idx == 0:
                    self._ctx.mqtt.publish_safe(config.TOPIC_RX_PUBLIC, evt_json, qos=0)
                else:
                    self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_CHANNEL}/ch_{frame.payload.channel_idx}", evt_json, qos=0)

                src_hex = f"0x{frame.header.src_node_id:04X}"
                self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_DIRECT}/{src_hex}", evt_json, qos=0)
