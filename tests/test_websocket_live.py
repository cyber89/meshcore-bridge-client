"""
Unit tests for WebSocket Live Streaming and Frame Handling in MeshCoreWebServer.
"""

import json
import unittest
from unittest.mock import MagicMock

from src.web.http_server import MeshCoreWebServer


class TestWebSocketLive(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mock_bridge = MagicMock()
        self.mock_bridge.node_registry = MagicMock()
        self.mock_bridge.node_registry.get_count.return_value = 0
        self.mock_bridge.node_registry.list_nodes.return_value = []
        self.server = MeshCoreWebServer(self.mock_bridge, host="127.0.0.1", port=0)

    def test_build_websocket_frame(self) -> None:
        payload = json.dumps({"event": "test_ping", "value": 123}).encode("utf-8")
        frame = self.server._build_websocket_frame(payload)

        # Primer byte: 0x81 (FIN=1, Opcode=0x1 text)
        self.assertEqual(frame[0], 0x81)
        # Segundo byte: longitud
        self.assertEqual(frame[1], len(payload))
        # Contenido
        self.assertEqual(frame[2:], payload)

    async def test_broadcast_event_queues_to_router(self) -> None:
        event = {
            "event_type": "public",
            "sender": "feedface0001",
            "text": "Mensaje de prueba",
            "timestamp": "2026-08-17T20:00:00Z",
        }
        await self.server.broadcast_event(event)

        # Debe registrarse en recent_messages del router
        self.assertEqual(len(self.server.router.recent_messages), 1)
        self.assertEqual(self.server.router.recent_messages[0]["sender"], "feedface0001")


if __name__ == "__main__":
    unittest.main()
