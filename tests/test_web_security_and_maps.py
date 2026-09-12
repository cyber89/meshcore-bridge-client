"""
Unit tests for SecurityTrafficInspector and MapTileService.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.web.map_tile_service import MapTileService
from src.web.security_inspector import HttpAccessEvent, SecurityTrafficInspector, SuspiciousTrafficEvent


class TestSecurityTrafficInspector(unittest.TestCase):
    def test_extract_client_ip_direct_and_headers(self) -> None:
        """Verifica la extracción de IP considerando proxies y peername del socket."""
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ("192.168.1.100", 45678)

        # 1. Sin cabeceras de proxy -> usa socket peername
        ip1 = SecurityTrafficInspector.extract_client_ip(mock_writer, {})
        self.assertEqual(ip1, "192.168.1.100")

        # 2. Con X-Forwarded-For -> primera IP de la cadena
        ip2 = SecurityTrafficInspector.extract_client_ip(
            mock_writer, {"x-forwarded-for": "203.0.113.195, 70.41.3.18, 150.172.238.178"}
        )
        self.assertEqual(ip2, "203.0.113.195")

        # 3. Con X-Real-IP
        ip3 = SecurityTrafficInspector.extract_client_ip(mock_writer, {"x-real-ip": "198.51.100.22"})
        self.assertEqual(ip3, "198.51.100.22")

        # 4. Limpieza de notación IPv4 mapeada en IPv6
        mock_writer.get_extra_info.return_value = ("::ffff:10.0.0.5", 12345)
        ip4 = SecurityTrafficInspector.extract_client_ip(mock_writer, {})
        self.assertEqual(ip4, "10.0.0.5")

    def test_directory_traversal_detection(self) -> None:
        """Verifica la detección de intentos de escape de directorio y codificaciones bypass."""
        traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\windows\\win.ini",
            "/api/static/%2e%2e/%2e%2e/config.json",
            "/api/maps/..../..../root",
            "/static/image.png\x00.exe",
            "/api/%c0%ae%c0%ae/etc/shadow",
        ]
        for path in traversal_attempts:
            self.assertTrue(
                SecurityTrafficInspector.is_traversal_attempt(path),
                f"Debería haber detectado traversal en '{path}'",
            )

        # Rutas legítimas no deben disparar falso positivo
        legit_paths = [
            "/api/nodes",
            "/api/map/tiles/12/234/567.png",
            "/static/css/styles.css",
            "/api/messages?target=node_1",
        ]
        for path in legit_paths:
            self.assertFalse(
                SecurityTrafficInspector.is_traversal_attempt(path),
                f"Falso positivo en ruta legítima '{path}'",
            )

    def test_inspect_http_request_anomalies(self) -> None:
        """Verifica la detección de escáneres automáticos, inyecciones y sondeos maliciosos."""
        # 1. Escáner automatizado (sqlmap)
        bad, anom, det = SecurityTrafficInspector.inspect_http_request(
            "GET", "/api/nodes", {"user-agent": "sqlmap/1.5.2#stable (http://sqlmap.org)"}
        )
        self.assertTrue(bad)
        self.assertEqual(anom, "SCANNER_AUTOMATIZADO")

        # 2. Sondeo a archivo sensible (.env)
        bad, anom, det = SecurityTrafficInspector.inspect_http_request(
            "GET", "/.env", {"user-agent": "Mozilla/5.0"}
        )
        self.assertTrue(bad)
        self.assertEqual(anom, "SONDEO_RUTA_SENSIBLE")

        # 3. Inyección XSS / script en query string
        bad, anom, det = SecurityTrafficInspector.inspect_http_request(
            "GET", "/api/nodes?filter=<script>alert(1)</script>", {"user-agent": "Mozilla/5.0"}
        )
        self.assertTrue(bad)
        self.assertEqual(anom, "INYECCION_COMANDO_O_SCRIPT")

        # 4. Solicitud limpia y normal
        bad, anom, det = SecurityTrafficInspector.inspect_http_request(
            "GET", "/api/status", {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        self.assertFalse(bad)


class TestMapTileService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.tile_service = MapTileService(data_dir=self.base_path)

    def tearDown(self) -> None:
        self.tile_service.close()
        self.temp_dir.cleanup()

    def test_storage_initialization(self) -> None:
        """Verifica la creación automática de directorios para mapas y teselas."""
        self.assertTrue(self.tile_service.maps_dir.is_dir())
        self.assertTrue(self.tile_service.tiles_dir.is_dir())

        status = self.tile_service.get_status()
        self.assertFalse(status["has_local_maps"])
        self.assertEqual(status["mbtiles_count"], 0)

    def test_loose_tiles_xyz_resolution(self) -> None:
        """Verifica la lectura de teselas sueltas en estructura de directorios XYZ."""
        # Crear tesela falsa en tiles/5/10/15.png (PNG signature: \x89PNG\r\n\x1a\n)
        png_magic = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        target_dir = self.tile_service.tiles_dir / "5" / "10"
        target_dir.mkdir(parents=True, exist_ok=True)
        tile_file = target_dir / "15.png"
        tile_file.write_bytes(png_magic)

        code, data, mime = self.tile_service.get_tile(z=5, x=10, y=15)
        self.assertEqual(code, 200)
        self.assertEqual(data, png_magic)
        self.assertEqual(mime, "image/png")

        # Tesela inexistente -> 404
        code_404, _, _ = self.tile_service.get_tile(z=5, x=99, y=99)
        self.assertEqual(code_404, 404)

    def test_mbtiles_sqlite_resolution(self) -> None:
        """Verifica la lectura e indexación de teselas dentro de una base SQLite MBTiles."""
        mbtiles_file = self.tile_service.maps_dir / "sample_map.mbtiles"
        conn = sqlite3.connect(mbtiles_file)
        conn.execute("CREATE TABLE metadata (name text, value text)")
        conn.execute("INSERT INTO metadata VALUES ('name', 'Mapa de Prueba'), ('format', 'png')")
        conn.execute("CREATE TABLE tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob)")

        # En MBTiles estándar, TMS Y para z=2, y=1 es: (1 << 2) - 1 - 1 = 2
        fake_png = b"\x89PNG\r\n\x1a\nFakeTile"
        conn.execute("INSERT INTO tiles VALUES (2, 1, 2, ?)", (fake_png,))
        conn.commit()
        conn.close()

        # Recargar bases MBTiles
        self.tile_service.reload_mbtiles()
        self.assertEqual(len(self.tile_service.mbtiles_conns), 1)

        # Consultar la tesela mediante coordenadas XYZ z=2, x=1, y=1
        code, data, mime = self.tile_service.get_tile(z=2, x=1, y=1)
        self.assertEqual(code, 200)
        self.assertEqual(data, fake_png)
        self.assertEqual(mime, "image/png")

        # Verificar metadatos reportados en get_status
        status = self.tile_service.get_status()
        self.assertTrue(status["has_local_maps"])
        self.assertEqual(status["mbtiles_count"], 1)
        self.assertEqual(status["mbtiles_files"][0]["name"], "Mapa de Prueba")


if __name__ == "__main__":
    unittest.main()
