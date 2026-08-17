"""
Unit tests for Serial Communication Adapters, Framing byte-stuffing, and Watchdog.
"""

import asyncio
import unittest

from src.protocol_types import (
    FrameHeader,
    MeshcoreFrame,
    OpCode,
    TelemetryPayload,
)
from src.serial_driver import (
    RawSerialFramingAdapter,
    SerialWatchdog,
)


class TestSerialAdapter(unittest.IsolatedAsyncioTestCase):
    def test_raw_framing_adapter_roundtrip(self) -> None:
        adapter = RawSerialFramingAdapter(port="COM_TEST")
        received_frames: list[MeshcoreFrame] = []
        adapter.set_rx_callback(lambda f: received_frames.append(f))

        # Crear trama sintética
        telem = TelemetryPayload(
            battery_mv=4000,
            solar_mv=5000,
            temperature_c=22.0,
            humidity_pct=50.0,
            pressure_hpa=1013.0,
            snr_db=10,
            rssi_dbm=-80,
            battery_pct=90,
        )
        telem_bytes = telem.pack()
        header = FrameHeader(
            opcode=OpCode.TELEMETRY,
            seq_num=1,
            src_node_id=0x1111,
            dst_node_id=0xFFFF,
            hop_limit=3,
            payload_len=len(telem_bytes),
        )
        frame = MeshcoreFrame(
            header=header,
            payload=telem,
            raw_payload=telem_bytes,
            crc16=0,
            is_valid=True,
        )

        serialized = frame.serialize()

        # Simular llegada en fragmentos / chunks
        chunk1 = serialized[:5]
        chunk2 = serialized[5:12]
        chunk3 = serialized[12:]

        adapter.process_incoming_bytes(chunk1)
        self.assertEqual(len(received_frames), 0)

        adapter.process_incoming_bytes(chunk2)
        self.assertEqual(len(received_frames), 0)

        adapter.process_incoming_bytes(chunk3)
        self.assertEqual(len(received_frames), 1)

        rx_frame = received_frames[0]
        self.assertTrue(rx_frame.is_valid)
        self.assertEqual(rx_frame.header.opcode, OpCode.TELEMETRY)
        self.assertEqual(rx_frame.header.src_node_id, 0x1111)

    async def test_serial_watchdog_timeout_trigger(self) -> None:
        adapter = RawSerialFramingAdapter(port="COM_TEST")
        reconnect_called = False

        def _on_reconnect() -> None:
            nonlocal reconnect_called
            reconnect_called = True

        watchdog = SerialWatchdog(
            adapter=adapter,
            timeout_sec=0.1,
            interval_sec=0.05,
            on_timeout_reconnect=_on_reconnect,
        )
        adapter.is_connected = True
        watchdog.start()

        # Simular inactividad
        adapter.last_heartbeat_time = 0.0
        await asyncio.sleep(0.15)
        await watchdog.stop()

        self.assertTrue(reconnect_called, "El Watchdog debe haber activado la reconexión")
