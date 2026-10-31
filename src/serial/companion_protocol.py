"""
companion_protocol.py: Constantes de protocolo, tablas binarias y validación de layouts Companion de MeshCore.
"""

from __future__ import annotations

import logging
from typing import Any

from src.protocol_types import normalize_tx_power, redact_command_str

# Firmware BaseChatMesh.h: MAX_TEXT_LEN = 10 * CIPHER_BLOCK_SIZE (16).
MAX_TEXT_BYTES = 160
# Firmware stores channel names in char[32], with a trailing NUL.
MAX_CHANNEL_NAME_BYTES = 31
# Firmware Companion NodePrefs.h: char wifi_ssid[33], char wifi_pwd[64].
MAX_WIFI_SSID_BYTES = 32
MAX_WIFI_PASSWORD_BYTES = 63

# Verified local NodePrefs getters: no RF request, setter or wifi.pwd is accepted here.
_FIRMWARE_READ_COMMANDS = (
    "get radio",
    "get freq",
    "get cad",
    "get radio.rxgain",
    "get path.hash.mode",
    "get wifi.ssid",
    "get wifi.enabled",
    "get wifi.status",
    "get wifi.ip",
)

# Companion MyMesh.cpp command branches, not a numeric range: new firmware
# opcodes require classification before the TCP proxy can forward them.
_COMPANION_RF_COMMANDS = frozenset({2, 3, 7, 16, 25, 26, 27, 36, 50, 52, 55, 57, 62, 65})
_COMPANION_LOCAL_COMMANDS = frozenset(
    {
        1,
        4,
        5,
        6,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
        28,
        29,
        30,
        31,
        32,
        33,
        34,
        35,
        37,
        38,
        40,
        41,
        42,
        43,
        51,
        54,
        56,
        58,
        59,
        60,
        61,
        63,
        64,
    }
)

# Mandatory bytes read by Companion MyMesh.cpp::handleCmdFrame and
# updateContactFromFrame, cross-checked with meshcore_py/commands encoders.
# Optional trailing fields remain optional. The contact path slot is 64 bytes.
_COMPANION_MIN_LENGTHS = {
    1: 8,
    2: 14,
    3: 7,
    4: 1,
    5: 1,
    6: 5,
    7: 1,
    8: 2,
    9: 136,
    10: 1,
    11: 11,
    12: 2,
    13: 33,
    14: 9,
    15: 33,
    16: 33,
    17: 1,
    18: 99,
    19: 7,
    20: 1,
    21: 9,
    22: 2,
    23: 1,
    24: 65,
    25: 6,
    26: 33,
    27: 33,
    28: 33,
    29: 33,
    30: 33,
    31: 2,
    32: 50,
    33: 1,
    34: 2,
    35: 1,
    36: 11,
    37: 5,
    38: 2,
    39: 4,
    40: 1,
    41: 4,
    42: 34,
    43: 1,
    50: 34,
    51: 6,
    52: 34,
    54: 2,
    55: 2,
    56: 2,
    57: 34,
    58: 2,
    59: 1,
    60: 1,
    61: 3,
    62: 5,
    63: 1,
    64: 1,
    65: 4,
    66: 3,
}

# Terminal synchronous response codes from Companion MyMesh.cpp.
_RAW_OK_COMMANDS = (
    3,
    6,
    7,
    8,
    9,
    11,
    12,
    13,
    14,
    15,
    16,
    18,
    21,
    24,
    25,
    28,
    29,
    32,
    34,
    37,
    38,
    41,
    51,
    54,
    55,
    58,
    61,
    62,
    63,
    65,
)
_RAW_REPLY_TYPES: dict[int, frozenset[int]] = {
    **{opcode: frozenset({0}) for opcode in _RAW_OK_COMMANDS},
    1: frozenset({5}),  # APP_START -> SELF_INFO
    2: frozenset({6}),  # SEND_TXT_MSG -> SENT (not delivery ACK)
    4: frozenset({4}),  # GET_CONTACTS -> END_OF_CONTACTS
    5: frozenset({9}),  # GET_DEVICE_TIME -> CURR_TIME
    10: frozenset({7, 8, 10, 16, 17}),  # SYNC_NEXT_MESSAGE
    17: frozenset({11}),  # EXPORT_CONTACT
    20: frozenset({12}),  # GET_BATT_AND_STORAGE
    22: frozenset({13}),  # DEVICE_QUERY
    23: frozenset({14}),  # EXPORT_PRIVATE_KEY
    26: frozenset({6}),  # SEND_LOGIN
    27: frozenset({6}),  # SEND_STATUS_REQ
    30: frozenset({3}),  # GET_CONTACT_BY_KEY
    31: frozenset({18}),  # GET_CHANNEL
    33: frozenset({19}),  # SIGN_START
    35: frozenset({20}),  # SIGN_FINISH
    36: frozenset({6}),  # SEND_TRACE_PATH
    39: frozenset({6}),  # Remote SEND_TELEMETRY_REQ; self telemetry is a push.
    40: frozenset({21}),  # GET_CUSTOM_VARS
    42: frozenset({22}),  # GET_ADVERT_PATH
    43: frozenset({23}),  # GET_TUNING_PARAMS
    50: frozenset({6}),  # SEND_BINARY_REQ
    52: frozenset({6}),  # SEND_PATH_DISCOVERY_REQ
    56: frozenset({24}),  # GET_STATS
    57: frozenset({6}),  # SEND_ANON_REQ
    59: frozenset({25}),  # GET_AUTOADD_CONFIG
    60: frozenset({26}),  # GET_ALLOWED_REPEAT_FREQ
    64: frozenset({28}),  # GET_DEFAULT_FLOOD_SCOPE
    66: frozenset({29}),  # RUN_CLI_COMMAND (v14+) -> CLI_REPLY, never generic OK.
}


def _companion_path_size(encoded: int) -> int | None:
    """MeshCore Packet::isValidPathLen/writePath: 1/2/3-byte hashes, 64-byte slot."""
    width = (encoded >> 6) + 1
    size = (encoded & 0x3F) * width
    return size if width != 4 and size <= 64 else None


def _complete_companion_rf_packet(
    payload: bytes, offset: int, *, allow_empty: bool = False
) -> bool:
    """Check Packet::readFrom's declared path before firmware memcpy reads it."""
    if len(payload) <= offset:
        return False
    path_offset = offset + (5 if (payload[offset] & 0x03) in (0, 3) else 1)
    if len(payload) <= path_offset:
        return False
    path_size = _companion_path_size(payload[path_offset])
    if path_size is None:
        return False
    body_offset = path_offset + 1 + path_size
    return len(payload) >= body_offset if allow_empty else len(payload) > body_offset


def _companion_layout_complete(payload: bytes) -> bool:
    opcode = payload[0]
    minimum = _COMPANION_MIN_LENGTHS.get(opcode)
    if minimum is None or len(payload) < minimum:
        return False
    if opcode == 19:
        return payload[1:7] == b"reboot"
    if opcode == 51:
        return payload[1:6] == b"reset"
    if opcode == 25:
        return payload[1] < 0x80 and len(payload) >= 2 + payload[1] + 4
    if opcode == 62:
        path_size = 0 if payload[2] == 0xFF else _companion_path_size(payload[2])
        return path_size is not None and len(payload) >= 3 + path_size + 2
    if opcode in (18, 65):
        return _complete_companion_rf_packet(
            payload, 1 if opcode == 18 else 2, allow_empty=opcode == 65
        )
    if opcode == 63 and len(payload) >= 48:
        return b"\x00" in payload[1:32]
    return True


def companion_command_kind(payload: bytes) -> str | None:
    """Classify supported Companion commands by RF side effects."""
    if not payload or not _companion_layout_complete(payload):
        return None
    opcode = payload[0]
    if opcode in _COMPANION_RF_COMMANDS:
        return "rf"
    if opcode in _COMPANION_LOCAL_COMMANDS:
        return "local"
    if opcode == 39:
        return "local" if len(payload) == 4 else ("rf" if len(payload) >= 36 else None)
    if opcode == 66:
        try:
            command = payload[1:].decode("ascii")
        except UnicodeDecodeError:
            return None
        return "local" if command in _FIRMWARE_READ_COMMANDS else None
    return None


class _MeshcoreLogRedactionFilter(logging.Filter):
    """Redact sensitive CLI commands and packet payloads logged by meshcore_py."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            raw_msg = record.getMessage()
            redacted = redact_command_str(raw_msg)
            if redacted != raw_msg:
                record.msg = redacted
                record.args = ()
        except Exception:
            pass
        return True


def ensure_meshcore_log_redaction() -> None:
    sdk_logger = logging.getLogger("meshcore")
    if not any(isinstance(flt, _MeshcoreLogRedactionFilter) for flt in sdk_logger.filters):
        sdk_logger.addFilter(_MeshcoreLogRedactionFilter())


def safe_truncate_utf8(text: str, max_bytes: int = 32) -> str:
    """Trunca una cadena asegurando que su codificación UTF-8 no exceda max_bytes."""
    raw = str(text or "").encode("utf-8")
    if len(raw) <= max_bytes:
        return str(text or "")
    return raw[:max_bytes].decode("utf-8", "ignore")


def copy_self_info_snapshot(info: dict[str, Any]) -> dict[str, Any]:
    """Normalize observed fields without modifying a private SDK payload."""
    snapshot = dict(info)
    if "tx_power" in snapshot:
        power = normalize_tx_power(snapshot["tx_power"])
        if power is not None or snapshot["tx_power"] is None:
            snapshot["tx_power"] = power
        else:
            snapshot.pop("tx_power")
    return snapshot


def is_raw_chat_permitted(
    data: bytes,
    self_info: dict[str, Any] | None,
    node_registry: Any,
    contacts_provider: Any = None,
) -> bool:
    """Keep the same local identity and infrastructure guards on the raw path."""
    if data[0] == 2:
        if len(data) < 14:
            return False
        prefix = data[7:13].hex()
        local = str((self_info or {}).get("public_key", "")).lower()
        if local and local.startswith(prefix):
            return False
        if node_registry and node_registry.is_local_key(prefix):
            return False
        # MeshCore text type 1 is administrative CLI, not user chat.
        if data[1] != 1:
            if node_registry and node_registry.is_repeater_key(prefix):
                return False
            contacts = contacts_provider() if callable(contacts_provider) else contacts_provider
            if isinstance(contacts, dict):
                for key, contact in contacts.items():
                    if str(key).lower().startswith(prefix) and isinstance(contact, dict):
                        if int(contact.get("type", -1)) == 2:
                            return False
        text = data[13:]
    elif data[0] == 3:
        if len(data) < 8:
            return False
        text = data[7:]
        name = str((self_info or {}).get("name", ""))
        if len(text) + len((name + ": ").encode("utf-8")) > MAX_TEXT_BYTES:
            return False
    else:
        return True
    return b"\x00" not in text and len(text) <= MAX_TEXT_BYTES
