"""
Prueba de Estrés y Ráfagas Masivas (Stress & Flood Test).
Verifica que el puente soporte la inyección de cientos de paquetes RX/TX
sin fugas de memoria, bloqueos ni excepciones no controladas.
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

import config
from meshcore_bridge import MeshCoreBridge


class MockEventType:
    def __init__(self, name: str):
        self.name = name

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if isinstance(other, str):
            return self.name == other
        if hasattr(other, "name"):
            return self.name == other.name
        return False


class MockEvent:
    def __init__(self, ev_type_name, payload):
        self.type = MockEventType(ev_type_name)
        self.payload = payload


class TestStressFlood(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.bridge = MeshCoreBridge(self.loop)
        self.bridge.mqtt_connected = True
        self.bridge.mqtt.publish_safe = MagicMock(return_value=True)
        self.bridge.mqtt.is_connected = MagicMock(return_value=True)
        self.bridge.mqtt_client = MagicMock()
        self.bridge.mqtt_client.publish = MagicMock(return_value=True)

        self.bridge.mc = MagicMock()
        self.bridge.mc.commands = MagicMock()
        self.bridge.mc.commands.send_chan_msg = AsyncMock(return_value={"status": "SENT"})
        self.bridge.mc.commands.send_msg = AsyncMock(return_value={"status": "SENT"})
        self.bridge.serial_adapter.is_connected = True
        self.bridge.serial_adapter.send_message = AsyncMock(return_value={"status": "SENT"})

    def tearDown(self):
        pending = asyncio.all_tasks(self.loop)
        for task in pending:
            task.cancel()
        if pending:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self.loop.close()

    def test_flood_rx_500_messages(self):
        """Inyecta 500 eventos RX en ráfaga para verificar estabilidad y conteo exacto."""
        async def run_rx():
            total_packets = 500
            start_time = time.time()

            for i in range(total_packets):
                ev = MockEvent("CHANNEL_MSG_RECV", {
                    "channel_idx": i % 3,
                    "sender": f"node_{i % 10}",
                    "sender_name": f"Nodo_{i % 10}",
                    "text": f"Mensaje de prueba de estrés #{i}",
                    "rssi": -70 - (i % 30),
                    "snr": 8.5
                })
                self.bridge.on_mesh_event(ev)

            # Esperar a que el semáforo y las tareas completen
            for _ in range(100):
                if self.bridge.rx_count >= total_packets:
                    break
                await asyncio.sleep(0.02)

            duration = time.time() - start_time
            self.assertEqual(self.bridge.rx_count, total_packets, "Todos los 500 paquetes deben haber sido procesados")
            self.assertLess(duration, 5.0, f"Procesamiento demasiado lento: {duration}s para 500 paquetes")

        self.loop.run_until_complete(run_rx())

    def test_flood_tx_queue_processing(self):
        """Encola 50 órdenes TX y verifica que se procesen sin pérdidas ni fallos."""
        async def run_stress_tx():
            config.TX_INTERVAL_SEC = 0.0001  # Acelerar intervalo para el test
            self.bridge.rate_limiter.tx_interval_sec = 0.0001
            self.bridge.rate_limiter._running = True
            self.bridge.serial_adapter.is_connected = True
            self.bridge.serial_adapter.send_message = AsyncMock(return_value={"status": "SENT"})
            worker = asyncio.create_task(self.bridge.rate_limiter._worker_loop())

            for i in range(50):
                await self.bridge.rate_limiter.submit({
                    "request_id": f"stress_req_{i}",
                    "to": "broadcast",
                    "channel_index": 0,
                    "text": f"Stress TX payload {i}"
                })

            await self.bridge.rate_limiter.queue.join()
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass

            self.assertEqual(self.bridge.tx_count, 50, "Las 50 órdenes TX deben haber sido transmitidas con éxito")
            self.assertEqual(self.bridge.tx_error_count, 0, "No debe haber errores de transmisión")

        self.loop.run_until_complete(run_stress_tx())


if __name__ == "__main__":
    unittest.main()
