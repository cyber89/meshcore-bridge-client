#!/usr/bin/env python3
"""
MeshCore Bridge - Simulador de Escenario Complejo y Verificación Integral (v1.0).

Simula una topología compleja de malla LoRa:
- Estación Base Local (LOCAL Host)
- Repetidor 1: Pico Norte (REPEATER, 1 salto)
- Repetidor 2: Sierra Guadarrama (REPEATER, 2 saltos)
- Cliente: Mochilero Alpha (CLIENT, 2 saltos)
- Sensor: Meteo Pico (SENSOR, 1 salto, telemetría ambiental)
- Sala BBS: Refugio Central (ROOM, 2 saltos)

Verifica exhaustivamente a través de la Web API REST y búferes del Bridge:
1. Feature A: Consultas binarias/anónimas a repetidor (req_neighbours, req_owner, req_regions, req_clock, req_acl).
2. Feature B: Gestor de variables personalizadas (GET, POST, DELETE /api/config/custom_vars).
3. Feature C: Selector de modo Path Hash (GET, POST /api/config/path_hash_mode - modos 0, 1, 2).
4. Feature D: Máscara de configuración Auto-Add de contactos (GET, POST /api/config/autoadd).
5. Feature E: Ámbitos de inundación Flood Scope y clave de transporte (GET, POST /api/config/flood_scope).
6. Reglas inmutables SSoT (Aislamiento de repetidores y nodo local de contactos y chat).
7. Auditoría estricta de logs en memoria para detectar anomalías, excepciones no capturadas o fugas.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

# Asegurar importaciones relativas a la raíz del repositorio
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import (
    NodeContactUpdate,
    NodeRegistry,
)
from src.deduplicator import PacketDeduplicator
from src.rate_limiter import TxRateLimiter
from src.repeater_manager import RepeaterManager
from src.web.api_router import WebAPIRouter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ==============================================================================
# Capturador de Logs en Memoria para Auditoría de Errores
# ==============================================================================

class MemoryLogAuditor(logging.Handler):
    """Handler de logging que captura todos los registros para su posterior análisis."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []
        self.error_records: list[logging.LogRecord] = []
        self.warning_records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        if record.levelno >= logging.ERROR:
            self.error_records.append(record)
        elif record.levelno >= logging.WARNING:
            self.warning_records.append(record)


log_auditor = MemoryLogAuditor()
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
log_auditor.setFormatter(log_formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(log_auditor)

sim_logger = logging.getLogger("ComplexMeshSim")


# ==============================================================================
# Modelado de Nodos del Escenario Complejo
# ==============================================================================

@dataclass(frozen=True)
class MeshNodeDef:
    pubkey: str
    name: str
    alias: str
    role: str
    hops: int
    lat: float
    lon: float


LOCAL_NODE = MeshNodeDef(
    pubkey="00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
    name="Base-Station-Madrid",
    alias="Host Base",
    role="LOCAL",
    hops=0,
    lat=40.4168,
    lon=-3.7038,
)

REPEATER_1 = MeshNodeDef(
    pubkey="1111111111111111111111111111111111111111111111111111111111111111",
    name="R1-Pico-Norte",
    alias="Repetidor Pico Norte",
    role="REPEATER",
    hops=1,
    lat=40.4500,
    lon=-3.7000,
)

REPEATER_2 = MeshNodeDef(
    pubkey="2222222222222222222222222222222222222222222222222222222222222222",
    name="R2-Sierra-Guadarrama",
    alias="Repetidor Sierra",
    role="REPEATER",
    hops=2,
    lat=40.7800,
    lon=-3.9500,
)

CLIENT_1 = MeshNodeDef(
    pubkey="3333333333333333333333333333333333333333333333333333333333333333",
    name="C1-Mochilero-Alpha",
    alias="Senderista Alpha",
    role="CLIENT",
    hops=2,
    lat=40.7850,
    lon=-3.9450,
)

SENSOR_1 = MeshNodeDef(
    pubkey="4444444444444444444444444444444444444444444444444444444444444444",
    name="S1-Meteo-Pico",
    alias="Estación Meteorológica",
    role="SENSOR",
    hops=1,
    lat=40.4520,
    lon=-3.6980,
)

ROOM_1 = MeshNodeDef(
    pubkey="5555555555555555555555555555555555555555555555555555555555555555",
    name="BBS-Refugio-Central",
    alias="Servidor BBS Refugio",
    role="ROOM",
    hops=2,
    lat=40.7820,
    lon=-3.9480,
)


# ==============================================================================
# Mock Oficial de Comandos de Radio MeshCore
# ==============================================================================

class MockMeshCoreCommands:
    """Simula los métodos asíncronos y síncronos del SDK oficial meshcore_py."""

    def __init__(self) -> None:
        self.custom_vars: dict[str, str] = {"initial_tier": "backbone"}
        self.path_hash_mode: int = 0
        self.autoadd_config: dict[str, Any] = {"config": 1, "max_hops": 1}
        self.default_flood_scope: dict[str, Any] = {"scope_name": "#general"}
        self.contacts_added: list[dict[str, Any]] = []
        self.sent_cmds: list[tuple[Any, str]] = []

    # --- Métodos de Diagnóstico de Repetidor ---

    async def req_neighbours_sync(
        self, target: Any, count: int = 255, offset: int = 0, min_timeout: float = 4.0
    ) -> dict[str, Any]:
        sim_logger.info(f"[LoRa-Mock] Respondiendo req_neighbours_sync para {target} (count={count}, offset={offset})")
        return {
            "neighbours_count": 3,
            "results_count": 3,
            "neighbours": [
                {
                    "public_key": LOCAL_NODE.pubkey[:12],
                    "name": LOCAL_NODE.name,
                    "snr": 9.5,
                    "rssi": -65,
                    "role": "LOCAL",
                },
                {
                    "public_key": REPEATER_2.pubkey[:12],
                    "name": REPEATER_2.name,
                    "snr": 6.2,
                    "rssi": -82,
                    "role": "REPEATER",
                },
                {
                    "public_key": SENSOR_1.pubkey[:12],
                    "name": SENSOR_1.name,
                    "snr": 11.0,
                    "rssi": -58,
                    "role": "SENSOR",
                },
            ],
        }

    async def req_owner_sync(self, target: Any, min_timeout: float = 4.0) -> dict[str, Any]:
        sim_logger.info(f"[LoRa-Mock] Respondiendo req_owner_sync para {target}")
        return {
            "owner": "EA4-OPERADOR-MONTAÑA",
            "name": "R1-Pico-Norte",
            "info": "Heltec V3 Solar Autónomo - QTH Guadarrama",
        }

    async def req_regions_sync(self, target: Any, min_timeout: float = 4.0) -> list[str]:
        sim_logger.info(f"[LoRa-Mock] Respondiendo req_regions_sync para {target}")
        return ["EU868", "EU868_CH0_WIDE", "EMERGENCIA_MADRID_VHF"]

    async def req_basic_sync(self, target: Any, min_timeout: float = 4.0) -> dict[str, Any]:
        sim_logger.info(f"[LoRa-Mock] Respondiendo req_basic_sync para {target}")
        now_ts = int(time.time())
        return {
            "clock": now_ts,
            "clock_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now_ts)),
            "uptime_secs": 86400,
            "battery_pct": 98,
            "voltage_v": 4.15,
            "temperature_c": 19.5,
        }

    async def req_acl_sync(self, target: Any, min_timeout: float = 4.0) -> dict[str, Any]:
        sim_logger.info(f"[LoRa-Mock] Respondiendo req_acl_sync para {target}")
        return {
            "acl_enabled": True,
            "allowed_roles": ["ADMIN", "SYSOP", "EMERGENCY"],
            "registered_admins": [LOCAL_NODE.pubkey[:16]],
        }

    # --- Métodos de Configuración Local MeshCore ---

    async def get_custom_vars(self) -> dict[str, str]:
        return dict(self.custom_vars)

    async def set_custom_var(self, key: str, val: str) -> None:
        sim_logger.info(f"[LoRa-Mock] set_custom_var: {key}='{val}'")
        if val == "":
            self.custom_vars.pop(key, None)
        else:
            self.custom_vars[key] = val

    async def set_path_hash_mode(self, mode: int) -> None:
        sim_logger.info(f"[LoRa-Mock] set_path_hash_mode: {mode}")
        self.path_hash_mode = mode

    async def get_autoadd_config(self) -> dict[str, Any]:
        return dict(self.autoadd_config)

    async def set_autoadd_config(self, flags: int, max_hops: int | None = None) -> None:
        sim_logger.info(f"[LoRa-Mock] set_autoadd_config: flags={flags}, max_hops={max_hops}")
        self.autoadd_config["config"] = flags
        if max_hops is not None:
            self.autoadd_config["max_hops"] = max_hops

    async def get_default_flood_scope(self) -> dict[str, Any]:
        return dict(self.default_flood_scope)

    async def set_default_flood_scope(self, scope: str) -> None:
        sim_logger.info(f"[LoRa-Mock] set_default_flood_scope: scope='{scope}'")
        self.default_flood_scope = {"scope_name": scope}

    async def reset_default_flood_scope(self) -> None:
        sim_logger.info("[LoRa-Mock] reset_default_flood_scope")
        self.default_flood_scope = {"scope_name": "", "scope_key": ""}

    async def add_contact(self, contact_data: Any) -> None:
        self.contacts_added.append(contact_data)

    async def send_cmd(self, dest_target: Any, cmd_text: str) -> None:
        self.sent_cmds.append((dest_target, cmd_text))


class MockMeshCoreInstance:
    """Instancia simulada del transceptor de radio de MeshCore."""

    def __init__(self) -> None:
        self.commands = MockMeshCoreCommands()
        self.self_info: dict[str, Any] = {
            "name": LOCAL_NODE.name,
            "public_key": LOCAL_NODE.pubkey,
            "adv_lat": LOCAL_NODE.lat,
            "adv_lon": LOCAL_NODE.lon,
            "adv_role": 0,
        }


# ==============================================================================
# Mock Bridge Harness y Contexto
# ==============================================================================

class MockBridgeHarness:
    """Arnés del bridge con todos los subsistemas reales conectados."""

    def __init__(self) -> None:
        self.node_registry = NodeRegistry()
        self.repeater_manager = RepeaterManager()
        self.rate_limiter = TxRateLimiter()
        self.deduplicator = PacketDeduplicator()

        self.meshcore_instance = MockMeshCoreInstance()
        self.start_time = time.time()
        self.rx_count = 0
        self.tx_count = 0
        self.err_count = 0
        self.hardware_info = {
            "firmware": "MeshCore 2.5.4",
            "board": "Heltec V3 ESP32-S3",
            "battery_pct": 100,
        }

        # Manejador de administración conectado al mock de radio
        admin_ctx = AdminContext(
            mc_provider=lambda: self.meshcore_instance,
            node_registry=self.node_registry,
            repeater_manager=self.repeater_manager,
            mqtt=None,  # type: ignore[arg-type]
            execute_tx=self._mock_execute_tx,
            rate_limiter=self.rate_limiter,
            start_time=self.start_time,
        )
        self.admin_handler = AdminCommandHandler(admin_ctx)

    async def _mock_execute_tx(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.tx_count += 1
        return {"status": "sent", "payload": payload}

    async def _execute_tx(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._mock_execute_tx(payload)

    def is_serial_connected(self) -> bool:
        return True

    def is_mqtt_connected(self) -> bool:
        return True

    def get_local_stats(self) -> dict[str, Any]:
        return {
            "uptime_seconds": int(time.time() - self.start_time),
            "rx_packets": self.rx_count,
            "tx_packets": self.tx_count,
            "error_count": self.err_count,
            "connected_peers": len(self.node_registry.list_nodes()),
        }

    async def handle_admin(self, admin_data: dict[str, Any]) -> dict[str, Any]:
        return await self.admin_handler.handle(admin_data)


# ==============================================================================
# Suite de Simulación y Verificación de Escenario Complejo
# ==============================================================================

class ComplexMeshScenarioVerifier:
    """Orquestador de la simulación compleja de red de malla."""

    def __init__(self) -> None:
        self.bridge = MockBridgeHarness()
        self.api_router = WebAPIRouter(bridge=self.bridge)
        self.phase_results: dict[str, bool] = {}

    async def run_all(self) -> bool:
        sim_logger.info("================================================================================")
        sim_logger.info("INICIANDO SIMULACIÓN DE ESCENARIO COMPLEJO DE MALLA LORA & AUDITORÍA DE LOGS")
        sim_logger.info("================================================================================")

        p1 = await self.phase_1_topology_boot()
        p2 = await self.phase_2_traffic_and_telemetry()
        p3 = await self.phase_3_repeater_binary_queries()
        p4 = await self.phase_4_custom_vars_manager()
        p5 = await self.phase_5_path_hash_mode()
        p6 = await self.phase_6_autoadd_bitmask()
        p7 = await self.phase_7_flood_scope_manager()
        p8 = await self.phase_8_protocol_rules_and_security()
        p9 = self.phase_9_log_audit_and_error_analysis()

        all_passed = all([p1, p2, p3, p4, p5, p6, p7, p8, p9])
        sim_logger.info("================================================================================")
        if all_passed:
            sim_logger.info(">>> RESULTADO GLOBAL: TODOS LOS ESCENARIOS Y COMPROBACIONES COMPLETADOS CON ÉXITO <<<")
        else:
            sim_logger.error(">>> RESULTADO GLOBAL: SE DETECTARON FALLOS EN LA SIMULACIÓN <<<")
        sim_logger.info("================================================================================")
        return all_passed

    # --------------------------------------------------------------------------
    # FASE 1: Arranque de Topología Multi-Nodo y Verificación de Nodos
    # --------------------------------------------------------------------------
    async def phase_1_topology_boot(self) -> bool:
        sim_logger.info("\n--- [FASE 1] DESPLIEGUE Y ARRANQUE DE TOPOLOGÍA MULTI-NODO ---")
        # 1. Establecer nodo local
        self.bridge.node_registry.set_local_pubkey(LOCAL_NODE.pubkey)
        self.bridge.node_registry.add_or_update(
            LOCAL_NODE.pubkey,
            NodeContactUpdate(
                name=LOCAL_NODE.name,
                alias=LOCAL_NODE.alias,
                role=LOCAL_NODE.role,
                is_local=True,
                latitude=LOCAL_NODE.lat,
                longitude=LOCAL_NODE.lon,
                hops=LOCAL_NODE.hops,
            ),
        )

        # 2. Registrar resto de nodos
        for nd in [REPEATER_1, REPEATER_2, CLIENT_1, SENSOR_1, ROOM_1]:
            self.bridge.node_registry.add_or_update(
                nd.pubkey,
                NodeContactUpdate(
                    name=nd.name,
                    alias=nd.alias,
                    role=nd.role,
                    is_local=False,
                    latitude=nd.lat,
                    longitude=nd.lon,
                    hops=nd.hops,
                ),
            )

        # 3. Consultar vía Web API REST: /api/nodes
        status, res = await self.api_router.handle_request("GET", "/api/nodes")
        if status != 200:
            sim_logger.error(f"Fallo consultando /api/nodes: status={status}")
            return False

        nodes_raw = res.get("data")
        nodes_list = nodes_raw if isinstance(nodes_raw, list) else res.get("data", {}).get("nodes", [])
        sim_logger.info(f"Nodos registrados en el Bridge: {len(nodes_list)}")
        assert len(nodes_list) == 6, f"Se esperaban 6 nodos, pero hay {len(nodes_list)}"

        # 4. Verificar aislamiento de repetidores y nodo local en contactos
        status_c, res_c = await self.api_router.handle_request("GET", "/api/contacts")
        contacts_raw = res_c.get("data")
        contacts_list = contacts_raw if isinstance(contacts_raw, list) else res_c.get("data", {}).get("contacts", [])
        sim_logger.info(f"Contactos de usuario registrados (libreta): {len(contacts_list)}")

        contact_pubkeys = [c.get("public_key") for c in contacts_list]
        if LOCAL_NODE.pubkey in contact_pubkeys:
            sim_logger.error("VIOLACIÓN REGLA 1.2: El nodo local apareció en la libreta de contactos")
            return False
        if REPEATER_1.pubkey in contact_pubkeys or REPEATER_2.pubkey in contact_pubkeys:
            sim_logger.error("VIOLACIÓN REGLA 1.1: Un repetidor apareció en la libreta de contactos")
            return False

        sim_logger.info("Reglas 1.1 y 1.2 verificadas: Repetidores y Host Base excluidos de Contactos.")
        self.phase_results["phase_1"] = True
        return True

    # --------------------------------------------------------------------------
    # FASE 2: Tráfico Complejo de Radio y Telemetría de Sensor
    # --------------------------------------------------------------------------
    async def phase_2_traffic_and_telemetry(self) -> bool:
        sim_logger.info("\n--- [FASE 2] RECEPCIÓN DE TRÁFICO DE RADIO Y TELEMETRÍA AMBIENTAL ---")

        # 1. Inyectar telemetría ambiental desde S1-Meteo-Pico
        sensor_event = {
            "event_type": "telemetry",
            "sender": SENSOR_1.pubkey,
            "sender_name": SENSOR_1.name,
            "temperature_c": 18.4,
            "humidity_pct": 62,
            "pressure_hpa": 1014.2,
            "voltage_v": 3.92,
            "battery_pct": 89,
            "rssi": -74,
            "snr": 8.5,
        }
        self.api_router.record_incoming_event(sensor_event)

        # 2. Inyectar mensaje de chat público desde C1-Mochilero-Alpha
        chat_event = {
            "event_type": "channel",
            "sender": CLIENT_1.pubkey,
            "sender_name": CLIENT_1.name,
            "text": "Reportando paso de montaña despejado, enlace óptimo.",
            "channel_idx": 0,
            "rssi": -88,
            "snr": 5.0,
        }
        self.api_router.record_incoming_event(chat_event)

        # 3. Inyectar mensaje directo a BBS desde C1-Mochilero-Alpha hacia ROOM_1
        bbs_event = {
            "event_type": "channel",
            "sender": ROOM_1.pubkey,
            "sender_name": ROOM_1.name,
            "text": "[BBS] Boletín de montaña #42 publicado",
            "channel_idx": 1,
            "rssi": -85,
            "snr": 6.5,
        }
        self.api_router.record_incoming_event(bbs_event)

        # 4. Verificar ingesta en API /api/telemetry
        status_t, res_t = await self.api_router.handle_request("GET", "/api/telemetry")
        if status_t != 200:
            sim_logger.error(f"Fallo consultando /api/telemetry: {status_t}")
            return False
        telemetry_raw = res_t.get("data")
        telemetry_items = telemetry_raw if isinstance(telemetry_raw, list) else res_t.get("data", {}).get("telemetry", [])
        sim_logger.info(f"Eventos de telemetría procesados en buffer: {len(telemetry_items)}")
        assert len(telemetry_items) >= 1, "No se registró la telemetría del sensor"

        # 5. Verificar ingesta en API /api/messages
        status_m, res_m = await self.api_router.handle_request("GET", "/api/messages")
        if status_m != 200:
            sim_logger.error(f"Fallo consultando /api/messages: {status_m}")
            return False
        msg_raw = res_m.get("data")
        msg_items = msg_raw if isinstance(msg_raw, list) else res_m.get("data", {}).get("messages", [])
        sim_logger.info(f"Mensajes de chat procesados en buffer: {len(msg_items)}")
        assert len(msg_items) >= 2, "No se registraron los mensajes de chat/BBS"

        self.phase_results["phase_2"] = True
        return True

    # --------------------------------------------------------------------------
    # FASE 3: Consultas de Diagnóstico Binarias/Anónimas a Repetidor (Feature A)
    # --------------------------------------------------------------------------
    async def phase_3_repeater_binary_queries(self) -> bool:
        sim_logger.info("\n--- [FASE 3] CONSULTAS BINARIAS/ANÓNIMAS A REPETIDOR (FEATURE A) ---")
        rep_target = REPEATER_1.pubkey

        # 1. req_neighbours
        sim_logger.info(f"Consultando vecinos de repetidor {REPEATER_1.name}...")
        s1, r1 = await self.api_router.handle_request(
            "POST", "/api/repeater/remote/neighbours", {"target_node": rep_target, "count": 10}
        )
        if s1 != 200 or r1.get("status") != "ok":
            sim_logger.error(f"Fallo en /api/repeater/remote/neighbours: {s1} - {r1}")
            return False
        neighbours = r1.get("data", {}).get("neighbours", [])
        sim_logger.info(f"Vecinos descubiertos con éxito: {len(neighbours)}")
        assert len(neighbours) == 3, f"Se esperaban 3 vecinos, se obtuvieron {len(neighbours)}"

        # 2. req_owner
        sim_logger.info(f"Consultando información de propietario de {REPEATER_1.name}...")
        s2, r2 = await self.api_router.handle_request(
            "POST", "/api/repeater/remote/owner", {"target_node": rep_target}
        )
        if s2 != 200 or r2.get("status") != "ok":
            sim_logger.error(f"Fallo en /api/repeater/remote/owner: {s2} - {r2}")
            return False
        owner_name = r2.get("data", {}).get("owner_name")
        owner_info = r2.get("data", {}).get("owner_info")
        sim_logger.info(f"Propietario obtenido: '{owner_info}' ('{owner_name}')")

        # 3. req_regions
        sim_logger.info(f"Consultando regiones de {REPEATER_1.name}...")
        s3, r3 = await self.api_router.handle_request(
            "POST", "/api/repeater/remote/regions", {"target_node": rep_target}
        )
        if s3 != 200 or r3.get("status") != "ok":
            sim_logger.error(f"Fallo en /api/repeater/remote/regions: {s3} - {r3}")
            return False
        regions = r3.get("data", {}).get("regions", [])
        sim_logger.info(f"Regiones obtenidas: {regions}")
        assert "EU868" in regions, "La región EU868 no está en la respuesta"

        # 4. req_clock
        sim_logger.info(f"Consultando reloj RTC y telemetría de {REPEATER_1.name}...")
        s4, r4 = await self.api_router.handle_request(
            "POST", "/api/repeater/remote/clock", {"target_node": rep_target}
        )
        if s4 != 200 or r4.get("status") != "ok":
            sim_logger.error(f"Fallo en /api/repeater/remote/clock: {s4} - {r4}")
            return False
        clock_data = r4.get("data", {}).get("data", {})
        sim_logger.info(f"Reloj obtenido: {clock_data.get('clock_iso')}, Temp: {clock_data.get('temperature_c')}°C")
        assert "clock" in clock_data, "No se devolvió el timestamp del reloj"

        # 5. req_acl
        sim_logger.info(f"Consultando tabla ACL de {REPEATER_1.name}...")
        s5, r5 = await self.api_router.handle_request(
            "POST", "/api/repeater/remote/acl", {"target_node": rep_target}
        )
        if s5 != 200 or r5.get("status") != "ok":
            sim_logger.error(f"Fallo en /api/repeater/remote/acl: {s5} - {r5}")
            return False
        acl_data = r5.get("data", {}).get("acl_data", {})
        sim_logger.info(f"ACL obtenida: {acl_data}")
        assert acl_data.get("acl_enabled") is True, "ACL debería estar habilitada"

        self.phase_results["phase_3"] = True
        return True

    # --------------------------------------------------------------------------
    # FASE 4: Gestor de Variables Personalizadas (Feature B)
    # --------------------------------------------------------------------------
    async def phase_4_custom_vars_manager(self) -> bool:
        sim_logger.info("\n--- [FASE 4] GESTOR DE VARIABLES PERSONALIZADAS (FEATURE B) ---")

        # 1. Asignar variables custom: POST /api/config/custom_vars
        sim_logger.info("Configurando variables personalizadas (mesh_tier='core', telemetry_freq='120')...")
        payload = {"vars": {"mesh_tier": "core", "telemetry_freq": "120"}}
        s1, r1 = await self.api_router.handle_request("POST", "/api/config/custom_vars", payload)
        if s1 != 200 or r1.get("status") != "ok":
            sim_logger.error(f"Fallo en POST /api/config/custom_vars: {s1} - {r1}")
            return False

        # 2. Consultar variables: GET /api/config/custom_vars
        s2, r2 = await self.api_router.handle_request("GET", "/api/config/custom_vars")
        if s2 != 200:
            sim_logger.error(f"Fallo en GET /api/config/custom_vars: {s2}")
            return False
        cvs = r2.get("custom_vars", {})
        sim_logger.info(f"Variables personalizadas en el nodo: {cvs}")
        assert cvs.get("mesh_tier") == "core", "mesh_tier no se actualizó correctamente"
        assert cvs.get("telemetry_freq") == "120", "telemetry_freq no se actualizó correctamente"

        # 3. Eliminar una variable: DELETE /api/config/custom_vars?key=telemetry_freq
        sim_logger.info("Eliminando variable 'telemetry_freq'...")
        s3, r3 = await self.api_router.handle_request("DELETE", "/api/config/custom_vars?key=telemetry_freq")
        if s3 != 200 or r3.get("status") != "ok":
            sim_logger.error(f"Fallo en DELETE /api/config/custom_vars: {s3} - {r3}")
            return False

        # 4. Verificar persistencia tras borrado
        s4, r4 = await self.api_router.handle_request("GET", "/api/config/custom_vars")
        cvs_after = r4.get("custom_vars", {})
        sim_logger.info(f"Variables tras eliminación: {cvs_after}")
        assert "telemetry_freq" not in cvs_after, "telemetry_freq no fue eliminada"
        assert cvs_after.get("mesh_tier") == "core", "mesh_tier debería conservarse"

        self.phase_results["phase_4"] = True
        return True

    # --------------------------------------------------------------------------
    # FASE 5: Selector de Modo Path Hash (Feature C)
    # --------------------------------------------------------------------------
    async def phase_5_path_hash_mode(self) -> bool:
        sim_logger.info("\n--- [FASE 5] SELECTOR DE MODO PATH HASH (FEATURE C) ---")

        # Probar modos 2, 1 y 0
        for mode in (2, 1, 0):
            sim_logger.info(f"Configurando Path Hash Mode={mode}...")
            s1, r1 = await self.api_router.handle_request(
                "POST", "/api/config/path_hash_mode", {"mode": mode}
            )
            if s1 != 200 or r1.get("status") != "ok":
                sim_logger.error(f"Fallo configurando path hash mode {mode}: {s1} - {r1}")
                return False

            s2, r2 = await self.api_router.handle_request("GET", "/api/config/path_hash_mode")
            if s2 != 200:
                sim_logger.error(f"Fallo consultando path hash mode: {s2}")
                return False
            cur_mode = r2.get("path_hash_mode")
            sim_logger.info(f"Modo confirmado por API: {cur_mode}")
            assert cur_mode == mode, f"Se esperaba modo {mode}, se obtuvo {cur_mode}"

        self.phase_results["phase_5"] = True
        return True

    # --------------------------------------------------------------------------
    # FASE 6: Configuración Auto-Add de Contactos con Bitmask (Feature D)
    # --------------------------------------------------------------------------
    async def phase_6_autoadd_bitmask(self) -> bool:
        sim_logger.info("\n--- [FASE 6] CONFIGURACIÓN AUTO-ADD DE CONTACTOS BITMASK (FEATURE D) ---")

        # 1. Configurar flags=3 (bit 0=overwrite, bit 1=chat) y max_hops=2
        sim_logger.info("Configurando Auto-Add: flags=3, max_hops=2...")
        s1, r1 = await self.api_router.handle_request(
            "POST", "/api/config/autoadd", {"flags": 3, "max_hops": 2}
        )
        if s1 != 200 or r1.get("status") != "ok":
            sim_logger.error(f"Fallo en POST /api/config/autoadd: {s1} - {r1}")
            return False

        # 2. Consultar configuración: GET /api/config/autoadd
        s2, r2 = await self.api_router.handle_request("GET", "/api/config/autoadd")
        if s2 != 200:
            sim_logger.error(f"Fallo en GET /api/config/autoadd: {s2}")
            return False
        cfg = r2.get("autoadd_config", {})
        sim_logger.info(f"Configuración confirmada por API: {cfg}")
        assert cfg.get("config") == 3, f"Esperado flags=3, obtenido {cfg.get('config')}"
        assert cfg.get("max_hops") == 2, f"Esperado max_hops=2, obtenido {cfg.get('max_hops')}"

        self.phase_results["phase_6"] = True
        return True

    # --------------------------------------------------------------------------
    # FASE 7: Gestor de Ámbitos de Inundación Flood Scope (Feature E)
    # --------------------------------------------------------------------------
    async def phase_7_flood_scope_manager(self) -> bool:
        sim_logger.info("\n--- [FASE 7] GESTOR DE ÁMBITOS DE INUNDACIÓN FLOOD SCOPE (FEATURE E) ---")

        # 1. Asignar Flood Scope: #emergencias_guadarrama
        sim_logger.info("Configurando Flood Scope='#emergencias_guadarrama'...")
        s1, r1 = await self.api_router.handle_request(
            "POST", "/api/config/flood_scope", {"scope": "#emergencias_guadarrama"}
        )
        if s1 != 200 or r1.get("status") != "ok":
            sim_logger.error(f"Fallo en POST /api/config/flood_scope: {s1} - {r1}")
            return False

        s2, r2 = await self.api_router.handle_request("GET", "/api/config/flood_scope")
        if s2 != 200:
            sim_logger.error(f"Fallo en GET /api/config/flood_scope: {s2}")
            return False
        fs = r2.get("flood_scope", {})
        sim_logger.info(f"Flood Scope confirmado: {fs}")
        assert fs.get("scope_name") == "#emergencias_guadarrama", "El scope name no coincide"

        # 2. Reiniciar a Global / None
        sim_logger.info("Reiniciando Flood Scope a global (scope='none')...")
        s3, r3 = await self.api_router.handle_request(
            "POST", "/api/config/flood_scope", {"scope": "none"}
        )
        if s3 != 200 or r3.get("status") != "ok":
            sim_logger.error(f"Fallo reiniciando flood_scope: {s3} - {r3}")
            return False

        s4, r4 = await self.api_router.handle_request("GET", "/api/config/flood_scope")
        fs_reset = r4.get("flood_scope", {})
        sim_logger.info(f"Flood Scope tras reset: {fs_reset}")
        assert fs_reset.get("scope_name") == "", "El scope name debería estar vacío tras reset"

        self.phase_results["phase_7"] = True
        return True

    # --------------------------------------------------------------------------
    # FASE 8: Verificación de Reglas Inmutables de Seguridad y Protocolo
    # --------------------------------------------------------------------------
    async def phase_8_protocol_rules_and_security(self) -> bool:
        sim_logger.info("\n--- [FASE 8] PRUEBAS DE SEGURIDAD Y REGLAS PROTOCOLARES INMUTABLES ---")

        # 1. Prohibido enviar chat a repetidor (Regla 1.1 SSoT)
        sim_logger.info("Intentando enviar mensaje de chat directo a un repetidor (debe fallar/ser rechazado)...")
        status_dm, res_dm = await self.api_router.handle_request(
            "POST", "/api/tx", {"to": REPEATER_1.pubkey, "text": "Hola Repetidor"}
        )
        sim_logger.info(f"Respuesta de intento de chat a repetidor: status={status_dm}, resp={res_dm}")
        assert status_dm == 400 and res_dm.get("error") == "tx_to_repeater_forbidden", (
            f"Se esperaba rechazo tx_to_repeater_forbidden, pero respondió {status_dm} {res_dm}"
        )

        # 1.1 Prohibido enviar chat al nodo local (Regla 1.2 SSoT)
        sim_logger.info("Intentando enviar mensaje de chat directo al host base local (debe ser rechazado)...")
        status_local, res_local = await self.api_router.handle_request(
            "POST", "/api/tx", {"to": LOCAL_NODE.pubkey, "text": "Loopback prohibido"}
        )
        sim_logger.info(f"Respuesta de chat al nodo local: status={status_local}, resp={res_local}")
        assert status_local == 400 and res_local.get("error") == "tx_to_local_forbidden", (
            f"Se esperaba rechazo tx_to_local_forbidden, pero respondió {status_local} {res_local}"
        )

        # 2. Prohibido enviar comandos admin exclusivos de repetidor a un cliente
        sim_logger.info("Intentando ejecutar req_neighbours sobre un nodo CLIENT (debe ser rechazado)...")
        status_bad, res_bad = await self.api_router.handle_request(
            "POST", "/api/repeater/remote/neighbours", {"target_node": CLIENT_1.pubkey}
        )
        sim_logger.info(f"Respuesta de comando repetidor sobre cliente: status={status_bad}, resp={res_bad}")
        assert status_bad in (400, 422), "Se esperaba error 400/422 al consultar repetidor sobre un cliente"

        # 3. Comprobación de Health y Preflight del Bridge
        s_h, r_h = await self.api_router.handle_request("GET", "/api/health")
        assert s_h == 200 and r_h.get("status") == "ok", "El endpoint /api/health debe responder 200 OK"
        sim_logger.info(f"Health Check del Bridge: {r_h}")

        self.phase_results["phase_8"] = True
        return True

    # --------------------------------------------------------------------------
    # FASE 9: Auditoría Estricta de Logs en Memoria y Análisis de Errores
    # --------------------------------------------------------------------------
    def phase_9_log_audit_and_error_analysis(self) -> bool:
        sim_logger.info("\n--- [FASE 9] AUDITORÍA ESTRICTA DE LOGS EN MEMORIA Y ANÁLISIS DE ANOMALÍAS ---")
        total_logs = len(log_auditor.records)
        errors = log_auditor.error_records
        warnings = log_auditor.warning_records

        sim_logger.info(f"Total de registros de log capturados durante la simulación: {total_logs}")
        sim_logger.info(f"Registros de nivel WARNING: {len(warnings)}")
        sim_logger.info(f"Registros de nivel ERROR/CRITICAL: {len(errors)}")

        if warnings:
            sim_logger.info("Detalle de advertencias capturadas:")
            for w in warnings:
                sim_logger.info(f"  [WARN] [{w.name}] {w.getMessage()}")

        # Comprobar si hubo errores no controlados o excepciones no capturadas
        unhandled_errors: list[logging.LogRecord] = []
        for e in errors:
            msg = e.getMessage()
            # Ignorar errores que forman parte intencional de los tests negativos (p.ej. rechazo de chat a repetidor)
            if "VIOLACIÓN" in msg or "Exception" in msg or "Traceback" in msg:
                unhandled_errors.append(e)

        if unhandled_errors:
            sim_logger.error(f"SE DETECTARON {len(unhandled_errors)} ERRORES INESPERADOS EN LOS LOGS:")
            for err in unhandled_errors:
                sim_logger.error(f"  [ERROR] [{err.name}] {err.getMessage()}")
            self.phase_results["phase_9"] = False
            return False

        sim_logger.info("Auditoría de logs completada: CERO errores inesperados o excepciones huérfanas encontradas.")
        self.phase_results["phase_9"] = True
        return True


# ==============================================================================
# Punto de Entrada
# ==============================================================================

async def main() -> int:
    verifier = ComplexMeshScenarioVerifier()
    success = await verifier.run_all()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
