"""
RxEventRouter: Despachador de eventos LoRa/Radio hacia MQTT, n8n y WebSocket.
Extraído de MeshCoreBridge (God Class) para separar la responsabilidad de enrutamiento RX
de la gestión del ciclo de vida del bridge.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import config
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.mqtt_client import AsyncBridgeMQTTClient
from src.protocol_types import MeshcoreFrame, OpCode, TextMessagePayload
from src.repeater_manager import RepeaterManager
from src.sensor_decoder import CayenneLPPDecoder
from src.serial_driver import BaseSerialAdapter
from src.store_forward import PacketDeduplicator


class BridgeCounters(Protocol):
    """Vista de los contadores del bridge compartidos con los componentes extraídos."""
    rx_count: int
    tx_count: int
    tx_error_count: int
    serial_reconnect_count: int


@dataclass(slots=True)
class MeshMessageEvent:
    """Mensaje de texto entrante con métricas RF (agrupa 6 argumentos)."""
    sender: str
    sender_name: str
    text: str
    channel_idx: int
    rssi: Any
    snr: Any


@dataclass(slots=True)
class RxRouterContext:
    """Contexto de dependencias del enrutador RX: evita constructores con demasiados argumentos."""
    mqtt: AsyncBridgeMQTTClient
    node_registry: NodeRegistry
    serial_adapter: BaseSerialAdapter
    deduplicator: PacketDeduplicator
    repeater_manager: RepeaterManager
    web_server: Any
    loop: asyncio.AbstractEventLoop | None
    background_tasks: set[asyncio.Task[Any]]
    counters: BridgeCounters


class RxEventRouter:
    """Enruta eventos de la red Mesh (RF/radio) hacia MQTT, n8n y WebSocket."""

    def __init__(self, ctx: RxRouterContext) -> None:
        self._ctx = ctx

    def handle_event(self, event: Any) -> None:
        """Procesa y enruta eventos de la red Mesh hacia MQTT y n8n."""
        self._ctx.counters.rx_count += 1
        self._ctx.serial_adapter.heartbeat()

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

        # Caso Sniffer RF (0x88 / LOG_DATA)
        if "LOG_DATA" in ev_type_str or "rf_log" in ev_type_str:
            parsed_log = self._ctx.repeater_manager.parse_log_packet(payload_dict.get("raw", payload_obj))
            self._ctx.mqtt.publish_safe(config.TOPIC_RX_LOG, json.dumps(parsed_log), qos=0)
            if self._ctx.web_server:
                self._ctx.web_server.broadcast_event(parsed_log)
            return

        rssi = payload_dict.get("rssi", -80)
        snr = payload_dict.get("snr", 10.0)
        sender = str(payload_dict.get("sender", payload_dict.get("pubkey_prefix", "unknown")))
        sender_name = str(payload_dict.get("sender_name", self._resolve_sender_name(sender)))
        text = str(payload_dict.get("text", payload_dict.get("message", "")))
        channel_idx = int(payload_dict.get("channel_idx", payload_dict.get("channel", 0)))
        hops = int(payload_dict.get("hop_count", payload_dict.get("hops", 0)))

        # Actualizar directorio dinámico de nodos
        if sender and sender != "unknown":
            bat_pct = int(payload_dict["battery"]) if "battery" in payload_dict and isinstance(payload_dict["battery"], (int, float)) else None
            self._ctx.node_registry.add_or_update(
                sender,
                NodeContactUpdate(
                    name=sender_name,
                    hops=hops,
                    last_rssi=int(rssi) if isinstance(rssi, (int, float)) else -80,
                    last_snr=float(snr) if isinstance(snr, (int, float)) else 10.0,
                    battery_pct=bat_pct,
                ),
            )

        if "CHANNEL_MSG" in ev_type_str or (text and channel_idx >= 0 and "DIRECT" not in ev_type_str):
            self._handle_mesh_channel_msg(MeshMessageEvent(sender, sender_name, text, channel_idx, rssi, snr))
        elif "DIRECT_MSG" in ev_type_str:
            self._handle_mesh_direct_msg(MeshMessageEvent(sender, sender_name, text, channel_idx, rssi, snr))
        else:
            self._handle_mesh_telemetry_msg(payload_dict)

    def _resolve_sender_name(self, prefix_or_key: str) -> str:
        # Primero consultar el registro dinámico local
        local_name = self._ctx.node_registry.resolve_name(prefix_or_key)
        if local_name and local_name != prefix_or_key:
            return local_name
        return self._ctx.serial_adapter.resolve_sender_name(prefix_or_key)

    def _handle_mesh_channel_msg(self, msg: MeshMessageEvent) -> None:
        event_type = "public" if msg.channel_idx == 0 else "channel"
        evt_payload = {
            "event_type": event_type,
            "sender": msg.sender,
            "sender_name": msg.sender_name,
            "text": msg.text,
            "channel_idx": msg.channel_idx,
            "channel_index": msg.channel_idx,
            "metrics": {"rssi": msg.rssi, "snr": msg.snr},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        evt_json = json.dumps(evt_payload)
        self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)
        if msg.channel_idx == 0:
            self._ctx.mqtt.publish_safe(config.TOPIC_RX_PUBLIC, evt_json, qos=0)
        else:
            self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_CHANNEL}/ch_{msg.channel_idx}", evt_json, qos=0)
        if self._ctx.web_server:
            self._ctx.web_server.broadcast_event(evt_payload)

    def _handle_mesh_direct_msg(self, msg: MeshMessageEvent) -> None:
        evt_payload = {
            "event_type": "direct",
            "sender": msg.sender,
            "sender_name": msg.sender_name,
            "text": msg.text,
            "metrics": {"rssi": msg.rssi, "snr": msg.snr},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        evt_json = json.dumps(evt_payload)
        self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)
        self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_DIRECT}/{msg.sender}", evt_json, qos=0)
        if self._ctx.web_server:
            self._ctx.web_server.broadcast_event(evt_payload)

    def _handle_mesh_telemetry_msg(self, payload_dict: dict[str, Any]) -> None:
        if "raw_bytes" in payload_dict and isinstance(payload_dict["raw_bytes"], (bytes, bytearray)):
            raw_b = bytes(payload_dict["raw_bytes"])
            _readings, summary = CayenneLPPDecoder.decode(raw_b)
            payload_dict["raw_hex"] = raw_b.hex()
            payload_dict.pop("raw_bytes", None)
            payload_dict.update(summary)

        # Sanitizar cualquier otro campo bytes restante
        for k, v in list(payload_dict.items()):
            if isinstance(v, (bytes, bytearray)):
                payload_dict[k] = bytes(v).hex()

        payload_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
        evt_json = json.dumps(payload_dict, sort_keys=True)
        self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)
        if "battery" in payload_dict or "voltage" in payload_dict or "temperature" in payload_dict or "temperature_c" in payload_dict:
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
