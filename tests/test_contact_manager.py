"""
Unit tests for NodeRegistry and Contact Directory.
"""

import time
import unittest

from src.contact_manager import NodeContactUpdate, NodeRegistry


class TestContactManager(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = NodeRegistry()

    def test_add_and_resolve_node(self) -> None:
        self.registry.add_or_update(
            "feedfacecafe0001",
            NodeContactUpdate(
                name="Heltec_Router",
                alias="Router_Principal",
                hops=1,
                last_rssi=-75,
                last_snr=12.0,
                battery_pct=95,
            ),
        )

        # 1. Búsqueda exacta por clave
        contact = self.registry.get_by_key_or_prefix("feedfacecafe0001")
        self.assertIsNotNone(contact)
        if contact:
            self.assertEqual(contact.name, "Heltec_Router")
            self.assertEqual(contact.battery_pct, 95)

        # 2. Búsqueda por prefijo
        contact_prefix = self.registry.get_by_key_or_prefix("feedface")
        self.assertIsNotNone(contact_prefix)

        # 3. Resolución de nombre
        name = self.registry.resolve_name("feedfacecafe0001")
        self.assertEqual(name, "Router_Principal")

        # 4. Búsqueda por alias
        contact_alias = self.registry.get_by_key_or_prefix("Router_Principal")
        self.assertIsNotNone(contact_alias)

    def test_cleanup_inactive_nodes(self) -> None:
        # Añadir un nodo antiguo
        self.registry.add_or_update(
            "0011223344556677",
            NodeContactUpdate(name="Old_Node"),
        )
        self.assertEqual(self.registry.get_count(), 1)

        # Simular que pasaron 100 segundos y limpiar con max_idle=10
        # Modificar artificialmente last_seen
        old_contact = self.registry.get_by_key_or_prefix("0011223344556677")
        if old_contact:
            self.registry._nodes_by_key["0011223344556677"] = old_contact.__class__(
                public_key=old_contact.public_key,
                name=old_contact.name,
                alias=old_contact.alias,
                last_seen=time.time() - 100.0,
            )

        deleted = self.registry.cleanup_inactive(max_idle_seconds=10.0)
        self.assertEqual(deleted, 1)
        self.assertEqual(self.registry.get_count(), 0)

    def test_local_pubkey_management(self) -> None:
        self.assertEqual(self.registry.get_local_pubkey(), "")
        self.assertEqual(self.registry.local_pubkey, "")

        self.registry.set_local_pubkey("A1B2C3D4E5F600112233445566778899A1B2C3D4E5F600112233445566778899")
        expected = "a1b2c3d4e5f600112233445566778899a1b2c3d4e5f600112233445566778899"
        self.assertEqual(self.registry.get_local_pubkey(), expected)
        self.assertEqual(self.registry.local_pubkey, expected)

        self.assertTrue(self.registry.is_local_key("local"))
        self.assertTrue(self.registry.is_local_key(expected))
        self.assertTrue(self.registry.is_local_key("a1b2c3d4e5f6"))
        self.assertFalse(self.registry.is_local_key("feedfacecafe"))


if __name__ == "__main__":
    unittest.main()
