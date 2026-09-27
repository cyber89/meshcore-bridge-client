"""
Unit tests for RAM PacketDeduplicator (Sliding window TTL & Cache eviction)
and stateless in-memory operation of MeshCoreBridge.
"""

import asyncio
import unittest
from unittest.mock import MagicMock

from src.bridge_core import MeshCoreBridge
from src.deduplicator import PacketDeduplicator


class TestPacketDeduplicator(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.dedup = PacketDeduplicator(ttl_seconds=1.0, max_history=10)

    async def test_deduplication_basic(self) -> None:
        """Verifica que el deduplicador en RAM identifique y descarte duplicados."""
        self.assertFalse(await self.dedup.is_duplicate("pkt_001"))
        self.assertTrue(await self.dedup.is_duplicate("pkt_001"))
        self.assertFalse(await self.dedup.is_duplicate("pkt_002"))

    async def test_deduplication_ttl_expiration(self) -> None:
        """Verifica que tras expirar la ventana TTL el paquete sea aceptado de nuevo."""
        self.assertFalse(await self.dedup.is_duplicate("pkt_expiring"))
        self.assertTrue(await self.dedup.is_duplicate("pkt_expiring"))

        await asyncio.sleep(1.1)

        self.assertFalse(await self.dedup.is_duplicate("pkt_expiring"))

    async def test_deduplication_capacity_eviction(self) -> None:
        """Verifica que se desaloje el elemento más antiguo al superar max_entries."""
        for i in range(15):
            self.assertFalse(await self.dedup.is_duplicate(f"pkt_batch_{i}"))

        self.assertLessEqual(len(self.dedup), 10)


class TestPacketDeduplicatorAsync(unittest.IsolatedAsyncioTestCase):
    async def test_async_deduplication(self) -> None:
        dedup = PacketDeduplicator(window_seconds=2.0, max_entries=50)
        self.assertFalse(await dedup.is_duplicate("async_pkt_1"))
        self.assertTrue(await dedup.is_duplicate("async_pkt_1"))
        self.assertFalse(await dedup.is_duplicate("async_pkt_2"))


class TestBridgeStatelessInitialization(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.bridge = MeshCoreBridge(self.loop)
        self.bridge.mqtt_client = MagicMock()

    def tearDown(self) -> None:
        self.loop.close()

    def test_bridge_initialization_stateless(self) -> None:
        """Verifica que el bridge inicialice correctamente en memoria sin depender de base de datos en disco."""
        self.assertIsNotNone(self.bridge)
        self.assertIsNotNone(self.bridge.deduplicator)
        self.assertFalse(hasattr(self.bridge, "store_and_forward"))


if __name__ == "__main__":
    unittest.main()
