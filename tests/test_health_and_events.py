"""
Unit tests for HealthReporter and event_utils.
"""

from __future__ import annotations

import asyncio
import time
import unittest
from dataclasses import dataclass
from unittest.mock import MagicMock

from src.contact_manager import NodeRegistry
from src.event_utils import extract_sender_from_payload
from src.health_reporter import HealthContext, HealthReporter
from src.mqtt_client import AsyncBridgeMQTTClient
from src.rate_limiter import TxRateLimiter
from src.serial_driver import BaseSerialAdapter


@dataclass
class MockCounters:
    rx_count: int = 0
    tx_count: int = 0
    tx_error_count: int = 0


class TestHealthAndEvents(unittest.IsolatedAsyncioTestCase):
    def test_extract_sender_from_payload_variations(self) -> None:
        """Verifica la extracción uniforme del remitente desde diversas estructuras de payload."""
        # 1. Directo: sender y sender_name
        k1, n1 = extract_sender_from_payload({"sender": "11223344", "sender_name": "Alpha"})
        self.assertEqual(k1, "11223344")
        self.assertEqual(n1, "Alpha")

        # 2. Clave pública y adv_name
        k2, n2 = extract_sender_from_payload({"public_key": "aabbccddeeff", "adv_name": "HeltecBase"})
        self.assertEqual(k2, "aabbccddeeff")
        self.assertEqual(n2, "HeltecBase")

        # 3. Prefijo pubkey_pre y alias
        k3, n3 = extract_sender_from_payload({"pubkey_pre": "31d03b1f", "alias": "Repeater_North"})
        self.assertEqual(k3, "31d03b1f")
        self.assertEqual(n3, "Repeater_North")

        # 4. Estructura anidada bajo 'contact'
        k4, n4 = extract_sender_from_payload({
            "contact": {"public_key": "deadbeefcafe", "name": "Sensor_Station"}
        })
        self.assertEqual(k4, "deadbeefcafe")
        self.assertEqual(n4, "Sensor_Station")

        # 5. Estructura anidada bajo 'payload'
        k5, n5 = extract_sender_from_payload({
            "payload": {"sender": "feedface0001", "sender_name": "MobileNode"}
        })
        self.assertEqual(k5, "feedface0001")
        self.assertEqual(n5, "MobileNode")

        # 6. Payload vacío
        k6, n6 = extract_sender_from_payload({})
        self.assertEqual(k6, "")
        self.assertEqual(n6, "")

    async def test_health_reporter_build_payload(self) -> None:
        """Verifica la construcción estructurada del snapshot de salud."""
        mock_mqtt = MagicMock(spec=AsyncBridgeMQTTClient)
        mock_mqtt.is_connected = True

        mock_serial = MagicMock(spec=BaseSerialAdapter)
        mock_serial.is_connected = True

        registry = NodeRegistry()
        counters = MockCounters(rx_count=100, tx_count=50, tx_error_count=2)

        mock_rate_limiter = MagicMock(spec=TxRateLimiter)
        mock_rate_limiter.get_queue_depth = MagicMock(return_value=3)

        ctx = HealthContext(
            mqtt=mock_mqtt,
            serial_adapter=mock_serial,
            node_registry=registry,
            rate_limiter=mock_rate_limiter,
            counters=counters,  # type: ignore[arg-type]
            start_time=time.time() - 3600.0,  # 1 hora de uptime
        )

        reporter = HealthReporter(ctx, interval_sec=1.0)
        payload = await reporter.build_payload()

        self.assertEqual(payload["status"], "healthy")
        self.assertGreaterEqual(payload["uptime_seconds"], 3599)
        self.assertEqual(payload["total_rx_packets"], 100)
        self.assertEqual(payload["total_tx_packets"], 50)
        self.assertEqual(payload["total_tx_errors"], 2)
        self.assertTrue(payload["serial_connected"])
        self.assertTrue(payload["mqtt_connected"])
        self.assertEqual(payload["tx_queue_depth"], 3)

    async def test_health_reporter_periodic_lifecycle(self) -> None:
        """Verifica el ciclo de vida de la tarea periódica de reporte."""
        mock_mqtt = MagicMock(spec=AsyncBridgeMQTTClient)
        mock_mqtt.is_connected = True
        mock_mqtt.publish_safe = MagicMock()

        mock_serial = MagicMock(spec=BaseSerialAdapter)
        mock_serial.is_connected = True

        registry = NodeRegistry()
        counters = MockCounters()
        mock_rate_limiter = MagicMock(spec=TxRateLimiter)
        mock_rate_limiter.get_queue_depth = MagicMock(return_value=0)

        ctx = HealthContext(
            mqtt=mock_mqtt,
            serial_adapter=mock_serial,
            node_registry=registry,
            rate_limiter=mock_rate_limiter,
            counters=counters,  # type: ignore[arg-type]
            start_time=time.time(),
        )

        reporter = HealthReporter(ctx, interval_sec=0.05)
        task = reporter.start()
        self.assertFalse(task.done())

        # Esperar 2 o 3 iteraciones del loop
        await asyncio.sleep(0.12)
        self.assertGreaterEqual(mock_mqtt.publish_safe.call_count, 1)

        # Detener limpiamente
        await reporter.stop()
        self.assertTrue(task.done())


if __name__ == "__main__":
    unittest.main()
