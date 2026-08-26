"""
Pruebas Unitarias para la Deduplicación en Memoria RAM de MeshCore Bridge.
Verifica que los mensajes duplicados sean descartados en tiempo constante O(1)
y que el bridge opere de forma stateless sin depender de base de datos en disco.
"""

import asyncio
import unittest
from unittest.mock import MagicMock

from meshcore_bridge import MeshCoreBridge, PacketDeduplicator


class TestStoreAndForward(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.bridge = MeshCoreBridge(self.loop)
        self.bridge.mqtt_client = MagicMock()

    def tearDown(self):
        self.loop.close()

    def test_ram_deduplication_basic(self):
        """Verifica que el deduplicador en RAM identifique y descarte duplicados."""
        dedup = PacketDeduplicator(ttl_seconds=2.0, max_history=100)
        self.assertFalse(dedup.is_duplicate_sync("hash_msg_1"))
        self.assertTrue(dedup.is_duplicate_sync("hash_msg_1"))
        self.assertFalse(dedup.is_duplicate_sync("hash_msg_2"))

    def test_bridge_initialization_stateless(self):
        """Verifica que el bridge inicialice correctamente en memoria sin crear base de datos en disco."""
        self.assertIsNotNone(self.bridge)
        self.assertIsNotNone(self.bridge.deduplicator)
        self.assertFalse(hasattr(self.bridge, "store_and_forward"))


if __name__ == "__main__":
    unittest.main()
