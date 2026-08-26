"""
Pruebas Unitarias para el SerialWatchdog de src/serial_driver.py.
Verifica que el Watchdog detecte inactividad o fallos en el transceptor serie
y active el callback de reconexión sin bloquear el loop.
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

from src.serial_driver import BaseSerialAdapter, SerialWatchdog


class TestSerialWatchdog(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.mock_adapter = MagicMock(spec=BaseSerialAdapter)
        self.mock_adapter.is_connected = False
        self.mock_adapter.last_heartbeat_time = time.time()
        self.mock_adapter.disconnect = AsyncMock()
        self.mock_adapter.ping_or_check_alive = AsyncMock(return_value=False)
        self.mock_adapter.heartbeat = MagicMock()
        self.reconnect_calls = 0

        def on_reconnect():
            self.reconnect_calls += 1
            self.mock_adapter.is_connected = True

        self.watchdog = SerialWatchdog(
            adapter=self.mock_adapter,
            timeout_sec=0.05,
            interval_sec=0.02,
            on_timeout_reconnect=on_reconnect,
        )
        self.watchdog._reconnect_backoff_sec = 0.02

    def tearDown(self):
        self.loop.close()

    def test_watchdog_detects_timeout_and_reconnects(self):
        """Simula desconexión y verifica que SerialWatchdog active la reconexión."""
        async def run_test():
            self.watchdog.start()
            await asyncio.sleep(0.1)
            await self.watchdog.stop()
            self.assertGreaterEqual(self.reconnect_calls, 1)

        self.loop.run_until_complete(run_test())


if __name__ == "__main__":
    unittest.main()
