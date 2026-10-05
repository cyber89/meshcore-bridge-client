"""
Unit and Integration tests for Local Node Configuration and Authenticated Remote Repeater Management.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock

from meshcore.events import Event, EventType

from src.admin_handler import AdminCommandHandler, AdminContext
from src.rate_limiter import LoRaRadioConfig, TxRateLimiter
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
            "cr": 5,
        }
        self.mock_mc.commands = MagicMock()
        repeater_key = "a1b2c3d4e5f6" + "00" * 26
        self.mock_mc.contacts = {repeater_key: {"public_key": repeater_key, "adv_name": "Tower", "type": 2}}
        self.mock_mc.get_contact_by_key_prefix.side_effect = lambda key: next(
            (contact for pk, contact in self.mock_mc.contacts.items() if pk.startswith(key)), None
        )
        self.mock_mc.get_contact_by_name.return_value = None
        self.mock_mc.commands.set_name = AsyncMock(return_value=Event(EventType.OK, {}))
        self.mock_mc.commands.set_tx_power = AsyncMock(return_value=Event(EventType.OK, {}))
        self.mock_mc.commands.set_radio = AsyncMock(return_value=Event(EventType.OK, {}))
        self.mock_mc.commands.reboot = AsyncMock(return_value=Event(EventType.OK, {}))
        self.mock_mc.commands.add_contact = AsyncMock(return_value=Event(EventType.OK, {}))
        self.mock_mc._contacts = {}
        # Both login and CLI requests use SDK opcodes; MSG_SENT is dispatch only.
        self.mock_mc.commands.send_login = AsyncMock(return_value=Event(EventType.MSG_SENT, {}))
        self.mock_mc.commands.send_login_sync = AsyncMock(return_value=None)
        self.mock_mc.commands.send_cmd = AsyncMock(return_value=Event(EventType.MSG_SENT, {}))
        self.mock_mc.dispatcher.wait_for_event = AsyncMock(return_value=None)

        self.mock_registry = MagicMock()
        self.mock_registry.list_nodes.return_value = []
        self.mock_registry.get_count.return_value = 0
        self.mock_registry.is_local_key.return_value = False
        self.mock_registry.find_by_name.return_value = None
        self.mock_registry.get_by_key_or_prefix.return_value = None
        self.mock_registry.get_canonical_key.side_effect = lambda key: str(key)

        self.repeater_mgr = RepeaterManager(
            min_cmd_interval_s=0.0,
            min_telemetry_interval_s=0.0,
            min_ping_interval_s=0.0,
            min_traceroute_interval_s=0.0,
            min_neighbours_interval_s=0.0,
        )
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

    def _provide_trace_reply(self, flags: int, hashes: list[str]) -> None:
        """Return an explicit SDK trace event with the requested correlation tag."""
        self.mock_mc.commands.send_trace = AsyncMock(return_value=Event(EventType.MSG_SENT, {}))

        async def trace_reply(
            event_type: EventType, attribute_filters: dict[str, Any], timeout: Any,
        ) -> Event:
            self.assertEqual(event_type, EventType.TRACE_DATA)
            self.assertIsNone(timeout)
            payload: dict[str, Any] = {
                "tag": attribute_filters["tag"], "auth": 0, "flags": flags,
                "path_len": len(hashes),
            }
            if hashes:
                payload["path"] = [
                    {"hash": hop, "snr": 8.0 - index} for index, hop in enumerate(hashes)
                ] + [{"snr": 9.25}]
            return Event(EventType.TRACE_DATA, payload, {"tag": payload["tag"], "auth_code": 0})

        self.mock_mc.dispatcher.wait_for_event = AsyncMock(side_effect=trace_reply)

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
            self.repeater_mgr.build_repeater_command_payload(
                "set_radio", {"freq": 868.0, "sf": 12, "bw": 125, "cr": 5}
            ),
            "set radio 868.0,125,12,5",
        )
        # CommonCLI accepts a complete RF tuple remotely. Legacy set freq is
        # restricted to sender_timestamp == 0; these remote setters are unsupported.
        for action, params in (
            ("set_freq", {"freq": 868.0}), ("set_sf", {"sf": 12}),
            ("set_bw", {"bw": 125}), ("set_hop_limit", {"hop_limit": 5}),
        ):
            self.assertIsNone(self.repeater_mgr.build_repeater_command_payload(action, params))
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("set_repeat", {"repeat": True}),
            "set repeat on",
        )
        self.assertEqual(
            self.repeater_mgr.build_repeater_command_payload("set_admin_password", {"password": "new_pin_999"}),
            "password new_pin_999",
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

    async def test_post_config_radio_updates_frozen_radio_config(self) -> None:
        """Verifica que POST /api/config/radio actualice TxRateLimiter con radio_config inmutable sin FrozenInstanceError."""
        rl = TxRateLimiter(tx_interval_sec=0.1, radio_config=LoRaRadioConfig(sf=7, bw_khz=125.0, cr=5))
        self.ctx.rate_limiter = rl
        self.mock_bridge.rate_limiter = rl

        radio_payload = {
            "spreading_factor": 12,
            "bandwidth": 250.0,
            "coding_rate": 8,
            "frequency": 915.0,
        }
        code, resp = await self.router.handle_request("POST", "/api/config/radio", radio_payload)

        self.assertEqual(code, 200)
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["data"]["applied"]["spreading_factor"], 12)
        # Verificar que el objeto inmutable fue reemplazado de manera segura con nuevos parámetros
        self.assertEqual(rl.radio_config.sf, 12)
        self.assertEqual(rl.radio_config.bw_khz, 250.0)
        self.assertEqual(rl.radio_config.cr, 8)

    async def test_remote_repeater_login_and_config(self) -> None:
        """Prueba login y configuración remota autenticada de un repetidor vecino."""
        # 1. Login remoto fallido (sin respuesta del repetidor por RF o clave incorrecta)
        code_fail, resp_fail = await self.router.handle_request(
            "POST",
            "/api/repeater/remote/login",
            {"target_node": "a1b2c3d4e5f6", "password": "wrong_password"},
        )
        self.assertEqual(code_fail, 401)
        self.assertEqual(resp_fail["status"], 401)

        # 2. Login remoto exitoso con send_login_sync
        self.mock_mc.commands.send_login_sync = AsyncMock(return_value=SimpleNamespace(type=EventType.LOGIN_SUCCESS, payload={}))
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
            },
        }
        code, resp = await self.router.handle_request("POST", "/api/repeater/remote/config", config_payload)
        self.assertEqual(code, 200)
        # Authentication uses the SDK opcode, followed by three supported CLI writes.
        self.assertEqual(len(self.dispatched_txs), 0)
        self.mock_mc.commands.send_login_sync.assert_awaited()
        cli_commands = [call.args[1] for call in self.mock_mc.commands.send_cmd.await_args_list]
        self.assertEqual(cli_commands, [
            "00|set tx 22", "01|set repeat on", "02|set name Tower_Alpha_West",
        ])
        self.assertEqual(resp["data"]["status"], "dispatched")
        self.assertEqual(resp["data"]["applied"], {})
        self.assertEqual(resp["data"]["unconfirmed"], {
            "tx_power": 22, "repeat_enabled": True, "name": "Tower_Alpha_West",
        })

        # 4. Acción remota (reboot del repetidor)
        self.dispatched_txs.clear()
        self.mock_mc.commands.send_cmd.reset_mock()
        action_payload = {
            "target_node": "a1b2c3d4e5f6",
            "password": "repeater_secret",
            "action": "reboot",
        }
        code, resp = await self.router.handle_request("POST", "/api/repeater/remote/action", action_payload)
        self.assertEqual(code, 200)
        self.mock_mc.commands.send_login_sync.assert_awaited()
        self.assertEqual(len(self.dispatched_txs), 0)
        self.assertEqual(self.mock_mc.commands.send_cmd.await_args.args[1], "03|reboot")
        self.assertEqual(resp["data"]["status"], "dispatched")

    async def test_remote_hop_limit_rejects_batch_before_login_or_commands(self) -> None:
        """Unsupported remote fields cannot turn a valid name write into a partial dispatch."""
        code, resp = await self.router.handle_request("POST", "/api/repeater/remote/config", {
            "target_node": "a1b2c3d4e5f6", "password": "repeater_secret",
            "params": {"name": "After", "hop_limit": 4},
        })
        self.assertEqual(code, 400)
        self.assertEqual(resp["status"], 400)
        self.assertIn("hop_limit", resp["detail"])
        self.mock_mc.commands.send_login_sync.assert_not_awaited()
        self.mock_mc.commands.send_cmd.assert_not_awaited()
        self.assertEqual(self.dispatched_txs, [])

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
        self.assertIn("nodo 'Repetidor_Norte' (31d03b1f)", last_log["message"])
        self.assertIn("4.12V", last_log["message"])
        self.assertIn("3h 25m 45s", last_log["message"])
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

    async def test_traceroute_empty_path_passes_none_and_flags_zero(self) -> None:
        """Verifica que un traceroute con path vacío despache path=None y flags=0 sin causar 'unknown path_hash_len 0'."""
        self._provide_trace_reply(flags=0, hashes=[])

        # 1. Petición con path vacío ""
        res = await self.admin_handler.handle({
            "action": "traceroute",
            "target_node": "feedfacecafe0011",
            "path": "",
        })
        self.assertEqual(res["status"], "ok")
        self.mock_mc.commands.send_trace.assert_awaited_once_with(path=None, flags=0, tag=ANY)
        tag = self.mock_mc.commands.send_trace.await_args.kwargs["tag"]
        self.mock_mc.dispatcher.wait_for_event.assert_awaited_once_with(
            EventType.TRACE_DATA, attribute_filters={"tag": tag}, timeout=None,
        )

        # 2. Petición con lista vacía []
        self.mock_mc.commands.send_trace.reset_mock()
        res2 = await self.admin_handler.handle({
            "action": "trace",
            "target_node": "feedfacecafe0011",
            "path": [],
        })
        self.assertEqual(res2["status"], "ok")
        self.mock_mc.commands.send_trace.assert_awaited_once_with(path=None, flags=0, tag=ANY)

    async def test_traceroute_custom_path_normalizes_hashes_and_flags(self) -> None:
        """Verifica que un traceroute con saltos intermedios normalice los hashes y use flags correctos."""
        self._provide_trace_reply(flags=1, hashes=["1122", "aabb"])

        # Petición con claves públicas completas de repetidores intermedios
        res = await self.admin_handler.handle({
            "action": "traceroute",
            "target_node": "deadbeefcafe0099",
            "path": ["1122", "aabb"],
        })
        self.assertEqual(res["status"], "ok")
        # Debe normalizar a 2 bytes (4 hex chars por salto) y flags=1
        self.mock_mc.commands.send_trace.assert_awaited_once_with(path="1122,aabb", flags=1, tag=ANY)
        self.assertEqual([hop["snr"] for hop in res["hops_breakdown"][1:]], [8.0, 7.0, None])
        self.assertEqual(res["hops_breakdown"][0]["snr"], 9.25)

    async def test_neighbors_command_excludes_local_node(self) -> None:
        """Verifica que el comando 'neighbors' excluya la estación base local y reporte solo vecinos remotos."""
        self.mock_mc.self_info = {
            "name": "Estación Base Heltec",
            "public_key": "34c0c75300000000",
        }
        self.mock_registry.is_local_key.side_effect = lambda key: "34c0c753" in str(key).lower()
        self.mock_registry.list_nodes.return_value = [
            {"public_key": "8d5accef11223344", "name": "Cu1.mobilUnit", "role": "CLIENT", "is_local": False, "last_rssi": -11, "last_snr": 12.5, "hops": 0, "lqi_score": 100.0, "lqi_status": "EXCELLENT"},
            {"public_key": "31d03b1f55667788", "name": "R1-Lee", "role": "REPEATER", "is_local": False, "last_rssi": None, "last_snr": 12.0, "hops": 0, "lqi_score": 82.5, "lqi_status": "EXCELLENT"},
            {"public_key": "34c0c75300000000", "name": "Estación Base Heltec", "role": "LOCAL", "is_local": True, "last_rssi": None, "last_snr": None, "hops": 0, "lqi_score": 100.0, "lqi_status": "EXCELLENT"},
        ]

        res = await self.admin_handler.handle({
            "target_node": "local",
            "action": "neighbors",
        })
        self.assertEqual(res["status"], "ok")
        result_text = res.get("result", "")
        # Debe reportar 2 vecinos (no 3)
        self.assertIn("Total Nodos Vecinos Descubiertos: 2", result_text)
        self.assertIn("Cu1.mobilUnit", result_text)
        self.assertIn("R1-Lee", result_text)
        self.assertNotIn("34c0c753", result_text)

    async def test_nodes_command_lists_all_with_local_tag(self) -> None:
        """Verifica que el comando 'nodes' liste todos los nodos y distinga la estación base local."""
        self.mock_mc.self_info = {
            "name": "Estación Base Heltec",
            "public_key": "34c0c75300000000",
        }
        self.mock_registry.is_local_key.side_effect = lambda key: "34c0c753" in str(key).lower()
        self.mock_registry.list_nodes.return_value = [
            {"public_key": "8d5accef11223344", "name": "Cu1.mobilUnit", "role": "CLIENT", "is_local": False, "last_rssi": -11, "last_snr": 12.5, "hops": 0},
            {"public_key": "34c0c75300000000", "name": "Estación Base Heltec", "role": "LOCAL", "is_local": True, "last_rssi": None, "last_snr": None, "hops": 0},
        ]

        res = await self.admin_handler.handle({
            "target_node": "local",
            "action": "nodes",
        })
        self.assertEqual(res["status"], "ok")
        result_text = res.get("result", "")
        self.assertIn("Total Nodos Registrados: 2", result_text)
        self.assertIn("[ESTACIÓN BASE LOCAL]", result_text)
        self.assertIn("Cu1.mobilUnit", result_text)


if __name__ == "__main__":
    unittest.main()
