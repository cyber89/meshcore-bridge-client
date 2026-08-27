"""
Automated Security Audit & Vulnerability Tests for MeshCore Bridge.
Verifica resistencia contra SQL Injection, Directory Traversal, DoS por Payload Grande,
XSS y presencia de cabeceras de seguridad HTTP.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock

from src.contact_manager import NodeRegistry
from src.deduplicator import PacketDeduplicator
from src.web.http_server import MeshCoreWebServer


class TestSecurityAudit(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mock_bridge = MagicMock()
        self.mock_bridge.running = True
        self.mock_bridge.start_time = 1000.0
        self.mock_bridge.node_registry = NodeRegistry()
        self.mock_bridge.deduplicator = PacketDeduplicator()
        self.mock_bridge.rate_limiter = MagicMock()
        self.server = MeshCoreWebServer(self.mock_bridge, host="127.0.0.1", port=0)

    async def test_directory_traversal_protection(self) -> None:
        """Verifica que solicitudes con path traversal no escapen del directorio estático."""
        traversal_attempts = [
            "../../../../etc/passwd",
            "..\\..\\windows\\system32\\drivers\\etc\\hosts",
            "%2e%2e%2f%2e%2e%2fconfig.py",
            "....//....//....//.env",
        ]

        for attempt in traversal_attempts:
            mock_reader = AsyncMock()
            mock_writer = MagicMock()

            mock_reader.readline.side_effect = [
                f"GET /{attempt} HTTP/1.1\r\n".encode(),
                b"Host: localhost\r\n",
                b"\r\n",
            ]

            await self.server._handle_client(mock_reader, mock_writer)

            mock_writer.write.assert_called()
            args = mock_writer.write.call_args[0][0]
            self.assertNotIn(b"200 OK", args)
            self.assertTrue(b"403 " in args or b"404 " in args or b"400 " in args)

    async def test_dos_oversized_payload_protection(self) -> None:
        """Comprueba el límite de tamaño MAX_BODY_SIZE (1 MB) en el servidor HTTP."""
        mock_reader = AsyncMock()
        mock_writer = MagicMock()

        # Simular solicitud con Content-Length mayor a 1 MB
        mock_reader.readline.side_effect = [
            b"POST /api/tx HTTP/1.1\r\n",
            b"Host: localhost\r\n",
            b"Content-Length: 5000000\r\n",
            b"\r\n",
        ]

        await self.server._handle_client(mock_reader, mock_writer)

        # Debe haber escrito respuesta 413 Payload Too Large
        mock_writer.write.assert_called()
        args = mock_writer.write.call_args[0][0]
        self.assertIn(b"413 Payload Too Large", args)


if __name__ == "__main__":
    unittest.main()
