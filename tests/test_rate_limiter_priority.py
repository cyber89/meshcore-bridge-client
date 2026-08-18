"""
Unit tests for LoRa Transmission Rate Limiter, PriorityQueue, and Airtime estimation.
"""

import asyncio
import unittest

from src.rate_limiter import (
    LoRaRadioConfig,
    TxItem,
    TxPriority,
    TxRateLimiter,
    estimate_lora_airtime_ms,
)


class TestRateLimiterPriority(unittest.IsolatedAsyncioTestCase):
    async def test_lora_airtime_estimation(self) -> None:
        # SF7, 250kHz vs SF11, 250kHz
        airtime_sf7 = estimate_lora_airtime_ms(32, LoRaRadioConfig(sf=7, bw_khz=250.0))
        airtime_sf11 = estimate_lora_airtime_ms(32, LoRaRadioConfig(sf=11, bw_khz=250.0))

        self.assertGreater(airtime_sf7, 0)
        self.assertGreater(airtime_sf11, airtime_sf7, "Mayor SF debe resultar en mayor Airtime")

    async def test_priority_queue_ordering(self) -> None:
        executed_order: list[str] = []

        async def _mock_tx(item: TxItem) -> dict[str, str]:
            executed_order.append(str(item.payload))
            return {"status": "SENT"}

        limiter = TxRateLimiter(tx_interval_sec=0.01, transmit_callback=_mock_tx)

        # Encolar en orden inverso de prioridad: LOW -> NORMAL -> HIGH
        # con el worker detenido para garantizar el encolamiento simultáneo
        f_low = await limiter.submit("Telemetry_LOW", priority=TxPriority.LOW)
        f_norm = await limiter.submit("Text_NORMAL", priority=TxPriority.NORMAL)
        f_high = await limiter.submit("ACK_HIGH", priority=TxPriority.HIGH)

        limiter.start()

        # Esperar resoluciones
        await asyncio.gather(f_low, f_norm, f_high)
        await limiter.stop()

        # HIGH (0) debe ejecutarse antes que NORMAL (1), y NORMAL antes que LOW (2)
        self.assertEqual(len(executed_order), 3)
        self.assertEqual(executed_order, ["ACK_HIGH", "Text_NORMAL", "Telemetry_LOW"])
