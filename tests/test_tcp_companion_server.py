"""
Unit and Integration tests for MeshCoreCompanionServer (TCP Companion Protocol).
Valida el ciclo de vida del servidor TCP en el puerto companion, de-framing
con delimitadores 0x3C y 0x3E, gestión de clientes concurrentes, descarte de basura
y protección contra tramas sobredimensionadas.
"""

import asyncio
import unittest
from typing import Any

from src.tcp_companion_server import (
    FRAME_APP_TO_RADIO,
    FRAME_RADIO_TO_APP,
    MAX_FRAME_SIZE,
    MeshCoreCompanionServer,
)


class MockBridgeWithCompanion:
    def __init__(self) -> None:
        self.received_commands: list[bytes] = []

    async def handle_tcp_companion_command(self, payload: bytes, client_writer: Any) -> None:
        self.received_commands.append(payload)


class TestMeshCoreCompanionServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.bridge = MockBridgeWithCompanion()
        # Usar puerto efímero asignado por el SO (127.0.0.1:0)
        self.server = MeshCoreCompanionServer(
            bridge=self.bridge,
            host="127.0.0.1",
            port=0,
        )
        await self.server.start()
        # Obtener el puerto real asignado
        assert self.server.server is not None
        sockets = self.server.server.sockets
        assert sockets is not None and len(sockets) > 0
        self.port = sockets[0].getsockname()[1]

    async def asyncTearDown(self) -> None:
        await self.server.stop()

    async def test_server_startup_and_client_count(self) -> None:
        self.assertTrue(self.server.running)
        self.assertEqual(self.server.get_connected_count(), 0)

        # Conectar un cliente
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        await asyncio.sleep(0.05)
        self.assertEqual(self.server.get_connected_count(), 1)

        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.05)
        self.assertEqual(self.server.get_connected_count(), 0)

    async def test_client_sends_valid_companion_frame(self) -> None:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        payload = b"\x01\x02\x03\x04\x05"
        frame_len = len(payload)
        header = bytearray([FRAME_APP_TO_RADIO, frame_len & 0xFF, (frame_len >> 8) & 0xFF])
        packet = bytes(header) + payload

        writer.write(packet)
        await writer.drain()
        await asyncio.sleep(0.1)

        self.assertEqual(len(self.bridge.received_commands), 1)
        self.assertEqual(self.bridge.received_commands[0], payload)

        writer.close()
        await writer.wait_closed()

    async def test_garbage_bytes_recovery_and_framing(self) -> None:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        payload = b"\xAA\xBB\xCC"
        frame_len = len(payload)
        header = bytearray([FRAME_APP_TO_RADIO, frame_len & 0xFF, (frame_len >> 8) & 0xFF])

        # Enviar basura previa + trama válida
        garbage_and_packet = b"\xFF\xFE\x00\x12\x34" + bytes(header) + payload
        writer.write(garbage_and_packet)
        await writer.drain()
        await asyncio.sleep(0.1)

        self.assertEqual(len(self.bridge.received_commands), 1)
        self.assertEqual(self.bridge.received_commands[0], payload)

        writer.close()
        await writer.wait_closed()

    async def test_broadcast_and_send_to_client(self) -> None:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        await asyncio.sleep(0.05)

        out_payload = b"\x10\x20\x30\x40"
        self.server.broadcast_companion_frame(out_payload)

        # Leer respuesta esperada '>' (0x3E) + len uint16 + payload
        resp_hdr = await reader.readexactly(3)
        self.assertEqual(resp_hdr[0], FRAME_RADIO_TO_APP)
        resp_len = resp_hdr[1] | (resp_hdr[2] << 8)
        self.assertEqual(resp_len, len(out_payload))

        resp_body = await reader.readexactly(resp_len)
        self.assertEqual(resp_body, out_payload)

        # Probar send_frame_to_client
        active_writer = next(iter(self.server.active_clients))
        direct_payload = b"\x99\x88\x77"
        self.server.send_frame_to_client(active_writer, direct_payload)

        direct_hdr = await reader.readexactly(3)
        self.assertEqual(direct_hdr[0], FRAME_RADIO_TO_APP)
        direct_len = direct_hdr[1] | (direct_hdr[2] << 8)
        self.assertEqual(direct_len, len(direct_payload))
        direct_body = await reader.readexactly(direct_len)
        self.assertEqual(direct_body, direct_payload)

        writer.close()
        await writer.wait_closed()

    async def test_oversized_frame_rejection(self) -> None:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)

        # Crear trama con longitud declarada mayor a MAX_FRAME_SIZE
        fake_len = MAX_FRAME_SIZE + 50
        bad_header = bytearray([FRAME_APP_TO_RADIO, fake_len & 0xFF, (fake_len >> 8) & 0xFF])
        writer.write(bytes(bad_header) + b"A" * 10)
        await writer.drain()
        await asyncio.sleep(0.1)

        # El servidor debe rechazar la trama sin caerse
        self.assertEqual(len(self.bridge.received_commands), 0)

        # Ahora enviar una trama normal válida y verificar que el servidor sigue funcionando
        good_payload = b"\x07\x08\x09"
        good_len = len(good_payload)
        good_header = bytearray([FRAME_APP_TO_RADIO, good_len & 0xFF, (good_len >> 8) & 0xFF])
        writer.write(bytes(good_header) + good_payload)
        await writer.drain()
        await asyncio.sleep(0.1)

        self.assertEqual(len(self.bridge.received_commands), 1)
        self.assertEqual(self.bridge.received_commands[0], good_payload)

        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    unittest.main()
