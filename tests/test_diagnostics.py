"""
Unit and Integration tests for Central Diagnostics and Real-time Log Hub.
"""

from __future__ import annotations

import logging
import unittest
from typing import Any
from unittest.mock import MagicMock

from src.diagnostics import DiagnosticManager, SystemLogHandler, SystemLogRecord
from src.web.api_router import WebAPIRouter


class TestDiagnosticsAndLogging(unittest.IsolatedAsyncioTestCase):
    def test_system_log_handler_emit_and_filter(self) -> None:
        captured_events: list[dict[str, Any]] = []

        def _broadcast(ev: dict[str, Any]) -> None:
            captured_events.append(ev)

        handler = SystemLogHandler(max_records=10, broadcast_callback=_broadcast)
        test_logger = logging.getLogger("test_meshcore_logger")
        test_logger.setLevel(logging.DEBUG)
        test_logger.addHandler(handler)

        test_logger.info("Mensaje informativo 1")
        test_logger.warning("Mensaje de advertencia")
        try:
            raise RuntimeError("Fallo simulado de radio LoRa")
        except RuntimeError:
            test_logger.error("Error en comunicación", exc_info=True)

        self.assertEqual(len(handler.buffer), 3)
        self.assertEqual(handler.info_count, 1)
        self.assertEqual(handler.warn_count, 1)
        self.assertEqual(handler.error_count, 1)
        self.assertIsNotNone(handler.last_error_time)
        self.assertIn("Error en comunicación", str(handler.last_error_msg))

        # Verificar broadcast en vivo
        self.assertEqual(len(captured_events), 3)
        self.assertEqual(captured_events[0]["event_type"], "system_log")
        self.assertEqual(captured_events[0]["data"]["level"], "INFO")

        # Filtrar por nivel
        error_logs = handler.get_logs(level="ERROR")
        self.assertEqual(len(error_logs), 1)
        self.assertIn("Fallo simulado de radio LoRa", str(error_logs[0]["exception"]))

        # Filtrar por búsqueda
        search_logs = handler.get_logs(search="advertencia")
        self.assertEqual(len(search_logs), 1)
        self.assertEqual(search_logs[0]["level"], "WARNING")

        # Limpiar
        handler.clear()
        self.assertEqual(len(handler.buffer), 0)
        self.assertEqual(handler.error_count, 0)

        test_logger.removeHandler(handler)

    def test_diagnostic_manager_level_switch_and_health(self) -> None:
        mock_bridge = MagicMock()
        mock_bridge.running = True
        mock_bridge.start_time = 1000.0
        mock_bridge.rx_count = 42
        mock_bridge.tx_count = 10
        mock_bridge.tx_error_count = 1
        mock_bridge.serial_adapter.is_connected = True
        mock_bridge.serial_adapter.port = "/dev/ttyACM0"
        mock_bridge.mqtt.is_connected = True
        mock_bridge.mqtt.broker = "127.0.0.1"
        mock_bridge.node_registry.get_count.return_value = 5
        mock_bridge.rate_limiter.get_queue_depth.return_value = 0

        handler = SystemLogHandler()
        manager = DiagnosticManager(bridge=mock_bridge, log_handler=handler)

        # Cambio de nivel
        orig_level = manager.get_current_log_level()
        new_lvl = manager.set_log_level("DEBUG")
        self.assertEqual(new_lvl, "DEBUG")
        self.assertEqual(manager.get_current_log_level(), "DEBUG")

        # Revertir
        manager.set_log_level(orig_level)

        # Snapshot de salud
        health = manager.collect_health_snapshot()
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["counters"]["rx_packets"], 42)
        self.assertEqual(health["subsystems"]["serial_companion"]["connected"], True)
        self.assertEqual(health["subsystems"]["mqtt_broker"]["connected"], True)

        # Paquete de diagnóstico exportable
        bundle = manager.generate_full_diagnostic_bundle()
        self.assertEqual(bundle["app_name"], "MeshCore Bridge")
        self.assertIn("environment", bundle)
        self.assertIn("health_snapshot", bundle)
        self.assertIn("recent_logs", bundle)

    async def test_api_router_diagnostic_endpoints(self) -> None:
        mock_bridge = MagicMock()
        mock_bridge.running = True
        mock_bridge.start_time = 1000.0
        mock_bridge.rx_count = 5
        mock_bridge.tx_count = 2
        mock_bridge.tx_error_count = 0
        mock_bridge.node_registry.list_nodes.return_value = []
        mock_bridge.node_registry.get_count.return_value = 0
        mock_bridge.rate_limiter.get_queue_depth.return_value = 0
        mock_bridge.store_and_forward.count.return_value = 0

        handler = SystemLogHandler()
        manager = DiagnosticManager(bridge=mock_bridge, log_handler=handler)
        mock_bridge.diagnostics = manager

        router = WebAPIRouter(bridge=mock_bridge)

        # 1. GET /api/diagnostics
        status, resp = await router.handle_request("GET", "/api/diagnostics")
        self.assertEqual(status, 200)
        self.assertEqual(resp["status"], "ok")
        self.assertIn("subsystems", resp["data"])

        # 2. GET /api/diagnostics/export
        status, resp = await router.handle_request("GET", "/api/diagnostics/export")
        self.assertEqual(status, 200)
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["data"]["app_name"], "MeshCore Bridge")

        # 3. GET & POST /api/system/logs/level
        status, resp = await router.handle_request("GET", "/api/system/logs/level")
        self.assertEqual(status, 200)
        self.assertIn("level", resp)

        status, resp = await router.handle_request("POST", "/api/system/logs/level", {"level": "DEBUG"})
        self.assertEqual(status, 200)
        self.assertEqual(resp["level"], "DEBUG")

        # 4. GET /api/system/logs con query params
        rec = SystemLogRecord(
            timestamp=1234.0,
            iso_time="2026-08-18 12:00:00.000",
            level="ERROR",
            logger_name="test",
            module="test_mod",
            func_name="test_fn",
            line_no=10,
            message="Test error alert",
        )
        handler.buffer.append(rec)

        status, resp = await router.handle_request("GET", "/api/system/logs?level=ERROR&search=alert")
        self.assertEqual(status, 200)
        self.assertEqual(resp["count"], 1)
        self.assertEqual(resp["data"][0]["message"], "Test error alert")

        # 5. DELETE /api/system/logs
        status, resp = await router.handle_request("DELETE", "/api/system/logs")
        self.assertEqual(status, 200)
        self.assertEqual(len(handler.buffer), 0)
