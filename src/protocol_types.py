"""
Protocol Types and Binary Data Contracts for MeshCore Bridge.
Define dataclasses inmutables y tipadas con validación y serialización estricta.
Single Source of Truth para el bridge y suites de pruebas.

Aligned with official MeshCore SDK (meshcore_py/src/meshcore/packets.py).
"""

from __future__ import annotations

import struct
from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any, Protocol

# ================= Constantes de Protocolo =================

SOF_BYTE: int = 0xAA
EOF_BYTE: int = 0x55
ESC_BYTE: int = 0x1B
ESC_MASK: int = 0x20
BROADCAST_NODE_ID: int = 0xFFFF
MAX_PAYLOAD_SIZE: int = 256
HEADER_SIZE_BYTES: int = 9
CRC_SIZE_BYTES: int = 2


class PacketType(IntEnum):
    """Tipos de paquete/respuesta del protocolo MeshCore (SDK packets.py).
    Nota: Este enum reemplaza al antiguo OpCode que era incompatible."""
    OK = 0
    ERROR = 1
    CONTACT_START = 2
    CONTACT = 3
    CONTACT_END = 4
    SELF_INFO = 5
    MSG_SENT = 6
    CONTACT_MSG_RECV = 7
    CHANNEL_MSG_RECV = 8
    CURRENT_TIME = 9
    NO_MORE_MSGS = 10
    CONTACT_URI = 11
    BATTERY = 12
    DEVICE_INFO = 13
    PRIVATE_KEY = 14
    DISABLED = 15
    CONTACT_MSG_RECV_V3 = 16
    CHANNEL_MSG_RECV_V3 = 17
    CHANNEL_INFO = 18
    SIGN_START = 19
    SIGNATURE = 20
    CUSTOM_VARS = 21
    ADVERT_PATH = 22
    TUNING_PARAMS = 23
    STATS = 24
    AUTOADD_CONFIG = 25
    ALLOWED_REPEAT_FREQ = 26
    CHANNEL_DATA_RECV = 27
    DEFAULT_FLOOD_SCOPE = 28

    # Push notifications (0x80-0x90)
    ADVERTISEMENT = 0x80
    PATH_UPDATE = 0x81
    ACK = 0x82
    MESSAGES_WAITING = 0x83
    RAW_DATA = 0x84
    LOGIN_SUCCESS = 0x85
    LOGIN_FAILED = 0x86
    STATUS_RESPONSE = 0x87
    LOG_DATA = 0x88
    TRACE_DATA = 0x89
    NEW_ADVERT = 0x8A
    TELEMETRY_RESPONSE = 0x8B
    BINARY_RESPONSE = 0x8C
    PATH_DISCOVERY_RESPONSE = 0x8D
    CONTROL_DATA = 0x8E
    CONTACT_DELETED = 0x8F
    CONTACTS_FULL = 0x90


# Deprecated: Use PacketType instead. OpCode was incompatible with the official SDK.
# This alias is maintained for legacy import compatibility only.


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


class CommandType(IntEnum):
    """OpCodes de comandos Host -> Radio del SDK oficial (packets.py).
    Aligned with meshcore_py/src/meshcore/packets.py CommandType."""
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
    SHARE_CONTACT = 16
    EXPORT_CONTACT = 17
    IMPORT_CONTACT = 18
    REBOOT = 19
    GET_BATT_AND_STORAGE = 20
    SET_TUNING_PARAMS = 21
    DEVICE_QUERY = 22
    EXPORT_PRIVATE_KEY = 23
    IMPORT_PRIVATE_KEY = 24
    SEND_RAW_DATA = 25
    SEND_LOGIN = 26
    SEND_STATUS_REQ = 27
    HAS_CONNECTION = 28
    LOGOUT = 29
    GET_CONTACT_BY_KEY = 30
    GET_CHANNEL = 31
    SET_CHANNEL = 32
    SIGN_START = 33
    SIGN_DATA = 34
    SIGN_FINISH = 35
    SEND_TRACE_PATH = 36
    SET_DEVICE_PIN = 37
    SET_OTHER_PARAMS = 38
    SEND_TELEMETRY_REQ = 39
    GET_CUSTOM_VARS = 40
    SET_CUSTOM_VAR = 41
    GET_ADVERT_PATH = 42
    GET_TUNING_PARAMS = 43
    BINARY_REQ = 50
    FACTORY_RESET = 51
    PATH_DISCOVERY = 52
    SET_FLOOD_SCOPE = 54
    SEND_CONTROL_DATA = 55
    GET_STATS = 56
    SEND_ANON_REQ = 57
    SET_AUTOADD_CONFIG = 58
    GET_AUTOADD_CONFIG = 59
    GET_ALLOWED_REPEAT_FREQ = 60
    SET_PATH_HASH_MODE = 61
    SET_DEFAULT_FLOOD_SCOPE = 63
    GET_DEFAULT_FLOOD_SCOPE = 64


# Deprecated: Use CommandType instead. FirmwareCommandType was an alias maintained
# for backward compatibility only.


class BinaryReqType(IntEnum):
    """Tipos de solicitud binaria (SDK packets.py)."""
    STATUS = 0x01
    KEEP_ALIVE = 0x02
    TELEMETRY = 0x03
    MMA = 0x04
    ACL = 0x05
    NEIGHBOURS = 0x06


class ControlType(IntEnum):
    """Tipos de control (SDK packets.py)."""
    NODE_DISCOVER_REQ = 0x80
    NODE_DISCOVER_RESP = 0x90


# Deprecated: Use PacketType instead. FirmwarePushCode was an alias maintained
# for backward compatibility only.


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


def get_packet_type_name(ptype: int) -> str:
    """Retorna el nombre legible de un tipo de paquete."""
    try:
        return PacketType(ptype).name
    except ValueError:
        return f"UNKNOWN_0x{ptype:02X}"


# Legacy aliases
get_opcode_name = get_packet_type_name
get_payload_type_name = get_packet_type_name
get_push_code_name = get_packet_type_name


@dataclass(frozen=True)
class FrameHeader:
    """Cabecera de 9 Bytes de trama binaria MeshCore."""
    packet_type: PacketType
    seq_num: int
    src_node_id: int
    dst_node_id: int
    hop_limit: int
    payload_len: int

    @property
    def opcode(self) -> PacketType:
        """Legacy property for backward compatibility."""
        return self.packet_type

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
            int(self.packet_type),
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
        ptype_raw, seq, src, dst, hop, plen = struct.unpack("<BBHHBH", data[:HEADER_SIZE_BYTES])
        return cls(
            packet_type=PacketType(ptype_raw),
            seq_num=seq,
            src_node_id=src,
            dst_node_id=dst,
            hop_limit=hop,
            payload_len=plen,
        )


class MeshCoreSDKProtocol(Protocol):
    """Protocolo estructural que define la interfaz esperada del SDK meshcore_py.
    Permite type checking sin acoplamiento a la implementación concreta."""
    commands: Any
    connection: Any
    cx: Any
    contacts: Any
    channels: Any
    def get_contact_by_name(self, name: str) -> Any: ...
    def get_contact_by_key_prefix(self, prefix: str) -> Any: ...
    async def start_auto_message_fetching(self) -> None: ...
    async def ensure_contacts(self) -> None: ...
    async def disconnect(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...
    def subscribe(self, event_type: Any, callback: Any) -> None: ...

import warnings


@dataclass(frozen=True)
class TelemetryPayload:
    """LEGACY: Payload estructurado de métricas y telemetría de nodo.
    NOTA: Este formato NO existe en el firmware real. El firmware envía
    STATUS_RESPONSE (0x87) con el formato de parse_status_response().
    Mantenido solo para compatibilidad con código existente."""
    battery_mv: int
    solar_mv: int
    temperature_c: float
    humidity_pct: float
    pressure_hpa: float
    snr_db: int
    rssi_dbm: int
    battery_pct: int

    def pack(self) -> bytes:
        warnings.warn(
            "TelemetryPayload.pack() is deprecated. Use parse_status_response() instead.",
            PendingDeprecationWarning,
            stacklevel=2,
        )
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
        warnings.warn(
            "TelemetryPayload.unpack() is deprecated. Use parse_status_response() instead.",
            PendingDeprecationWarning,
            stacklevel=2,
        )
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


def parse_status_response(data: bytes, pubkey_prefix: str | None = None, offset: int = 0) -> dict[str, Any]:
    """
    Parsea STATUS_RESPONSE (0x87) del firmware real.
    Formato: 1 type + 1 reserved + 6 pubkey + 52 status fields
    Basado en SDK: meshcore_py/src/meshcore/parsing.py parse_status()
    """
    res: dict[str, Any] = {}

    # Handle pubkey
    if pubkey_prefix is None:
        if len(data) >= 8:
            res["pubkey_pre"] = data[2:8].hex()
            offset = 8
        else:
            return res
    else:
        res["pubkey_pre"] = pubkey_prefix

    if len(data) < offset + 52:
        return res

    res["bat"] = int.from_bytes(data[offset:offset+2], byteorder="little")
    res["tx_queue_len"] = int.from_bytes(data[offset+2:offset+4], byteorder="little")
    res["noise_floor"] = int.from_bytes(data[offset+4:offset+6], byteorder="little", signed=True)
    res["last_rssi"] = int.from_bytes(data[offset+6:offset+8], byteorder="little", signed=True)
    res["nb_recv"] = int.from_bytes(data[offset+8:offset+12], byteorder="little", signed=False)
    res["nb_sent"] = int.from_bytes(data[offset+12:offset+16], byteorder="little", signed=False)
    res["airtime"] = int.from_bytes(data[offset+16:offset+20], byteorder="little")
    res["uptime"] = int.from_bytes(data[offset+20:offset+24], byteorder="little")
    res["sent_flood"] = int.from_bytes(data[offset+24:offset+28], byteorder="little")
    res["sent_direct"] = int.from_bytes(data[offset+28:offset+32], byteorder="little")
    res["recv_flood"] = int.from_bytes(data[offset+32:offset+36], byteorder="little")
    res["recv_direct"] = int.from_bytes(data[offset+36:offset+40], byteorder="little")
    res["full_evts"] = int.from_bytes(data[offset+40:offset+42], byteorder="little")
    res["last_snr"] = int.from_bytes(data[offset+42:offset+44], byteorder="little", signed=True) / 4
    res["direct_dups"] = int.from_bytes(data[offset+44:offset+46], byteorder="little")
    res["flood_dups"] = int.from_bytes(data[offset+46:offset+48], byteorder="little")
    res["rx_airtime"] = int.from_bytes(data[offset+48:offset+52], byteorder="little")

    if len(data) >= offset + 56:
        res["recv_errors"] = int.from_bytes(data[offset+52:offset+56], byteorder="little")
    else:
        res["recv_errors"] = None

    # Standard aliases for bridge
    res["battery_mv"] = res["bat"]
    res["queue_len"] = res["tx_queue_len"]
    res["noise_floor_dbm"] = res["noise_floor"]
    res["errors"] = res["recv_errors"] or 0
    res["uptime_secs"] = res["uptime"]

    return res


# Legacy alias
parse_telemetry_from_sdk = parse_status_response


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
        if header.packet_type == PacketType.TELEMETRY_RESPONSE:
            payload = TelemetryPayload.unpack(payload_data)
        elif header.packet_type == PacketType.CHANNEL_MSG_RECV:
            payload = TextMessagePayload.unpack(payload_data)
        elif header.packet_type == PacketType.CONTACT:
            payload = NodeAdvertisement.unpack(payload_data)
        elif header.packet_type == PacketType.ACK:
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
            "event_type": self.header.packet_type.name,
            "packet_type": int(self.header.packet_type),
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

_DEPRECATED_ALIASES: dict[str, str] = {
    "OpCode": "PacketType",
    "FirmwareCommandType": "CommandType", 
    "FirmwarePushCode": "PacketType",
}

def __getattr__(name: str) -> Any:
    """Provide deprecated aliases with runtime warnings."""
    if name in _DEPRECATED_ALIASES:
        import warnings
        canonical = _DEPRECATED_ALIASES[name]
        warnings.warn(
            f"{name} is deprecated, use {canonical} instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return globals()[canonical]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

