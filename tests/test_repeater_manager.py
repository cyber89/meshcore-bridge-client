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

        cmd4 = self.manager.build_repeater_command_payload("login", {"password": "secret_pin_123"})
        self.assertEqual(cmd4, "login secret_pin_123")

        cmd5 = self.manager.build_repeater_command_payload("get_pos", {})
        self.assertEqual(cmd5, "get pos")


if __name__ == "__main__":
    unittest.main()
