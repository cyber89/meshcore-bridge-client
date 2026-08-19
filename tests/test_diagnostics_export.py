"""
Unit and integration tests for Persistent File Logging, Rotating Logs,
and Markdown/JSON AI Diagnostic Exporter.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.diagnostics import DiagnosticManager, setup_file_logging
from src.web.api_router import WebAPIRouter


class TestDiagnosticsExport(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="meshcore_test_logs_")
        self.main_log = os.path.join(self.test_dir, "test_bridge.log")
        self.err_log = os.path.join(self.test_dir, "test_bridge.error.log")

    def tearDown(self) -> None:
        # Remover handlers adjuntos para no afectar otros tests
        root = logging.getLogger()
        for h in list(root.handlers):
            if isinstance(h, logging.FileHandler):
                h.close()
                root.removeHandler(h)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_setup_file_logging_and_rotation(self) -> None:
        h_main, h_err = setup_file_logging(
            log_file_path=self.main_log,
            error_file_path=self.err_log,
            max_bytes=1024,
            backup_count=2,
            level="DEBUG",
        )
        self.assertIsNotNone(h_main)
        self.assertIsNotNone(h_err)

        logging.info("Mensaje informativo de prueba 1")
        logging.warning("Advertencia de prueba 2")
        logging.error("Error crítico de prueba 3")

        # Forzar flush
        if h_main:
            h_main.flush()
        if h_err:
            h_err.flush()

        self.assertTrue(os.path.exists(self.main_log))
        self.assertTrue(os.path.exists(self.err_log))

        main_content = Path(self.main_log).read_text(encoding="utf-8")
        err_content = Path(self.err_log).read_text(encoding="utf-8")

        self.assertIn("Mensaje informativo de prueba 1", main_content)
        self.assertIn("Advertencia de prueba 2", main_content)
        self.assertIn("Error crítico de prueba 3", main_content)

        # En error log no debe estar el INFO
        self.assertNotIn("Mensaje informativo de prueba 1", err_content)
        self.assertIn("Advertencia de prueba 2", err_content)
        self.assertIn("Error crítico de prueba 3", err_content)

    def test_generate_markdown_report(self) -> None:
        mock_bridge = MagicMock()
        mock_bridge.running = True
        mock_bridge.start_time = 1000.0
        mock_bridge.rx_count = 42
        mock_bridge.tx_count = 15
        mock_bridge.tx_error_count = 1
        mock_bridge.node_registry.get_count.return_value = 3
        mock_bridge.serial_adapter.is_connected = True
        mock_bridge.serial_adapter.port = "/dev/ttyACM0"
        mock_bridge.serial_adapter.baud_rate = 115200
        mock_bridge.mqtt.is_connected = True
        mock_bridge.mqtt.broker = "127.0.0.1"
        mock_bridge.mqtt.port = 1883
        mock_bridge.mqtt.reconnect_count = 0
        mock_bridge.store_and_forward.db_path = "meshcore_buffer.db"
        mock_bridge.rate_limiter.get_queue_depth.return_value = 0

        diag = DiagnosticManager(bridge=mock_bridge)
        diag.log_handler.error_count = 1
        diag.log_handler.warn_count = 2

        report_md = diag.generate_markdown_report()
        self.assertIsInstance(report_md, str)
        self.assertIn("# 📡 Reporte de Diagnóstico - MeshCore Bridge", report_md)
        self.assertIn("Radio Serial Companion", report_md)
        self.assertIn("/dev/ttyACM0", report_md)
        self.assertIn("Broker MQTT", report_md)
        self.assertIn("127.0.0.1:1883", report_md)
        self.assertIn("Paquetes RX (LoRa -> Bridge):", report_md)
        self.assertIn("`42`", report_md)

    async def test_rest_api_report_md_and_log_download(self) -> None:
        mock_bridge = MagicMock()
        mock_bridge.running = True
        diag = DiagnosticManager(bridge=mock_bridge)
        mock_bridge.diagnostics = diag
        mock_bridge.serial_adapter.port = "AUTO"
        mock_bridge.serial_adapter.is_connected = True
        mock_bridge.mqtt.is_connected = True
        mock_bridge.mqtt.broker = "127.0.0.1"
        mock_bridge.mqtt.port = 1883
        mock_bridge.store_and_forward.db_path = "test.db"
        mock_bridge.rate_limiter.get_queue_depth.return_value = 0
        mock_bridge.node_registry.get_count.return_value = 2

        router = WebAPIRouter(bridge=mock_bridge)

        # 1. Test GET /api/diagnostics/report.md
        code, resp = await router.handle_request("GET", "/api/diagnostics/report.md")
        self.assertEqual(code, 200)
        self.assertEqual(resp["status"], "ok")
        self.assertIn("markdown", resp)
        self.assertIn("# 📡 Reporte de Diagnóstico", resp["markdown"])

        # 2. Test GET /api/logs/download
        code2, resp2 = await router.handle_request("GET", "/api/logs/download")
        self.assertEqual(code2, 200)
        self.assertEqual(resp2["status"], "ok")
        self.assertIn("raw_logs", resp2)


if __name__ == "__main__":
    unittest.main()
