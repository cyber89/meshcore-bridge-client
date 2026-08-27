"""
Unit and Integration tests for Local Node Configuration and Authenticated Remote Repeater Management.
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from src.admin_handler import AdminCommandHandler, AdminContext
from src.repeater_manager import RepeaterManager
from src.web.api_router import WebAPIRouter


class TestNodeAndRepeaterConfig(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mock_mc = MagicMock()
        self.mock_mc.self_info = {
            "name": "Test_Base_Station",
            "public_key": "aabbccddeeff",
            "tx_power": 20,
            "radio_freq": 915.0,
            "sf": 11,
            "bw": 250,
        }
        self.mock_mc.commands = MagicMock()
        self.mock_mc.commands.set_name = AsyncMock()
        self.mock_mc.commands.set_tx_power = AsyncMock()
        self.mock_mc.commands.reboot = AsyncMock()

        self.mock_registry = MagicMock()
        self.mock_registry.list_nodes.return_value = []
        self.mock_registry.get_count.return_value = 0
        self.mock_registry.is_local_key.return_value = False

        self.repeater_mgr = RepeaterManager()
        self.mock_mqtt = MagicMock()
        self.mock_mqtt.publish_safe = MagicMock()

        self.dispatched_txs: list[dict[str, Any]] = []

        async def _mock_tx(item: dict[str, Any]) -> dict[str, Any]:
            self.dispatched_txs.append(item)
            return {"status": "dispatched"}

        self.ctx = AdminContext(
            mc_provider=lambda: self.mock_mc,
            node_registry=self.mock_registry,
            repeater_manager=self.repeater_mgr,
            mqtt=self.mock_mqtt,
            execute_tx=_mock_tx,
        )
        self.admin_handler = AdminCommandHandler(self.ctx)

        self.mock_bridge = MagicMock()
        self.mock_bridge.admin_handler = self.admin_handler
        self.mock_bridge.handle_admin = self.admin_handler.handle
        self.mock_bridge.node_registry = self.mock_registry
        self.mock_bridge.rate_limiter = MagicMock()
        self.mock_bridge.rate_limiter.get_queue_depth.return_value = 0
        self.mock_bridge.store_and_forward = MagicMock()
        self.mock_bridge.store_and_forward.count = AsyncMock(return_value=0)

        self.router = WebAPIRouter(self.mock_bridge)

    def test_repeater_manager_payload_builder(self) -> None:
        """Verifica la serialización precisa de comandos para firmware MeshCore."""
        # Login
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("login", {"password": "admin_secret_123"}),
            "login admin_secret_123",
        )
        # Radio params
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("set_tx_power", {"power": 22}),
            "set tx 22",
        )
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("set_name", {"name": "Mountain_Alpha"}),
            "set name Mountain_Alpha",
        )
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("set_freq", {"freq": 868.0}),
            "set freq 868.0",
        )
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("set_sf", {"sf": 12}),
            "set sf 12",
        )
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("set_bw", {"bw": 125}),
            "set bw 125",
        )
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("set_repeat", {"repeat": True}),
            "set repeat on",
        )
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("set_hop_limit", {"hop_limit": 5}),
            "set hop_limit 5",
        )
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("set_admin_password", {"password": "new_pin_999"}),
            "set admin.password new_pin_999",
        )
        # Direct actions
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("reboot", {}),
            "reboot",
        )
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("clear stats", {}),
            "clear stats",
        )

    async def test_local_node_get_and_set_config(self) -> None:
        """Prueba consulta y actualización de parámetros del nodo local."""
        # 1. GET local config
        code, resp = await self.router.handle_request("GET", "/api/node/config")
        self.assertEqual(code, 200)
        self.assertEqual(resp["data"]["name"], "Test_Base_Station")
        self.assertEqual(resp["data"]["tx_power"], 20)

        # 2. POST local config
        update_payload = {
            "name": "Base_Station_Pro_v3",
            "tx_power": 22,
            "frequency": 915.0,
            "spreading_factor": 10,
            "bandwidth": 500,
            "hop_limit": 4,
            "telemetry_interval": 120,
        }
        code, resp = await self.router.handle_request("POST", "/api/node/config", update_payload)
        self.assertEqual(code, 200)
        self.assertEqual(resp["status"], "ok")
        self.mock_mc.commands.set_name.assert_awaited_with("Base_Station_Pro_v3")
        self.mock_mc.commands.set_tx_power.assert_awaited_with(22)

        # 3. POST local reboot
        code, resp = await self.router.handle_request("POST", "/api/node/reboot")
        self.assertEqual(code, 200)
        self.mock_mc.commands.reboot.assert_awaited()

    async def test_remote_repeater_login_and_config(self) -> None:
        """Prueba login y configuración remota autenticada de un repetidor vecino."""
        # 1. Login remoto fallido (sin respuesta del repetidor por RF o clave incorrecta)
        code_fail, resp_fail = await self.router.handle_request(
            "POST",
            "/api/repeater/remote/login",
            {"target_node": "a1b2c3d4e5f6", "password": "wrong_password"},
        )
        self.assertEqual(code_fail, 401)
        self.assertEqual(resp_fail["status"], "error")

        # 2. Login remoto exitoso con send_login_sync
        self.mock_mc.commands.send_login_sync = AsyncMock(return_value=MagicMock(type="LOGIN_SUCCESS"))
        code, resp = await self.router.handle_request(
            "POST",
            "/api/repeater/remote/login",
            {"target_node": "a1b2c3d4e5f6", "password": "repeater_secret"},
        )
        self.assertEqual(code, 200)
        self.assertEqual(resp["status"], "ok")
        self.assertTrue(resp["data"]["authenticated"])

        # 3. Configuración remota múltiple
        self.dispatched_txs.clear()
        config_payload = {
            "target_node": "a1b2c3d4e5f6",
            "password": "repeater_secret",
            "params": {
                "name": "Tower_Alpha_West",
                "tx_power": 22,
                "repeat": True,
                "hop_limit": 4,
            },
        }
        code, resp = await self.router.handle_request("POST", "/api/repeater/remote/config", config_payload)
        self.assertEqual(code, 200)
        # Login + 4 set commands = 5 transmissions
        self.assertEqual(len(self.dispatched_txs), 5)
        self.assertEqual(self.dispatched_txs[0]["text"], "cmd login repeater_secret")
        self.assertIn("cmd set name Tower_Alpha_West", [tx["text"] for tx in self.dispatched_txs])
        self.assertIn("cmd set tx 22", [tx["text"] for tx in self.dispatched_txs])
        self.assertIn("cmd set repeat on", [tx["text"] for tx in self.dispatched_txs])
        self.assertIn("cmd set hop_limit 4", [tx["text"] for tx in self.dispatched_txs])

        # 4. Acción remota (reboot del repetidor)
        self.dispatched_txs.clear()
        action_payload = {
            "target_node": "a1b2c3d4e5f6",
            "password": "repeater_secret",
            "action": "reboot",
        }
        code, resp = await self.router.handle_request("POST", "/api/repeater/remote/action", action_payload)
        self.assertEqual(code, 200)
        self.assertEqual(self.dispatched_txs[0]["text"], "login repeater_secret")
        self.assertEqual(self.dispatched_txs[1]["text"], "reboot")

    def test_record_incoming_telemetry_with_known_and_unknown_nodes(self) -> None:
        """Verifica que la telemetría identifique al repetidor por nombre o prefijo y registre todas las métricas."""
        # 1. Caso con repetidor registrado en NodeRegistry
        mock_contact = MagicMock()
        mock_contact.public_key = "31d03b1f47d5affaea5052d392e3dfec4e1c35e75b62822309a5d68eba15df42"
        mock_contact.name = "Repetidor_Norte"
        mock_contact.alias = "Repetidor_Norte"
        self.mock_registry.get_by_key_or_prefix.side_effect = lambda key: mock_contact if "31d03b1f" in str(key) else None

        telem_data = {
            "pubkey_pre": "31d03b1f47d5",
            "battery_mv": 4120,
            "uptime_secs": 12345,
            "errors": 0,
            "queue_len": 0,
            "rssi": -65,
            "snr": 8.5,
        }
        self.router.record_incoming_event("telemetry_response", telem_data)

        # Verificar logs del sistema
        logs = list(self.router.recent_system_logs)
        last_log = logs[-1]
        self.assertEqual(last_log["source"], "telemetry")
        self.assertIn("Repetidor_Norte (31d03b1f)", last_log["message"])
        self.assertIn("4.12V", last_log["message"])
        self.assertIn("12345s", last_log["message"])
        self.assertIn("SNR 8.5dB", last_log["message"])
        self.assertIn("-65dBm", last_log["message"])
        self.assertNotIn("nodo anónimo", last_log["message"])

        # 2. Caso con nodo anónimo pero con prefijo conocido
        anon_data = {
            "pubkey_pre": "8d5accef196f",
            "temperature_c": 22.4,
            "humidity_pct": 55.0,
            "rssi": -72,
            "snr": 6.0,
        }
        self.router.record_incoming_event("telemetry", anon_data)
        logs = list(self.router.recent_system_logs)
        last_log = logs[-1]
        self.assertIn("nodo [8d5accef]", last_log["message"])
        self.assertIn("22.4°C", last_log["message"])
        self.assertIn("55.0%", last_log["message"])
        self.assertNotIn("nodo anónimo", last_log["message"])


if __name__ == "__main__":
    unittest.main()
