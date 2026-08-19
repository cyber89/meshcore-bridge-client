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

    def test_check_sqlite_access_success(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            res = self.checker.check_sqlite_access(db_path)
            self.assertTrue(res.passed)
            self.assertIn("operativa", res.message)
        finally:
            for ext in ["", "-wal", "-shm"]:
                p = db_path + ext
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    def test_check_serial_port_auto(self) -> None:
        res = self.checker.check_serial_port("AUTO")
        self.assertTrue(res.passed)
        self.assertIn("AUTO", res.message)

    def test_run_all_summary(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            report = self.checker.run_all(
                mqtt_host="127.0.0.1",
                mqtt_port=1883,
                db_path=db_path,
                serial_port="AUTO",
            )
            self.assertIn("status", report)
            self.assertIn("checks", report)
            self.assertEqual(len(report["checks"]), 3)
        finally:
            for ext in ["", "-wal", "-shm"]:
                p = db_path + ext
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass


if __name__ == "__main__":
    unittest.main()
