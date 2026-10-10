"""
Pruebas de Concurrencia Extrema y Fallas en Caliente para MeshCore Bridge.
Verifica la estabilidad del deduplicador en RAM con escrituras multihilo concurrentes
y manejo resiliente de excepciones de hardware serie.
"""

import asyncio
import json
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock

from meshcore_bridge import MeshCoreBridge, PacketDeduplicator


class TestConcurrencyAndFlapping(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.bridge = MeshCoreBridge(self.loop)
        self.bridge.mqtt_client = MagicMock()
        self.published = []
        self.bridge.mqtt_client.publish.side_effect = lambda t, p, qos=0, retain=False: self.published.append((t, p))
        self.bridge.mqtt_connected = True

        self.mock_mc = MagicMock()
        self.mock_mc.commands = MagicMock()
        self.mock_mc.commands.send_chan_msg = AsyncMock(return_value=MagicMock(type=MagicMock(name="SENT")))
        self.mock_mc.contacts = []
        self.bridge.mc = self.mock_mc
        self.bridge.serial_adapter.is_connected = True
        self.bridge.serial_adapter.send_message = AsyncMock(return_value={"status": "SENT"})

    def tearDown(self):
        try:
            self.loop.run_until_complete(self.bridge.rate_limiter.stop())
            self.loop.run_until_complete(self.loop.shutdown_default_executor())
        finally:
            self.loop.close()

    def test_concurrent_deduplicator_multithreaded(self):
        """Prueba 10 hilos concurrentes verificando hashes de paquetes en RAM sin condiciones de carrera."""
        dedup = PacketDeduplicator(ttl_seconds=5.0, max_history=1000)
        num_threads = 10
        ops_per_thread = 50

        def worker(thread_idx):
            for i in range(ops_per_thread):
                asyncio.run(dedup.is_duplicate(f"pkt_{thread_idx}_{i}"))

        threads = []
        for t in range(num_threads):
            th = threading.Thread(target=worker, args=(t,))
            threads.append(th)
            th.start()

        for th in threads:
            th.join()

        self.assertEqual(len(dedup), num_threads * ops_per_thread)

    def test_serial_exception_during_active_tx(self):
        """Verifica que una falla de hardware en el puerto USB durante TX no congele el worker."""
        self.bridge.serial_adapter.send_message = AsyncMock(side_effect=OSError("USB Device Disconnected"))

        tx_data = {
            "request_id": "test_crash_safe",
            "to": "broadcast",
            "channel_index": 0,
            "text": "Mensaje en puerto fallido",
        }

        # Ejecutar TX (debe manejar la excepción limpiamente)
        self.loop.run_until_complete(self.bridge._execute_tx(tx_data))
        self.assertEqual(self.bridge.tx_error_count, 1)

        # El worker debe continuar operativo
        status_publishes = [p for t, p in self.published if t == "meshcore/tx/status"]
        self.assertTrue(len(status_publishes) > 0)
        status_data = json.loads(status_publishes[-1])
        self.assertEqual(status_data["status"], "error")
        # SDK exception strings are private; MQTT exposes the fixed failure.
        self.assertEqual(status_data["error"], "No se confirmó la transmisión por radio")
        self.assertNotIn("USB Device Disconnected", json.dumps(status_data))

        # A subsequent transmission must still finish after the adapter failed.
        self.bridge.serial_adapter.send_message.side_effect = None
        self.bridge.serial_adapter.send_message.return_value = {"status": "SENT"}
        recovery = self.loop.run_until_complete(
            self.bridge._execute_tx({**tx_data, "request_id": "test_after_failure"})
        )
        self.assertEqual(recovery["status"], "sent")
        self.assertEqual(self.bridge.tx_count, 2)
        self.assertEqual(self.bridge.tx_error_count, 1)
        self.assertEqual(self.bridge.serial_adapter.send_message.await_count, 2)
        latest_status = json.loads([
            p for t, p in self.published if t == "meshcore/tx/status"
        ][-1])
        self.assertEqual(latest_status["request_id"], "test_after_failure")
        self.assertEqual(latest_status["status"], "sent")


if __name__ == "__main__":
    unittest.main()
