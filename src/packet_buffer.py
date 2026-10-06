"""
PacketBuffer: Búfer circular en RAM para tramas LoRa con generadores de exportación
(contenedor PCAP DLT_USER0, CSV tabular y JSON estructurado).
DLT_USER0 no define un dissector ni acredita captura/replay RF de MeshCore.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import struct
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.metrics_aggregator import MetricsAggregator


@dataclass(slots=True)
class CapturedPacket:
    """Representa una trama de radio LoRa capturada en tránsito por el bridge."""

    packet_id: int
    timestamp: float
    iso_time: str
    direction: str  # "rx" o "tx"
    channel_idx: int
    packet_type: str
    sender: str
    sender_name: str
    target: str
    text: str
    rssi: int | None = None
    snr: float | None = None
    lqi_score: float | None = None
    lqi_status: str = "N/A"
    raw_bytes: bytes = b""
    payload_dict: dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0
    session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serializa la trama a un diccionario apto para JSON / API REST."""
        res = asdict(self)
        # Convertir bytes crudos a representación hexadecimal
        res["raw_hex"] = self.raw_bytes.hex() if self.raw_bytes else ""
        del res["raw_bytes"]
        return res


@dataclass(slots=True)
class PacketInput:
    """Objeto de parámetros para record() en PacketBuffer."""
    direction: str = "rx"
    channel_idx: int = 0
    packet_type: str = "PACKET"
    sender: str = ""
    sender_name: str = ""
    target: str = "broadcast"
    text: str = ""
    rssi: int | None = None
    snr: float | None = None
    lqi_score: float | None = None
    lqi_status: str = "N/A"
    raw_bytes: bytes | bytearray | None = None
    payload_dict: dict[str, Any] | None = None
    redact_content: bool = False


class PacketBuffer:
    """
    Búfer circular no bloqueante en memoria RAM para almacenar los últimos N paquetes LoRa.
    Permite exportación a formato binario PCAP (Wireshark DLT_USER0 147), CSV y JSON.
    """

    def __init__(self, max_packets: int = 500) -> None:
        self.max_packets = max_packets
        self._buffer: deque[CapturedPacket] = deque(maxlen=max_packets)
        self._counter = 0
        self.session_id = uuid4().hex
        self.capture_enabled = True
        self.metrics_aggregator = MetricsAggregator()

    def record(
        self,
        direction: str | PacketInput = "rx",
        channel_idx: int = 0,
        packet_type: str = "PACKET",
        sender: str = "",
        sender_name: str = "",
        target: str = "broadcast",
        text: str = "",
        rssi: int | None = None,
        snr: float | None = None,
        lqi_score: float | None = None,
        lqi_status: str = "N/A",
        raw_bytes: bytes | bytearray | None = None,
        payload_dict: dict[str, Any] | None = None,
        redact_content: bool = False,
    ) -> CapturedPacket | None:
        """Registra una trama en el búfer circular aceptando PacketInput o parámetros individuales."""
        if not self.capture_enabled:
            return None

        if isinstance(direction, PacketInput):
            inp = direction
            direction_str = inp.direction
            channel_idx = inp.channel_idx
            packet_type = inp.packet_type
            sender = inp.sender
            sender_name = inp.sender_name
            target = inp.target
            text = inp.text
            rssi = inp.rssi
            snr = inp.snr
            lqi_score = inp.lqi_score
            lqi_status = inp.lqi_status
            raw_bytes = inp.raw_bytes
            payload_dict = inp.payload_dict
            redact_content = inp.redact_content
        else:
            direction_str = str(direction)

        self._counter += 1
        now_ts = time.time()
        iso_time = datetime.now(timezone.utc).isoformat()

        b_bytes = bytes(raw_bytes) if raw_bytes else b""
        if not b_bytes and text:
            b_bytes = text.encode("utf-8", errors="ignore")
        size_bytes = len(b_bytes)
        # CLI scalar replies can be credentials even without a password label.
        # Never retain their arbitrary payload or decoded Companion bytes in a
        # public capture. Correlation and private waiter delivery happen upstream.
        capture_payload = payload_dict or {}
        redact_content = bool(
            redact_content
            or str(packet_type).upper() == "CLI_REPLY"
            or capture_payload.get("txt_type", capture_payload.get("text_type")) in (1, "1")
            or capture_payload.get("sensitive_response")
        )
        if redact_content:
            text = "Contenido de administración protegido"
            b_bytes = b""
            capture_payload = {"content_redacted": True}

        pkt = CapturedPacket(
            packet_id=self._counter,
            session_id=self.session_id,
            timestamp=now_ts,
            iso_time=iso_time,
            direction=direction_str.lower(),
            channel_idx=channel_idx,
            packet_type=str(packet_type).upper(),
            sender=str(sender),
            sender_name=str(sender_name or sender),
            target=str(target),
            text=str(text),
            rssi=rssi,
            snr=snr,
            lqi_score=lqi_score,
            lqi_status=lqi_status,
            raw_bytes=b_bytes,
            payload_dict=copy.deepcopy(capture_payload),
            size_bytes=size_bytes,
        )

        self._buffer.append(pkt)
        if self.metrics_aggregator is not None:
            self.metrics_aggregator.record_packet(
                direction=pkt.direction,
                packet_type=pkt.packet_type,
                target=pkt.target,
                size_bytes=pkt.size_bytes,
                snr=pkt.snr,
                rssi=pkt.rssi,
                timestamp=pkt.timestamp,
            )
        return pkt

    def get_packets(
        self,
        limit: int = 200,
        offset: int = 0,
        direction: str | None = None,
        p_type: str | None = None,
        order: str = "asc",
    ) -> tuple[list[dict[str, Any]], int]:
        """Obtiene un lote paginado y filtrado de paquetes."""
        if order not in ("asc", "desc"):
            raise ValueError("order must be asc or desc")
        items = list(self._buffer)
        if direction:
            dir_clean = direction.strip().lower()
            items = [p for p in items if p.direction == dir_clean]
        if p_type:
            type_clean = p_type.strip().upper()
            items = [p for p in items if p.packet_type == type_clean]

        total = len(items)
        if order == "desc":
            items.reverse()
        if offset > 0:
            items = items[offset:]
        if limit > 0:
            items = items[:limit]

        return [p.to_dict() for p in items], total

    def clear(self) -> None:
        """Vacía el búfer de paquetes en memoria."""
        self._buffer.clear()
        if self.metrics_aggregator is not None:
            self.metrics_aggregator.reset()

    def generate_json(self) -> str:
        """Serializa todas las tramas en formato JSON estructurado."""
        packets = [p.to_dict() for p in self._buffer]
        export_bundle = {
            "version": "1.0",
            "generator": "MeshCore Bridge v3.0 LoRa Sniffer",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "packet_count": len(packets),
            "packets": packets,
        }
        return json.dumps(export_bundle, indent=2, ensure_ascii=False)

    def generate_csv(self) -> str:
        """Exporta las tramas a formato CSV estándar."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID",
            "Timestamp_ISO",
            "Epoch",
            "Direction",
            "Channel",
            "Type",
            "Sender",
            "Sender_Name",
            "Target",
            "RSSI_dBm",
            "SNR_dB",
            "LQI_Score",
            "Size_Bytes",
            "Text_Message",
            "Raw_Hex",
        ])

        for p in self._buffer:
            row: list[Any] = [
                p.packet_id,
                p.iso_time,
                f"{p.timestamp:.4f}",
                p.direction.upper(),
                p.channel_idx,
                p.packet_type,
                p.sender,
                p.sender_name,
                p.target,
                p.rssi if p.rssi is not None else "",
                p.snr if p.snr is not None else "",
                p.lqi_score if p.lqi_score is not None else "",
                p.size_bytes,
                p.text.replace("\n", " ").replace("\r", ""),
                p.raw_bytes.hex(),
            ]
            writer.writerow([
                "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
                for value in row
            ])

        return output.getvalue()

    def generate_pcap(self) -> bytes:
        """
        Construye un archivo binario PCAP estándar (RFC/libpcap) compatible con Wireshark.
        Link-layer header type: DLT_USER0 (147).
        """
        pcap_data = bytearray()

        # Cabecera Global PCAP (24 bytes)
        # magic_number: 0xa1b2c3d4 (microsegundos, standard endianness)
        # version_major: 2, version_minor: 4
        # thiszone: 0, sigfigs: 0
        # snaplen: 65535
        # network: 147 (DLT_USER0 para tramas de radio personalizadas / Wireshark)
        magic = 0xA1B2C3D4
        ver_major = 2
        ver_minor = 4
        thiszone = 0
        sigfigs = 0
        snaplen = 65535
        network = 147  # DLT_USER0

        pcap_data.extend(struct.pack("<IHHiIII", magic, ver_major, ver_minor, thiszone, sigfigs, snaplen, network))

        # Escribir cada registro de paquete PCAP
        for p in self._buffer:
            ts_sec = int(p.timestamp)
            ts_usec = int((p.timestamp - ts_sec) * 1_000_000)

            frame_data = p.raw_bytes
            if not frame_data:
                # Construir una cabecera de carga sintética si no hay bytes de radio
                simulated_payload = f"[{p.packet_type}] From:{p.sender} To:{p.target} Ch:{p.channel_idx} Msg:{p.text}"
                frame_data = simulated_payload.encode("utf-8", errors="ignore")

            pkt_len = len(frame_data)
            incl_len = min(pkt_len, snaplen)

            # Cabecera de paquete PCAP (16 bytes): ts_sec, ts_usec, incl_len, orig_len
            pcap_data.extend(struct.pack("<IIII", ts_sec, ts_usec, incl_len, pkt_len))
            pcap_data.extend(frame_data[:incl_len])

        return bytes(pcap_data)
