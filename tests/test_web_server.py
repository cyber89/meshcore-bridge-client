"""
Unit and Integration tests for MeshCore Web Server and REST API Router.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock

from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.web.api_router import WebAPIRouter


class TestWebServerRouter(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.mock_bridge = MagicMock()
        self.mock_bridge.running = True
        self.mock_bridge.start_time = 1000.0
        self.mock_bridge.node_registry = NodeRegistry()
        self.mock_bridge.node_registry.add_or_update(
            "feedface0001",
            NodeContactUpdate(
                name="Heltec_Base",
                alias="Base_Station",
                hops=1,
                last_rssi=-70,
                last_snr=11.5,
                battery_pct=90,
                rx_packets=15,
                tx_packets=5,
            ),
        )
        self.mock_bridge.rate_limiter = MagicMock()
        self.mock_bridge.rate_limiter.get_queue_depth.return_value = 0
        self.mock_bridge.rx_count = 10
        self.mock_bridge.tx_count = 5
        self.mock_bridge.tx_error_count = 0
        self.mock_bridge.err_count = 0
        self.mock_bridge.store_and_forward = MagicMock()
        self.mock_bridge.store_and_forward.count = AsyncMock(return_value=0)
        self.mock_bridge._execute_tx = AsyncMock(return_value={"status": "sent"})
        self.mock_bridge.handle_admin = AsyncMock(return_value={"status": "ok", "action": "set_name"})

        self.router = WebAPIRouter(self.mock_bridge)

    async def test_get_status_endpoint(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/status")
        self.assertEqual(code, 200)
        self.assertEqual(data["data"]["bridge_status"], "online")
        self.assertEqual(data["data"]["known_mesh_nodes"], 1)

    async def test_get_nodes_and_contacts(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/nodes")
        self.assertEqual(code, 200)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["data"][0]["alias"], "Base_Station")

        code, data = await self.router.handle_request("GET", "/api/contacts")
        self.assertEqual(code, 200)
        self.assertEqual(len(data["data"]), 1)

    async def test_add_contact_endpoint(self) -> None:
        body = {
            "public_key": "aabbccddeeff0002",
            "name": "Lilygo_Node",
            "alias": "Repeater_Alpha",
        }
        code, data = await self.router.handle_request("POST", "/api/contacts", body)
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["data"]["alias"], "Repeater_Alpha")

        # Verificar que se añadió a NodeRegistry
        self.assertEqual(self.mock_bridge.node_registry.get_count(), 2)

    async def test_channels_crud(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/channels")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(len(data["data"]), 1)

        new_ch = {"index": 4, "name": "Canal Táctico", "psk": "KEY_12345"}
        code, data = await self.router.handle_request("POST", "/api/channels", new_ch)
        self.assertEqual(code, 200)
        self.assertEqual(data["data"]["name"], "Canal Táctico")

    async def test_tx_message_endpoint(self) -> None:
        body = {
            "text": "Hola mundo LoRa desde la Web",
            "to": "broadcast",
            "channel_index": 0,
        }
        code, data = await self.router.handle_request("POST", "/api/tx", body)
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "ok")
        self.mock_bridge._execute_tx.assert_called_once()

    async def test_admin_repeater_command_endpoint(self) -> None:
        body = {
            "target_node": "feedface0001",
            "action": "stats-radio",
        }
        code, data = await self.router.handle_request("POST", "/api/admin/repeater", body)
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "ok")
        self.mock_bridge.handle_admin.assert_called_once()

    async def test_analytics_endpoint(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/analytics")
        self.assertEqual(code, 200)
        self.assertIn("top_nodes_by_traffic", data["data"])
        self.assertEqual(len(data["data"]["top_nodes_by_traffic"]), 1)
        self.assertEqual(data["data"]["top_nodes_by_traffic"][0]["public_key"], "feedface0001")
        self.assertEqual(data["data"]["top_nodes_by_traffic"][0]["total_packets"], 20)

    async def test_sniffer_control_endpoint(self) -> None:
        code, data = await self.router.handle_request("POST", "/api/sniffer/control", {"action": "start"})
        self.assertEqual(code, 200)
        self.assertTrue(data["data"]["sniffer_active"])

    async def test_system_logs_endpoint(self) -> None:
        self.router.log_system_event("WARN", "Prueba de advertencia en logs", source="test")
        code, data = await self.router.handle_request("GET", "/api/system/logs")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(data["count"], 1)
        self.assertEqual(data["data"][-1]["level"], "WARN")

    async def test_ha_endpoints(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/ha/status")
        self.assertEqual(code, 200)
        self.assertIn("enabled", data["data"])

        code, data = await self.router.handle_request("POST", "/api/ha/publish")
        self.assertEqual(code, 200)
        self.assertIn("published_entities", data["data"])

    async def test_preflight_endpoint(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/preflight")
        self.assertEqual(code, 200)
        self.assertIn("status", data["data"])

    async def test_trace_endpoint(self) -> None:
        code, data = await self.router.handle_request("POST", "/api/trace", {"to": "node_alpha", "auth_code": 1234})
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "ok")

    def test_record_incoming_event_ignores_system_log(self) -> None:
        initial_msg_count = len(self.router.recent_messages)
        initial_rf_count = len(self.router.recent_rf_logs)

        # 1. system_log no debe entrar en mensajes de chat ni en logs rf
        self.router.record_incoming_event({"event_type": "system_log", "data": {"message": "Test log"}})
        self.assertEqual(len(self.router.recent_messages), initial_msg_count)
        self.assertEqual(len(self.router.recent_rf_logs), initial_rf_count)

        # 2. rf_log debe entrar a recent_rf_logs
        self.router.record_incoming_event({"event_type": "rf_log", "byte_length": 12, "raw_hex": "010203"})
        self.assertEqual(len(self.router.recent_rf_logs), initial_rf_count + 1)


if __name__ == "__main__":
    unittest.main()
