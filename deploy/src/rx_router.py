"""
RxEventRouter: Enrutamiento de eventos entrantes de la radio hacia MQTT, n8n y WebSocket.
Extraído de MeshCoreBridge para separar responsabilidades y facilitar pruebas unitarias.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import config
from src.contact_manager import NodeContactUpdate, NodeRegistry, PacketRecord
from src.mqtt_client import AsyncBridgeMQTTClient
from src.protocol_types import MeshcoreFrame, OpCode, TextMessagePayload
from src.repeater_manager import RepeaterManager
from src.sensor_decoder import CayenneLPPDecoder
from src.store_forward import PacketDeduplicator


@dataclass(slots=True)
class MeshMessageEvent:
    """Representa un mensaje de texto normalizado recibido por RF."""
    sender: str
    sender_name: str
    text: str
    channel_idx: int
    rssi: float | int | None = None
    snr: float | None = None


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
    store_forward: Any = None
    store_and_forward: Any = None


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

            # Caso Sniffer RF (0x88 / LOG_DATA / RX_LOG_DATA)
            if "LOG_DATA" in ev_type_str.upper() or "rf_log" in ev_type_str.lower():
                raw_target = payload_dict.get("raw", payload_obj)
                parsed_log = self._ctx.repeater_manager.parse_log_packet(raw_target)
                self._ctx.mqtt.publish_safe(config.TOPIC_RX_LOG, json.dumps(parsed_log), qos=0)
                if self._ctx.web_server:
                    self._ctx.web_server.broadcast_event(parsed_log)
                return

            if payload_dict.get("is_outgoing") is True:
                return

            rssi = payload_dict.get("rssi", payload_dict.get("RSSI"))
            snr = payload_dict.get("snr", payload_dict.get("SNR"))
            sender_raw = str(payload_dict.get("sender", payload_dict.get("pubkey_prefix", payload_dict.get("public_key", "unknown")))).strip()
            sender = self._ctx.node_registry.get_canonical_key(sender_raw)
            sender_name = str(payload_dict.get("sender_name", self._resolve_sender_name(sender)))
            text = str(payload_dict.get("text", payload_dict.get("message", ""))).strip()
            channel_idx = int(payload_dict.get("channel_idx", payload_dict.get("channel", 0)))
            hops = int(payload_dict.get("hop_count", payload_dict.get("hops", 0)))

            # Actualizar directorio dinámico de nodos
            if sender and sender != "unknown":
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

                is_local_sender = self._ctx.node_registry.is_local_key(sender)
                effective_role = "LOCAL" if is_local_sender else (role_val or "CLIENT")
                effective_rssi = None if is_local_sender else (int(rssi) if isinstance(rssi, (int, float)) else None)
                effective_snr = None if is_local_sender else (float(snr) if isinstance(snr, (int, float)) else None)
                effective_hops = 0 if is_local_sender else hops

                is_new, contact_info = self._ctx.node_registry.discover_node(
                    public_key=sender,
                    name=sender_name if sender_name != sender else None,
                    role=effective_role,
                    rssi=effective_rssi,
                    snr=effective_snr,
                    hops=effective_hops,
                )

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

            # Caso ACK de Entrega E2E (Delivery Receipt)
            if "ACK" in ev_upper or "ACK" in p_type_upper or payload_dict.get("event_type") == "ack" or "code" in payload_dict or "code" in ev_attrs:
                ack_code = str(payload_dict.get("code", payload_dict.get("ack_code", ev_attrs.get("code", "")))).strip().lower()
                trip_time = float(payload_dict.get("trip_time_ms", payload_dict.get("trip_time", payload_dict.get("rtt", 0.0))))
                ack_msg_id = str(payload_dict.get("msg_id", payload_dict.get("id", ""))).strip()

                if not ack_msg_id and ack_code and getattr(self._ctx, "store_forward", None):
                    ack_msg_id = self._ctx.store_forward.get_msg_id_by_expected_ack(ack_code) or ""

                if ack_msg_id and getattr(self._ctx, "store_forward", None):
                    self._ctx.store_forward.mark_message_delivered(ack_msg_id, trip_time)

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
                self._handle_mesh_direct_msg(MeshMessageEvent(sender, sender_name, text, channel_idx, rssi, snr))
            elif is_channel and text:
                self._handle_mesh_channel_msg(MeshMessageEvent(sender, sender_name, text, channel_idx, rssi, snr))
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
        event_type = "public" if msg.channel_idx == 0 else "channel"
        evt_payload = {
            "event_type": event_type,
            "sender": msg.sender,
            "sender_name": msg.sender_name,
            "text": msg.text,
            "channel_idx": msg.channel_idx,
            "channel_index": msg.channel_idx,
            "rssi": msg.rssi,
            "snr": msg.snr,
            "metrics": {
                "rssi": msg.rssi,
                "snr": msg.snr,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
        clean_text_lower = (msg.text or "").strip().lower()
        is_cmd_response = (
            is_repeater_sender
            or clean_text_lower.startswith(("cmd ", "login ", "unknown command", "ok", "error", "auth "))
            or clean_text_lower in ("unknown command", "ok", "error", "success", "failed", "unauthorized")
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        if is_cmd_response:
            admin = getattr(self._ctx, "admin_handler", None)
            if admin and hasattr(admin, "notify_ping_response"):
                admin.notify_ping_response(
                    msg.sender,
                    {
                        "rssi": msg.rssi,
                        "snr_there": msg.snr,
                        "snr_back": msg.snr,
                        "text": msg.text,
                        "source": "repeater_response",
                    },
                )

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
                if frame.payload.channel_idx == 0:
                    self._ctx.mqtt.publish_safe(config.TOPIC_RX_PUBLIC, evt_json, qos=0)
                else:
                    self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_CHANNEL}/ch_{frame.payload.channel_idx}", evt_json, qos=0)

                src_hex = f"0x{frame.header.src_node_id:04X}"
                self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_DIRECT}/{src_hex}", evt_json, qos=0)
