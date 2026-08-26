"""
Unit tests for Preflight Diagnostics Engine.
"""

import os
import tempfile
import unittest

from src.preflight import PreflightChecker


class TestPreflightChecker(unittest.TestCase):
    def setUp(self) -> None:
        self.checker = PreflightChecker()

    def test_check_serial_port_auto(self) -> None:
        res = self.checker.check_serial_port("AUTO")
        self.assertTrue(res.passed)
        self.assertIn("AUTO", res.message)

    def test_check_tcp_companion_port(self) -> None:
        res = self.checker.check_tcp_companion_port("127.0.0.1", 59999, enabled=True)
        self.assertTrue(res.passed)

    def test_run_all_summary(self) -> None:
        report = self.checker.run_all(
            mqtt_host="127.0.0.1",
            mqtt_port=1883,
            serial_port="AUTO",
            tcp_server_port=59998,
            tcp_server_enabled=True,
        )
        self.assertIn("status", report)
        self.assertIn("checks", report)
        self.assertEqual(len(report["checks"]), 3)


if __name__ == "__main__":
    unittest.main()
