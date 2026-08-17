"""
Pruebas Unitarias para el Watchdog Serial.
Verifica que el Watchdog detecte inactividad o fallos en el enlace con el Heltec v4
y fuerce una reconexión limpia sin congelar el proceso.
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

import config
from meshcore_bridge import MeshCoreBridge


class TestSerialWatchdog(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.bridge = MeshCoreBridge(self.loop)
        self.bridge.mqtt_client = MagicMock()
        self.bridge.mc = MagicMock()
        self.bridge.mc.disconnect = AsyncMock()

    def tearDown(self):
        self.loop.close()

    def test_force_serial_reconnect(self):
        """Verifica que forzar la reconexión serial desconecte la sesión previa e incremente contadores."""
        async def run_test():
            self.assertEqual(self.bridge.serial_reconnect_count, 0)
            self.assertIsNotNone(self.bridge.mc)

            await self.bridge._force_serial_reconnect()

            self.assertEqual(self.bridge.serial_reconnect_count, 1)
            self.assertIsNone(self.bridge.mc)

        self.loop.run_until_complete(run_test())

    def test_watchdog_detects_timeout_and_reconnects(self):
        """Simula que la radio no responde a una consulta y el Watchdog activa la reconexión."""
        async def run_test():
            config.WATCHDOG_INTERVAL_SEC = 0.05
            self.bridge.last_serial_activity = time.time() - 10.0  # Simular 10 segundos sin actividad

            # Configurar un comando que lance timeout
            self.bridge.mc.commands = MagicMock()
            async def mock_hang():
                await asyncio.sleep(2.0)  # Cuelgue simulado
            self.bridge.mc.commands.get_contacts = mock_hang

            # Iniciar el watchdog por un breve instante
            watchdog_task = asyncio.create_task(self.bridge._watchdog_loop())
            await asyncio.sleep(0.20)
            self.bridge.running = False
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass

            # El watchdog debió haber detectado el cuelgue y forzado la desconexión
            self.assertGreaterEqual(self.bridge.serial_reconnect_count, 1)
            self.assertIsNone(self.bridge.mc)

        self.loop.run_until_complete(run_test())


if __name__ == "__main__":
    unittest.main()
