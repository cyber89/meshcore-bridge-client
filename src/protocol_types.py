"""
Protocol Types and Binary Data Contracts for MeshCore Bridge.
Define dataclasses inmutables y tipadas con validación y serialización estricta.
Single Source of Truth para el bridge y suites de pruebas.
"""

from __future__ import annotations

import struct
from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any

# ================= Constantes de Protocolo =================

SOF_BYTE: int = 0xAA
EOF_BYTE: int = 0x55
ESC_BYTE: int = 0x1B
ESC_MASK: int = 0x20
BROADCAST_NODE_ID: int = 0xFFFF
MAX_PAYLOAD_SIZE: int = 256
HEADER_SIZE_BYTES: int = 9
CRC_SIZE_BYTES: int = 2


class OpCode(IntEnum):
    """Códigos de Operación del protocolo binario MeshCore."""
    TELEMETRY = 0x01
    TEXT_MSG = 0x02
    NODE_ADVERT = 0x03
    ROUTING_INFO = 0x04
    ADMIN_CMD = 0x05
    ADMIN_RESP = 0x06
    ACK = 0x07


class FirmwareRouteType(IntEnum):
    """Tipos de enrutamiento LoRa en el firmware C/C++ (Packet.h)."""
    TRANSPORT_FLOOD = 0x00
    FLOOD = 0x01
    DIRECT = 0x02
    TRANSPORT_DIRECT = 0x03


class FirmwarePayloadType(IntEnum):
    """Tipos de payload en la capa wire del firmware C/C++ (Packet.h)."""
    REQ = 0x00
    RESPONSE = 0x01
    TXT_MSG = 0x02
    ACK = 0x03
    ADVERT = 0x04
    GRP_TXT = 0x05
    GRP_DATA = 0x06
    ANON_REQ = 0x07
    PATH = 0x08
    TRACE = 0x09
    MULTIPART = 0x0A
    CONTROL = 0x0B
    RAW_CUSTOM = 0x0F


class FirmwareAdvertType(IntEnum):
    """Tipos de anuncio y roles de nodo en el firmware MeshCore C/C++ (AdvertDataHelpers.h)."""
    NONE = 0
    CHAT = 1       # Cliente / Companion de Chat
    REPEATER = 2   # Nodo Repetidor / Router de Malla
    ROOM = 3       # Servidor de Sala / Room Server
    SENSOR = 4     # Nodo Sensor de Telemetría


class FirmwareCommandType(IntEnum):
    """OpCodes de comandos Host -> Radio del SDK oficial (packets.py)."""
    APP_START = 1
    SEND_TXT_MSG = 2
    SEND_CHANNEL_TXT_MSG = 3
    GET_CONTACTS = 4
    GET_DEVICE_TIME = 5
    SET_DEVICE_TIME = 6
    SEND_SELF_ADVERT = 7
    SET_ADVERT_NAME = 8
    ADD_UPDATE_CONTACT = 9
    SYNC_NEXT_MESSAGE = 10
    SET_RADIO_PARAMS = 11
    SET_RADIO_TX_POWER = 12
    RESET_PATH = 13
    SET_ADVERT_LATLON = 14
    REMOVE_CONTACT = 15
    REBOOT = 19
    GET_BATT_AND_STORAGE = 20
    SEND_RAW_DATA = 25
    SEND_TRACE_PATH = 36
    SEND_TELEMETRY_REQ = 39
    BINARY_REQ = 50
    GET_STATS = 56


class FirmwarePushCode(IntEnum):
    """Códigos de notificaciones Push asíncronas Radio -> Host (packets.py)."""
    ADVERTISEMENT = 0x80
    PATH_UPDATE = 0x81
    ACK = 0x82
    MESSAGES_WAITING = 0x83
    RAW_DATA = 0x84
    STATUS_RESPONSE = 0x87
    LOG_DATA = 0x88
    TRACE_DATA = 0x89
    TELEMETRY_RESPONSE = 0x8B
    BINARY_RESPONSE = 0x8C
    CONTROL_DATA = 0x8E
    CONTACT_DELETED = 0x8F
    CONTACTS_FULL = 0x90


class HardwareModel(IntEnum):
    """Modelos de hardware soportados por MeshCore."""
    UNKNOWN = 0x00
    HELTEC_V2 = 0x01
    HELTEC_V3 = 0x02
    LILYGO_TBEAM = 0x03
    LILYGO_TECHO = 0x04
    HELTEC_V4 = 0x05
    RAK4631 = 0x06
    LILYGO_TDECK = 0x07
    M5STACK_CORE = 0x08
    SEEED_XIAO = 0x09
    RP2040_LORA = 0x0A


def compute_crc16_ccitt(data: bytes, init: int = 0xFFFF, poly: int = 0x1021) -> int:
    """Calcula el checksum CRC-16-CCITT de forma determinista."""
    crc = init
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def get_opcode_name(opcode: int) -> str:
    """Retorna el nombre legible de un OpCode de protocolo."""
    try:
        return OpCode(opcode).name
    except ValueError:
        return f"UNKNOWN_0x{opcode:02X}"


def get_payload_type_name(ptype: int) -> str:
    """Retorna el nombre legible de un FirmwarePayloadType."""
    try:
        return FirmwarePayloadType(ptype).name
    except ValueError:
        return f"RAW_0x{ptype:02X}"


def get_push_code_name(code: int) -> str:
    """Retorna el nombre legible de una notificación Push."""
    try:
        return FirmwarePushCode(code).name
    except ValueError:
        return f"PUSH_0x{code:02X}"


@dataclass(frozen=True)
class FrameHeader:
    """Cabecera de 9 Bytes de trama binaria MeshCore."""
    opcode: OpCode
    seq_num: int
    src_node_id: int
    dst_node_id: int
    hop_limit: int
    payload_len: int

    def __post_init__(self) -> None:
        if not (0 <= self.seq_num <= 0xFF):
            raise ValueError(f"seq_num fuera de rango 0..255: {self.seq_num}")
        if not (0 <= self.src_node_id <= 0xFFFF):
            raise ValueError(f"src_node_id fuera de rango uint16: {self.src_node_id}")
        if not (0 <= self.dst_node_id <= 0xFFFF):
            raise ValueError(f"dst_node_id fuera de rango uint16: {self.dst_node_id}")
        if not (0 <= self.hop_limit <= 0x0F):
            raise ValueError(f"hop_limit fuera de rango 0..15: {self.hop_limit}")
        if not (0 <= self.payload_len <= MAX_PAYLOAD_SIZE):
            raise ValueError(f"payload_len excede {MAX_PAYLOAD_SIZE} bytes: {self.payload_len}")

    def pack(self) -> bytes:
        """Serializa la cabecera en 9 bytes binarios (Little-Endian)."""
        return struct.pack(
            "<BBHHBH",
            int(self.opcode),
            self.seq_num,
            self.src_node_id,
            self.dst_node_id,
            self.hop_limit,
            self.payload_len,
        )

    @classmethod
    def unpack(cls, data: bytes) -> FrameHeader:
        """Deserializa 9 bytes binarios a una instancia de FrameHeader."""
        if len(data) < HEADER_SIZE_BYTES:
            raise ValueError(f"Datos insuficientes para cabecera: {len(data)}B < {HEADER_SIZE_BYTES}B")
        opcode_raw, seq, src, dst, hop, plen = struct.unpack("<BBHHBH", data[:HEADER_SIZE_BYTES])
        return cls(
            opcode=OpCode(opcode_raw),
            seq_num=seq,
            src_node_id=src,
            dst_node_id=dst,
            hop_limit=hop,
            payload_len=plen,
        )


@dataclass(frozen=True)
class TelemetryPayload:
    """Payload estructurado de métricas y telemetría de nodo (OpCode 0x01)."""
    battery_mv: int
    solar_mv: int
    temperature_c: float
    humidity_pct: float
    pressure_hpa: float
    snr_db: int
    rssi_dbm: int
    battery_pct: int

    def pack(self) -> bytes:
        temp_cdeg = int(round(self.temperature_c * 100))
        hum_pct = int(round(self.humidity_pct * 100))
        press_pa = int(round(self.pressure_hpa * 100))
        return struct.pack(
            "<HHhhIbhB",
            self.battery_mv,
            self.solar_mv,
            temp_cdeg,
            hum_pct,
            press_pa,
            self.snr_db,
            self.rssi_dbm,
            self.battery_pct,
        )

    @classmethod
    def unpack(cls, data: bytes) -> TelemetryPayload:
        if len(data) < 16:
            raise ValueError(f"Payload de telemetría demasiado corto: {len(data)}B < 16B")
        bat_mv, sol_mv, t_cdeg, h_pct, p_pa, snr, rssi, bat_pct = struct.unpack("<HHhhIbhB", data[:16])
        return cls(
            battery_mv=bat_mv,
            solar_mv=sol_mv,
            temperature_c=round(t_cdeg / 100.0, 2),
            humidity_pct=round(h_pct / 100.0, 2),
            pressure_hpa=round(p_pa / 100.0, 2),
            snr_db=snr,
            rssi_dbm=rssi,
            battery_pct=bat_pct,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TextMessagePayload:
    """Payload de mensaje de texto en canal o directo (OpCode 0x02)."""
    channel_idx: int
    sender_alias: str
    text: str

    def pack(self) -> bytes:
        alias_bytes = self.sender_alias.encode("utf-8")[:15].ljust(16, b"\x00")
        text_bytes = self.text.encode("utf-8")[:238]
        return struct.pack("<B16sB", self.channel_idx, alias_bytes, len(text_bytes)) + text_bytes

    @classmethod
    def unpack(cls, data: bytes) -> TextMessagePayload:
        if len(data) < 18:
            raise ValueError(f"Payload de texto demasiado corto: {len(data)}B < 18B")
        ch_idx, alias_raw, text_len = struct.unpack("<B16sB", data[:18])
        alias = alias_raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        text = data[18: 18 + text_len].decode("utf-8", errors="replace")
        return cls(channel_idx=ch_idx, sender_alias=alias, text=text)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NodeAdvertisement:
    """Payload de anuncio y presencia de nodo (OpCode 0x03)."""
    node_id: int
    short_name: str
    long_name: str
    hw_model: HardwareModel
    fw_version: str
    latitude: float
    longitude: float
    altitude_m: int

    def pack(self) -> bytes:
        sname_bytes = self.short_name.encode("utf-8")[:4].ljust(4, b"\x00")
        lname_bytes = self.long_name.encode("utf-8")[:20].ljust(20, b"\x00")
        lat_e7 = int(round(self.latitude * 1e7))
        lon_e7 = int(round(self.longitude * 1e7))
        fw_val = int(self.fw_version.replace(".", "").replace("v", "")[:4] or "0")
        return struct.pack(
            "<H4s20sBHiih",
            self.node_id,
            sname_bytes,
            lname_bytes,
            int(self.hw_model),
            fw_val,
            lat_e7,
            lon_e7,
            self.altitude_m,
        )

    @classmethod
    def unpack(cls, data: bytes) -> NodeAdvertisement:
        if len(data) < 39:
            raise ValueError(f"Payload de anuncio demasiado corto: {len(data)}B < 39B")
        node_id, sname_raw, lname_raw, hw, fw, lat_e7, lon_e7, alt = struct.unpack("<H4s20sBHiih", data[:39])
        sname = sname_raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        lname = lname_raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        try:
            hw_model = HardwareModel(hw)
        except ValueError:
            hw_model = HardwareModel.UNKNOWN
        return cls(
            node_id=node_id,
            short_name=sname,
            long_name=lname,
            hw_model=hw_model,
            fw_version=f"v{fw / 100:.2f}",
            latitude=round(lat_e7 / 1e7, 6),
            longitude=round(lon_e7 / 1e7, 6),
            altitude_m=alt,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["hw_model_name"] = self.hw_model.name
        return d


@dataclass(frozen=True)
class AckPayload:
    """Payload de confirmación / ACK (OpCode 0x07)."""
    ack_seq_num: int
    status_code: int

    def pack(self) -> bytes:
        return struct.pack("<BB", self.ack_seq_num, self.status_code)

    @classmethod
    def unpack(cls, data: bytes) -> AckPayload:
        if len(data) < 2:
            raise ValueError(f"Payload ACK demasiado corto: {len(data)}B < 2B")
        ack_seq, status = struct.unpack("<BB", data[:2])
        return cls(ack_seq_num=ack_seq, status_code=status)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ParsedPayload = (
    TelemetryPayload | TextMessagePayload | NodeAdvertisement | AckPayload | bytes
)


@dataclass(frozen=True)
class MeshcoreFrame:
    """Trama binaria completa y verificada de MeshCore."""
    header: FrameHeader
    payload: ParsedPayload
    raw_payload: bytes
    crc16: int
    is_valid: bool

    def serialize(self) -> bytes:
        """Serializa la trama completa con framing SOF/EOF, byte stuffing y CRC-16."""
        header_bytes = self.header.pack()
        body = header_bytes + self.raw_payload
        crc_val = compute_crc16_ccitt(body)
        # NOTE: CRC is serialized as big-endian (>H) while the header uses little-endian (<BB HH BH). This is intentional per the MeshCore wire format spec. Do NOT change.
        crc_bytes = struct.pack(">H", crc_val)

        # Aplicar Byte Stuffing
        raw_stream = body + crc_bytes
        escaped_stream = bytearray()
        escaped_stream.append(SOF_BYTE)
        for b in raw_stream:
            if b in (SOF_BYTE, EOF_BYTE, ESC_BYTE):
                escaped_stream.append(ESC_BYTE)
                escaped_stream.append(b ^ ESC_MASK)
            else:
                escaped_stream.append(b)
        escaped_stream.append(EOF_BYTE)
        return bytes(escaped_stream)

    @classmethod
    def parse_raw_packet(cls, unescaped_body: bytes, strict: bool = False) -> MeshcoreFrame:
        """Parsea una trama des-escapada (Header + Payload + CRC)."""
        if len(unescaped_body) < HEADER_SIZE_BYTES + CRC_SIZE_BYTES:
            raise ValueError(f"Trama truncada ({len(unescaped_body)}B)")

        data_to_crc = unescaped_body[:-CRC_SIZE_BYTES]
        # NOTE: CRC is serialized as big-endian (>H) while the header uses little-endian (<BB HH BH). This is intentional per the MeshCore wire format spec. Do NOT change.
        crc_embedded = struct.unpack(">H", unescaped_body[-CRC_SIZE_BYTES:])[0]
        crc_calc = compute_crc16_ccitt(data_to_crc)

        if strict and crc_embedded != crc_calc:
            raise ValueError(f"CRC mismatch: embedded=0x{crc_embedded:04X} calculated=0x{crc_calc:04X}")

        is_valid = (crc_embedded == crc_calc)
        header = FrameHeader.unpack(data_to_crc[:HEADER_SIZE_BYTES])
        payload_data = data_to_crc[HEADER_SIZE_BYTES: HEADER_SIZE_BYTES + header.payload_len]

        payload: ParsedPayload
        if header.opcode == OpCode.TELEMETRY:
            payload = TelemetryPayload.unpack(payload_data)
        elif header.opcode == OpCode.TEXT_MSG:
            payload = TextMessagePayload.unpack(payload_data)
        elif header.opcode == OpCode.NODE_ADVERT:
            payload = NodeAdvertisement.unpack(payload_data)
        elif header.opcode == OpCode.ACK:
            payload = AckPayload.unpack(payload_data)
        else:
            payload = payload_data

        return cls(
            header=header,
            payload=payload,
            raw_payload=payload_data,
            crc16=crc_embedded,
            is_valid=is_valid,
        )

    def to_mqtt_event(self) -> dict[str, Any]:
        """Convierte la trama a formato JSON estructurado para n8n."""
        payload_data: Any
        if isinstance(self.payload, (TelemetryPayload, TextMessagePayload, NodeAdvertisement, AckPayload)):
            payload_data = self.payload.to_dict()
        else:
            payload_data = {"raw_hex": self.raw_payload.hex().upper()}

        return {
            "event_type": self.header.opcode.name,
            "opcode": int(self.header.opcode),
            "seq_num": self.header.seq_num,
            "sender": {
                "node_id": f"0x{self.header.src_node_id:04X}",
                "node_id_int": self.header.src_node_id,
            },
            "recipient": {
                "node_id": f"0x{self.header.dst_node_id:04X}",
                "node_id_int": self.header.dst_node_id,
                "is_broadcast": (self.header.dst_node_id == BROADCAST_NODE_ID),
            },
            "lora_metrics": {
                "hop_limit": self.header.hop_limit,
            },
            "payload": payload_data,
            "crc_valid": self.is_valid,
        }
