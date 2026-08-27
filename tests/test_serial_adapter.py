"""
Unit tests for Serial Communication Adapters, Framing byte-stuffing, and Watchdog.
"""

import asyncio
import unittest

from src.protocol_types import (
    FrameHeader,
    MeshcoreFrame,
    PacketType,
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
            packet_type=PacketType.TELEMETRY_RESPONSE,
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
        self.assertEqual(rx_frame.header.packet_type, PacketType.TELEMETRY_RESPONSE)
        self.assertEqual(rx_frame.header.src_node_id, 0x1111)

    async def test_serial_watchdog_timeout_trigger(self) -> None:
        from unittest.mock import AsyncMock

        adapter = RawSerialFramingAdapter(port="COM_TEST")
        adapter.ping_or_check_alive = AsyncMock(return_value=False)
        reconnect_called = False

        def _on_reconnect() -> None:
            nonlocal reconnect_called
            reconnect_called = True

        watchdog = SerialWatchdog(
            adapter=adapter,
            timeout_sec=0.02,
            interval_sec=0.02,
            on_timeout_reconnect=_on_reconnect,
        )
        adapter.is_connected = True
        watchdog.start()

        # Simular inactividad
        adapter.last_heartbeat_time = 0.0
        await asyncio.sleep(0.10)
        await watchdog.stop()
        self.assertTrue(reconnect_called, "El Watchdog debe haber activado la reconexión")

    async def test_meshcore_sdk_adapter_connect_lifecycle(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.serial_driver import MeshcoreSDKAdapter

        mock_mc = MagicMock()
        mock_mc.start_auto_message_fetching = AsyncMock()
        mock_mc.ensure_contacts = AsyncMock()
        mock_mc.subscribe = MagicMock()
        mock_mc.disconnect = AsyncMock()

        with patch("src.serial_driver.MeshCore") as MockMeshCoreClass:
            MockMeshCoreClass.create_serial = AsyncMock(return_value=mock_mc)

            adapter = MeshcoreSDKAdapter(port="/dev/ttyACM0", baud_rate=115200)
            res = await adapter.connect()

            self.assertTrue(res)
            self.assertTrue(adapter.is_connected)
            MockMeshCoreClass.create_serial.assert_awaited_once_with("/dev/ttyACM0", 115200, auto_reconnect=True)
            mock_mc.start_auto_message_fetching.assert_awaited_once()
            mock_mc.ensure_contacts.assert_awaited_once()

            await adapter.disconnect()
            self.assertFalse(adapter.is_connected)
            mock_mc.disconnect.assert_awaited_once()

    async def test_meshcore_sdk_adapter_send_message_channel_and_dm(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from src.serial_driver import MeshcoreSDKAdapter

        adapter = MeshcoreSDKAdapter(port="/dev/ttyACM0")
        adapter.is_connected = True
        mock_mc = MagicMock()
        mock_mc.commands.send_chan_msg = AsyncMock(return_value="OK_CHAN")
        mock_mc.commands.send_msg = AsyncMock(return_value="OK_DM")
        mock_mc.get_contact_by_name = MagicMock(return_value={"adv_name": "Alpha", "public_key": "a1b2c3d4e5f6"})
        mock_mc.get_contact_by_key_prefix = MagicMock(return_value={"adv_name": "Alpha", "public_key": "a1b2c3d4e5f6"})
        adapter.mc = mock_mc

        # 1. Enviar broadcast
        res_chan = await adapter.send_message("Hola Canal 0", target="broadcast", channel_idx=0)
        self.assertEqual(res_chan["status"], "SENT")
        mock_mc.commands.send_chan_msg.assert_awaited_once_with(0, "Hola Canal 0")

        # 2. Enviar DM a nodo por nombre
        res_dm = await adapter.send_message("Hola Alpha", target="Alpha")
        self.assertEqual(res_dm["status"], "SENT")
        mock_mc.commands.send_msg.assert_awaited_once_with({"adv_name": "Alpha", "public_key": "a1b2c3d4e5f6"}, "Hola Alpha")

