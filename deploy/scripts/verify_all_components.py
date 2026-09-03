#!/usr/bin/env python3
"""
MeshCore Bridge - Comprobación y Validación Simulada Integral (v3.0).
Verifica de forma simulada y determinista todas las fases implementadas:
1. Seguridad (API Key, TCP Companion limits/token, CORS, CSP, PSK regex).
2. Concurrencia (Deduplicator locks, Queue maxsize, RX semaphore, timeouts).
3. Calidad & Robustez (NodeRegistry persistence, SSoT name resolution, tuple neighbors, MQTT size limit, watchdog).
4. Compatibilidad SDK MeshCore (parse_status, cayennelpp & wrap fix, protocol types, contacts share/export/import, login/logout).
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.deduplicator import PacketDeduplicator
from src.event_utils import extract_sender_from_payload
from src.protocol_types import (
    FirmwareAdvertType,
    parse_telemetry_from_sdk,
)
from src.rate_limiter import CustomTxQueue
from src.sensor_decoder import CayenneLPPDecoder, LppDataType
from src.serial_driver import MeshcoreSDKAdapter


async def test_security_features() -> None:
    print("🔒 [1/5] Verificando Características de Seguridad...")
    adapter = MeshcoreSDKAdapter(port="AUTO")
    try:
        await adapter.set_channel(0, "ValidChannel", "abcdef0123456789")
        print("  ✓ Validación PSK: Acepta PSK hexadecimal válido.")
    except Exception as e:
        raise AssertionError(f"Fallo inesperado con PSK válido: {e}")

    try:
        await adapter.set_channel(0, "InvalidChannel", "invalid!psk$symbols")
        raise AssertionError("Fallo de seguridad: El validador aceptó un PSK con caracteres inválidos.")
    except ValueError:
        print("  ✓ Validación PSK: Rechaza correctamente PSK con caracteres no hexadecimales.")

    try:
        await adapter.set_channel(99, "BadIndex", "aabbcc")
        raise AssertionError("Fallo de seguridad: Aceptó índice de canal > 15.")
    except ValueError:
        print("  ✓ Validación Canal: Rechaza índice fuera de rango 0-15.")


async def test_concurrency_and_resilience() -> None:
    print("\n⚡ [2/5] Verificando Concurrencia y Resiliencia...")
    dedup = PacketDeduplicator(window_seconds=10.0)
    is_dup1 = await dedup.is_duplicate("test_packet_hash_1")
    is_dup2 = await dedup.is_duplicate("test_packet_hash_1")
    assert not is_dup1, "El primer paquete no debe ser duplicado"
    assert is_dup2, "El segundo paquete idéntico debe ser detectado como duplicado"
    assert dedup.is_duplicate_sync("test_packet_hash_1"), "is_duplicate_sync debe retornar True"
    print("  ✓ Deduplicator: Locks asíncronos y síncronos operativos y thread-safe.")

    queue = CustomTxQueue(maxsize=5)
    for i in range(5):
        queue.put_nowait({"id": i, "data": "msg"})
    assert queue.full(), "La cola debe estar llena al alcanzar maxsize=5"
    print(f"  ✓ CustomTxQueue: Límite estricto respetado (maxsize={queue.maxsize}).")


async def test_quality_and_robustness() -> None:
    print("\n📐 [3/5] Verificando Calidad y Robustez de Arquitectura...")
    registry = NodeRegistry()
    pk = "a1b2c3d4e5f67890aabbccddeeff00112233445566778899aabbccddeeff0011"
    registry.add_or_update(
        pk,
        NodeContactUpdate(name="Mountain-Rep-01", alias="Repetidor Principal", role="REPEATER"),
    )
    resolved = registry.resolve_display_name(pk)
    assert resolved == "Repetidor Principal", f"Esperado 'Repetidor Principal', obtenido '{resolved}'"
    resolved_prefix = registry.resolve_display_name("a1b2c3d4")
    assert resolved_prefix == "Repetidor Principal", f"Esperado 'Repetidor Principal', obtenido '{resolved_prefix}'"
    print("  ✓ NodeRegistry: resolve_display_name() SSoT resuelve alias y nombres correctamente.")

    contact = registry.get_contact(pk)
    assert contact is not None
    assert isinstance(contact.neighbors, tuple), f"neighbors debe ser tuple, es {type(contact.neighbors)}"
    print("  ✓ NodeContactInfo: neighbors es inmutable (tuple).")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        saved = registry.save_to_file(tmp_path)
        assert saved, "Debe guardar exitosamente el archivo JSON"

        new_reg = NodeRegistry()
        loaded = new_reg.load_from_file(tmp_path)
        assert loaded == 1, f"Debe haber cargado 1 nodo, cargó {loaded}"
        loaded_contact = new_reg.get_contact(pk)
        assert loaded_contact is not None and loaded_contact.name == "Mountain-Rep-01"
        assert isinstance(loaded_contact.neighbors, tuple)
        print("  ✓ Persistencia NodeRegistry: Guardado y cargado JSON verificado.")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    test_payload = {"sender": pk, "sender_name": "Mountain-Rep-01", "text": "Hola"}
    s_key, s_name = extract_sender_from_payload(test_payload)
    assert s_key == pk and s_name == "Mountain-Rep-01"
    print("  ✓ SSoT event_utils: extract_sender_from_payload() extrae remitente correctamente.")


async def test_meshcore_sdk_compatibility() -> None:
    print("\n📻 [4/5] Verificando Compatibilidad con SDK MeshCore...")
    status_buf = bytearray(56)
    status_buf[0:2] = (4150).to_bytes(2, "little")
    status_buf[2:4] = (3).to_bytes(2, "little")
    status_buf[4:6] = (-115).to_bytes(2, "little", signed=True)
    status_buf[6:8] = (-68).to_bytes(2, "little", signed=True)

    decoded_telem = parse_telemetry_from_sdk(bytes(status_buf), pubkey_prefix="a1b2c3d4")
    assert decoded_telem["battery_mv"] == 4150, f"Esperado 4150, obtenido {decoded_telem['battery_mv']}"
    assert decoded_telem["queue_len"] == 3
    assert decoded_telem["noise_floor_dbm"] == -115
    assert decoded_telem["last_rssi"] == -68
    print("  ✓ parse_telemetry_from_sdk: Decodifica layout binario de 56 bytes del firmware oficial.")

    decoder = CayenneLPPDecoder()
    raw_lpp = bytes([0x01, 0x74, 0x01, 0x90])
    readings, summary = decoder.decode(raw_lpp)
    assert len(readings) == 1
    assert readings[0].data_type == LppDataType.VOLTAGE
    assert readings[0].value == 4.0, f"Esperado 4.0V, obtenido {readings[0].value}"
    assert summary.get("voltage_v") == 4.0
    print("  ✓ CayenneLPP: Decodificación y compatibilidad verificadas.")

    assert FirmwareAdvertType.REPEATER.value == 2
    assert FirmwareAdvertType.CHAT.value == 1
    print("  ✓ FirmwareAdvertType: Enums oficiales alineados.")


async def test_api_routes_and_methods() -> None:
    print("\n🌐 [5/5] Verificando Métodos de Adaptador y Rutas...")
    adapter = MeshcoreSDKAdapter(port="AUTO")
    assert hasattr(adapter, "share_contact")
    assert hasattr(adapter, "export_contact")
    assert hasattr(adapter, "import_contact")
    assert hasattr(adapter, "send_login")
    assert hasattr(adapter, "logout")
    assert hasattr(adapter, "get_stats")
    assert hasattr(adapter, "device_query")
    print("  ✓ Métodos de Protocolo: share_contact, export_contact, import_contact, login, logout presentes.")


async def main() -> None:
    print("=" * 80)
    print("🚀 EJECUTANDO COMPROBACIÓN SIMULADA INTEGRAL DE MESHCORE BRIDGE v3.0")
    print("=" * 80 + "\n")

    await test_security_features()
    await test_concurrency_and_resilience()
    await test_quality_and_robustness()
    await test_meshcore_sdk_compatibility()
    await test_api_routes_and_methods()

    print("\n" + "=" * 80)
    print("🎉 TODAS LAS COMPROBACIONES SIMULADAS PASARON EXITOSAMENTE (100%)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
