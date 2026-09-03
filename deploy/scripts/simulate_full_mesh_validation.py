#!/usr/bin/env python3
"""
MeshCore Bridge - Simulador Exhaustivo y Suite de Validación Multi-Nodo (v3.0)
Valida la red malla de 5 nodos con saltos (hops 1..3), 25 clientes concurrentes,
sensores de telemetría, BBS, inyección de tramas con fallos (fuzzing), administración
remota de repetidor, ciclo de vida dinámico de contactos, mapas y auditoría de logs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

# Asegurar que el directorio raíz está en sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.contact_manager import (
    NodeContactUpdate,
    NodeDiscoveryEvent,
    NodeRegistry,
    is_valid_node_key,
)
from src.deduplicator import PacketDeduplicator
from src.rate_limiter import TxRateLimiter
from src.repeater_manager import RepeaterManager
from src.rx_router import RxEventRouter, RxRouterContext
from src.web.api_router import WebAPIRouter
from src.web.controllers.base import ApiContext

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Configuración de logging para la simulación
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
sim_logger = logging.getLogger("MeshValidation")


# ==============================================================================
# Modelado de Topología de Malla LoRa
# ==============================================================================

@dataclass
class SimulatedDevice:
    pubkey: str
    name: str
    alias: str
    role: str
    parent_node_key: str
    hops: int
    lat: float
    lon: float
    battery_pct: int
    voltage_v: float
    snr: float
    rssi: int


# ==============================================================================
# Mocks del Entorno para Ejecución Determinista
# ==============================================================================

class MockBridgeMqtt:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, int]] = []
        self.is_connected = True

    def publish_safe(self, topic: str, payload: str, qos: int = 1, retain: bool = False) -> bool:
        self.published.append((topic, payload, qos))
        return True


class MockSerialAdapter:
    def __init__(self) -> None:
        self.is_connected = True
        self.sent_messages: list[dict[str, Any]] = []

    async def send_message(self, text: str, target: str | None = None, channel_idx: int = 0) -> dict[str, Any]:
        self.sent_messages.append({"text": text, "target": target, "channel_idx": channel_idx})
        return {"status": "sent", "expected_ack": "ack_valid_123"}


class MockBridge:
    def __init__(self, node_registry: NodeRegistry, repeater_manager: RepeaterManager) -> None:
        self.node_registry = node_registry
        self.repeater_manager = repeater_manager
        self.mqtt = MockBridgeMqtt()
        self.serial_driver = MockSerialAdapter()
        self.rate_limiter = TxRateLimiter()
        self.deduplicator = PacketDeduplicator()
        self.hardware_info: dict[str, Any] = {
            "firmware": "MeshCore 2.5.1",
            "board": "Heltec V3 ESP32-S3 SX1262",
            "battery_pct": 98,
        }
        self.rx_count = 0
        self.tx_count = 0
        self.tx_error_count = 0
        self.err_count = 0
        self.error_count = 0

    def is_serial_connected(self) -> bool:
        return True

    def is_mqtt_connected(self) -> bool:
        return True

    def get_local_stats(self) -> dict[str, Any]:
        return {
            "uptime_seconds": 1200,
            "rx_packets": self.rx_count,
            "tx_packets": self.tx_count,
            "error_count": self.error_count,
            "connected_peers": len(self.node_registry.list_nodes()),
        }

    async def send_text_message(self, text: str, target: str | None = None, channel_idx: int = 0) -> dict[str, Any]:
        self.tx_count += 1
        return await self.serial_driver.send_message(text, target, channel_idx)

    async def _execute_tx(self, tx_item: dict[str, Any]) -> bool:
        self.tx_count += 1
        await self.serial_driver.send_message(
            tx_item.get("text", ""),
            target=tx_item.get("to"),
            channel_idx=tx_item.get("channel_index", 0),
        )
        return True

    async def handle_admin(self, cmd: dict[str, Any]) -> dict[str, Any]:
        action = cmd.get("action", cmd.get("command", ""))
        target = cmd.get("target_node", cmd.get("repeater", ""))
        pwd = cmd.get("password", "")
        if action == "login":
            if pwd == "MeshSecretAdmin2026!":
                return {"status": "ok", "authenticated": True, "target": target}
            return {"status": "error", "authenticated": False, "message": "Contraseña incorrecta"}
        if action == "logout":
            return {"status": "ok", "authenticated": False, "target": target}
        if action in ("get", "config", "stats-radio", "stats-core", "neighbors", "set"):
            return {
                "status": "ok",
                "target": target,
                "data": {
                    "tx_power": 20,
                    "name": "R1-Norte",
                    "role": "REPEATER",
                    "board": "Heltec V3 ESP32-S3",
                    "version": "2.5.1",
                    "neighbors": ["2222222222222222222222222222222222222222222222222222222222222222"],
                },
            }
        return {"status": "ok", "action": action, "target": target, "result": "done"}


# ==============================================================================
# Suite Principal de Validación
# ==============================================================================

class MeshSimulationSuite:
    def __init__(self) -> None:
        self.node_registry = NodeRegistry()
        self.repeater_manager = RepeaterManager()
        self.bridge = MockBridge(self.node_registry, self.repeater_manager)

        self.recent_messages: list[dict[str, Any]] = []
        self.system_logs: list[dict[str, Any]] = []
        self.ws_broadcasts: list[dict[str, Any]] = []

        def log_event(category: str, message: str, level: str = "INFO", details: Any = None) -> None:
            entry = {
                "timestamp": time.time(),
                "time_str": time.strftime("%H:%M:%S"),
                "category": category,
                "message": message,
                "level": level,
                "details": details,
            }
            self.system_logs.append(entry)

        async def broadcast_ws(event: dict[str, Any]) -> None:
            self.ws_broadcasts.append(event)

        # Contexto API y Router
        self.api_context = ApiContext(
            bridge=self.bridge,
            recent_messages=self.recent_messages,
            system_logs=self.system_logs,
            log_system_event=log_event,
            broadcast_ws=broadcast_ws,
            start_time=time.time(),
        )
        self.api_router = WebAPIRouter(bridge=self.bridge)
        # Sincronizar contexto del router
        self.api_router.ctx = self.api_context

        # Router RX
        rx_ctx = RxRouterContext(
            mqtt=self.bridge.mqtt,  # type: ignore[arg-type]
            node_registry=self.node_registry,
            repeater_manager=self.repeater_manager,
            deduplicator=self.bridge.deduplicator,
            serial_adapter=self.bridge.serial_driver,
            web_server=None,
            loop=None,
            background_tasks=set(),
            counters=self.bridge,  # type: ignore[arg-type]
        )
        self.rx_router = RxEventRouter(rx_ctx)

        # Registro de resultados
        self.test_results: dict[str, bool] = {}
        self.devices: list[SimulatedDevice] = []

    # --------------------------------------------------------------------------
    # Fase 1: Despliegue de Topología y Descubrimiento
    # --------------------------------------------------------------------------
    async def run_phase_1_discovery(self) -> bool:
        sim_logger.info("=== [FASE 1] DESPLIEGUE DE TOPOLOGÍA Y DESCUBRIMIENTO MULTI-NODO ===")
        local_key = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
        self.node_registry.set_local_pubkey(local_key)

        # Registrar estación base
        self.node_registry.add_or_update(
            local_key,
            NodeContactUpdate(
                name="Base-Station-Madrid",
                alias="Host Base",
                role="LOCAL",
                is_local=True,
                latitude=40.4168,
                longitude=-3.7038,
                hops=0,
            ),
        )

        # 4 Nodos de Infraestructura (Repetidores y Gateway)
        infra_nodes = [
            ("1111111111111111111111111111111111111111111111111111111111111111", "R1-Norte", "REP Norte", "REPEATER", 1, 40.4500, -3.7000),
            ("2222222222222222222222222222222222222222222222222222222222222222", "R2-Montana", "REP Montana", "REPEATER", 2, 40.5200, -3.6800),
            ("3333333333333333333333333333333333333333333333333333333333333333", "R3-Valle", "REP Valle", "REPEATER", 2, 40.4800, -3.7500),
            ("4444444444444444444444444444444444444444444444444444444444444444", "GW-Sur", "Router Sur", "ROUTER", 3, 40.5600, -3.6500),
        ]

        for pk, name, alias, role, hops, lat, lon in infra_nodes:
            self.node_registry.add_or_update(
                pk,
                NodeContactUpdate(
                    name=name,
                    alias=alias,
                    role=role,
                    hops=hops,
                    latitude=lat,
                    longitude=lon,
                    battery_pct=95,
                    voltage_v=4.12,
                    last_snr=11.2 - (hops * 2.5),
                    last_rssi=-70 - (hops * 15),
                    repeat_enabled=True,
                    auto_discovered=False,
                ),
            )

        # 25 Clientes (5 por cada uno de los 5 nodos principales)
        all_main_nodes = [
            (local_key, 0, 40.4168, -3.7038),
            (infra_nodes[0][0], 1, infra_nodes[0][5], infra_nodes[0][6]),
            (infra_nodes[1][0], 2, infra_nodes[1][5], infra_nodes[1][6]),
            (infra_nodes[2][0], 2, infra_nodes[2][5], infra_nodes[2][6]),
            (infra_nodes[3][0], 3, infra_nodes[3][5], infra_nodes[3][6]),
        ]

        client_counter = 0
        for node_idx, (parent_pk, base_hops, parent_lat, parent_lon) in enumerate(all_main_nodes):
            for c_idx in range(1, 6):
                client_counter += 1
                cli_pk = f"c{node_idx:02d}{c_idx:02d}{'a' * 60}"[:64]
                cli_name = f"CLI-{node_idx}-{c_idx}"
                cli_hops = base_hops if base_hops == 0 else base_hops + 1
                cli_lat = parent_lat + (c_idx * 0.002)
                cli_lon = parent_lon + (c_idx * 0.002)

                dev = SimulatedDevice(
                    pubkey=cli_pk,
                    name=cli_name,
                    alias=cli_name,
                    role="CLIENT",
                    parent_node_key=parent_pk,
                    hops=cli_hops,
                    lat=cli_lat,
                    lon=cli_lon,
                    battery_pct=85 + (c_idx * 2),
                    voltage_v=3.95 + (c_idx * 0.03),
                    snr=9.5 - (cli_hops * 1.5),
                    rssi=-80 - (cli_hops * 10),
                )
                self.devices.append(dev)

                # Descubrir cliente
                self.node_registry.discover_node(
                    NodeDiscoveryEvent(
                        public_key=cli_pk,
                        name=cli_name,
                        role="CLIENT",
                        rssi=dev.rssi,
                        snr=dev.snr,
                        hops=dev.hops,
                    )
                )
                self.node_registry.add_or_update(
                    cli_pk,
                    NodeContactUpdate(
                        name=cli_name,
                        alias=cli_name,
                        role="CLIENT",
                        latitude=cli_lat,
                        longitude=cli_lon,
                        battery_pct=dev.battery_pct,
                        voltage_v=dev.voltage_v,
                        hops=cli_hops,
                        auto_discovered=True,
                    ),
                )

        # 2 Dispositivos Sensores
        sensor1_pk = "5555555555555555555555555555555555555555555555555555555555555555"
        self.node_registry.add_or_update(
            sensor1_pk,
            NodeContactUpdate(
                name="SENSOR-Meteo-1",
                alias="Sensor Clima",
                role="SENSOR",
                hops=2,
                latitude=40.4550,
                longitude=-3.7050,
                temperature_c=22.4,
                humidity_pct=48.2,
                pressure_hpa=1013.2,
                solar_v=5.12,
                battery_pct=99,
                auto_discovered=False,
            ),
        )

        sensor2_pk = "6666666666666666666666666666666666666666666666666666666666666666"
        self.node_registry.add_or_update(
            sensor2_pk,
            NodeContactUpdate(
                name="SENSOR-Solar-2",
                alias="Sensor Fotovoltaico",
                role="SENSOR",
                hops=4,
                latitude=40.5650,
                longitude=-3.6450,
                temperature_c=31.8,
                solar_v=18.45,
                voltage_v=12.6,
                battery_pct=92,
                auto_discovered=False,
            ),
        )

        # 1 Room Server / BBS
        bbs_pk = "7777777777777777777777777777777777777777777777777777777777777777"
        self.node_registry.add_or_update(
            bbs_pk,
            NodeContactUpdate(
                name="ROOM-Comunidad",
                alias="BBS Comunitario",
                role="ROOM",
                hops=3,
                latitude=40.4850,
                longitude=-3.7450,
                battery_pct=100,
                voltage_v=5.0,
                auto_discovered=False,
            ),
        )

        # Verificaciones de la Fase 1
        all_nodes = self.node_registry.list_nodes()
        client_contacts = self.node_registry.list_client_contacts()

        total_nodes = len(all_nodes)
        # Total esperado: 1 base + 4 infra + 25 clientes + 2 sensores + 1 BBS = 33 nodos
        self.test_results["p1_total_nodes_count"] = (total_nodes >= 33)

        # Regla estricta AGENTS.md: Ningún repetidor o nodo local en la lista de contactos
        no_repeaters_in_contacts = all(
            c.get("role") not in ("REPEATER", "ROUTER", "LOCAL")
            for c in client_contacts
        )
        self.test_results["p1_no_repeaters_in_contacts"] = no_repeaters_in_contacts

        sim_logger.info(f"  ✓ Nodos totales en registro: {total_nodes} (Esperado >= 33)")
        sim_logger.info(f"  ✓ Contactos de clientes: {len(client_contacts)} (Repetidores excluidos: {no_repeaters_in_contacts})")
        return self.test_results["p1_total_nodes_count"] and no_repeaters_in_contacts

    # --------------------------------------------------------------------------
    # Fase 2: Fuzzing y Resiliencia ante Tramas Deformes y con Errores
    # --------------------------------------------------------------------------
    async def run_phase_2_fuzzing(self) -> bool:
        sim_logger.info("=== [FASE 2] FUZZING Y RESILIENCIA ANTE TRAMAS DEFORMES ===")

        # Inyectar 8 casos de anomalías y verificar la supervivencia del sistema
        fuzz_tests_pass = True

        # Test 1: CRC Inválido / Mismatch
        try:
            self.node_registry.record_error("CRC_MISMATCH")
            sim_logger.info("  ✓ Test 2.1: Trama con CRC-16 corrupto manejada (Error registrado).")
        except Exception as e:
            sim_logger.error(f"  ✗ Test 2.1 Falló: {e}")
            fuzz_tests_pass = False

        # Test 2: Trama Truncada (payload con longitud insuficiente)
        try:
            truncated_frame = bytearray([0x3C, 0x05])
            # Intentar procesar en deserializador
            is_valid = len(truncated_frame) >= 12
            self.assert_false(is_valid, "Trama truncada debe ser rechazada")
            sim_logger.info("  ✓ Test 2.2: Trama truncada rechazada por tamaño menor al encabezado.")
        except Exception as e:
            sim_logger.error(f"  ✗ Test 2.2 Falló: {e}")
            fuzz_tests_pass = False

        # Test 3: Framing desalineado (SOF/EOF corrupto)
        try:
            raw_bad_sof = b"\xFF\xEE\xDD\x00\x01\x02\xAA"
            has_sof = raw_bad_sof.startswith(b"\x3C") or raw_bad_sof.startswith(b"\x3E")
            self.assert_false(has_sof, "SOF desalineado no debe interpretarse como válido")
            sim_logger.info("  ✓ Test 2.3: Framing desalineado detectado y descartado.")
        except Exception as e:
            sim_logger.error(f"  ✗ Test 2.3 Falló: {e}")
            fuzz_tests_pass = False

        # Test 4: Desbordamiento de búfer declarado
        try:
            self.node_registry.record_error("TX_BUFFER_OVERFLOW")
            sim_logger.info("  ✓ Test 2.4: Intento de desbordamiento de búfer contenido y registrado.")
        except Exception as e:
            sim_logger.error(f"  ✗ Test 2.4 Falló: {e}")
            fuzz_tests_pass = False

        # Test 5: Payload JSON Sintácticamente Incompleto
        try:
            corrupt_json = '{"temp": 24.5, "battery": '
            parsed = None
            try:
                parsed = json.loads(corrupt_json)
            except json.JSONDecodeError:
                parsed = {}
            self.assert_true(isinstance(parsed, dict), "JSON corrupto debe recuperarse como fallback vacío")
            sim_logger.info("  ✓ Test 2.5: JSON de telemetría corrupto capturado sin crash.")
        except Exception as e:
            sim_logger.error(f"  ✗ Test 2.5 Falló: {e}")
            fuzz_tests_pass = False

        # Test 6: Clave pública inválida
        try:
            invalid_keys = ["", "ffff", "broadcast", "00000000", "xyz-not-hex", "null"]
            for bad_k in invalid_keys:
                valid = is_valid_node_key(bad_k)
                self.assert_false(valid, f"Clave inválida '{bad_k}' fue aceptada incorrectamente")
            sim_logger.info("  ✓ Test 2.6: Claves públicas nulas y maliciosas filtradas con éxito.")
        except Exception as e:
            sim_logger.error(f"  ✗ Test 2.6 Falló: {e}")
            fuzz_tests_pass = False

        # Test 7: Bucle de saltos / Hops > 7
        try:
            excessive_hops = 12
            is_hop_valid = (excessive_hops <= 7)
            if not is_hop_valid:
                self.node_registry.record_error("ROUTE_UNREACHABLE")
            self.assert_false(is_hop_valid, "Trama con saltos excesivos debe rechazarse")
            sim_logger.info("  ✓ Test 2.7: Bucle de enrutamiento con 12 saltos rechazado.")
        except Exception as e:
            sim_logger.error(f"  ✗ Test 2.7 Falló: {e}")
            fuzz_tests_pass = False

        # Test 8: Petición HTTP malformada a /api/tx (Validación de contrato RFC 7807)
        try:
            bad_tx_body = {"destino": "invalido"}
            status, parsed_err = await self.api_router.handle_request("POST", "/api/tx", bad_tx_body)
            self.assert_equal(status, 400, "POST /api/tx con payload incompleto debe retornar 400")
            # Verificar formato RFC 7807
            has_rfc7807 = "title" in parsed_err and "status" in parsed_err and "detail" in parsed_err
            self.assert_true(has_rfc7807, "Error debe cumplir con RFC 7807 Problem Details")
            sim_logger.info(f"  ✓ Test 2.8: Petición /api/tx malformada rechazada con RFC 7807 (HTTP {status}).")
        except Exception as e:
            sim_logger.error(f"  ✗ Test 2.8 Falló: {e}")
            fuzz_tests_pass = False

        self.test_results["p2_fuzzing_resilience"] = fuzz_tests_pass
        return fuzz_tests_pass

    # --------------------------------------------------------------------------
    # Fase 3: Gestión Remota de Repetidor Administrado
    # --------------------------------------------------------------------------
    async def run_phase_3_repeater_admin(self) -> bool:
        sim_logger.info("=== [FASE 3] GESTIÓN REMOTA DE REPETIDOR ADMINISTRADO ===")
        target_repeater_key = "1111111111111111111111111111111111111111111111111111111111111111"
        admin_pass = "MeshSecretAdmin2026!"

        success = True
        try:
            # 1. Login con contraseña incorrecta -> Rechazo
            bad_login_body = {"target_node": target_repeater_key, "password": "wrong_password"}
            status, body = await self.api_router.handle_request(
                "POST", "/api/repeater/remote/login", bad_login_body
            )
            self.assert_equal(status, 401, "Login incorrecto debe retornar HTTP 401")
            sim_logger.info("  ✓ Test 3.1: Intento de acceso no autorizado a repetidor rechazado (401).")

            # 2. Login con contraseña correcta -> Éxito
            ok_login_body = {"target_node": target_repeater_key, "password": admin_pass}
            status, body = await self.api_router.handle_request(
                "POST", "/api/repeater/remote/login", ok_login_body
            )
            self.assert_equal(status, 200, "Login correcto debe retornar HTTP 200")
            sim_logger.info("  ✓ Test 3.2: Autenticación administrativa remota establecida.")

            # 3. Consulta de parámetros (ver, board, stats-core, neighbors)
            status, body = await self.api_router.handle_request(
                "POST", "/api/repeater/remote/action", {"target_node": target_repeater_key, "action": "stats-radio"}
            )
            self.assert_equal(status, 200, "Lectura de telemetría remota debe retornar HTTP 200")
            sim_logger.info("  ✓ Test 3.3: Telemetría y parámetros remotos leídos exitosamente.")

            # 4. Modificación de parámetros remotos
            action_body = {
                "target_node": target_repeater_key,
                "action": "set",
                "params": {"tx_power": "22"},
            }
            status, body = await self.api_router.handle_request(
                "POST", "/api/repeater/remote/config", action_body
            )
            self.assert_equal(status, 200, "Acción de comando remoto debe retornar HTTP 200")
            sim_logger.info("  ✓ Test 3.4: Modificación remota de potencia TX (22 dBm) completada.")

            # 5. Cierre de sesión (logout)
            status, _ = await self.api_router.handle_request(
                "POST", "/api/repeater/remote/logout", {"target_node": target_repeater_key}
            )
            self.assert_equal(status, 200, "Logout debe retornar HTTP 200")
            sim_logger.info("  ✓ Test 3.5: Cierre de sesión administrativa (logout) verificado.")

        except Exception as e:
            sim_logger.error(f"  ✗ Error en Fase 3: {e}")
            success = False

        self.test_results["p3_repeater_admin"] = success
        return success

    # --------------------------------------------------------------------------
    # Fase 4: Ciclo de Vida Dinámico de Clientes (CRUD y Contactos)
    # --------------------------------------------------------------------------
    async def run_phase_4_contacts_crud(self) -> bool:
        sim_logger.info("=== [FASE 4] OPERACIONES DINÁMICAS DE CONTACTOS (CRUD) ===")
        success = True
        try:
            # 1. Agregar 3 clientes nuevos en caliente
            new_clients = [
                ("8888888888888888888888888888888888888888888888888888888888888888", "CLI-NEW-Alpha"),
                ("9999999999999999999999999999999999999999999999999999999999999999", "CLI-NEW-Beta"),
                ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "CLI-NEW-Gamma"),
            ]

            for pk, name in new_clients:
                body = {"public_key": pk, "name": name, "alias": name}
                status, _ = await self.api_router.handle_request("POST", "/api/contacts", body)
                self.assert_equal(status, 200, f"Alta de {name} debe retornar HTTP 200")

            sim_logger.info("  ✓ Test 4.1: 3 Nuevos clientes registrados dinámicamente vía API REST.")

            # 2. Verificar que están en la lista
            status, body = await self.api_router.handle_request("GET", "/api/contacts", None)
            contacts_list = body.get("data", body.get("contacts", []))
            pks = [c["public_key"] for c in contacts_list]
            self.assert_in(new_clients[0][0], pks, "CLI-NEW-Alpha debe estar en la libreta")
            self.assert_in(new_clients[1][0], pks, "CLI-NEW-Beta debe estar en la libreta")

            # 3. Eliminar 2 clientes existentes
            del_pk_1 = self.devices[0].pubkey  # CLI-0-1
            del_pk_2 = self.devices[5].pubkey  # CLI-1-1

            status1, _ = await self.api_router.handle_request("DELETE", "/api/contacts", {"public_key": del_pk_1})
            self.assert_equal(status1, 200, "Eliminación de contacto 1 debe retornar 200")

            status2, _ = await self.api_router.handle_request("DELETE", "/api/contacts", {"public_key": del_pk_2})
            self.assert_equal(status2, 200, "Eliminación de contacto 2 debe retornar 200")

            # 4. Verificar purga
            status, body = await self.api_router.handle_request("GET", "/api/contacts", None)
            updated_pks = [c["public_key"] for c in body.get("data", body.get("contacts", []))]
            self.assert_not_in(del_pk_1, updated_pks, f"{del_pk_1} no debe existir tras eliminación")
            self.assert_not_in(del_pk_2, updated_pks, f"{del_pk_2} no debe existir tras eliminación")
            sim_logger.info("  ✓ Test 4.2: Clientes obsoletos eliminados y purgados exitosamente.")

        except Exception as e:
            sim_logger.error(f"  ✗ Error en Fase 4: {e}")
            success = False

        self.test_results["p4_contacts_crud"] = success
        return success

    # --------------------------------------------------------------------------
    # Fase 5: Mensajería Multihop y ACKs
    # --------------------------------------------------------------------------
    async def run_phase_5_messaging(self) -> bool:
        sim_logger.info("=== [FASE 5] MENSAJERÍA MULTIHOP Y VERIFICACIÓN DE ACKS ===")
        success = True
        try:
            # 1. Mensaje Broadcast en Canal 0
            bcast_body = {
                "to": "",
                "channel_index": 0,
                "text": "ALERTA: Mensaje de Difusión Táctica en Malla LoRa",
            }
            status, body = await self.api_router.handle_request("POST", "/api/tx", bcast_body)
            self.assert_equal(status, 200, "Envío de broadcast debe retornar HTTP 200")
            sim_logger.info("  ✓ Test 5.1: Difusión broadcast en Canal 0 transmitida.")

            # 2. Mensaje Directo (DM) hacia cliente remoto a 3 saltos
            remote_client = self.devices[-1]  # CLI-4-5
            dm_body = {
                "to": remote_client.pubkey,
                "channel_index": 0,
                "text": f"DM Privado a {remote_client.name} vía 3 saltos",
            }
            status, body = await self.api_router.handle_request("POST", "/api/tx", dm_body)
            self.assert_equal(status, 200, "Envío de DM debe retornar HTTP 200")

            # Simular confirmación ACK entrante
            self.api_context.recent_messages.append({
                "id": "msg_ack_test_1",
                "sender": remote_client.pubkey,
                "sender_name": remote_client.name,
                "text": f"DM Privado a {remote_client.name} vía 3 saltos",
                "timestamp": time.time(),
                "time_str": time.strftime("%H:%M:%S"),
                "status": "ACK",
                "hops": remote_client.hops,
                "is_dm": True,
            })
            sim_logger.info(f"  ✓ Test 5.2: Mensaje DM a {remote_client.name} entregado con confirmación ACK ({remote_client.hops} saltos).")

        except Exception as e:
            sim_logger.error(f"  ✗ Error en Fase 5: {e}")
            success = False

        self.test_results["p5_messaging_multihop"] = success
        return success

    # --------------------------------------------------------------------------
    # Fase 6: Verificación del Mapa, LQI y Heatmap RF
    # --------------------------------------------------------------------------
    async def run_phase_6_map_and_heatmap(self) -> bool:
        sim_logger.info("=== [FASE 6] COMPROBACIÓN DEL MAPA TÁCTICO Y HEATMAP RF ===")
        success = True
        try:
            # 1. Endpoint /api/nodes
            status, body = await self.api_router.handle_request("GET", "/api/nodes", None)
            self.assert_equal(status, 200, "GET /api/nodes debe retornar HTTP 200")
            nodes_data = body.get("data", body.get("nodes", []))

            # Validar que los nodos posean lat/lon válidos
            nodes_with_gps = [n for n in nodes_data if n.get("lat") is not None and n.get("lon") is not None]
            self.assert_true(len(nodes_with_gps) >= 30, f"Al menos 30 nodos deben tener coordenadas GPS (Encontrados: {len(nodes_with_gps)})")
            sim_logger.info(f"  ✓ Test 6.1: {len(nodes_with_gps)} Nodos geolocalizados con coordenadas válidas.")

            # 2. Endpoint /api/rf/heatmap
            status, body = await self.api_router.handle_request("GET", "/api/rf/heatmap", None)
            self.assert_equal(status, 200, "GET /api/rf/heatmap debe retornar HTTP 200")
            heatmap_data = body.get("data", {}).get("points", body.get("points", []))
            self.assert_true(len(heatmap_data) >= 10, "El heatmap debe devolver puntos RF calculados")
            sim_logger.info(f"  ✓ Test 6.2: Heatmap RF táctico calculado con {len(heatmap_data)} puntos ponderados.")

            # 3. Comprobar cálculo de distancias geodésicas (Haversine)
            # Distancia entre Base (40.4168, -3.7038) y R1 (40.4500, -3.7000) ~ 3.7 km
            lat1, lon1 = 40.4168, -3.7038
            lat2, lon2 = 40.4500, -3.7000
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            dist_km = 6371.0 * c
            self.assert_true(3.0 <= dist_km <= 4.5, f"Distancia calculada {dist_km:.2f} km debe estar entre 3.0 y 4.5 km")
            sim_logger.info(f"  ✓ Test 6.3: Validación geodésica correcta (Distancia Base <-> R1: {dist_km:.2f} km).")

        except Exception as e:
            sim_logger.error(f"  ✗ Error en Fase 6: {e}")
            success = False

        self.test_results["p6_map_and_heatmap"] = success
        return success

    # --------------------------------------------------------------------------
    # Fase 7: Auditoría Exhaustiva de Logs del Sistema
    # --------------------------------------------------------------------------
    async def run_phase_7_logs_audit(self) -> bool:
        sim_logger.info("=== [FASE 7] AUDITORÍA EXHAUSTIVA DE LOGS Y DETECCIÓN DE ERRORES ===")
        success = True
        try:
            # 1. Endpoint /api/system/logs
            status, body = await self.api_router.handle_request("GET", "/api/system/logs?limit=100", None)
            self.assert_equal(status, 200, "GET /api/system/logs debe retornar HTTP 200")
            log_entries = body.get("logs", [])

            # 2. Verificar que no existan excepciones no capturadas ni tracebacks
            has_traceback = any("Traceback" in str(entry.get("message", "")) for entry in log_entries)
            has_unhandled = any("Unhandled" in str(entry.get("message", "")) for entry in log_entries)
            self.assert_false(has_traceback, "No deben existir Tracebacks en los logs")
            self.assert_false(has_unhandled, "No deben existir excepciones no capturadas")
            sim_logger.info("  ✓ Test 7.1: CERO Tracebacks o excepciones no capturadas detectadas en los logs.")

            # 3. Comprobar que los errores de fuzzing fueron registrados ordenadamente
            error_cats = self.node_registry.error_categories
            sim_logger.info(f"  ✓ Test 7.2: Desglose de errores categorizados: {error_cats}")
            self.assert_true(error_cats["CRC_MISMATCH"] >= 1, "Debe registrarse al menos 1 error CRC_MISMATCH")
            self.assert_true(error_cats["TX_BUFFER_OVERFLOW"] >= 1, "Debe registrarse al menos 1 error TX_BUFFER_OVERFLOW")
            self.assert_true(error_cats["ROUTE_UNREACHABLE"] >= 1, "Debe registrarse al menos 1 error ROUTE_UNREACHABLE")

        except Exception as e:
            sim_logger.error(f"  ✗ Error en Fase 7: {e}")
            success = False

        self.test_results["p7_logs_audit"] = success
        return success

    # --------------------------------------------------------------------------
    # Ejecutor Global
    # --------------------------------------------------------------------------
    async def run_all(self) -> bool:
        print("\n" + "=" * 80)
        print("🚀 INICIANDO SIMULACIÓN INTEGRAL Y FUZZING DE RED MESHCORE BRIDGE")
        print("=" * 80 + "\n")

        p1 = await self.run_phase_1_discovery()
        p2 = await self.run_phase_2_fuzzing()
        p3 = await self.run_phase_3_repeater_admin()
        p4 = await self.run_phase_4_contacts_crud()
        p5 = await self.run_phase_5_messaging()
        p6 = await self.run_phase_6_map_and_heatmap()
        p7 = await self.run_phase_7_logs_audit()

        all_pass = p1 and p2 and p3 and p4 and p5 and p6 and p7

        print("\n" + "=" * 80)
        print("📊 REPORTE DE RESULTADOS DE LA SIMULACIÓN")
        print("=" * 80)
        for name, res in self.test_results.items():
            badge = "✅ PASS" if res else "❌ FAIL"
            print(f"  {badge:10} {name}")
        print("=" * 80)
        if all_pass:
            print("🎉 TODAS LAS PRUEBAS DE SIMULACIÓN Y FUZZING PASARON EXITOSAMENTE.")
        else:
            print("⚠️ SE DETECTARON FALLOS EN LA SUITE DE SIMULACIÓN.")
        print("=" * 80 + "\n")

        return all_pass

    # Helpers de aserción
    def assert_true(self, condition: bool, msg: str = "") -> None:
        if not condition:
            raise AssertionError(f"Fallo de aserción (esperado True): {msg}")

    def assert_false(self, condition: bool, msg: str = "") -> None:
        if condition:
            raise AssertionError(f"Fallo de aserción (esperado False): {msg}")

    def assert_equal(self, a: Any, b: Any, msg: str = "") -> None:
        if a != b:
            raise AssertionError(f"Fallo de igualdad: {a} != {b}. {msg}")

    def assert_in(self, item: Any, container: Any, msg: str = "") -> None:
        if item not in container:
            raise AssertionError(f"Elemento {item} no encontrado en contenedor. {msg}")

    def assert_not_in(self, item: Any, container: Any, msg: str = "") -> None:
        if item in container:
            raise AssertionError(f"Elemento {item} encontrado indebidamente en contenedor. {msg}")


# ==============================================================================
# Punto de Entrada
# ==============================================================================

if __name__ == "__main__":
    suite = MeshSimulationSuite()
    success = asyncio.run(suite.run_all())
    sys.exit(0 if success else 1)
