"""
Unit tests for Home Assistant MQTT Auto-Discovery Generator.
"""

import unittest
from unittest.mock import MagicMock

from src.ha_discovery import HomeAssistantDiscovery


class TestHomeAssistantDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        self.ha = HomeAssistantDiscovery(
            topic_prefix="meshcore",
            ha_prefix="homeassistant",
            enabled=True,
        )

    def test_generate_node_discovery_configs(self) -> None:
        node_info = {
            "public_key": "a1b2c3d4e5f6",
            "name": "Repeater Montaña",
            "hardware": "Heltec v3",
            "battery": 85,
            "voltage": 4.12,
            "snr": 12.5,
            "rssi": -65,
        }
        configs = self.ha.generate_node_discovery_configs(node_info)
        self.assertGreaterEqual(len(configs), 4, "Debe generar al menos 4 sensores HA para el nodo")

        topics = [c[0] for c in configs]
        self.assertTrue(any("sensor/meshcore_a1b2c3d4e5f6_battery/config" in t for t in topics))
        self.assertTrue(any("sensor/meshcore_a1b2c3d4e5f6_voltage/config" in t for t in topics))
        self.assertTrue(any("sensor/meshcore_a1b2c3d4e5f6_snr/config" in t for t in topics))
        self.assertTrue(any("sensor/meshcore_a1b2c3d4e5f6_rssi/config" in t for t in topics))

        # Verificar payload de batería
        battery_payload = next(c[1] for c in configs if "battery" in c[0])
        self.assertEqual(battery_payload["unit_of_measurement"], "%")
        self.assertEqual(battery_payload["device_class"], "battery")
        self.assertEqual(battery_payload["device"]["name"], "Repeater Montaña")

    def test_generate_bridge_discovery_configs(self) -> None:
        configs = self.ha.generate_bridge_discovery_configs()
        self.assertGreaterEqual(len(configs), 4, "Debe generar al menos 4 entidades para el bridge")

        topics = [c[0] for c in configs]
        self.assertTrue(any("binary_sensor/meshcore_bridge_status/config" in t for t in topics))
        self.assertTrue(any("sensor/meshcore_bridge_rx_packets/config" in t for t in topics))
        self.assertTrue(any("sensor/meshcore_bridge_tx_packets/config" in t for t in topics))
        self.assertTrue(any("sensor/meshcore_bridge_offline_buffer/config" in t for t in topics))

    def test_publish_discovery_for_node(self) -> None:
        mock_publish = MagicMock()
        node_info = {"public_key": "feedface0001", "name": "Rover Scout"}

        count = self.ha.publish_discovery_for_node(node_info, mock_publish)
        self.assertGreater(count, 0)
        self.assertEqual(mock_publish.call_count, count)

        # Segundo intento no debe republicar (deduplicación interna)
        count_again = self.ha.publish_discovery_for_node(node_info, mock_publish)
        self.assertEqual(count_again, 0)


if __name__ == "__main__":
    unittest.main()
