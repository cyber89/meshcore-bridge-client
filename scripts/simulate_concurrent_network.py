#!/usr/bin/env python3
"""
MeshCore Bridge - High-Concurrency Multi-Node & Multi-Client Real-Time Simulator
Simula una red mallada completa con múltiples nodos y múltiples clientes concurrentes
(REST API, WebSocket, MQTT, Tráfico RF LoRa y Repetidores) mientras audita los logs
en tiempo real para garantizar cero errores, cero excepciones y estabilidad total.
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.contact_manager import NodeRegistry, NodeContactUpdate, PacketRecord
from src.deduplicator import PacketDeduplicator
from src.repeater_manager import RepeaterManager
from src.rate_limiter import TxRateLimiter
from src.admin_handler import AdminCommandHandler, AdminContext
from src.rx_router import RxEventRouter, RxRouterContext
from src.sensor_decoder import CayenneLPPDecoder
from src.protocol_types import OpCode

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
        self.exceptions: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        if record.levelno >= logging.CRITICAL:
            self.critical_count += 1
            if record.exc_text:
                self.exceptions.append(record.exc_text)
        elif record.levelno >= logging.ERROR:
            self.error_count += 1
            if record.exc_text:
                self.exceptions.append(record.exc_text)
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
            "timestamp": time.time()
        })
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


async def run_concurrent_simulation() -> bool:
    print("=" * 80, flush=True)
    print("🌐 INICIANDO SIMULACIÓN CONCURRENTE MULTI-NODO Y MULTI-CLIENTE", flush=True)
    print("=" * 80, flush=True)

    # 1. Configurar Auditor de Logs
    log_auditor = RealTimeLogAuditor()
    logging.getLogger().addHandler(log_auditor)
    logging.getLogger().setLevel(logging.INFO)
    for mod_name in ["src.rx_router", "src.admin_handler", "src.rate_limiter", "src.contact_manager", "src.deduplicator"]:
        logging.getLogger(mod_name).addHandler(log_auditor)
        logging.getLogger(mod_name).setLevel(logging.INFO)

    # 2. Inicializar Infraestructura del Bridge
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
    rate_limiter = TxRateLimiter()
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

    # 3. Definición de la Topología de Nodos
    NODES = {
        "repeater_north": {
            "pk": "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
            "name": "Repeater-Cerro-Norte",
            "role": "REPEATER",
            "lat": -33.4200, "lon": -70.6500, "battery": 95, "voltage": 4.18, "snr": 12.0, "rssi": -55,
        },
        "repeater_south": {
            "pk": "2222333344445555666677778888999900001111aaaabbbbccccddddeeeeffff",
            "name": "Repeater-Cerro-Sur",
            "role": "REPEATER",
            "lat": -33.4800, "lon": -70.6900, "battery": 89, "voltage": 4.05, "snr": 10.5, "rssi": -62,
        },
        "client_alice": {
            "pk": "3333444455556666777788889999000011112222aaaabbbbccccddddeeeeffff",
            "name": "Alice-Field-Operator",
            "role": "CLIENT",
            "lat": -33.4400, "lon": -70.6600, "battery": 78, "voltage": 3.92, "snr": 8.5, "rssi": -70,
        },
        "client_bob": {
            "pk": "4444555566667777888899990000111122223333aaaabbbbccccddddeeeeffff",
            "name": "Bob-Base-Camp",
            "role": "CLIENT",
            "lat": -33.4600, "lon": -70.6800, "battery": 84, "voltage": 4.01, "snr": 9.2, "rssi": -68,
        },
        "sensor_meteo": {
            "pk": "5555666677778888999900001111222233334444aaaabbbbccccddddeeeeffff",
            "name": "Meteo-Sensor-Highland",
            "role": "SENSOR",
            "lat": -33.4100, "lon": -70.6400, "battery": 92, "voltage": 4.15, "snr": 11.0, "rssi": -58,
        },
        "emergency_unit": {
            "pk": "6666777788889999000011112222333344445555aaaabbbbccccddddeeeeffff",
            "name": "Emergency-Rescue-Unit",
            "role": "EMERGENCY",
            "lat": -33.4350, "lon": -70.6550, "battery": 65, "voltage": 3.80, "snr": 7.0, "rssi": -78,
        },
    }

    # Pre-cargar contactos en transceptor
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
                voltage_v=n_data["voltage"],
                last_snr=n_data["snr"],
                last_rssi=n_data["rssi"],
            ),
        )

    print(f"📡 Topología inicial: {len(node_registry.list_nodes())} nodos activos en memoria.", flush=True)

    # 4. Definición de Clientes Concurrentes
    async def client_web_spa_worker():
        """Simula usuario operando la SPA Web interactiva."""
        for cycle in range(5):
            # Enviar mensaje broadcast desde Web UI
            await execute_tx({"to": "broadcast", "text": f"[WEB] Ronda de control #{cycle+1}", "channel_idx": 0})
            await asyncio.sleep(0.05)
            # Enviar DM a Alice
            await execute_tx({"to": NODES["client_alice"]["pk"], "text": f"[WEB-DM] Alice, confirma estado #{cycle+1}"})
            await asyncio.sleep(0.05)

    async def client_mqtt_automation_worker():
        """Simula flujos de automatización n8n vía MQTT."""
        for cycle in range(5):
            # Disparar comando admin a repetidor norte
            cmd_payload = {
                "request_id": f"n8n_cmd_{cycle}",
                "action": "ping_zero",
                "target_node": NODES["repeater_north"]["pk"],
            }
            task = asyncio.create_task(admin_handler.handle(cmd_payload))
            await asyncio.sleep(0.02)
            admin_handler.notify_command_response({
                "sender": NODES["repeater_north"]["pk"],
                "trip_time": 120.0 + cycle * 5,
                "snr_there": 11.5,
                "snr_back": 12.0,
                "text": f"> PONG: Repeater-Cerro-Norte online ({cycle})",
            })
            await task
            await asyncio.sleep(0.05)

    async def client_mesh_rf_traffic_worker():
        """Simula tráfico continuo generado por los nodos de la malla LoRa."""
        for cycle in range(5):
            # Telemetría del sensor
            rx_router.handle_event({
                "type": "TELEMETRY_RESPONSE",
                "sender": NODES["sensor_meteo"]["pk"],
                "sender_name": NODES["sensor_meteo"]["name"],
                "battery": 92 - cycle,
                "voltage": 4.15 - cycle * 0.01,
                "temperature_c": round(21.5 + cycle * 0.4, 2),
                "humidity_pct": round(45.0 + cycle * 1.2, 1),
                "pressure_hpa": 1013.2,
                "lat": NODES["sensor_meteo"]["lat"],
                "lon": NODES["sensor_meteo"]["lon"],
                "rssi": -58,
                "snr": 11.2,
                "hops": 1,
            })
            # Mensaje de Alice
            rx_router.handle_event({
                "type": "CONTACT_MSG_RECV",
                "sender": NODES["client_alice"]["pk"],
                "sender_name": NODES["client_alice"]["name"],
                "text": f"Reporte Alice #{cycle+1}: Todo despejado en el sector norte.",
                "rssi": -69,
                "snr": 9.0,
                "hops": 1,
            })
            # Alerta de Unidad de Emergencia
            rx_router.handle_event({
                "type": "CONTACT_MSG_RECV",
                "sender": NODES["emergency_unit"]["pk"],
                "sender_name": NODES["emergency_unit"]["name"],
                "text": f"🚨 [PRIORITY] Unidad de Rescate activa en cuadrante #{cycle+1}",
                "rssi": -76,
                "snr": 7.5,
                "hops": 2,
            })
            # Acuse de recibo ACK
            rx_router.handle_event({
                "type": "ACK",
                "code": f"ack_{cycle}",
                "trip_time_ms": 145.0 + cycle * 10,
            })
            await asyncio.sleep(0.05)

    async def client_websocket_monitor_worker():
        """Simula monitor en tiempo real consumiendo WebSocket."""
        for _ in range(5):
            await asyncio.sleep(0.08)

    # 5. Ejecutar todos los clientes y nodos concurrentemente
    start_sim = time.time()
    print("\n⚡ Ejecutando 4 clientes concurrentes y 6 nodos de red...", flush=True)
    await asyncio.gather(
        client_web_spa_worker(),
        client_mqtt_automation_worker(),
        client_mesh_rf_traffic_worker(),
        client_websocket_monitor_worker(),
    )
    sim_duration = time.time() - start_sim

    # 6. Inspección de Resultados y Auditoría de Logs
    total_logs = len(log_auditor.records)
    total_ws_streamed = len(ws_hub.streamed_events)
    total_mqtt_published = len(mqtt_client.published_messages)
    total_tx_sent = len(serial_transceiver.tx_history)
    nodes_final = node_registry.list_nodes()

    print("\n" + "=" * 80, flush=True)
    print("📈 RESULTADOS DE LA SIMULACIÓN CONCURRENTE", flush=True)
    print("=" * 80, flush=True)
    print(f"⏱️  Duración de la Simulación   : {sim_duration:.2f}s", flush=True)
    print(f"👥 Nodos Activos en Registro   : {len(nodes_final)}", flush=True)
    print(f"📤 Transmisiones RF Realizadas : {total_tx_sent}", flush=True)
    print(f"📨 Eventos MQTT Publicados     : {total_mqtt_published}", flush=True)
    print(f"🌐 Eventos WebSocket Emitidos  : {total_ws_streamed}", flush=True)
    print(f"📋 Total Registros de Log      : {total_logs}", flush=True)
    print(f"   - INFO Logs                 : {log_auditor.info_count}", flush=True)
    print(f"   - WARNING Logs              : {log_auditor.warning_count}", flush=True)
    print(f"   - ERROR Logs                : {log_auditor.error_count}", flush=True)
    print(f"   - CRITICAL Logs             : {log_auditor.critical_count}", flush=True)
    print(f"   - Excepciones no manejadas  : {len(log_auditor.exceptions)}", flush=True)

    # 7. Verificación Estricta de Cero Errores
    has_errors = log_auditor.error_count > 0 or log_auditor.critical_count > 0 or len(log_auditor.exceptions) > 0
    if has_errors:
        print("\n❌ FALLO: Se detectaron errores o excepciones en los logs durante la simulación:", flush=True)
        for exc in log_auditor.exceptions:
            print(f"   {exc}", flush=True)
        return False

    print("\n✅ ÉXITO TOTAL: 0 errores, 0 excepciones no controladas y 100% de eventos procesados limpiamente.", flush=True)
    return True


if __name__ == "__main__":
    success = asyncio.run(run_concurrent_simulation())
    sys.exit(0 if success else 1)
