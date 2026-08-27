"""
Pruebas Unitarias para el Rate Limiter de Transmisión (TX).
Verifica que las transmisiones RF se espacien temporalmente para no saturar
el transceptor LoRa SX1262 y que se emitan los ACKs correspondientes.
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

import config
from meshcore_bridge import MeshCoreBridge


class TestTXRateLimiter(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.bridge = MeshCoreBridge(self.loop)
        self.bridge.mqtt_client = MagicMock()
        self.bridge.mqtt_connected = True

        # Mock de MeshCore
        self.bridge.mc = MagicMock()
        self.bridge.mc.commands = MagicMock()
        self.bridge.mc.commands.send_chan_msg = AsyncMock()
        self.bridge.mc.commands.send_msg = AsyncMock()

    def tearDown(self):
        self.loop.close()

    def test_tx_rate_limiting_spacing(self):
        """Verifica que 3 paquetes TX consecutivos sean espaciados por TX_INTERVAL_SEC."""
        async def run_test():
            config.TX_INTERVAL_SEC = 0.1
            self.bridge.rate_limiter.tx_interval_sec = 0.1
            self.bridge.rate_limiter._running = True
            tx_timestamps = []

            async def mock_send(text, target=None, channel_idx=0):
                tx_timestamps.append(time.time())
                return {"status": "SENT"}

            self.bridge.serial_adapter.is_connected = True
            self.bridge.serial_adapter.send_message = AsyncMock(side_effect=mock_send)

            # Iniciar el worker en segundo plano
            worker_task = asyncio.create_task(self.bridge.rate_limiter._worker_loop())

            # Encolar 3 mensajes casi al instante
            await self.bridge.rate_limiter.submit({"request_id": "req_1", "text": "Msg 1", "to": "broadcast"})
            await self.bridge.rate_limiter.submit({"request_id": "req_2", "text": "Msg 2", "to": "broadcast"})
            await self.bridge.rate_limiter.submit({"request_id": "req_3", "text": "Msg 3", "to": "broadcast"})

            # Esperar a que la cola se procese
            await self.bridge.rate_limiter.queue.join()
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            # Validar que los 3 mensajes fueron transmitidos
            self.assertEqual(len(tx_timestamps), 3)

            diff1 = tx_timestamps[1] - tx_timestamps[0]
            diff2 = tx_timestamps[2] - tx_timestamps[1]

            self.assertGreaterEqual(diff1, 0.05, f"Espaciado entre msg 1 y 2 insuficiente ({diff1}s)")
            self.assertGreaterEqual(diff2, 0.05, f"Espaciado entre msg 2 y 3 insuficiente ({diff2}s)")

        self.loop.run_until_complete(run_test())

    def test_tx_ack_emission(self):
        """Verifica que cada transmisión emita su acuse de recibo correspondiente."""
        async def run_test():
            published_acks = []
            self.bridge.mqtt.publish_safe = MagicMock(side_effect=lambda t, p, qos=0, retain=False: published_acks.append((t, p)))

            await self.bridge._execute_tx({
                "request_id": "n8n_test_ack_99",
                "to": "broadcast",
                "channel_index": 0,
                "text": "Prueba de confirmación"
            })

            # Verificar que se publicó en el tópico de estado de TX
            self.assertEqual(len(published_acks), 1)
            topic, payload = published_acks[0]
            self.assertIn("meshcore/tx/status", topic)
            self.assertIn("n8n_test_ack_99", payload)
            self.assertIn('"status": "sent"', payload)

        self.loop.run_until_complete(run_test())


if __name__ == "__main__":
    unittest.main()
