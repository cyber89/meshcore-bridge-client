"""
Unit tests for RAM PacketDeduplicator (Sliding window TTL & Cache eviction).
"""

import time
import unittest

from src.deduplicator import PacketDeduplicator


class TestPacketDeduplicator(unittest.TestCase):
    def setUp(self) -> None:
        self.dedup = PacketDeduplicator(ttl_seconds=1.0, max_history=10)

    def test_deduplication_basic(self) -> None:
        # Primer paquete no debe ser duplicado
        self.assertFalse(self.dedup.is_duplicate_sync("pkt_001"))
        # El mismo paquete inmediatamente debe ser detectado como duplicado
        self.assertTrue(self.dedup.is_duplicate_sync("pkt_001"))

    def test_deduplication_ttl_expiration(self) -> None:
        self.assertFalse(self.dedup.is_duplicate_sync("pkt_expiring"))
        self.assertTrue(self.dedup.is_duplicate_sync("pkt_expiring"))

        # Esperar a que expire la ventana TTL
        time.sleep(1.1)

        # Tras expirar el TTL, debe aceptarse nuevamente
        self.assertFalse(self.dedup.is_duplicate_sync("pkt_expiring"))

    def test_deduplication_capacity_eviction(self) -> None:
        # Llenar más allá del límite de historial (10)
        for i in range(15):
            self.assertFalse(self.dedup.is_duplicate_sync(f"pkt_batch_{i}"))

        self.assertLessEqual(len(self.dedup), 10)


if __name__ == "__main__":
    unittest.main()
