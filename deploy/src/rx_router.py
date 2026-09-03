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
from src.contact_manager import (
    NodeContactUpdate,
    NodeRegistry,
    PacketRecord,
    _safe_int,
    is_valid_node_key,
)
from src.deduplicator import PacketDeduplicator
from src.lqi_engine import LinkQualityEngine
from src.mqtt_client import AsyncBridgeMQTTClient
from src.protocol_types import MeshcoreFrame, PacketType, TextMessagePayload
from src.repeater_manager import RepeaterManager
from src.sensor_decoder import (
    extract_telemetry_fields,
    format_telemetry_summary,
)

_SENDER_PREFIX_RE = re.compile(
    r"^(?:\[([a-zA-Z0-9_\-\.]{2,32})\]|<([a-zA-Z0-9_\-\.]{2,32})>|([a-zA-Z0-9_\-\.]{2,32})):\s*(.*)$",
    re.DOTALL,
)


def _get_coord(d: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    """Extrae coordenadas GPS válidas evitando tuplas nulas o ceros."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] is not None:
            try:
                v = float(d[k])
                if v != 0.0:
                    return v
            except (ValueError, TypeError):
                pass
    for sub in ("gps", "position", "pos", "location", "telemetry"):
        if sub in d and isinstance(d[sub], dict):
            res = _get_coord(d[sub], keys)
            if res is not None:
                return res
    return None


def extract_sender_from_text(text: str) -> tuple[str | None, str]:
    """Extrae el nombre del remitente si el texto tiene el prefijo 'Nombre: Mensaje'.

    Retorna (candidate_name, clean_text). Si no hay prefijo o si es una URL,
    retorna (None, text).
    """
    if not text or not isinstance(text, str):
        return None, text
    m = _SENDER_PREFIX_RE.match(text.strip())
    if m:
        candidate_name = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        actual_text = (m.group(4) or "").strip()
        if actual_text.startswith("//"):
            return None, text
        if candidate_name.lower() not in (
            "http", "https", "ftp", "ws", "wss", "json", "data", "cmd",
            "r", "ack", "req", "res", "echo", "status", "meshcore", "loc",
        ):
            return candidate_name, actual_text
    return None, text



from src.routers.base import MeshMessageEvent


_SYSTEM_EXACT_MATCHES: frozenset[str] = frozenset({
    "unknown command", "ok", "error", "success", "failed",
    "unauthorized", "advert", "[advert]", "beacon",
    "logging off", "log erased", "eof", "pong", "ping",
})

_SYSTEM_PREFIXES: tuple[str, ...] = (
    "unknown command", "error: unknown command", "error unknown command",
    "invalid command", "cmd ", "login ", "auth ", "stats-", "stats ",
    "set ", "get ", "log ", "reboot", "logging off", "log erased",
    "eof", "welcome admin", "access denied", "bad pin",
    "wrong password", "incorrect password", "permission denied",
    "not logged in",
)

_SYSTEM_EMOJI_PREFIXES: tuple[str, ...] = (
    "[Eco ", "[Status ", "[ACK", "\U0001f4e1 ", "\u26d4 ", "\U0001f4d6 ", "\u23f0 ", "\U0001f4c5 ", "\U0001f3d3 ",
)


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

    if clean_lower.startswith(_SYSTEM_PREFIXES) or clean_lower in _SYSTEM_EXACT_MATCHES:
        return True

    # Respuestas de bots reflejadas
    if clean.startswith(_SYSTEM_EMOJI_PREFIXES):
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
    last_rx_rssi: int | None = None
    last_rx_snr: float | None = None


class RxEventRouter:
    """Enruta eventos de la red Mesh (RF/radio) hacia MQTT, n8n y WebSocket."""

    def __init__(self, ctx: RxRouterContext) -> None:
        import os
        from src.routers import (
            BaseRxHandler,
            AdvertHandler,
            ChannelMessageHandler,
            DirectMessageHandler,
            RepeaterAdminHandler,
            TelemetryHandler,
        )

        self._ctx = ctx
        self._rx_semaphore = asyncio.Semaphore(int(os.getenv("MAX_RX_CONCURRENCY", "20")))
        self._handlers: list[BaseRxHandler] = [
            RepeaterAdminHandler(),
            AdvertHandler(),
            TelemetryHandler(),
            DirectMessageHandler(),
            ChannelMessageHandler(),
        ]

    def handle_event(self, event: Any) -> None:
        """Procesa y enruta eventos de la red Mesh hacia MQTT y n8n."""
        self._ctx.counters.rx_count += 1
        self._ctx.serial_adapter.heartbeat()

        try:
            if isinstance(event, MeshcoreFrame):
                loop = self._ctx.loop or asyncio.get_running_loop()
                task = loop.create_task(self._dispatch_parsed_frame(event))
                self._ctx.background_tasks.add(task)
                task.add_done_callback(self._ctx.background_tasks.discard)
                return

            normalized = self._extract_normalized_meta(event)
            if not normalized:
                return

            payload_dict, meta = normalized
            loop = self._ctx.loop or asyncio.get_running_loop()

            for handler in self._handlers:
                if handler.can_handle(meta, payload_dict):
                    task = loop.create_task(handler.handle(self, payload_dict, meta, event))
                    self._ctx.background_tasks.add(task)
                    task.add_done_callback(self._ctx.background_tasks.discard)
                    return

            if "event_type" not in payload_dict:
                payload_dict["event_type"] = "telemetry"
            self._handle_mesh_telemetry_msg(payload_dict)

        except Exception as e:
            self._ctx.counters.err_count += 1
            logging.error(f"Error procesando evento de radio Mesh: {e}", exc_info=True)

    def _extract_normalized_meta(self, event: Any) -> tuple[dict[str, Any], RxMeta] | None:
        from src.routers.base import RxMeta

        ev_type_str = str(getattr(event, "type", getattr(event, "event_type", "")))
        payload_obj = getattr(event, "payload", getattr(event, "data", event))
        attributes = getattr(event, "attributes", None)

        if isinstance(payload_obj, dict):
            payload_dict = dict(payload_obj)
        elif hasattr(payload_obj, "__dict__"):
            payload_dict = {k: v for k, v in payload_obj.__dict__.items() if not k.startswith("_")}
        else:
            payload_dict = {"raw": str(payload_obj)}

        if isinstance(attributes, dict):
            for ak, av in attributes.items():
                if ak not in payload_dict or payload_dict[ak] is None:
                    payload_dict[ak] = av

        if payload_dict.get("is_outgoing") is True:
            return None

        from src.event_utils import extract_sender_from_payload
        sender_raw, sender_name = extract_sender_from_payload(payload_dict)
        sender = ""

        if sender_raw:
            contact = self._ctx.node_registry.get_by_key_or_prefix(sender_raw)
            if contact and contact.public_key:
                sender = contact.public_key
                sender_name = contact.alias or contact.name
            elif is_valid_node_key(sender_raw):
                sender = self._ctx.node_registry.get_canonical_key(sender_raw)
                resolved = self._resolve_sender_name(sender)
                if resolved and resolved != sender:
                    sender_name = resolved
                elif not sender_name or sender_name.lower() in ("unknown", "anónimo", "anonimo", ""):
                    sender_name = f"Nodo [{sender_raw[:8]}]"
            elif not sender_name or sender_name.lower() in ("unknown", "anónimo", "anonimo", ""):
                sender_name = f"Nodo [{sender_raw[:8]}]"

        if sender_name:
            if not sender:
                found_c = self._ctx.node_registry.find_by_name(sender_name)
                if found_c and found_c.public_key:
                    sender = found_c.public_key

        text = str(payload_dict.get("text", payload_dict.get("message", ""))).strip()
        channel_idx = int(payload_dict.get("channel_idx", payload_dict.get("channel", 0)))
        hops = int(payload_dict.get("hop_count", payload_dict.get("hops", 0)))

        extracted_name, clean_text = extract_sender_from_text(text)
        if extracted_name:
            text = clean_text
            if not sender_name or sender_name.lower() in ("unknown", "anónimo", "anonimo", "") or sender_name == sender:
                sender_name = extracted_name
            if not sender or not is_valid_node_key(sender):
                found_c = self._ctx.node_registry.find_by_name(extracted_name)
                if found_c and is_valid_node_key(found_c.public_key):
                    sender = found_c.public_key
        elif sender_name and sender_name.lower() not in ("unknown", "anónimo", "anonimo", ""):
            s_clean = sender_name.strip()
            prefix_check = f"{s_clean}:"
            if text.lower().startswith(prefix_check.lower()):
                candidate_clean = text[len(prefix_check):].strip()
                if not candidate_clean.startswith("//"):
                    text = candidate_clean

        ev_upper_cand = ev_type_str.upper()
        if not sender:
            if any(k in ev_upper_cand for k in ("SELF", "BATTERY", "DEVICE_INFO", "LOCAL")):
                local_pk = (
                    self._ctx.node_registry.get_local_pubkey()
                    if hasattr(self._ctx.node_registry, "get_local_pubkey")
                    else getattr(self._ctx.node_registry, "_local_pubkey", "")
                )
                sender = local_pk or "LOCAL"
                sender_name = "Estación Base Local"
            elif sender_raw:
                sender = sender_raw
                sender_name = f"Nodo [{sender_raw[:8]}]"

        rssi = payload_dict.get("rssi", payload_dict.get("RSSI", payload_dict.get("last_rssi")))
        snr = payload_dict.get("snr", payload_dict.get("SNR", payload_dict.get("last_snr")))

        is_local_sender = bool(sender and is_valid_node_key(sender) and self._ctx.node_registry.is_local_key(sender))
        effective_rssi = None if is_local_sender else (int(rssi) if isinstance(rssi, (int, float)) else None)
        effective_snr = None if is_local_sender else (float(snr) if isinstance(snr, (int, float)) else None)
        effective_hops = 0 if is_local_sender else hops

        if effective_snr is not None:
            self._ctx.last_rx_snr = effective_snr
        if effective_rssi is not None:
            self._ctx.last_rx_rssi = effective_rssi
        if self._ctx.admin_handler and hasattr(self._ctx.admin_handler, "_ctx"):
            if effective_rssi is not None:
                self._ctx.admin_handler._ctx.last_rx_rssi = effective_rssi
            if effective_snr is not None:
                self._ctx.admin_handler._ctx.last_rx_snr = effective_snr

        if sender:
            payload_dict["sender"] = sender
        if sender_name:
            payload_dict["sender_name"] = sender_name
        if effective_rssi is not None:
            payload_dict["rssi"] = effective_rssi
        if effective_snr is not None:
            payload_dict["snr"] = effective_snr

        if sender and is_valid_node_key(sender):
            self._update_node_registry_presence(
                sender=sender,
                sender_name=sender_name,
                payload_dict=payload_dict,
                effective_rssi=effective_rssi,
                effective_snr=effective_snr,
                effective_hops=effective_hops,
                is_local_sender=is_local_sender,
            )

        meta = RxMeta(
            ev_type_str=ev_type_str,
            ev_upper=ev_type_str.upper(),
            sender=sender,
            sender_name=sender_name,
            text=text,
            channel_idx=channel_idx,
            hops=hops,
            effective_rssi=effective_rssi,
            effective_snr=effective_snr,
            effective_hops=effective_hops,
            is_local_sender=is_local_sender,
        )
        return payload_dict, meta

    def _update_node_registry_presence(
        self,
        sender: str,
        sender_name: str,
        payload_dict: dict[str, Any],
        effective_rssi: int | None,
        effective_snr: float | None,
        effective_hops: int,
        is_local_sender: bool,
    ) -> None:
        raw_bat = payload_dict.get("battery_pct", payload_dict.get("battery", payload_dict.get("batt", payload_dict.get("bat"))))
        bat_pct: int | None = None
        if raw_bat is not None and isinstance(raw_bat, (int, float)):
            if 0 <= raw_bat <= 100:
                bat_pct = int(raw_bat)
            elif raw_bat > 100:
                bat_pct = max(0, min(100, int((raw_bat - 3300) / (4200 - 3300) * 100)))

        volt_val = payload_dict.get("voltage_v", payload_dict.get("voltage", payload_dict.get("vbat")))
        if bat_pct is None and volt_val is not None and isinstance(volt_val, (int, float)):
            v_flt = float(volt_val)
            if v_flt > 100:
                v_flt = v_flt / 1000.0
            if v_flt >= 4.8:
                bat_pct = 100
            elif v_flt >= 3.0:
                bat_pct = max(0, min(100, int((v_flt - 3.3) / (4.2 - 3.3) * 100)))

        sender_name_cand = (sender_name or "").upper()
        is_named_rep = (
            sender_name_cand.startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-", "REP_", "ROUTER_"))
            or "REPEATER" in sender_name_cand or "ROUTER" in sender_name_cand or "REPETIDOR" in sender_name_cand
        )

        role_val = payload_dict.get("role")
        if not role_val:
            raw_type = payload_dict.get("adv_type", payload_dict.get("type"))
            if raw_type == 2 or raw_type == "REPEATER" or is_named_rep:
                role_val = "REPEATER"
            elif raw_type == 3 or raw_type == "ROOM":
                role_val = "ROOM"
            elif raw_type == 4 or raw_type == "SENSOR":
                role_val = "SENSOR"
            elif raw_type == 1 or raw_type == "CHAT" or raw_type == "CLIENT":
                role_val = "CLIENT"

        lat_val = _get_coord(payload_dict, ("lat", "latitude", "gps_lat"))
        lon_val = _get_coord(payload_dict, ("lon", "longitude", "gps_lon"))

        effective_role = "LOCAL" if is_local_sender else (role_val or ("REPEATER" if is_named_rep else "CLIENT"))

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
                self._ctx.node_registry.add_or_update(
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
                    asyncio.create_task(self._ctx.web_server.broadcast_event({
                        "type": "contact_discovered" if is_new else "contact_updated",
                        "event_type": "contact_discovered" if is_new else "contact_updated",
                        "is_new": is_new,
                        "contact": contact_info.to_dict(),
                    }))

    def _resolve_sender_name(self, prefix_or_key: str) -> str:
        # Primero consultar el registro dinámico local
        local_name = self._ctx.node_registry.resolve_name(prefix_or_key)
        if local_name and local_name != prefix_or_key:
            return local_name
        return str(self._ctx.serial_adapter.resolve_sender_name(prefix_or_key))

    async def _handle_mesh_msg_common(self, msg: MeshMessageEvent, event_type_str: str) -> dict[str, Any] | None:
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
                    hop_limit=extracted_telem.get("hop_limit"),
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
                asyncio.create_task(self._ctx.web_server.broadcast_event(rep_payload))
            return None

        lqi_val = LinkQualityEngine.compute_instant_lqi(msg.snr, msg.rssi, 0)
        lqi_stat = LinkQualityEngine.classify_lqi_status(lqi_val)

        evt_payload = {
            "event_type": event_type_str,
            "sender": msg.sender,
            "sender_name": msg.sender_name,
            "text": msg.text,
            "channel_idx": msg.channel_idx,
            "channel_index": msg.channel_idx,
            "txt_type": msg.txt_type,
            "rssi": msg.rssi,
            "snr": msg.snr,
            "lqi_score": lqi_val,
            "lqi_status": lqi_stat,
            "metrics": {
                "rssi": msg.rssi,
                "snr": msg.snr,
                "lqi_score": lqi_val,
                "lqi_status": lqi_stat,
            },
            "telemetry": extracted_telem if extracted_telem else None,
            "timestamp": now_iso,
        }

        evt_json = json.dumps(evt_payload, sort_keys=True)
        self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)
        if self._ctx.web_server:
            asyncio.create_task(self._ctx.web_server.broadcast_event(evt_payload))

        return evt_payload

    async def _handle_mesh_channel_msg(self, msg: MeshMessageEvent) -> None:
        evt_payload = await self._handle_mesh_msg_common(msg, "public" if msg.channel_idx == 0 else "channel")
        if not evt_payload:
            return

        evt_json = json.dumps(evt_payload, sort_keys=True)
        if msg.channel_idx == 0:
            self._ctx.mqtt.publish_safe(config.TOPIC_RX_PUBLIC, evt_json, qos=0)
        else:
            self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_CHANNEL}/ch_{msg.channel_idx}", evt_json, qos=0)

        logging.info(
            f"[RX-CANAL] De: {msg.sender_name or msg.sender} -> Para: Canal #{msg.channel_idx} | "
            f"Texto: '{msg.text}' | LQI: {evt_payload['lqi_score']}% [{evt_payload['lqi_status']}] | RSSI: {msg.rssi} dBm, SNR: {msg.snr} dB"
        )

    async def _handle_mesh_direct_msg(self, msg: MeshMessageEvent) -> None:
        evt_payload = await self._handle_mesh_msg_common(msg, "direct")
        if not evt_payload:
            return

        evt_json = json.dumps(evt_payload, sort_keys=True)
        topic = f"{config.TOPIC_RX_DIRECT}/{msg.sender}"
        self._ctx.mqtt.publish_safe(topic, evt_json, qos=1)

        logging.info(
            f"[RX-DM] De: {msg.sender_name or msg.sender} -> Para: Estación Base Local | "
            f"Texto: '{msg.text}' | LQI: {evt_payload['lqi_score']}% [{evt_payload['lqi_status']}] | RSSI: {msg.rssi} dBm, SNR: {msg.snr} dB"
        )

    def _handle_mesh_telemetry_msg(self, payload_dict: dict[str, Any]) -> None:
        # Extraer y normalizar exhaustivamente todas las lecturas de telemetría/sensores
        extracted_fields = extract_telemetry_fields(payload_dict)
        payload_dict.update(extracted_fields)

        # Si el payload contiene texto de telemetría de repetidor
        raw_text_cand = payload_dict.get("text", payload_dict.get("raw_text", payload_dict.get("message", "")))
        if isinstance(raw_text_cand, str) and raw_text_cand.strip():
            extracted_rep = self._ctx.repeater_manager.parse_repeater_telemetry_or_response(raw_text_cand)
            if extracted_rep:
                payload_dict.update(extracted_rep)

        # Resolver emisor si aún no está resuelto
        sender = str(payload_dict.get("sender", payload_dict.get("public_key", "")))
        if not sender and payload_dict.get("pubkey_prefix"):
            contact = self._ctx.node_registry.get_by_key_or_prefix(str(payload_dict["pubkey_prefix"]))
            if contact and contact.public_key:
                sender = contact.public_key
                payload_dict["sender"] = sender
                payload_dict["sender_name"] = contact.alias or contact.name

        if sender and is_valid_node_key(sender):
            sender_name_cand = str(
                payload_dict.get("sender_name")
                or payload_dict.get("adv_name")
                or payload_dict.get("name")
                or payload_dict.get("alias")
                or self._resolve_sender_name(sender)
            )
            name_cand_upper = sender_name_cand.upper()
            existing_contact = self._ctx.node_registry.get_contact(sender)
            is_known_rep = bool(
                (existing_contact and existing_contact.role in ("REPEATER", "ROUTER"))
                or name_cand_upper.startswith(("R-", "R1-", "R2-", "R3-", "REP-", "ROUTER-", "REP_", "ROUTER_"))
                or "REPEATER" in name_cand_upper or "ROUTER" in name_cand_upper or "REPETIDOR" in name_cand_upper
            )

            raw_telem_bat = payload_dict.get("battery_pct", payload_dict.get("battery", payload_dict.get("batt", payload_dict.get("bat"))))
            calc_bat_pct: int | None = None
            if raw_telem_bat is not None and isinstance(raw_telem_bat, (int, float)):
                if 0 <= raw_telem_bat <= 100:
                    calc_bat_pct = int(raw_telem_bat)
                elif raw_telem_bat > 100:
                    calc_bat_pct = max(0, min(100, int((raw_telem_bat - 3300) / (4200 - 3300) * 100)))

            telem_volt = payload_dict.get("voltage_v", payload_dict.get("voltage", payload_dict.get("vbat")))
            if calc_bat_pct is None and telem_volt is not None and isinstance(telem_volt, (int, float)):
                v_flt = float(telem_volt)
                if v_flt > 100:
                    v_flt = v_flt / 1000.0
                if v_flt >= 4.8:
                    calc_bat_pct = 100
                elif v_flt >= 3.0:
                    calc_bat_pct = max(0, min(100, int((v_flt - 3.3) / (4.2 - 3.3) * 100)))

            telem_role = payload_dict.get("role")
            if not telem_role:
                if is_known_rep:
                    telem_role = "REPEATER"
                elif any(k in payload_dict for k in ("temperature_c", "temp", "humidity_pct", "humidity", "pressure_hpa")):
                    telem_role = "SENSOR"
                elif existing_contact and existing_contact.role:
                    telem_role = existing_contact.role
                else:
                    telem_role = "CLIENT"

            self._ctx.node_registry.add_or_update(
                sender,
                NodeContactUpdate(
                    name=sender_name_cand,
                    role=telem_role,
                    battery_pct=calc_bat_pct,
                    voltage_v=payload_dict.get("voltage_v", telem_volt),
                    solar_v=payload_dict.get("solar_v"),
                    latitude=payload_dict.get("latitude"),
                    longitude=payload_dict.get("longitude"),
                    altitude_m=payload_dict.get("altitude_m"),
                    fixed_position=payload_dict.get("fixed_position"),
                    uptime=payload_dict.get("uptime"),
                    clock=payload_dict.get("clock"),
                    airtime_ms=payload_dict.get("airtime_ms"),
                    noise_floor_dbm=payload_dict.get("noise_floor_dbm"),
                    packets_sent=payload_dict.get("packets_sent"),
                    packets_recv=payload_dict.get("packets_recv"),
                    duplicate_packets=payload_dict.get("duplicate_packets"),
                    packet_errors=payload_dict.get("packet_errors"),
                    queue_len=payload_dict.get("queue_len"),
                    owner_name=payload_dict.get("owner_name"),
                    owner_info=payload_dict.get("owner_info"),
                    firmware_version=payload_dict.get("firmware_version"),
                    hardware_board=payload_dict.get("hardware_board"),
                    frequency=payload_dict.get("frequency"),
                    tx_power=payload_dict.get("tx_power"),
                    spreading_factor=payload_dict.get("spreading_factor"),
                    bandwidth=payload_dict.get("bandwidth"),
                    coding_rate=payload_dict.get("coding_rate"),
                    repeat_enabled=payload_dict.get("repeat_enabled"),
                    advert_interval=payload_dict.get("advert_interval"),
                    hop_limit=payload_dict.get("hop_limit"),
                    hops=payload_dict.get("hops"),
                ),
            )

        # Sanitizar cualquier otro campo bytes restante
        for k, v in list(payload_dict.items()):
            if isinstance(v, (bytes, bytearray)):
                payload_dict[k] = bytes(v).hex()

        payload_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
        evt_json = json.dumps(payload_dict, sort_keys=True)
        self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)
        if any(k in payload_dict for k in ("battery", "battery_pct", "battery_mv", "voltage", "voltage_v", "temperature", "temperature_c", "humidity_pct", "pressure_hpa", "solar_v")):
            self._ctx.mqtt.publish_safe(config.TOPIC_RX_TELEMETRY, evt_json, qos=0)
        if self._ctx.web_server:
            asyncio.create_task(self._ctx.web_server.broadcast_event(payload_dict))

        ev_name = str(payload_dict.get("event_type", payload_dict.get("type", "telemetry")))

        # Si el evento corresponde a configuración o hardware del nodo local, registrar con formato limpio [ESTACIÓN LOCAL]
        if ev_name in ("self_info", "SELF_INFO", "self"):
            node_name = payload_dict.get("name") or "Estación Base"
            pk_short = str(payload_dict.get("public_key", sender))[:8]
            freq = payload_dict.get("radio_freq", "--")
            sf = payload_dict.get("radio_sf", "--")
            bw = payload_dict.get("radio_bw", "--")
            cr = payload_dict.get("radio_cr", "--")
            tx_p = payload_dict.get("tx_power", "--")
            logging.info(
                f"[ESTACIÓN LOCAL] Configuración: {node_name} ({pk_short}) | Freq: {freq} MHz, SF{sf}/BW{bw}/CR{cr}, TX: {tx_p} dBm"
            )
            return

        if ev_name in ("device_info", "DEVICE_INFO", "device"):
            model = payload_dict.get("model") or "LoRa Device"
            ver = payload_dict.get("ver") or payload_dict.get("firmware_version") or ""
            build = payload_dict.get("fw_build") or ""
            max_c = payload_dict.get("max_contacts", "--")
            if "repeat" in payload_dict and self._ctx.admin_handler:
                self._ctx.admin_handler._local_config["repeat"] = bool(payload_dict["repeat"])
            rep_status = "ON" if payload_dict.get("repeat") else "OFF"
            logging.info(
                f"[ESTACIÓN LOCAL] Hardware: {model} {ver} (Build: {build}, Contactos Máx: {max_c}, Repetidor: {rep_status})"
            )
            return

        sender_name_val = payload_dict.get("sender_name")
        if sender and sender_name_val and sender_name_val != sender and len(sender) >= 8:
            sender_label = f"{sender_name_val} ({sender[:8]})"
        elif sender_name_val:
            sender_label = str(sender_name_val)
        elif sender and len(sender) >= 8:
            sender_label = f"Nodo [{sender[:8]}]"
        elif payload_dict.get("pubkey_prefix"):
            sender_label = f"Nodo [{str(payload_dict['pubkey_prefix'])[:8]}]"
        else:
            sender_label = "Estación Base Local" if ev_name in ("self_info", "battery", "device_info") else "Desconocido"

        rssi_val = payload_dict.get("rssi", payload_dict.get("RSSI", payload_dict.get("last_rssi")))
        snr_val = payload_dict.get("snr", payload_dict.get("SNR", payload_dict.get("last_snr")))
        rssi_str = f"{rssi_val} dBm" if rssi_val is not None else "N/A"
        snr_str = f"{snr_val} dB" if snr_val is not None else "N/A"

        lqi_part = ""
        if rssi_val is not None and snr_val is not None:
            instant_lqi = LinkQualityEngine.compute_instant_lqi(float(snr_val), float(rssi_val), hops=int(payload_dict.get("hops", 0)))
            lqi_stat = LinkQualityEngine.classify_lqi_status(instant_lqi)
            lqi_part = f" | LQI: {instant_lqi:.1f}% [{lqi_stat}]"
            payload_dict["lqi_score"] = instant_lqi
            payload_dict["lqi_status"] = lqi_stat

        telem_summary = format_telemetry_summary(payload_dict)
        logging.info(
            f"[RX-TELEMETRÍA] De: {sender_label} -> Para: Gateway/MQTT | "
            f"Tipo: {ev_name} | {telem_summary} | RSSI: {rssi_str}, SNR: {snr_str}{lqi_part}"
        )

    async def _dispatch_parsed_frame(self, frame: MeshcoreFrame) -> None:
        """Enruta instancias de MeshcoreFrame validadas a MQTT."""
        async with self._rx_semaphore:
            mqtt_evt = frame.to_mqtt_event()
            evt_json = json.dumps(mqtt_evt)

            dedup_key = f"frame::{frame.header.src_node_id}::{frame.header.seq_num}::{int(frame.header.opcode)}"
            if await self._ctx.deduplicator.is_duplicate(dedup_key):
                return

            self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)

            if frame.header.packet_type == PacketType.TELEMETRY_RESPONSE:
                self._ctx.mqtt.publish_safe(config.TOPIC_RX_TELEMETRY, evt_json, qos=0)
            elif frame.header.packet_type == PacketType.CONTACT:
                self._ctx.mqtt.publish_safe(config.TOPIC_RX_NODES, evt_json, qos=0)
            elif frame.header.packet_type in (PacketType.CHANNEL_MSG_RECV, PacketType.CONTACT_MSG_RECV):
                if isinstance(frame.payload, TextMessagePayload):
                    if not is_common_chat_message(frame.payload.text):
                        return
                    if frame.payload.channel_idx == 0:
                        self._ctx.mqtt.publish_safe(config.TOPIC_RX_PUBLIC, evt_json, qos=0)
                    else:
                        self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_CHANNEL}/ch_{frame.payload.channel_idx}", evt_json, qos=0)

                    src_hex = f"0x{frame.header.src_node_id:04X}"
                    self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_DIRECT}/{src_hex}", evt_json, qos=0)

            logging.info(
                f"[RX-FRAME] De: 0x{frame.header.src_node_id:04X} -> Para: 0x{frame.header.dst_node_id:04X} | "
                f"OpCode: {frame.header.opcode.name} | Seq: {frame.header.seq_num} | Válido: {frame.is_valid}"
            )
