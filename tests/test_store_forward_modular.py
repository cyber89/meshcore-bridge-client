"""
Unit tests for modular SQLite Store & Forward, TTL expiration, and Packet Deduplication.
"""

import os
import tempfile
import time
import unittest

from src.store_forward import PacketDeduplicator, SQLiteStoreAndForward


class TestStoreForwardModular(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        self.sf = SQLiteStoreAndForward(
            db_path=self.db_path,
            max_size=10,
            default_ttl_hours=1.0,
        )
        self.dedup = PacketDeduplicator(window_seconds=1.0, max_entries=100)

    def tearDown(self) -> None:
        for ext in ["", "-wal", "-shm"]:
            p = self.db_path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def test_enqueue_and_fifo_batch_dequeue(self) -> None:
        # Encolar 5 mensajes
        for i in range(5):
            ok = self.sf.enqueue(f"topic/{i}", f"payload_{i}", qos=1)
            self.assertTrue(ok)

        self.assertEqual(self.sf.get_size(), 5)

        # Dequeue batch
        batch = self.sf.dequeue_batch(limit=3)
        self.assertEqual(len(batch), 3)
        self.assertEqual(batch[0][1], "topic/0")
        self.assertEqual(batch[1][1], "topic/1")
        self.assertEqual(batch[2][1], "topic/2")

        # Eliminar procesados
        for item in batch:
            self.sf.delete(item[0])

        self.assertEqual(self.sf.get_size(), 2)

    def test_capacity_limit_circular_trim(self) -> None:
        # max_size es 10, encolar 15 mensajes
        for i in range(15):
            self.sf.enqueue("test/topic", f"payload_{i}")

        self.assertLessEqual(self.sf.get_size(), 10)
        batch = self.sf.dequeue_batch(limit=10)
        # Los más antiguos deben haberse descartado, quedando del 5 al 14
        self.assertEqual(batch[0][2], "payload_5")
        self.assertEqual(batch[-1][2], "payload_14")

    def test_ttl_expiration_purging(self) -> None:
        # Encolar con TTL de 0.5 segundos
        self.sf.enqueue("fast/expire", "expired_payload", ttl_seconds=0.5)
        self.assertEqual(self.sf.get_size(), 1)

        time.sleep(0.6)  # Esperar a que expire
        purged = self.sf.purge_expired()
        self.assertEqual(purged, 1)
        self.assertEqual(self.sf.get_size(), 0)

    def test_packet_deduplicator(self) -> None:
        # Primera vez -> No es duplicado
        self.assertFalse(self.dedup.is_duplicate("packet_hash_123"))

        # Inmediato -> Es duplicado
        self.assertTrue(self.dedup.is_duplicate("packet_hash_123"))

        # Otra clave -> No es duplicado
        self.assertFalse(self.dedup.is_duplicate("packet_hash_456"))

        # Tras ventana de tiempo -> Deja de ser duplicado
        time.sleep(1.1)
        self.assertFalse(self.dedup.is_duplicate("packet_hash_123"))
