"""
Unit tests for NodeRegistry and ContactManager telemetry tracking in RAM.
Verifies telemetry tracking, client contact filtering, and analytics in RAM.
"""

import unittest

from src.contact_manager import NodeContactUpdate, NodeRegistry, PacketRecord


class TestNodeRegistryTelemetry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = NodeRegistry()

    def test_node_registration_and_telemetry(self) -> None:
        update = NodeContactUpdate(
            name="Repeater Montaña",
            role="REPEATER",
            battery_pct=85,
            voltage_v=4.12,
            last_snr=12.5,
            last_rssi=-65,
        )
        self.registry.add_or_update("a1b2c3d4e5f6", update)
        node = self.registry.get_contact("a1b2c3d4e5f6")
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.name, "Repeater Montaña")
        self.assertEqual(node.battery_pct, 85)
        self.assertEqual(node.voltage_v, 4.12)
        self.assertEqual(node.last_snr, 12.5)
        self.assertEqual(node.last_rssi, -65)

    def test_client_contact_excludes_repeater(self) -> None:
        rep_update = NodeContactUpdate(name="Mountain Repeater", role="REPEATER")
        client_update = NodeContactUpdate(name="Field Scout", role="CLIENT")
        self.registry.add_or_update("aaaa11112222", rep_update)
        self.registry.add_or_update("bbbb33334444", client_update)

        contacts = self.registry.list_client_contacts()
        contact_pks = [c["public_key"] for c in contacts]
        self.assertIn("bbbb33334444", contact_pks)
        self.assertNotIn("aaaa11112222", contact_pks)

    def test_packet_recording_and_analytics(self) -> None:
        self.registry.add_or_update("cccc55556666", NodeContactUpdate(name="Tracker Node", role="SENSOR"))
        self.registry.record_packet(PacketRecord(public_key="cccc55556666", is_rx=True, rssi=-80, snr=6.0, hop_count=1))
        node = self.registry.get_contact("cccc55556666")
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.rx_packets, 1)
        self.assertEqual(node.last_rssi, -80)

        summary = self.registry.get_analytics_summary()
        self.assertGreaterEqual(summary["summary"]["total_nodes"], 1)


if __name__ == "__main__":
    unittest.main()
