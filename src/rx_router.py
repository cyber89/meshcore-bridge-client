"""
RxEventRouter: Enrutamiento de eventos entrantes de la radio hacia MQTT, n8n y WebSocket.
Extraído de MeshCoreBridge para separar responsabilidades y facilitar pruebas unitarias.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, cast

import config
from src.contact_manager import (
    NodeContactUpdate,
    NodeDiscoveryEvent,
    NodeRegistry,
    PacketRecord,
    is_valid_node_key,
)
from src.deduplicator import PacketDeduplicator
from src.event_utils import extract_sender_from_payload
from src.lqi_engine import LinkQualityEngine
from src.mqtt_client import AsyncBridgeMQTTClient
from src.protocol_types import MeshcoreFrame, PacketType, TextMessagePayload
from src.repeater_manager import RepeaterManager
from src.routers.base import MeshMessageEvent, RxMeta
from src.sensor_decoder import (
    extract_telemetry_fields,
    format_telemetry_summary,
)
from src.shared_utils import (
    classify_device_role,
    clean_coordinate_value,
    clean_numeric_value,
    is_empty_channel_slot,
    sanitize_public_payload,
)

_SENDER_PREFIX_RE = re.compile(
    r"^(?:\[([a-zA-Z0-9_\-\.]{2,32})\]|<([a-zA-Z0-9_\-\.]{2,32})>|([a-zA-Z0-9_\-\.]{2,32})):\s*(.*)$",
    re.DOTALL,
)


def _get_coord(d: dict[str, Any], keys: tuple[str, ...], *, latitude: bool = False) -> float | None:
    """Extract a finite, bounded geographic coordinate; zero can be valid."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] is not None:
            value = clean_coordinate_value(d[k], latitude=latitude)
            if value is not None:
                return value
    for sub in ("gps", "position", "pos", "location", "telemetry"):
        if sub in d and isinstance(d[sub], dict):
            res = _get_coord(d[sub], keys, latitude=latitude)
            if res is not None:
                return res
    return None


def _location_pair(data: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = _get_coord(data, ("lat", "latitude", "gps_lat", "adv_lat"), latitude=True)
    lon = _get_coord(data, ("lon", "longitude", "gps_lon", "adv_lon"))
    # Firmware advert (0,0) denotes no GPS; a single zero is incomplete too.
    if lat == 0 and lon in (0, None):
        lat = None
    if lon == 0 and lat is None:
        lon = None
    return lat, lon


def extract_sender_from_text(text: str) -> tuple[str | None, str]:
    """Extrae el nombre del remitente si el texto tiene el prefijo 'Nombre: Mensaje'.

    Retorna (candidate_name, clean_text). Si no hay prefijo o si es una URL,
    retorna (None, text).
    """
    if not text or not isinstance(text, str):
        return None, text
    stripped = text.strip()
    if re.match(r"^\d{1,2}:\d{2}(?::\d{2})?", stripped):
        return None, text
    m = _SENDER_PREFIX_RE.match(stripped)
    if m:
        candidate_name = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        actual_text = (m.group(4) or "").strip()
        if actual_text.startswith("//"):
            return None, text
        if candidate_name.isdigit():
            return None, text
        if candidate_name.lower() not in (
            "http", "https", "ftp", "ws", "wss", "json", "data", "cmd",
            "r", "ack", "req", "res", "echo", "status", "meshcore", "loc",
        ):
            return candidate_name, actual_text
    return None, text



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
        clean_lower = re.sub(r"^(?:->|- >|>)\s*", "", clean_lower)

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
    register_task: Callable[[asyncio.Task[Any]], asyncio.Task[Any]] | None = None
    last_rx_snr: float | None = None
    packet_buffer: Any = None
    bridge: Any = None


class RxEventRouter:
    """Enruta eventos de la red Mesh (RF/radio) hacia MQTT, n8n y WebSocket."""

    def __init__(self, ctx: RxRouterContext) -> None:
        import os

        from src.routers import (
            AdvertHandler,
            BaseRxHandler,
            ChannelMessageHandler,
            DirectMessageHandler,
            RepeaterAdminHandler,
            SystemHandler,
            TelemetryHandler,
        )

        self._ctx = ctx
        self._rx_semaphore = asyncio.Semaphore(int(os.getenv("MAX_RX_CONCURRENCY", "20")))
        self._handlers: list[BaseRxHandler] = [
            RepeaterAdminHandler(),
            DirectMessageHandler(),
            ChannelMessageHandler(),
            AdvertHandler(),
            TelemetryHandler(),
            SystemHandler(),
        ]

    def handle_event(self, event: Any) -> None:
        """Procesa y enruta eventos de la red Mesh hacia MQTT y n8n."""
        self._ctx.serial_adapter.heartbeat()

        try:
            if isinstance(event, MeshcoreFrame):
                if not event.is_valid or event.header.packet_type == PacketType.PRIVATE_KEY:
                    return
                self._ctx.counters.rx_count += 1
                if getattr(self._ctx, "packet_buffer", None) is not None:
                    try:
                        raw_b = getattr(event, "raw_payload", b"")
                        pkt = self._ctx.packet_buffer.record(
                            direction="rx",
                            channel_idx=getattr(event, "channel_idx", 0),
                            packet_type=str(getattr(event, "frame_type", "FRAME")),
                            sender=str(getattr(event, "sender_pubkey", "")),
                            target=str(getattr(event, "recipient_pubkey", "broadcast")),
                            text="",
                            rssi=getattr(event, "rssi", None),
                            snr=getattr(event, "snr", None),
                            raw_bytes=raw_b,
                        )
                        if pkt and self._ctx.web_server:
                            self._spawn_broadcast_task({"type": "rf_packet", "event": "rf_packet", "data": pkt.to_dict()})
                    except Exception as ex:
                        logging.debug(f"Error registrando MeshcoreFrame en packet_buffer: {ex}")

                loop = self._ctx.loop or asyncio.get_running_loop()
                task = loop.create_task(self._dispatch_parsed_frame(event))
                self._register_task(task)
                return

            normalized = self._extract_normalized_meta(event)
            if not normalized:
                return

            payload_dict, meta = normalized

            # Filtrar eventos internos, diagnóstico y logs para que no se contabilicen como paquetes RF de entrada
            is_internal_or_diag = (
                meta.is_local_sender
                or any(k in meta.ev_upper for k in (
                    "SELF", "BATTERY", "DEVICE_INFO", "STATUS", "STATS", "TUNING",
                    "CUSTOM_VARS", "MSG_SENT", "ACK", "LOGIN", "CONTROL", "LOG", "DEBUG",
                    "NO_MORE", "CHANNEL_INFO"
                ))
                or payload_dict.get("event_type") in (
                    "system_log", "log_data", "rx_log_data", "metrics_update", "status", "ping", "pong", "no_more_messages", "channel_info"
                )
                or "messages_available" in payload_dict
            )

            # Registro en el búfer circular de tramas LoRa para el Sniffer y contador RX (exclusivo para RF legítimo)
            if not is_internal_or_diag:
                self._ctx.counters.rx_count += 1
                if getattr(self._ctx, "packet_buffer", None) is not None:
                    try:
                        raw_b = getattr(event, "raw_data", None) or getattr(event, "raw", None)
                        if not raw_b and isinstance(payload_dict.get("raw"), (bytes, bytearray)):
                            raw_b = bytes(payload_dict["raw"])
                        pkt = self._ctx.packet_buffer.record(
                            direction="rx",
                            channel_idx=meta.channel_idx,
                            packet_type=meta.ev_upper or "PACKET",
                            sender=meta.sender or "",
                            sender_name=meta.sender_name or "",
                            target=str(payload_dict.get("to") or payload_dict.get("target") or "broadcast"),
                            text=meta.text or str(payload_dict.get("text") or ""),
                            rssi=meta.effective_rssi,
                            snr=meta.effective_snr,
                            raw_bytes=raw_b if isinstance(raw_b, (bytes, bytearray)) else None,
                            payload_dict=payload_dict,
                        )
                        if pkt and self._ctx.web_server:
                            self._spawn_broadcast_task({"type": "rf_packet", "event": "rf_packet", "data": pkt.to_dict()})
                    except Exception as ex:
                        logging.debug(f"Error registrando paquete RX en packet_buffer: {ex}")

            loop = self._ctx.loop or asyncio.get_running_loop()

            for handler in self._handlers:
                if handler.can_handle(meta, payload_dict):
                    task = loop.create_task(cast(Coroutine[Any, Any, None], handler.handle(self, payload_dict, meta, event)))
                    self._register_task(task)
                    return

            # Descartar eventos internos de control de flujo de la radio (NO_MORE_MSGS)
            if "NO_MORE" in meta.ev_upper or payload_dict.get("event_type") == "no_more_messages" or "messages_available" in payload_dict:
                logging.debug("[INTERNAL-RADIO] Fin de cola de mensajes en transceptor (NO_MORE_MSGS)")
                return

            # Manejar eventos de configuración de canales de la estación local
            if "CHANNEL_INFO" in meta.ev_upper or payload_dict.get("event_type") == "channel_info":
                ch_name = str(payload_dict.get("channel_name", "")).strip()
                ch_sec = payload_dict.get("channel_secret")
                if is_empty_channel_slot(ch_name, ch_sec):
                    logging.debug(f"[ESTACIÓN LOCAL] Canal #{payload_dict.get('channel_idx')} no configurado / vacío")
                    return
                ch_idx = int(payload_dict.get("channel_idx", 0))
                ch_hash = str(payload_dict.get("channel_hash", "--"))
                logging.info(f"[ESTACIÓN LOCAL] Canal #{ch_idx}: {ch_name} (Hash: {ch_hash})")
                if self._ctx.web_server and hasattr(self._ctx.web_server, "router") and hasattr(self._ctx.web_server.router, "channels"):
                    self._ctx.web_server.router.channels[ch_idx] = {
                        "index": ch_idx,
                        "name": ch_name,
                        "channel_hash": ch_hash,
                    }
                return

            if "event_type" not in payload_dict:
                payload_dict["event_type"] = (
                    "self_info" if "SELF" in meta.ev_upper
                    else ("device_info" if "DEVICE" in meta.ev_upper
                    else ("battery" if "BATTERY" in meta.ev_upper
                    else ("stats_core" if "STATS_CORE" in meta.ev_upper
                    else ("stats_radio" if "STATS_RADIO" in meta.ev_upper
                    else ("tuning" if "TUNING" in meta.ev_upper
                    else ("time" if "TIME" in meta.ev_upper
                    else ("channel_info" if "CHANNEL_INFO" in meta.ev_upper
                    else "telemetry")))))))
                )
            self._handle_mesh_telemetry_msg(payload_dict)

        except Exception as e:
            self._ctx.counters.err_count += 1
            logging.error(f"Error procesando evento de radio Mesh: {e}", exc_info=True)

    def _register_task(self, task: asyncio.Task[Any]) -> None:
        if self._ctx.register_task is not None:
            self._ctx.register_task(task)
        else:
            self._ctx.background_tasks.add(task)
            task.add_done_callback(self._ctx.background_tasks.discard)

    def _spawn_broadcast_task(self, payload: dict[str, Any]) -> None:
        """Emite eventos WebSocket registrando la tarea en background_tasks."""
        if not self._ctx.web_server:
            return
        try:
            loop = self._ctx.loop or asyncio.get_running_loop()
        except RuntimeError:
            return
        coro = self._ctx.web_server.broadcast_event(payload)
        if asyncio.iscoroutine(coro):
            task: asyncio.Task[Any] = loop.create_task(coro)
            self._register_task(task)

    def _extract_normalized_meta(self, event: Any) -> tuple[dict[str, Any], RxMeta] | None:
        raw_type = getattr(event, "type", getattr(event, "event_type", ""))
        if hasattr(raw_type, "name"):
            ev_type_str = str(raw_type.name)
        elif hasattr(raw_type, "value") and isinstance(raw_type.value, str):
            ev_type_str = str(raw_type.value)
        else:
            ev_type_str = str(raw_type)
        if ev_type_str.startswith("EventType."):
            ev_type_str = ev_type_str[len("EventType."):]
        if ev_type_str.upper() == "PRIVATE_KEY":
            # The original SDK event stays available to its command waiter.
            return None

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

        payload_dict = sanitize_public_payload(payload_dict)

        if payload_dict.get("is_outgoing") is True:
            return None

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
            if any(k in ev_upper_cand for k in (
                "SELF", "BATTERY", "DEVICE_INFO", "LOCAL", "STATS", "TUNING", "CUSTOM_VARS", "TIME", "STATUS"
            )):
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

        is_local_sender = bool(
            sender
            and (
                str(sender).lower() in ("local", "000000000000")
                or self._ctx.node_registry.is_local_key(sender)
                or (is_valid_node_key(sender) and self._ctx.node_registry.is_local_key(sender))
            )
        )
        clean_rssi = clean_numeric_value(rssi)
        clean_snr = clean_numeric_value(snr)
        effective_rssi = None if is_local_sender or clean_rssi is None else int(clean_rssi)
        effective_snr = None if is_local_sender else clean_snr
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

        if sender and is_valid_node_key(sender):
            self._update_node_registry_presence(meta, payload_dict)

        return payload_dict, meta

    @staticmethod
    def _extract_battery_percentage(payload_dict: dict[str, Any]) -> int | None:
        """Calcula el porcentaje de batería de telemetría a partir de lecturas raw, level o voltaje."""
        telem = extract_telemetry_fields(payload_dict)
        return telem.get("battery_pct")

    @staticmethod
    def _resolve_effective_role(payload_dict: dict[str, Any], sender_name: str, is_local_sender: bool) -> str:
        """Determina el rol canónico del nodo participante."""
        if is_local_sender:
            return "LOCAL"
        role_val = payload_dict.get("role")
        if role_val:
            return str(role_val)
        raw_type = payload_dict.get("adv_type", payload_dict.get("type"))
        if isinstance(raw_type, int):
            return classify_device_role(raw_type)
        if raw_type == "REPEATER":
            return "REPEATER"
        if raw_type in (3, "ROOM"):
            return "ROOM"
        if raw_type in (4, "SENSOR"):
            return "SENSOR"
        if raw_type in (1, "CHAT", "CLIENT"):
            return "CLIENT"
        return "CLIENT"

    def _update_node_registry_presence(
        self,
        meta: RxMeta,
        payload_dict: dict[str, Any],
    ) -> None:
        bat_pct = self._extract_battery_percentage(payload_dict)
        existing = self._ctx.node_registry.get_contact(meta.sender)
        has_role = any(key in payload_dict for key in ("role", "adv_type")) or isinstance(payload_dict.get("type"), int)
        effective_role = (existing.role if existing and not has_role and not meta.is_local_sender
                          else self._resolve_effective_role(payload_dict, meta.sender_name, meta.is_local_sender))

        lat_val, lon_val = _location_pair(payload_dict)

        is_new, contact_info = self._ctx.node_registry.discover_node(
            NodeDiscoveryEvent(
                public_key=meta.sender,
                name=meta.sender_name if meta.sender_name and meta.sender_name != meta.sender else None,
                role=effective_role,
                rssi=meta.effective_rssi,
                snr=meta.effective_snr,
                hops=meta.effective_hops,
            )
        )

        if is_valid_node_key(contact_info.public_key):
            if lat_val is not None or lon_val is not None or bat_pct is not None:
                self._ctx.node_registry.add_or_update(
                    meta.sender,
                    NodeContactUpdate(
                        last_seen=time.time() if not meta.is_local_sender else None,
                        battery_pct=bat_pct,
                        latitude=lat_val,
                        longitude=lon_val,
                        adv_lat=lat_val,
                        adv_lon=lon_val,
                        is_local=meta.is_local_sender,
                    ),
                )

            if not meta.is_local_sender:
                self._ctx.node_registry.record_packet(
                    PacketRecord(
                        public_key=meta.sender,
                        is_rx=True,
                        rssi=meta.effective_rssi,
                        snr=meta.effective_snr,
                        hop_count=meta.effective_hops,
                    )
                )
                self._spawn_broadcast_task({
                    "type": "contact_discovered" if is_new else "contact_updated",
                    "event_type": "contact_discovered" if is_new else "contact_updated",
                    "is_new": is_new,
                    "contact": contact_info.to_dict(),
                })

    def _resolve_sender_name(self, prefix_or_key: str) -> str:
        # Primero consultar el registro dinámico local
        local_name = self._ctx.node_registry.resolve_name(prefix_or_key)
        if local_name and local_name != prefix_or_key:
            return local_name
        return str(self._ctx.serial_adapter.resolve_sender_name(prefix_or_key))

    async def _handle_mesh_msg_common(self, msg: MeshMessageEvent, event_type_str: str) -> dict[str, Any] | None:
        if self._ctx.node_registry.is_local_key(msg.sender):
            return None

        extracted_telem = self._ctx.repeater_manager.parse_repeater_telemetry_or_response(msg.text)
        existing_contact = self._ctx.node_registry.get_contact(msg.sender)
        should_treat_as_repeater = bool(
            existing_contact and existing_contact.role in ("REPEATER", "ROUTER")
        )

        if extracted_telem and should_treat_as_repeater:
            rep_update = NodeContactUpdate.from_dict(
                extracted_telem,
                last_seen=time.time(),
                name=msg.sender_name,
                role="REPEATER",
                last_rssi=int(msg.rssi) if isinstance(msg.rssi, (int, float)) else extracted_telem.get("last_rssi"),
                last_snr=float(msg.snr) if isinstance(msg.snr, (int, float)) else extracted_telem.get("last_snr"),
            )
            updated_rep = self._ctx.node_registry.add_or_update(msg.sender, rep_update)
            if updated_rep:
                self._spawn_broadcast_task({
                    "type": "contact_updated",
                    "event_type": "contact_updated",
                    "contact": updated_rep.to_dict(),
                })

        sender_contact = self._ctx.node_registry.get_contact(msg.sender)
        is_repeater_sender = (
            (sender_contact and sender_contact.role in ("REPEATER", "ROUTER"))
            or should_treat_as_repeater
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
            self._spawn_broadcast_task(rep_payload)
            return None

        lqi_val = LinkQualityEngine.compute_instant_lqi(msg.snr, msg.rssi, 0)
        lqi_stat = LinkQualityEngine.classify_lqi_status(lqi_val)

        # Actualizar presencia y métricas del nodo emisor en NodeRegistry si es remoto
        if msg.sender and is_valid_node_key(msg.sender) and not self._ctx.node_registry.is_local_key(msg.sender):
            self._ctx.node_registry.record_packet(
                PacketRecord(
                    public_key=msg.sender,
                    is_rx=True,
                    rssi=int(msg.rssi) if isinstance(msg.rssi, (int, float)) else None,
                    snr=float(msg.snr) if isinstance(msg.snr, (int, float)) else None,
                )
            )
            updated_contact = self._ctx.node_registry.add_or_update(
                msg.sender,
                NodeContactUpdate(
                    last_seen=time.time(),
                    name=msg.sender_name if msg.sender_name and msg.sender_name != msg.sender else None,
                    last_rssi=int(msg.rssi) if isinstance(msg.rssi, (int, float)) else None,
                    last_snr=float(msg.snr) if isinstance(msg.snr, (int, float)) else None,
                ),
            )
            if updated_contact:
                self._spawn_broadcast_task({
                    "type": "contact_updated",
                    "event_type": "contact_updated",
                    "contact": updated_contact.to_dict(),
                })

        evt_payload = {
            "type": event_type_str,
            "event_type": event_type_str,
            "is_direct": (event_type_str == "direct"),
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
        self._spawn_broadcast_task(evt_payload)

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
        payload_dict = sanitize_public_payload(payload_dict)
        # Extraer y normalizar exhaustivamente todas las lecturas de telemetría/sensores
        extracted_fields = extract_telemetry_fields(payload_dict)
        payload_dict.update(extracted_fields)
        latitude, longitude = _location_pair(payload_dict)
        for key in ("lat", "latitude", "gps_lat", "adv_lat"):
            if key in payload_dict:
                payload_dict[key] = latitude
        for key in ("lon", "longitude", "gps_lon", "adv_lon"):
            if key in payload_dict:
                payload_dict[key] = longitude

        # Si el payload contiene texto de telemetría de repetidor
        raw_text_cand = payload_dict.get("text", payload_dict.get("raw_text", payload_dict.get("message", "")))
        if isinstance(raw_text_cand, str) and raw_text_cand.strip():
            extracted_rep = self._ctx.repeater_manager.parse_repeater_telemetry_or_response(raw_text_cand)
            if extracted_rep:
                payload_dict.update(extracted_rep)

        # Resolver emisor si aún no está resuelto
        sender, sender_name_cand = extract_sender_from_payload(payload_dict)
        if not sender and payload_dict.get("pubkey_prefix"):
            contact = self._ctx.node_registry.get_by_key_or_prefix(str(payload_dict["pubkey_prefix"]))
            if contact and contact.public_key:
                sender = contact.public_key
                if not sender_name_cand:
                    sender_name_cand = contact.alias or contact.name
        if sender:
            payload_dict["sender"] = sender
        if sender_name_cand:
            payload_dict["sender_name"] = sender_name_cand

        if sender and is_valid_node_key(sender):
            is_local_telem = bool(
                payload_dict.get("is_local")
                or self._ctx.node_registry.is_local_key(sender)
            )
            sender_name_cand = str(
                payload_dict.get("sender_name")
                or payload_dict.get("adv_name")
                or payload_dict.get("name")
                or payload_dict.get("alias")
                or self._resolve_sender_name(sender)
            )
            existing_contact = self._ctx.node_registry.get_contact(sender)
            is_known_rep = bool(
                existing_contact and existing_contact.role in ("REPEATER", "ROUTER")
            )

            telem_role = payload_dict.get("role")
            if not telem_role:
                if is_known_rep:
                    telem_role = "REPEATER"
                elif existing_contact and existing_contact.role:
                    telem_role = existing_contact.role
                else:
                    telem_role = "CLIENT"

            clean_rssi = clean_numeric_value(payload_dict.get("last_rssi", payload_dict.get("rssi")))
            clean_snr = clean_numeric_value(payload_dict.get("last_snr", payload_dict.get("snr")))

            telem_update = NodeContactUpdate.from_dict(
                payload_dict,
                last_seen=time.time() if not is_local_telem else None,
                name=sender_name_cand,
                role=telem_role,
                last_rssi=int(round(clean_rssi)) if clean_rssi is not None else None,
                last_snr=round(clean_snr, 1) if clean_snr is not None else None,
            )
            updated_telem_contact = self._ctx.node_registry.add_or_update(sender, telem_update)
            if updated_telem_contact and not is_local_telem:
                self._spawn_broadcast_task({
                    "type": "contact_updated",
                    "event_type": "contact_updated",
                    "contact": updated_telem_contact.to_dict(),
                })

        # Sanitizar cualquier otro campo bytes restante
        for k, v in list(payload_dict.items()):
            if isinstance(v, (bytes, bytearray)):
                payload_dict[k] = bytes(v).hex()

        payload_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
        evt_json = json.dumps(payload_dict, sort_keys=True)
        self._ctx.mqtt.publish_safe(config.TOPIC_RX_ALL, evt_json, qos=0)
        if any(k in payload_dict for k in ("battery", "battery_pct", "battery_mv", "voltage", "voltage_v", "temperature", "temperature_c", "humidity_pct", "pressure_hpa", "solar_v")):
            self._ctx.mqtt.publish_safe(config.TOPIC_RX_TELEMETRY, evt_json, qos=0)
        self._spawn_broadcast_task(payload_dict)

        # Actualizar ocupación de canal en RateLimiter para gobernar el Airtime Cutoff
        ch_util_cand = payload_dict.get("channel_utilization", payload_dict.get("ch_util"))
        if ch_util_cand is not None:
            try:
                ch_util_val = float(ch_util_cand)
                bridge = getattr(self._ctx, "bridge", None) or getattr(self._ctx, "_bridge", None)
                if bridge and hasattr(bridge, "rate_limiter") and bridge.rate_limiter:
                    bridge.rate_limiter.update_channel_utilization(ch_util_val)
            except Exception as e:
                logging.debug(f"Error actualizando ocupación de canal en rate limiter: {e}")


        ev_name = str(payload_dict.get("event_type", payload_dict.get("type", "telemetry")))

        # Si el evento corresponde a configuración o hardware del nodo local, registrar con formato limpio [ESTACIÓN LOCAL]
        if ev_name in ("self_info", "SELF_INFO", "self") or "SELF" in ev_name.upper():
            node_name = payload_dict.get("name") or "Estación Base"
            pk_val = str(payload_dict.get("public_key", sender or "")).strip().lower()
            freq = payload_dict.get("radio_freq", "--")
            sf = payload_dict.get("radio_sf", "--")
            bw = payload_dict.get("radio_bw", "--")
            cr = payload_dict.get("radio_cr", "--")
            tx_p = payload_dict.get("tx_power", "--")

            if pk_val and is_valid_node_key(pk_val):
                self._ctx.node_registry.set_local_pubkey(pk_val)
                self._ctx.node_registry.add_or_update(
                    pk_val,
                    NodeContactUpdate(
                        name=node_name,
                        alias=node_name,
                        role="LOCAL",
                        is_local=True,
                        hops=0,
                        fixed_position=True,
                    ),
                )
            if self._ctx.admin_handler and hasattr(self._ctx.admin_handler, "_local_config"):
                cfg_update: dict[str, Any] = {"name": node_name}
                if pk_val:
                    cfg_update["public_key"] = pk_val
                if freq != "--":
                    try:
                        cfg_update["frequency"] = float(freq)
                        cfg_update["radio_freq"] = float(freq)
                    except (ValueError, TypeError):
                        pass
                if sf != "--":
                    try:
                        cfg_update["spreading_factor"] = int(sf)
                    except (ValueError, TypeError):
                        pass
                if bw != "--":
                    try:
                        cfg_update["bandwidth"] = float(bw)
                    except (ValueError, TypeError):
                        pass
                if cr != "--":
                    try:
                        cfg_update["coding_rate"] = int(cr)
                    except (ValueError, TypeError):
                        pass
                if tx_p != "--":
                    try:
                        cfg_update["tx_power"] = int(tx_p)
                    except (ValueError, TypeError):
                        pass
                self._ctx.admin_handler._local_config.update(cfg_update)

            logging.info(
                f"[ESTACIÓN LOCAL] Configuración: {node_name} ({pk_val[:8] if pk_val else '??'}) | Freq: {freq} MHz, SF{sf}/BW{bw}/CR{cr}, TX: {tx_p} dBm"
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
            is_ev_local = any(k in ev_name.lower() for k in (
                "self", "battery", "device", "stats", "tuning", "time", "custom_vars", "status", "channel"
            ))
            sender_label = "Estación Base Local" if is_ev_local else "Desconocido"

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

        # Distinguir telemetría de hardware local o tramas vacías vs telemetría RF legítima de nodos remotos
        is_local_station = (
            sender_label.startswith("Estación Base Local")
            or (sender and self._ctx.node_registry and sender == self._ctx.node_registry.local_pubkey)
            or (sender and str(sender).upper() == "LOCAL")
            or payload_dict.get("is_local") is True
            or any(k in ev_name.lower() for k in ("self", "battery", "device", "stats", "tuning", "time", "custom_vars", "channel"))
        )
        has_readings = telem_summary != "Sin lecturas adicionales"

        if is_local_station:
            logging.info(
                f"[ESTACIÓN LOCAL] Telemetría/Diagnóstico ({ev_name}): {telem_summary}"
            )
            return

        if sender_label == "Desconocido" and not has_readings:
            logging.debug(
                f"[RX-TELEMETRÍA] Respuesta interna/vacía sin emisor (Tipo: {ev_name})"
            )
            return

        logging.info(
            f"[RX-TELEMETRÍA] De: {sender_label} -> Para: Gateway/MQTT | "
            f"Tipo: {ev_name} | {telem_summary} | RSSI: {rssi_str}, SNR: {snr_str}{lqi_part}"
        )

    async def _dispatch_parsed_frame(self, frame: MeshcoreFrame) -> None:
        """Enruta instancias de MeshcoreFrame validadas a MQTT."""
        if not frame.is_valid or frame.header.packet_type == PacketType.PRIVATE_KEY:
            return
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
                    if frame.header.packet_type == PacketType.CHANNEL_MSG_RECV:
                        if frame.payload.channel_idx == 0:
                            self._ctx.mqtt.publish_safe(config.TOPIC_RX_PUBLIC, evt_json, qos=0)
                        else:
                            self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_CHANNEL}/ch_{frame.payload.channel_idx}", evt_json, qos=0)
                    elif frame.header.packet_type == PacketType.CONTACT_MSG_RECV:
                        src_hex = f"0x{frame.header.src_node_id:04X}"
                        self._ctx.mqtt.publish_safe(f"{config.TOPIC_RX_DIRECT}/{src_hex}", evt_json, qos=0)

            logging.info(
                f"[RX-FRAME] De: 0x{frame.header.src_node_id:04X} -> Para: 0x{frame.header.dst_node_id:04X} | "
                f"OpCode: {frame.header.opcode.name} | Seq: {frame.header.seq_num} | Válido: {frame.is_valid}"
            )
