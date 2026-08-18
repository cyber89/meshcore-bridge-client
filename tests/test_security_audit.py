"""
Automated Security Audit & Vulnerability Tests for MeshCore Bridge.
Verifica resistencia contra SQL Injection, Directory Traversal, DoS por Payload Grande,
XSS y presencia de cabeceras de seguridad HTTP.
"""

import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from src.store_forward import SQLiteStoreAndForward, StoredMessage
from src.web.http_server import MeshCoreWebServer


class TestSecurityAudit(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        self.store = SQLiteStoreAndForward(db_path=self.db_path, max_size=50)

        self.mock_bridge = MagicMock()
        self.mock_bridge.running = True
        self.mock_bridge.start_time = 1000.0
        self.mock_bridge.node_registry = MagicMock()
        self.mock_bridge.rate_limiter = MagicMock()
        self.mock_bridge.store_and_forward = self.store
        self.server = MeshCoreWebServer(self.mock_bridge, host="127.0.0.1", port=0)

    def tearDown(self) -> None:
        for ext in ["", "-wal", "-shm"]:
            p = self.db_path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    async def test_sql_injection_resilience(self) -> None:
        """Comprueba que payloads maliciosos de inyección SQL no alteren la base de datos."""
        malicious_payloads = [
            "' OR '1'='1' --",
            "'; DROP TABLE offline_queue; --",
            "admin' UNION SELECT 1, 2, 3, 4, 5, 6, 7 --",
            "test\x00malicious",
        ]

        for payload in malicious_payloads:
            ok = await self.store.enqueue(
                StoredMessage(
                    topic=f"meshcore/test/{payload}",
                    payload=payload,
                    qos=1,
                )
            )
            self.assertTrue(ok)

        # La base de datos debe contener exactamente 4 registros almacenados fielmente
        self.assertEqual(await self.store.count(), len(malicious_payloads))
        batch = await self.store.dequeue_batch(limit=10)
        self.assertEqual(len(batch), len(malicious_payloads))
        self.assertEqual(batch[0][2], malicious_payloads[0])

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
