"""
Unit and Integration tests for MeshCore Web Server and REST API Router.
"""

import asyncio
import unittest
from typing import Any
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
            "feedface00010000feedface00010000feedface00010000feedface00010000",
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
        serial = MagicMock()
        serial.is_connected = True
        serial.add_contact = AsyncMock(return_value={"status": "OK"})
        serial.set_channel = AsyncMock(return_value={"status": "OK"})
        serial.delete_channel = AsyncMock(return_value={"status": "OK"})
        self.mock_bridge.serial_adapter = serial

        def admitted_tx(**kwargs: Any) -> asyncio.Future[dict[str, str]]:
            result: asyncio.Future[dict[str, str]] = asyncio.get_running_loop().create_future()
            result.set_result({"status": "sent", "request_id": str(kwargs.get("request_id", "req_1"))})
            return result

        self.mock_bridge.rate_limiter.submit.side_effect = admitted_tx

        self.router = WebAPIRouter(self.mock_bridge)

    async def test_get_status_endpoint(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/status")
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "ok")
        self.assertIn("health", data)

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
            "public_key": "aabbccddeeff0002aabbccddeeff0002aabbccddeeff0002aabbccddeeff0002",
            "name": "Lilygo_Node",
            "alias": "Repeater_Alpha",
        }
        code, data = await self.router.handle_request("POST", "/api/contacts", body)
        self.assertIn(code, (200, 201))
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["data"]["alias"], "Repeater_Alpha")

        # Verificar que se añadió a NodeRegistry
        self.assertEqual(self.mock_bridge.node_registry.get_count(), 2)

    async def test_channels_crud(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/channels")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(len(data["data"]), 1)

        new_ch = {"index": 4, "name": "Canal Táctico", "psk": "ab" * 16}
        code, data = await self.router.handle_request("POST", "/api/channels", new_ch)
        self.assertIn(code, (200, 201))
        self.assertEqual(data["data"]["name"], "Canal Táctico")
        await self.router.handle_request("DELETE", "/api/channels", {"index": 4})

    async def test_tx_message_endpoint(self) -> None:
        body = {
            "text": "Hola mundo LoRa desde la Web",
            "to": "broadcast",
            "channel_index": 0,
        }
        code, data = await self.router.handle_request("POST", "/api/tx", body)
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "ok")
        self.mock_bridge.rate_limiter.submit.assert_called_once()
        self.mock_bridge._execute_tx.assert_not_awaited()

    async def test_admin_repeater_command_endpoint(self) -> None:
        body = {
            "target_node": "feedface00010000feedface00010000feedface00010000feedface00010000",
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
        self.assertEqual(data["data"]["top_nodes_by_traffic"][0]["public_key"], "feedface00010000feedface00010000feedface00010000feedface00010000")
        self.assertEqual(data["data"]["top_nodes_by_traffic"][0]["total_packets"], 20)

    async def test_system_logs_endpoint(self) -> None:
        self.router.log_system_event("WARN", "Prueba de advertencia en logs", source="test")
        code, data = await self.router.handle_request("GET", "/api/system/logs")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(data["count"], 1)
        self.assertEqual(data["data"][-1]["level"], "WARN")

    async def test_preflight_endpoint(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/preflight")
        self.assertEqual(code, 200)
        self.assertIn("status", data["data"])

    async def test_trace_endpoint(self) -> None:
        code, data = await self.router.handle_request("POST", "/api/trace", {"to": "node_alpha", "auth_code": 1234})
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "ok")

    async def test_node_ping_zero_endpoint(self) -> None:
        self.mock_bridge.handle_admin.return_value = {"status": "ok", "rtt_ms": 35.5, "snr": 4.2}
        code, data = await self.router.handle_request("POST", "/api/node/ping_zero", {"target_node": "feedface00010000feedface00010000feedface00010000feedface00010000"})
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["data"]["rtt_ms"], 35.5)


if __name__ == "__main__":
    unittest.main()
