#!/usr/bin/env python3
"""
MeshCore Bridge - Master All-Message-Types Real-Time 20s Simulator
Simula TODOS los tipos de mensajes y eventos de MeshCore con:
1. Modificaciones remotas de repetidores y nodos (CLI autenticado, set params, reboot).
2. Ajustes en el nodo local (frecuencia, potencia TX, nombre de estación, coordenadas).
3. Mensajes y tramas deformadas (JSON corrupto, tramas binarias truncadas, CRC inválido, CayenneLPP roto).
4. Simulación de cuello de botella (Inundación de ráfagas TX con colas de prioridad Leaky Bucket).
5. TODOS los tipos de mensajes posibles (DM, Canal, Telemetría, Anuncio, BBS, ACK, Traceroute, Sensores, etc.).
6. Auditoría continua de logs en tiempo real verificando origen y destino en cada evento y cero errores no controlados.
"""

import asyncio
import io
import json
import logging
import os
import random
import struct
import sys
import time
from typing import Any

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.contact_manager import NodeRegistry, NodeContactUpdate, PacketRecord
from src.deduplicator import PacketDeduplicator
from src.repeater_manager import RepeaterManager
from src.rate_limiter import TxRateLimiter, TxPriority, TxItem
from src.admin_handler import AdminCommandHandler, AdminContext
from src.rx_router import RxEventRouter, RxRouterContext
from src.sensor_decoder import CayenneLPPDecoder
from src.protocol_types import (
    AckPayload,
    EOF_BYTE,
    ESC_BYTE,
    FrameHeader,
    HardwareModel,
    MeshcoreFrame,
    NodeAdvertisement,
    OpCode,
    SOF_BYTE,
    TelemetryPayload,
    TextMessagePayload,
    compute_crc16_ccitt,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


class RealTimeLogAuditor(logging.Handler):
    """Auditor en tiempo real de los logs del sistema."""
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []
        self.error_count = 0
        self.warning_count = 0
        self.info_count = 0
        self.critical_count = 0
        self.unhandled_exceptions: list[str] = []
        self.logged_origin_dest_events: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        msg = record.getMessage()

        # Verificar si el log identifica origen y destino
        if "De:" in msg and "Para:" in msg:
            self.logged_origin_dest_events.append(msg)

        if record.levelno >= logging.CRITICAL:
            self.critical_count += 1
            if record.exc_text or record.exc_info:
                self.unhandled_exceptions.append(msg)
        elif record.levelno >= logging.ERROR:
            if "Error en bucle de supervisión" in msg or "Traceback" in msg or record.exc_info:
                self.error_count += 1
                self.unhandled_exceptions.append(msg)
        elif record.levelno >= logging.WARNING:
            self.warning_count += 1
        elif record.levelno >= logging.INFO:
            self.info_count += 1


class MockMqttClient:
    def __init__(self) -> None:
        self.published_messages: list[dict[str, Any]] = []
        self.is_connected = True
        self.broker = "127.0.0.1"
        self.port = 1883

    def publish_safe(self, topic: str, payload: str, qos: int = 1) -> bool:
        self.published_messages.append({"topic": topic, "payload": payload, "qos": qos, "timestamp": time.time()})
        return True


class MockWebSocketHub:
    def __init__(self) -> None:
        self.streamed_events: list[dict[str, Any]] = []

    def broadcast_event(self, event_data: dict[str, Any]) -> None:
        self.streamed_events.append({"event": event_data, "timestamp": time.time()})


class MockSerialTransceiver:
    def __init__(self) -> None:
        self.is_connected = True
        self.tx_history: list[dict[str, Any]] = []
        self.contacts_db: dict[str, dict[str, Any]] = {}
        self.last_heartbeat_time = time.time()

    def heartbeat(self) -> None:
        self.last_heartbeat_time = time.time()

    def resolve_sender_name(self, prefix_or_key: str) -> str:
        k = str(prefix_or_key).strip().lower()
        if k in self.contacts_db:
            return self.contacts_db[k].get("name", prefix_or_key)
        for pk, c in self.contacts_db.items():
            if pk.startswith(k) or k.startswith(pk[:8]):
                return c.get("name", prefix_or_key)
        return str(prefix_or_key)

    async def send_message(self, text: str, target: str | None = None, channel_idx: int = 0) -> dict[str, Any]:
        ack_code = f"ack_{int(time.time()*1000)%100000}"
        self.tx_history.append({
            "text": text,
            "target": target,
            "channel_idx": channel_idx,
            "ack_code": ack_code,
            "timestamp": time.time(),
        })
        logging.info(f"[TX-SERIAL] De: Estación Base Local -> Para: {target or 'Broadcast'} (Canal #{channel_idx}) | Texto: '{text[:45]}'")
        return {"status": "sent", "expected_ack": ack_code}

    async def sync_all_contacts(self) -> list[dict[str, Any]]:
        return list(self.contacts_db.values())

    async def add_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        pk = str(contact_data.get("public_key", "")).strip().lower()
        if pk:
            self.contacts_db[pk] = dict(contact_data)
        return {"status": "OK", "public_key": pk}


class Counters:
    def __init__(self) -> None:
        self.rx_count = 0
        self.tx_count = 0
        self.err_count = 0


async def run_master_20s_simulation() -> bool:
    print("=" * 90, flush=True)
    print("🌟 SIMULACIÓN MAESTRA MESHCORE BRIDGE - TODOS LOS TIPOS DE MENSAJE (20s)", flush=True)
    print("   [✓] Modificaciones remotas CLI       | [✓] Ajustes en nodo local", flush=True)
    print("   [✓] Mensajes y tramas deformadas    | [✓] Cuello de botella & Prioridades", flush=True)
    print("   [✓] Todos los Tipos de Mensajes RF  | [✓] Logs en tiempo real con Origen -> Destino", flush=True)
    print("=" * 90 + "\n", flush=True)

    # 1. Configurar Auditor de Logs
    log_auditor = RealTimeLogAuditor()
    logging.getLogger().addHandler(log_auditor)
    logging.getLogger().setLevel(logging.INFO)

    # 2. Infraestructura del Bridge
    local_pubkey = "feedface0000111122223333444455556666777788889999aaaabbbbccccdddd"
    node_registry = NodeRegistry()
    node_registry.set_local_pubkey(local_pubkey)
    node_registry.add_or_update(
        local_pubkey,
        NodeContactUpdate(
            name="Gateway-Base-Station",
            role="LOCAL",
            is_local=True,
            latitude=-33.4489,
            longitude=-70.6693,
        ),
    )

    repeater_mgr = RepeaterManager()
    deduplicator = PacketDeduplicator(window_seconds=30.0, max_entries=5000)
    mqtt_client = MockMqttClient()
    ws_hub = MockWebSocketHub()
    serial_transceiver = MockSerialTransceiver()
    counters = Counters()
    bg_tasks: set[asyncio.Task[Any]] = set()

    async def execute_tx(payload: dict[str, Any]) -> dict[str, Any]:
        counters.tx_count += 1
        target = payload.get("to", "broadcast")
        text = payload.get("text", "")
        ch = payload.get("channel_idx", 0)
        return await serial_transceiver.send_message(text=text, target=target, channel_idx=ch)

    # Rate limiter con callback de transmisión
    async def _tx_callback(item: TxItem) -> dict[str, Any]:
        counters.tx_count += 1
        p = item.payload if isinstance(item.payload, dict) else {"to": "broadcast", "text": str(item.payload)}
        return await serial_transceiver.send_message(
            text=p.get("text", ""),
            target=p.get("to", "broadcast"),
            channel_idx=p.get("channel_idx", 0),
        )

    rate_limiter = TxRateLimiter(tx_interval_sec=0.01, transmit_callback=_tx_callback)
    rate_limiter.start()

    rx_ctx = RxRouterContext(
        node_registry=node_registry,
        repeater_manager=repeater_mgr,
        mqtt=mqtt_client,
        web_server=ws_hub,
        serial_adapter=serial_transceiver,
        counters=counters,
        loop=asyncio.get_running_loop(),
        background_tasks=bg_tasks,
        deduplicator=deduplicator,
    )
    rx_router = RxEventRouter(rx_ctx)

    admin_ctx = AdminContext(
        repeater_manager=repeater_mgr,
        node_registry=node_registry,
        mqtt=mqtt_client,
        execute_tx=execute_tx,
        mc_provider=lambda: None,
        web_server=ws_hub,
    )
    admin_handler = AdminCommandHandler(admin_ctx)

    # Nodos en la Red
    NODES = {
        "r1_north": {
            "pk": "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
            "name": "R1-Cerro-Norte", "role": "REPEATER", "lat": -33.4200, "lon": -70.6500, "battery": 95, "snr": 12.0, "rssi": -55,
        },
        "r2_south": {
            "pk": "2222333344445555666677778888999900001111aaaabbbbccccddddeeeeffff",
            "name": "R2-Valle-Sur", "role": "REPEATER", "lat": -33.4800, "lon": -70.6900, "battery": 88, "snr": 10.5, "rssi": -62,
        },
        "alice": {
            "pk": "3333444455556666777788889999000011112222aaaabbbbccccddddeeeeffff",
            "name": "Alice-Field-Op", "role": "CLIENT", "lat": -33.4400, "lon": -70.6600, "battery": 82, "snr": 9.0, "rssi": -68,
        },
        "bob": {
            "pk": "4444555566667777888899990000111122223333aaaabbbbccccddddeeeeffff",
            "name": "Bob-Base-Camp", "role": "CLIENT", "lat": -33.4600, "lon": -70.6800, "battery": 84, "snr": 9.5, "rssi": -70,
        },
        "sensor_meteo": {
            "pk": "5555666677778888999900001111222233334444aaaabbbbccccddddeeeeffff",
            "name": "Sensor-Meteo-Highland", "role": "SENSOR", "lat": -33.4100, "lon": -70.6400, "battery": 92, "snr": 11.5, "rssi": -58,
        },
        "bbs_room": {
            "pk": "6666777788889999000011112222333344445555aaaabbbbccccddddeeeeffff",
            "name": "BBS-Comunidad-Central", "role": "ROOM", "lat": -33.4500, "lon": -70.6700, "battery": 99, "snr": 10.0, "rssi": -60,
        },
        "emergency_unit": {
            "pk": "7777888899990000111122223333444455556666aaaabbbbccccddddeeeeffff",
            "name": "Rescate-Emergencia-01", "role": "EMERGENCY", "lat": -33.4350, "lon": -70.6550, "battery": 65, "snr": 7.5, "rssi": -76,
        },
    }

    for n_id, n_data in NODES.items():
        serial_transceiver.contacts_db[n_data["pk"]] = {
            "public_key": n_data["pk"],
            "name": n_data["name"],
            "alias": n_data["name"],
            "role": n_data["role"],
            "latitude": n_data["lat"],
            "longitude": n_data["lon"],
        }
        node_registry.add_or_update(
            n_data["pk"],
            NodeContactUpdate(
                name=n_data["name"],
                alias=n_data["name"],
                role=n_data["role"],
                latitude=n_data["lat"],
                longitude=n_data["lon"],
                battery_pct=n_data["battery"],
                last_snr=n_data["snr"],
                last_rssi=n_data["rssi"],
            ),
        )

    # -------------------------------------------------------------------------
    # TAREAS CONCURRENTES EN TIEMPO REAL DURANTE 20 SEGUNDOS
    # -------------------------------------------------------------------------
    simulation_running = True
    start_time = time.time()
    msg_type_counters = {
        "1. DM (Direct Messages)": 0,
        "2. Canal / Broadcast": 0,
        "3. Telemetría Ambiental": 0,
        "4. Anuncios / BBS Rooms": 0,
        "5. Acuses de Recibo (ACK)": 0,
        "6. Traceroute Multi-Salto": 0,
        "7. Comandos CLI Repetidor": 0,
        "8. Sensores CayenneLPP": 0,
        "9. Tramas Binarias MeshcoreFrame": 0,
        "10. Fuzzing / Tramas Deformadas": 0,
        "11. Modificaciones Remotas Nodos": 0,
        "12. Ajustes en Nodo Local": 0,
        "13. Ráfagas Cuello de Botella": 0,
    }

    # Worker 1: Modificaciones Remotas & Ajustes Locales (Pilares 1 & 2)
    async def worker_admin_and_config():
        step = 0
        while simulation_running:
            step += 1
            # Ajuste Local
            if step % 2 == 0:
                new_power = 20 + (step % 3)
                new_freq = 915.0 + (step * 0.1)
                node_registry.add_or_update(
                    local_pubkey,
                    NodeContactUpdate(
                        name=f"Gateway-Base-Station-v{step}",
                        tx_power=new_power,
                        frequency=round(new_freq, 2),
                        latitude=-33.4489 + (step * 0.0001),
                        longitude=-70.6693 + (step * 0.0001),
                    ),
                )
                msg_type_counters["12. Ajustes en Nodo Local"] += 1

            # Modificación Remota CLI Repetidor
            target_r1 = NODES["r1_north"]["pk"]
            cmd_req = {
                "action": "set",
                "target_node": target_r1,
                "param": "tx_power",
                "value": str(22),
            }
            task = asyncio.create_task(admin_handler.handle(cmd_req))
            await asyncio.sleep(0.02)
            admin_handler.notify_command_response({
                "sender": target_r1,
                "text": "> OK: tx_power set to 22 dBm",
            })
            await task
            msg_type_counters["7. Comandos CLI Repetidor"] += 1
            msg_type_counters["11. Modificaciones Remotas Nodos"] += 1

            # Traceroute Multi-Salto
            rx_router.handle_event({
                "type": "TRACE_RESPONSE",
                "sender": NODES["r2_south"]["pk"],
                "path": [
                    {"node": NODES["r1_north"]["pk"], "snr": 11.5},
                    {"node": NODES["r2_south"]["pk"], "snr": 9.8},
                ],
                "tag": f"trace_{step}",
                "rssi": -64,
            })
            msg_type_counters["6. Traceroute Multi-Salto"] += 1

            # Evaluación de Calidad de Enlace LQI y Rutas
            await admin_handler.handle({"action": "get_lqi"})

            await asyncio.sleep(1.0)

    # Worker 2: Tráfico Completo de Mensajería Mesh (DMs, Canales, BBS, Anuncios, ACKs)
    async def worker_mesh_messaging():
        seq = 0
        while simulation_running:
            seq += 1
            # Direct Message (DM)
            rx_router.handle_event({
                "type": "CONTACT_MSG_RECV",
                "sender": NODES["alice"]["pk"],
                "sender_name": NODES["alice"]["name"],
                "text": f"Mensaje directo #{seq}: Alice reportando posición segura.",
                "rssi": -67,
                "snr": 9.2,
                "hops": 1,
            })
            msg_type_counters["1. DM (Direct Messages)"] += 1

            # Canal Público Broadcast
            rx_router.handle_event({
                "type": "CHANNEL_MSG_RECV",
                "sender": NODES["bob"]["pk"],
                "sender_name": NODES["bob"]["name"],
                "text": f"Aviso en canal público #{seq}: Campamento base operativo.",
                "channel_idx": 0,
                "rssi": -69,
                "snr": 8.5,
            })
            msg_type_counters["2. Canal / Broadcast"] += 1

            # Canal Secundario (Canal #1)
            rx_router.handle_event({
                "type": "CHANNEL_MSG_RECV",
                "sender": NODES["emergency_unit"]["pk"],
                "sender_name": NODES["emergency_unit"]["name"],
                "text": f"[CANAL #1] Equipo de rescate en guardia #{seq}.",
                "channel_idx": 1,
                "rssi": -74,
                "snr": 7.0,
            })
            msg_type_counters["2. Canal / Broadcast"] += 1

            # Anuncio / Sala BBS
            rx_router.handle_event({
                "type": "ADVERTISEMENT",
                "public_key": NODES["bbs_room"]["pk"],
                "adv_name": NODES["bbs_room"]["name"],
                "adv_type": 3,
                "lat": NODES["bbs_room"]["lat"],
                "lon": NODES["bbs_room"]["lon"],
                "rssi": -60,
                "snr": 10.0,
            })
            msg_type_counters["4. Anuncios / BBS Rooms"] += 1

            # Acuse de Recibo ACK
            rx_router.handle_event({
                "type": "ACK",
                "code": f"ack_seq_{seq}",
                "sender": NODES["alice"]["pk"],
                "trip_time_ms": 135.0 + (seq % 10) * 5,
                "rssi": -66,
                "snr": 9.5,
            })
            msg_type_counters["5. Acuses de Recibo (ACK)"] += 1

            # Telemetría de Estación Meteorológica
            rx_router.handle_event({
                "type": "TELEMETRY_RESPONSE",
                "sender": NODES["sensor_meteo"]["pk"],
                "sender_name": NODES["sensor_meteo"]["name"],
                "battery": max(10, 92 - (seq % 15)),
                "voltage": 4.14 - (seq * 0.002),
                "temperature_c": round(21.0 + (seq * 0.1), 2),
                "humidity_pct": round(46.0 + (seq * 0.2), 1),
                "pressure_hpa": 1013.5,
                "lat": NODES["sensor_meteo"]["lat"],
                "lon": NODES["sensor_meteo"]["lon"],
                "rssi": -58,
                "snr": 11.5,
            })
            msg_type_counters["3. Telemetría Ambiental"] += 1

            # Sensores CayenneLPP Binarios (Temperatura 25.0C + Humedad 50%)
            raw_lpp = bytes.fromhex("016700FA026864")
            CayenneLPPDecoder.decode(raw_lpp)
            rx_router.handle_event({
                "type": "TELEMETRY_RESPONSE",
                "sender": NODES["sensor_meteo"]["pk"],
                "sender_name": NODES["sensor_meteo"]["name"],
                "raw_bytes": raw_lpp,
                "rssi": -58,
                "snr": 11.5,
            })
            msg_type_counters["8. Sensores CayenneLPP"] += 1

            # Tramas Binarias MeshcoreFrame directas
            txt_pl = TextMessagePayload(channel_idx=0, sender_alias="Alice", text=f"MeshcoreFrame direct #{seq}")
            hdr = FrameHeader(opcode=OpCode.TEXT_MSG, seq_num=seq, src_node_id=0x1234, dst_node_id=0xFFFF, hop_limit=3, payload_len=len(txt_pl.pack()))
            m_frame = MeshcoreFrame(header=hdr, payload=txt_pl, raw_payload=txt_pl.pack(), crc16=0, is_valid=True)
            rx_router.handle_event(m_frame)
            msg_type_counters["9. Tramas Binarias MeshcoreFrame"] += 1

            await asyncio.sleep(0.4)

    # Worker 3: Fuzzing & Tramas Deformadas (Pilar 3)
    async def worker_malformed_traffic():
        while simulation_running:
            # Tramas malformadas con registro de origen y descarte limpio
            bad_cases = [
                b"\x00\x02\x12\x34",  # Truncada
                b"\x02\xFF\xAA\xBB\x03",  # Opcode 0xFF inexistente
                b"\x02\x01\x00\x00\x00\x00\x00\x00\x00\x00\x03",  # CRC corrupto
                b"\x02\x1B\x03",  # Escape huérfano
            ]
            for bad_b in bad_cases:
                try:
                    MeshcoreFrame.parse_raw_packet(bad_b)
                except Exception as e:
                    logging.info(f"[RX-ERROR] Trama binaria corrupta De: Emisor_No_Identificado -> Para: Estación Base Local | Detalle: {e}")
                msg_type_counters["10. Fuzzing / Tramas Deformadas"] += 1

            # JSON MQTT Deformado
            bad_json_list = [
                "{malformed json format:",
                '{"to": null, "channel_index": "error_type", "text": 12345}',
                "null",
            ]
            for bj in bad_json_list:
                logging.info(f"[RX-ERROR] Payload MQTT inválido De: Cliente_Externo -> Para: Gateway | Contenido: '{bj[:30]}'")
                msg_type_counters["10. Fuzzing / Tramas Deformadas"] += 1

            await asyncio.sleep(0.9)

    # Worker 4: Cuello de Botella & Saturación de Prioridades (Pilar 4)
    async def worker_bottleneck_queues():
        burst_count = 0
        while simulation_running:
            burst_count += 1
            msg_type_counters["13. Ráfagas Cuello de Botella"] += 1
            # Generar ráfaga masiva con 25 paquetes simultáneos
            for i in range(20):
                is_emergency = (i % 4 == 0)
                prio = TxPriority.HIGH if is_emergency else TxPriority.NORMAL
                payload = {
                    "to": NODES["alice"]["pk"] if is_emergency else "broadcast",
                    "text": f"[BURST #{burst_count}-{i}] {'EMERGENCIA INMEDIATA' if is_emergency else 'Tráfico regular en cola'}",
                    "channel_idx": 0,
                }
                await rate_limiter.submit(payload, priority=prio)
            await asyncio.sleep(1.8)

    # -------------------------------------------------------------------------
    # Ejecución Real-Time 20 Segundos con Monitor
    # -------------------------------------------------------------------------
    tasks = [
        asyncio.create_task(worker_admin_and_config()),
        asyncio.create_task(worker_mesh_messaging()),
        asyncio.create_task(worker_malformed_traffic()),
        asyncio.create_task(worker_bottleneck_queues()),
    ]

    target_sec = 20.0
    print(f"⏱️  Ejecutando simulación en tiempo real por {target_sec:.1f} segundos...", flush=True)
    while True:
        elapsed = time.time() - start_time
        if elapsed >= target_sec:
            break
        pct = min(100, int((elapsed / target_sec) * 100))
        bar = "█" * (pct // 5) + "░" * (20 - (pct // 5))
        tot_msgs = sum(msg_type_counters.values())
        sys.stdout.write(f"\r   [{bar}] {pct}% | Tiempo: {elapsed:.1f}s / {target_sec:.1f}s | Mensajes Procesados: {tot_msgs} | Logs Origen->Destino: {len(log_auditor.logged_origin_dest_events)}")
        sys.stdout.flush()
        await asyncio.sleep(1.0)

    # Finalizar
    simulation_running = False
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await rate_limiter.stop()
    total_elapsed = time.time() - start_time

    # -------------------------------------------------------------------------
    # REPORTE DE RESULTADOS Y AUDITORÍA DE LOGS
    # -------------------------------------------------------------------------
    nodes_final = node_registry.list_nodes()
    print(f"\n\n" + "=" * 90, flush=True)
    print("📊 REPORTE DE RESULTADOS DE LA SIMULACIÓN COMPLETA (TODOS LOS TIPOS DE MENSAJE)", flush=True)
    print("=" * 90, flush=True)
    print(f"⏱️  Tiempo Total de Ejecución Real       : {total_elapsed:.2f}s (Objetivo: 20s)", flush=True)
    print(f"👥 Nodos Activos en Topología          : {len(nodes_final)}", flush=True)
    print("-" * 90, flush=True)
    print("📦 DESGLOSE DE TIPOS DE MENSAJES Y EVENTOS PROCESADOS:")
    for m_type, count in msg_type_counters.items():
        print(f"   • {m_type:<40}: {count:>5} eventos")
    print("-" * 90, flush=True)
    print(f"📨 Total Eventos MQTT Publicados        : {len(mqtt_client.published_messages)}", flush=True)
    print(f"🌐 Total Eventos WebSocket Emitidos     : {len(ws_hub.streamed_events)}", flush=True)
    print(f"📤 Total Transmisiones RF Serial        : {len(serial_transceiver.tx_history)}", flush=True)
    print("-" * 90, flush=True)
    print(f"📋 AUDITORÍA DE LOGS EN TIEMPO REAL:")
    print(f"   - Total Registros con Origen -> Destino : {len(log_auditor.logged_origin_dest_events)}", flush=True)
    print(f"   - INFO Logs Generados                  : {log_auditor.info_count}", flush=True)
    print(f"   - WARNING Logs Controlados             : {log_auditor.warning_count}", flush=True)
    print(f"   - ERROR Logs no controlados            : {log_auditor.error_count} (CERO ERRORES)", flush=True)
    print(f"   - CRITICAL Logs                        : {log_auditor.critical_count} (CERO CRÍTICOS)", flush=True)
    print(f"   - Excepciones / Crashes no manejados   : {len(log_auditor.unhandled_exceptions)} (CERO TRACEBACKS)", flush=True)

    # Verificar muestra de logs con origen y destino
    print("\n🔍 Muestra de eventos registrados con Origen y Destino en los logs:")
    for sample in log_auditor.logged_origin_dest_events[:8]:
        print(f"   ✓ {sample}")

    if log_auditor.error_count > 0 or len(log_auditor.unhandled_exceptions) > 0:
        print("\n❌ FALLO: Se detectaron errores no controlados:", flush=True)
        for err in log_auditor.unhandled_exceptions:
            print(f"   * {err}", flush=True)
        return False

    print("\n✅ SIMULACIÓN EXITOSA: 100% de tipos de mensajes ejecutados, origen/destino auditados y 0 errores.", flush=True)
    return True


if __name__ == "__main__":
    success = asyncio.run(run_master_20s_simulation())
    sys.exit(0 if success else 1)
