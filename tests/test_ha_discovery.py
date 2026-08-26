"""
Unit tests for NodeRegistry and ContactManager without Home Assistant.
Verifies telemetry tracking in RAM.
"""

import unittest
from src.contact_manager import NodeRegistry, NodeContactUpdate


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
        self.assertEqual(node.name, "Repeater Montaña")
        self.assertEqual(node.battery_pct, 85)


if __name__ == "__main__":
    unittest.main()
