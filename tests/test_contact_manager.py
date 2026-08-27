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

    def test_local_node_never_duplicated(self) -> None:
        """Verifica que el nodo local nunca se duplica bajo ningún escenario de registro o prefijo."""
        full_pk = "a1b2c3d4e5f600112233445566778899a1b2c3d4e5f600112233445566778899"

        # 1. Registrar primero con clave parcial o 'local'
        self.registry.add_or_update(
            "local",
            NodeContactUpdate(name="Estación Base", role="LOCAL", is_local=True),
        )
        self.assertEqual(self.registry.get_count(), 1)

        # 2. Configurar la clave oficial del hardware
        self.registry.set_local_pubkey(full_pk)
        self.assertEqual(self.registry.get_count(), 1)
        self.assertEqual(self.registry.get_local_pubkey(), full_pk)

        # 3. Recibir una trama proveniente del prefijo del propio nodo local
        self.registry.add_or_update(
            "a1b2c3d4e5f6",
            NodeContactUpdate(name="Estación Base Heltec", role="LOCAL", is_local=True),
        )
        self.assertEqual(self.registry.get_count(), 1)

        # 4. Añadir 3 nodos remotos reales
        self.registry.add_or_update("1111222233334444", NodeContactUpdate(name="Remoto_1", role="CLIENT"))
        self.registry.add_or_update("5555666677778888", NodeContactUpdate(name="Remoto_2", role="SENSOR"))
        self.registry.add_or_update("9999aaaabbbbcccc", NodeContactUpdate(name="Remoto_3", role="REPEATER"))

        # El conteo total DEBE ser exactamente 4 (1 local + 3 remotos)
        self.assertEqual(self.registry.get_count(), 4)
        all_nodes = self.registry.list_nodes()
        self.assertEqual(len(all_nodes), 4)

        local_nodes = [n for n in all_nodes if n.get("is_local") or n.get("role") == "LOCAL"]
        self.assertEqual(len(local_nodes), 1)
        self.assertEqual(local_nodes[0]["public_key"], full_pk)

    def test_prefix_and_name_deduplication(self) -> None:
        """Verifica que nodos remotos con prefijos o nombres coincidentes se fusionan limpiamente."""
        # Insertar nodo con prefijo de 8 caracteres
        self.registry.add_or_update("feedface11223344", NodeContactUpdate(name="Nodo_Remoto", last_rssi=-80))
        self.assertEqual(self.registry.get_count(), 1)

        # Actualizar con clave completa de 64 caracteres compartiendo prefijo
        full_remote_pk = "feedface112233445566778899aabbccddeeff00112233445566778899aabbcc"
        self.registry.add_or_update(full_remote_pk, NodeContactUpdate(name="Nodo_Remoto", last_snr=10.5))

        # Debe mantenerse exactamente en 1 nodo fusionado
        self.assertEqual(self.registry.get_count(), 1)
        node = self.registry.get_by_key_or_prefix("feedface11223344")
        self.assertIsNotNone(node)
        if node:
            self.assertEqual(node.public_key, full_remote_pk)
            self.assertEqual(node.last_rssi, -80)
            self.assertEqual(node.last_snr, 10.5)


if __name__ == "__main__":
    unittest.main()
