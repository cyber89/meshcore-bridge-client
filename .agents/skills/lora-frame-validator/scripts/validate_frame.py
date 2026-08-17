#!/usr/bin/env python3
"""
MeshCore & LoRa Frame Validator CLI.
Validador y calculador determinista de tramas binarias, framing (SOF/EOF/ESC) y algoritmos CRC.
Permite verificar tramas capturadas de hardware LoRa o sintetizadas por el bridge.
"""

import argparse
import binascii
import json
import re
import struct
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ================= Implementaciones de CRC =================

def crc16_ccitt(data: bytes, init: int = 0xFFFF, poly: int = 0x1021) -> int:
    """CRC-16-CCITT / XModem calculation."""
    crc = init
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

def crc16_ibm(data: bytes, init: int = 0x0000, poly: int = 0xA001) -> int:
    """CRC-16-IBM / Modbus (reflected)."""
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
    return crc & 0xFFFF

def crc32_ieee(data: bytes) -> int:
    """Standard CRC-32 IEEE 802.3."""
    return binascii.crc32(data) & 0xFFFFFFFF

def crc8_standard(data: bytes, init: int = 0x00, poly: int = 0x07) -> int:
    """CRC-8 standard."""
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc

def fletcher16(data: bytes) -> int:
    """Fletcher-16 Checksum."""
    sum1 = 0
    sum2 = 0
    for byte in data:
        sum1 = (sum1 + byte) % 255
        sum2 = (sum2 + sum1) % 255
    return (sum2 << 8) | sum1

def xor_checksum(data: bytes) -> int:
    """Simple 8-bit XOR checksum."""
    res = 0
    for byte in data:
        res ^= byte
    return res

CRC_ALGORITHMS = {
    "ccitt": ("CRC-16 CCITT (0x1021)", crc16_ccitt, 2),
    "ibm": ("CRC-16 IBM/Modbus (0x8005)", crc16_ibm, 2),
    "crc32": ("CRC-32 IEEE 802.3", crc32_ieee, 4),
    "crc8": ("CRC-8 (0x07)", crc8_standard, 1),
    "fletcher16": ("Fletcher-16", fletcher16, 2),
    "xor": ("8-bit XOR", xor_checksum, 1),
}


@dataclass
class FrameValidationResult:
    raw_hex: str
    raw_length_bytes: int
    sof_detected: Optional[str]
    eof_detected: Optional[str]
    is_framing_valid: bool
    unescaped_hex: str
    unescaped_length: int
    header_fields: Dict[str, Any]
    payload_hex: str
    payload_length: int
    calculated_crcs: Dict[str, str]
    embedded_crc_hex: Optional[str]
    crc_matches: Dict[str, bool]
    validation_status: str
    errors: List[str]


def parse_and_validate_frame(
    raw_bytes: bytes,
    sof_byte: Optional[int] = 0xAA,
    eof_byte: Optional[int] = 0x55,
    esc_byte: Optional[int] = 0x1B,
    crc_type: str = "ccitt",
    crc_endian: str = "big",
) -> FrameValidationResult:
    errors: List[str] = []
    sof_detected = None
    eof_detected = None
    is_framing_valid = True

    if len(raw_bytes) == 0:
        return FrameValidationResult(
            raw_hex="",
            raw_length_bytes=0,
            sof_detected=None,
            eof_detected=None,
            is_framing_valid=False,
            unescaped_hex="",
            unescaped_length=0,
            header_fields={},
            payload_hex="",
            payload_length=0,
            calculated_crcs={},
            embedded_crc_hex=None,
            crc_matches={},
            validation_status="EMPTY_FRAME",
            errors=["Trama vacía de longitud 0"],
        )

    # 1. Validar SOF y EOF si se especifican
    body = raw_bytes
    if sof_byte is not None:
        if raw_bytes[0] == sof_byte:
            sof_detected = f"0x{raw_bytes[0]:02X}"
            body = body[1:]
        else:
            errors.append(f"SOF inválido: esperado 0x{sof_byte:02X}, recibido 0x{raw_bytes[0]:02X}")
            is_framing_valid = False

    if eof_byte is not None and len(body) > 0:
        if body[-1] == eof_byte:
            eof_detected = f"0x{body[-1]:02X}"
            body = body[:-1]
        else:
            errors.append(f"EOF inválido: esperado 0x{eof_byte:02X}, recibido 0x{body[-1]:02X}")
            is_framing_valid = False

    # 2. Deshacer Byte Stuffing (Escaping)
    unescaped = bytearray()
    i = 0
    while i < len(body):
        b = body[i]
        if esc_byte is not None and b == esc_byte:
            i += 1
            if i < len(body):
                escaped_val = body[i]
                # En protocolo MeshCore / SLIP estándar: ESC + XOR 0x20 o ESC + mapped byte
                unescaped.append(escaped_val ^ 0x20 if escaped_val in (0x8A, 0x35, 0x3B) else escaped_val)
            else:
                errors.append("Secuencia de escape ESC truncada al final de la trama")
                is_framing_valid = False
        else:
            unescaped.append(b)
        i += 1

    unescaped_bytes = bytes(unescaped)
    unescaped_len = len(unescaped_bytes)

    # 3. Descomponer Header, Payload y CRC
    # Suponemos layout genérico de protocolo binario:
    # Header: [OpCode: 1B] [Seq: 1B] [SenderID: 2B] [DestID: 2B] [PayloadLen: 2B] = 8 Bytes
    header_fields: Dict[str, Any] = {}
    payload_hex = ""
    payload_len = 0
    embedded_crc_hex = None
    crc_matches: Dict[str, bool] = {}
    calculated_crcs: Dict[str, str] = {}

    crc_size = CRC_ALGORITHMS.get(crc_type, ("CRC", crc16_ccitt, 2))[2]

    if unescaped_len >= crc_size:
        data_to_crc = unescaped_bytes[:-crc_size]
        crc_embedded_bytes = unescaped_bytes[-crc_size:]
        embedded_crc_hex = crc_embedded_bytes.hex().upper()

        # Calcular todos los algoritmos disponibles
        for alg_key, (alg_name, fn, sz) in CRC_ALGORITHMS.items():
            calc_val = fn(data_to_crc)
            if sz == 1:
                calc_bytes = struct.pack(">B", calc_val)
                fmt_str = f"0x{calc_val:02X}"
            elif sz == 2:
                calc_bytes = struct.pack(">H" if crc_endian == "big" else "<H", calc_val)
                fmt_str = f"0x{calc_val:04X}"
            elif sz == 4:
                calc_bytes = struct.pack(">I" if crc_endian == "big" else "<I", calc_val)
                fmt_str = f"0x{calc_val:08X}"
            else:
                calc_bytes = b""
                fmt_str = f"{calc_val}"

            calculated_crcs[alg_name] = fmt_str
            if sz == crc_size:
                crc_matches[alg_name] = (calc_bytes == crc_embedded_bytes)

        # Parsear Header si hay al menos 4 bytes
        if len(data_to_crc) >= 4:
            opcode = data_to_crc[0]
            header_fields["opcode"] = f"0x{opcode:02X} ({opcode})"
            if len(data_to_crc) >= 8:
                seq = data_to_crc[1]
                src = int.from_bytes(data_to_crc[2:4], "little")
                dst = int.from_bytes(data_to_crc[4:6], "little")
                plen = int.from_bytes(data_to_crc[6:8], "little")
                header_fields["sequence"] = seq
                header_fields["source_node_id"] = f"0x{src:04X} ({src})"
                header_fields["dest_node_id"] = f"0x{dst:04X} ({dst})"
                header_fields["declared_payload_len"] = plen
                payload_data = data_to_crc[8:]
            else:
                payload_data = data_to_crc[1:]
            
            payload_hex = payload_data.hex().upper()
            payload_len = len(payload_data)
        else:
            payload_hex = data_to_crc.hex().upper()
            payload_len = len(data_to_crc)

    else:
        errors.append(f"Trama demasiado corta ({unescaped_len} B) para contener checksum de {crc_size} B")

    selected_alg_name = CRC_ALGORITHMS.get(crc_type, ("CRC-16 CCITT (0x1021)", None, 2))[0]
    is_crc_valid = crc_matches.get(selected_alg_name, False)

    if not is_framing_valid:
        status = "FRAMING_ERROR"
    elif not is_crc_valid and embedded_crc_hex is not None:
        status = "CRC_MISMATCH"
    elif errors:
        status = "MALFORMED_PACKET"
    else:
        status = "VALID"

    return FrameValidationResult(
        raw_hex=raw_bytes.hex().upper(),
        raw_length_bytes=len(raw_bytes),
        sof_detected=sof_detected,
        eof_detected=eof_detected,
        is_framing_valid=is_framing_valid,
        unescaped_hex=unescaped_bytes.hex().upper(),
        unescaped_length=unescaped_len,
        header_fields=header_fields,
        payload_hex=payload_hex,
        payload_length=payload_len,
        calculated_crcs=calculated_crcs,
        embedded_crc_hex=embedded_crc_hex,
        crc_matches=crc_matches,
        validation_status=status,
        errors=errors,
    )


def format_validation_report(res: FrameValidationResult) -> str:
    lines = [
        "===========================================================",
        f" [TRAMA LORA/UART] ESTADO: {res.validation_status}",
        "===========================================================",
        f"• Longitud Raw:       {res.raw_length_bytes} Bytes",
        f"• Hex Raw:            {res.raw_hex}",
        f"• SOF / EOF:          {res.sof_detected or 'Ninguno'} / {res.eof_detected or 'Ninguno'}",
        f"• Framing Válido:     {'SÍ' if res.is_framing_valid else 'NO'}",
        f"• Longitud Unescaped: {res.unescaped_length} Bytes",
        f"• Hex Unescaped:      {res.unescaped_hex}",
    ]

    if res.header_fields:
        lines.append("\n[Campos de Cabecera]")
        for k, v in res.header_fields.items():
            lines.append(f"  - {k}: {v}")

    lines.append(f"\n[Payload]")
    lines.append(f"  - Longitud: {res.payload_length} Bytes")
    lines.append(f"  - Hex:      {res.payload_hex or '(vacío)'}")

    lines.append("\n[Análisis de Checksum & CRC]")
    lines.append(f"  - CRC Embebido en Trama: 0x{res.embedded_crc_hex or 'N/A'}")
    for alg, calc_val in res.calculated_crcs.items():
        match_str = ""
        if alg in res.crc_matches:
            match_str = " -> [COINCIDE]" if res.crc_matches[alg] else " -> [DISCREPANCIA]"
        lines.append(f"  - {alg:<28}: {calc_val}{match_str}")

    if res.errors:
        lines.append("\n[Errores Detectados]")
        for err in res.errors:
            lines.append(f"  ❌ {err}")

    lines.append("===========================================================")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="MeshCore & LoRa Frame and CRC Validator")
    parser.add_argument("--hex", type=str, help="Cadena hexadecimal de la trama (ej: AA01020355)")
    parser.add_argument("--file", type=str, help="Archivo binario o de texto con tramas a inspeccionar")
    parser.add_argument("--sof", type=str, default="AA", help="Byte SOF en hex (default: AA, 'none' para desactivar)")
    parser.add_argument("--eof", type=str, default="55", help="Byte EOF en hex (default: 55, 'none' para desactivar)")
    parser.add_argument("--esc", type=str, default="1B", help="Byte ESC en hex (default: 1B, 'none' para desactivar)")
    parser.add_argument("--crc-type", choices=list(CRC_ALGORITHMS.keys()), default="ccitt", help="Algoritmo de CRC")
    parser.add_argument("--crc-endian", choices=["big", "little"], default="big", help="Endianness del CRC")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Formato de salida")

    args = parser.parse_args()

    sof_val = None if args.sof.lower() == "none" else int(args.sof, 16)
    eof_val = None if args.eof.lower() == "none" else int(args.eof, 16)
    esc_val = None if args.esc.lower() == "none" else int(args.esc, 16)

    if args.hex:
        clean_hex = args.hex.replace(" ", "").replace("0x", "")
        raw_bytes = bytes.fromhex(clean_hex)
    elif args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"Error: Archivo {args.file} no existe.", file=sys.stderr)
            sys.exit(1)
        content = p.read_bytes()
        # Si es texto ASCII hex
        try:
            text = content.decode("utf-8").strip()
            clean_hex = re.sub(r"[^A-Fa-f0-9]", "", text)
            raw_bytes = bytes.fromhex(clean_hex)
        except Exception:
            raw_bytes = content
    else:
        print("Uso: Debe proporcionar --hex '<cadena>' o --file '<archivo>'")
        sys.exit(1)

    result = parse_and_validate_frame(
        raw_bytes=raw_bytes,
        sof_byte=sof_val,
        eof_byte=eof_val,
        esc_byte=esc_val,
        crc_type=args.crc_type,
        crc_endian=args.crc_endian,
    )

    if args.format == "json":
        print(json.dumps(asdict(result), indent=2))
    else:
        print(format_validation_report(result))

if __name__ == "__main__":
    main()
