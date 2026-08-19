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
        # 1. Trama sintética de bytes de 0x88 LOG_DATA (header byte: Route 0x01 [FLOOD], Type 0x02 [TXT_MSG], Ver 0x00)
        # header = 0x01 | (0x02 << 2) | (0x00 << 6) = 0x09
        raw_log = bytes([0x09, 0xAA, 0xBB, 0xCC])
        res = self.manager.parse_log_packet(raw_log)

        self.assertEqual(res["event_type"], "rf_log")
        self.assertEqual(res["route_type_id"], 0x01)
        self.assertEqual(res["payload_type_id"], 0x02)
        self.assertEqual(res["version"], 0x00)
        self.assertEqual(res["byte_length"], 4)
        self.assertEqual(res["raw_hex"], "09aabbcc")

        # 2. Diccionario emitido por MeshCore SDK
        sdk_dict = {
            "route_type": 1,
            "route_typename": "FLOOD",
            "payload_type": 2,
            "payload_typename": "TXT_MSG",
            "message": "Hello mesh",
            "pkt_payload": b"\x01\x02\x03",
        }
        res_dict = self.manager.parse_log_packet(sdk_dict)
        self.assertEqual(res_dict["event_type"], "rf_log")
        self.assertEqual(res_dict["message"], "Hello mesh")
        self.assertEqual(res_dict["pkt_payload"], "010203")

        # 3. String plano
        res_str = self.manager.parse_log_packet("Raw ASCII log from repeater")
        self.assertEqual(res_str["event_type"], "rf_log")
        self.assertEqual(res_str["raw_text"], "Raw ASCII log from repeater")


if __name__ == "__main__":
    unittest.main()
