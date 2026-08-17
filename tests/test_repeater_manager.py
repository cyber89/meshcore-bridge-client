"""
Unit tests for RepeaterManager and RF Packet Sniffer.
"""

import unittest

from src.repeater_manager import RepeaterManager


class TestRepeaterManager(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = RepeaterManager()

    def test_build_repeater_command_payload(self) -> None:
        cmd1 = self.manager.build_repeater_command_payload("stats-radio", {})
        self.assertEqual(cmd1, "stats-radio")

        cmd2 = self.manager.build_repeater_command_payload("set_tx_power", {"power": 18})
        self.assertEqual(cmd2, "set tx 18")

        cmd3 = self.manager.build_repeater_command_payload("set_name", {"name": "Hilltop_Router"})
        self.assertEqual(cmd3, "set name Hilltop_Router")

    def test_parse_log_packet(self) -> None:
        # Trama sintética de 0x88 LOG_DATA (header byte: Route 0x01 [FLOOD], Type 0x02 [TXT_MSG], Ver 0x00)
        # header = 0x01 | (0x02 << 2) | (0x00 << 6) = 0x09
        raw_log = bytes([0x09, 0xAA, 0xBB, 0xCC])
        res = self.manager.parse_log_packet(raw_log)

        self.assertEqual(res["event_type"], "rf_log")
        self.assertEqual(res["route_type_id"], 0x01)
        self.assertEqual(res["payload_type_id"], 0x02)
        self.assertEqual(res["version"], 0x00)
        self.assertEqual(res["byte_length"], 4)


if __name__ == "__main__":
    unittest.main()
