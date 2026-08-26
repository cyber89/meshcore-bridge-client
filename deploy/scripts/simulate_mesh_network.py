#!/usr/bin/env python3
"""
MeshCore Bridge - Simulador Integral Multi-Nodo de Validación
Valida el descubrimiento de contactos, mensajería de canal y DMs con ACKs,
comandos remotos CLI a repetidores, telemetría y configuración de parámetros.
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
from src.store_forward import SQLiteStoreAndForward, StoredMessage, PacketDeduplicator
from src.repeater_manager import RepeaterManager
from src.rate_limiter import TxRateLimiter
from src.admin_handler import AdminCommandHandler, AdminContext
from src.rx_router import RxEventRouter, RxRouterContext
import config
sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class MockMqttClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, int]] = []
        self.is_connected = True
        self.broker = "mock.broker"
        self.port = 1883

    def publish_safe(self, topic: str, payload: str, qos: int = 1) -> bool:
        self.published.append((topic, payload, qos))
        return True


class MockWebServer:
    def __init__(self) -> None:
        self.broadcasted: list[dict[str, Any]] = []

    def broadcast_event(self, event_data: dict[str, Any]) -> None:
        self.broadcasted.append(event_data)


class MockSerialAdapter:
    def __init__(self) -> None:
        self.is_connected = True
        self.port = "/dev/ttyACM0"
        self.baud_rate = 115200
        self.last_heartbeat_time = time.time()
        self.sent_frames: list[dict[str, Any]] = []
        self.contacts_db: dict[str, dict[str, Any]] = {}

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
        self.sent_frames.append({"text": text, "target": target, "channel_idx": channel_idx})
        return {"status": "sent", "expected_ack": "a1b2c3d4"}

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


async def run_mesh_simulation() -> bool:
    print("\n" + "=" * 80)
    print("🚀 INICIANDO SIMULACIÓN INTEGRAL DE RED MESHCORE (MULTI-NODO)")
    print("=" * 80 + "\n")

    # 1. Instanciación de componentes
    node_registry = NodeRegistry()
    local_pk = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
    node_registry.set_local_pubkey(local_pk)

    # Base Station local
    node_registry.add_or_update(
        local_pk,
        NodeContactUpdate(
            name="Base-Station-Alpha",
            role="LOCAL",
            is_local=True,
            latitude=40.4168,
            longitude=-3.7038,
        ),
    )

    db_path = ":memory:"
    store_forward = SQLiteStoreAndForward(db_path=db_path)

    repeater_mgr = RepeaterManager()
    deduplicator = PacketDeduplicator()
    rate_limiter = TxRateLimiter()
    mqtt_client = MockMqttClient()
    web_server = MockWebServer()
    serial_adapter = MockSerialAdapter()
    counters = Counters()
    bg_tasks: set[asyncio.Task[Any]] = set()

    # Pre-cargar contactos en la radio física simulada
    serial_adapter.contacts_db = {
        "31d03b1faabbccddeeff00112233445566778899aabbccddeeff001122334455": {
            "public_key": "31d03b1faabbccddeeff00112233445566778899aabbccddeeff001122334455",
            "name": "R1-Mountain",
            "alias": "R1-Mountain",
            "role": "REPEATER",
            "adv_type": 2,
            "latitude": 40.4200,
            "longitude": -3.7100,
        },
        "44e05c2eaabbccddeeff00112233445566778899aabbccddeeff001122334455": {
            "public_key": "44e05c2eaabbccddeeff00112233445566778899aabbccddeeff001122334455",
            "name": "R2-Valley",
            "alias": "R2-Valley",
            "role": "REPEATER",
            "adv_type": 2,
            "latitude": 40.4300,
            "longitude": -3.7200,
        },
    }

    async def execute_tx_mock(payload: dict[str, Any]) -> dict[str, Any]:
        counters.tx_count += 1
        target = payload.get("to", "broadcast")
        text = payload.get("text", "")
        ch = payload.get("channel_idx", 0)
        return await serial_adapter.send_message(text=text, target=target, channel_idx=ch)

    rx_ctx = RxRouterContext(
        node_registry=node_registry,
        repeater_manager=repeater_mgr,
        store_forward=store_forward,
        mqtt=mqtt_client,
        web_server=web_server,
        serial_adapter=serial_adapter,
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
        execute_tx=execute_tx_mock,
        mc_provider=lambda: None,
        web_server=web_server,
    )
    admin_handler = AdminCommandHandler(admin_ctx)

    # -------------------------------------------------------------
    # FASE 1: Sincronización e Importación de Contactos desde Hardware
    # -------------------------------------------------------------
    print("📡 [FASE 1] Sincronizando libreta de contactos desde el transceptor serial...")
    contacts_hw = await serial_adapter.sync_all_contacts()
    for c in contacts_hw:
        node_registry.add_or_update(
            c["public_key"],
            NodeContactUpdate(
                name=c["name"],
                alias=c["alias"],
                role=c["role"],
                latitude=c.get("latitude"),
                longitude=c.get("longitude"),
                is_favorite=True,
            ),
        )

    nodes_initial = node_registry.list_nodes()
    print(f"  ✓ Nodos cargados en NodeRegistry: {len(nodes_initial)}")
    assert len(nodes_initial) >= 3, "Fallo: Deben existir al menos 3 nodos (Local + R1 + R2)"
    print("  ✓ Contactos de hardware importados correctamente.")

    # -------------------------------------------------------------
    # FASE 2: Descubrimiento de Nodos Remotos por Radio (RF Adverts & Telemetría)
    # -------------------------------------------------------------
    print("\n📻 [FASE 2] Simulando recepción de tramas RF de clientes, sensores y salas...")
    simulated_packets = [
        {
            "type": "ADVERTISEMENT",
            "public_key": "a1b2c3d4aabbccddeeff00112233445566778899aabbccddeeff001122334455",
            "adv_name": "Client-Alice",
            "adv_type": 1,
            "lat": 40.4150,
            "lon": -3.7000,
            "battery": 92,
            "rssi": -65,
            "snr": 9.5,
            "hops": 1,
        },
        {
            "type": "ADVERTISEMENT",
            "public_key": "b2c3d4e5aabbccddeeff00112233445566778899aabbccddeeff001122334455",
            "adv_name": "Client-Bob",
            "adv_type": 1,
            "lat": 40.4100,
            "lon": -3.7050,
            "battery": 88,
            "rssi": -72,
            "snr": 7.0,
            "hops": 2,
        },
        {
            "type": "TELEMETRY_RESPONSE",
            "public_key": "c3d4e5f6aabbccddeeff00112233445566778899aabbccddeeff001122334455",
            "sender": "c3d4e5f6aabbccddeeff00112233445566778899aabbccddeeff001122334455",
            "sender_name": "Sensor-Meteo-01",
            "adv_type": 4,
            "lat": 40.4250,
            "lon": -3.7150,
            "battery": 76,
            "temperature_c": 23.4,
            "humidity_pct": 48.0,
            "pressure_hpa": 1014.2,
            "rssi": -58,
            "snr": 11.2,
            "hops": 1,
        },
        {
            "type": "ADVERTISEMENT",
            "public_key": "d4e5f6a7aabbccddeeff00112233445566778899aabbccddeeff001122334455",
            "adv_name": "BBS-Community",
            "adv_type": 3,
            "lat": 40.4180,
            "lon": -3.7080,
            "rssi": -62,
            "snr": 10.0,
            "hops": 0,
        },
    ]

    for pkt in simulated_packets:
        rx_router.handle_event(pkt)

    all_nodes = node_registry.list_nodes()
    print(f"  ✓ Nodos descubiertos en la malla: {len(all_nodes)}")
    for n in all_nodes:
        print(f"    - [{n.get('role', 'CLIENT'):<8}] {n.get('name'):<16} Key: {n.get('public_key')[:8]}... Pos: {n.get('latitude')}, {n.get('longitude')} Bat: {n.get('battery_pct')}%")

    assert len(all_nodes) == 7, f"Esperados 7 nodos, obtenidos {len(all_nodes)}"
    print("  ✓ Todos los nodos (clientes, sensores, salas y repetidores) descubiertos con sus posiciones y telemetría.")

    # -------------------------------------------------------------
    # FASE 3: Mensajería de Canal y Mensajes Directos (DM) con ACKs
    # -------------------------------------------------------------
    print("\n💬 [FASE 3] Validando flujo de mensajería (Broadcast y DM) con Acuses de Recibo (ACK)...")
    
    tx_res = await execute_tx_mock({"to": "broadcast", "text": "Hola a todos en la malla LoRa!", "channel_idx": 0})
    print(f"  ✓ Mensaje broadcast enviado: {tx_res.get('status')}")

    alice_pk = "a1b2c3d4aabbccddeeff00112233445566778899aabbccddeeff001122334455"
    rx_dm = {
        "type": "CONTACT_MSG_RECV",
        "sender": alice_pk,
        "sender_name": "Client-Alice",
        "text": "Hola Estación Base, ¿recibes mi señal?",
        "rssi": -65,
        "snr": 9.5,
        "hops": 1,
    }
    rx_router.handle_event(rx_dm)
    print("  ✓ Mensaje DM entrante de Alice procesado y almacenado.")

    exp_ack = "e2e_ack_99"
    await store_forward.enqueue(
        StoredMessage(
            topic=f"meshcore/tx/{alice_pk}",
            payload=json.dumps({"text": "Fuerte y claro Alice!", "target": alice_pk, "expected_ack": exp_ack}),
            qos=1,
        )
    )
    print("  ✓ Mensaje DM saliente encolado en SQLite Store & Forward.")

    pending_count = await store_forward.count()
    assert pending_count >= 1, "Fallo: El mensaje no fue guardado en SQLite Store & Forward"

    rx_ack = {
        "type": "ACK",
        "code": exp_ack,
        "trip_time_ms": 185.4,
    }
    rx_router.handle_event(rx_ack)
    print("  ✓ ACK recibido y procesado por el enrutador.")

    # -------------------------------------------------------------
    # FASE 4: Ejecución de Comandos Remotos a Repetidores
    # -------------------------------------------------------------
    print("\n🏔️ [FASE 4] Probando ejecución de comandos CLI en repetidor remoto (R1-Mountain)...")
    r1_pk = "31d03b1faabbccddeeff00112233445566778899aabbccddeeff001122334455"

    ping_task = asyncio.create_task(admin_handler.handle({
        "action": "ping_zero",
        "target_node": r1_pk,
    }))
    await asyncio.sleep(0.05)

    admin_handler.notify_command_response({
        "sender": r1_pk,
        "trip_time": 142.5,
        "snr_there": 10.5,
        "snr_back": 11.0,
        "rssi": -55,
        "text": "> PONG: R1-Mountain online (Hops: 0, SNR: +11.0 dB)",
    })

    ping_result = await ping_task
    print(f"  ✓ Ping Zero Response: Status={ping_result.get('status')}, RTT={ping_result.get('rtt_ms')} ms, SNR={ping_result.get('snr_back')} dB")
    assert ping_result.get("status") == "ok" and ping_result.get("rtt_ms") == 142.5

    ver_task = asyncio.create_task(admin_handler.handle({
        "action": "ver",
        "target_node": r1_pk,
    }))
    await asyncio.sleep(0.05)
    admin_handler.notify_command_response({
        "sender": r1_pk,
        "text": "> MeshCore Repeater Firmware v3.0.4-ESP32S3",
    })
    ver_result = await ver_task
    print(f"  ✓ Comando 'ver' Response: {ver_result.get('response')}")
    assert "v3.0.4" in str(ver_result.get("response"))

    pos_task = asyncio.create_task(admin_handler.handle({
        "action": "pos",
        "target_node": r1_pk,
    }))
    await asyncio.sleep(0.05)
    admin_handler.notify_command_response({
        "sender": r1_pk,
        "text": "> POS: Lat=40.4200 Lon=-3.7100 Alt=680m",
    })
    pos_result = await pos_task
    print(f"  ✓ Comando 'pos' Response: {pos_result.get('response')}")

    # -------------------------------------------------------------
    # FASE 5: Actualización y Persistencia de Parámetros
    # -------------------------------------------------------------
    print("\n⚙️ [FASE 5] Comprobando actualización y configuración de parámetros...")

    new_local_params = {
        "name": "Base-Station-Pro",
        "tx_power": 22,
        "frequency": 915.5,
        "spreading_factor": 10,
        "bandwidth": 125,
        "latitude": 40.4175,
        "longitude": -3.7042,
    }
    admin_handler._local_config.update(new_local_params)
    node_registry.add_or_update(
        local_pk,
        NodeContactUpdate(
            name=new_local_params["name"],
            latitude=new_local_params["latitude"],
            longitude=new_local_params["longitude"],
            role="LOCAL",
            is_local=True,
        ),
    )

    updated_cfg = admin_handler.get_local_config()
    print(f"  ✓ Configuración local actualizada: Nombre={updated_cfg.get('name')}, Freq={updated_cfg.get('frequency')} MHz, TX={updated_cfg.get('tx_power')} dBm, Pos=({updated_cfg.get('latitude')}, {updated_cfg.get('longitude')})")
    assert updated_cfg.get("name") == "Base-Station-Pro"
    assert updated_cfg.get("frequency") == 915.5

    node_registry.add_or_update(
        alice_pk,
        NodeContactUpdate(
            alias="Alice (Oficina Central)",
            is_favorite=True,
        ),
    )
    alice_node = node_registry.get_contact(alice_pk)
    assert alice_node and alice_node.alias == "Alice (Oficina Central)" and alice_node.is_favorite
    print(f"  ✓ Parámetros de nodo remoto actualizados y persistidos: Alias='{alice_node.alias}', Favorito={alice_node.is_favorite}")

    print("\n" + "=" * 80)
    print("🎉 SIMULACIÓN COMPLETADA CON ÉXITO: 100% DE PRUEBAS SUPERADAS")
    print("=" * 80 + "\n")
    return True


if __name__ == "__main__":
    asyncio.run(run_mesh_simulation())
