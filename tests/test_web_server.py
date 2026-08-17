"""
Unit and Integration tests for MeshCore Web Server and REST API Router.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock

from src.contact_manager import NodeRegistry
from src.web.api_router import WebAPIRouter


class TestWebServerRouter(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.mock_bridge = MagicMock()
        self.mock_bridge.running = True
        self.mock_bridge.start_time = 1000.0
        self.mock_bridge.node_registry = NodeRegistry()
        self.mock_bridge.node_registry.add_or_update(
            public_key="feedface0001",
            name="Heltec_Base",
            alias="Base_Station",
            hops=1,
            last_rssi=-70,
            last_snr=11.5,
            battery_pct=90,
        )
        self.mock_bridge.rate_limiter = MagicMock()
        self.mock_bridge.rate_limiter.get_queue_depth.return_value = 0
        self.mock_bridge.store_and_forward = MagicMock()
        self.mock_bridge.store_and_forward.get_size.return_value = 0
        self.mock_bridge._execute_tx = AsyncMock(return_value={"status": "sent"})
        self.mock_bridge.handle_admin = AsyncMock(return_value={"status": "ok", "action": "set_name"})

        self.router = WebAPIRouter(self.mock_bridge)

    async def test_get_status_endpoint(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/status")
        self.assertEqual(code, 200)
        self.assertEqual(data["bridge_status"], "online")
        self.assertEqual(data["known_mesh_nodes"], 1)

    async def test_get_nodes_and_contacts(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/nodes")
        self.assertEqual(code, 200)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["nodes"][0]["alias"], "Base_Station")

        code, data = await self.router.handle_request("GET", "/api/contacts")
        self.assertEqual(code, 200)
        self.assertEqual(len(data["contacts"]), 1)

    async def test_add_contact_endpoint(self) -> None:
        body = {
            "public_key": "aabbccddeeff0002",
            "name": "Lilygo_Node",
            "alias": "Repeater_Alpha",
        }
        code, data = await self.router.handle_request("POST", "/api/contacts", body)
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["contact"]["alias"], "Repeater_Alpha")

        # Verificar que se añadió a NodeRegistry
        self.assertEqual(self.mock_bridge.node_registry.get_count(), 2)

    async def test_channels_crud(self) -> None:
        code, data = await self.router.handle_request("GET", "/api/channels")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(len(data["channels"]), 1)

        new_ch = {"index": 4, "name": "Canal Táctico", "psk": "KEY_12345"}
        code, data = await self.router.handle_request("POST", "/api/channels", new_ch)
        self.assertEqual(code, 200)
        self.assertEqual(data["channel"]["name"], "Canal Táctico")

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


if __name__ == "__main__":
    unittest.main()
