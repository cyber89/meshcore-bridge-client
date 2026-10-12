"""
Servicio de Mosaicos y Mapas Offline para MeshCore Bridge.
Proporciona soporte autónomo para servir teselas cartográficas locales
desde bases de datos SQLite MBTiles (.mbtiles) o directorios XYZ en disco.
"""

from __future__ import annotations

import logging
import sqlite3
import struct
import threading
import zlib
from pathlib import Path
from typing import Any

import config


class MapTileService:
    """Gestiona el almacenamiento y despacho de teselas cartográficas offline."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        if data_dir:
            self.base_dir = Path(data_dir)
        else:
            self.base_dir = Path(config.DATA_DIR)

        self.maps_dir = self.base_dir / "maps"
        self.tiles_dir = self.maps_dir / "tiles"
        self.mbtiles_conns: list[tuple[Path, sqlite3.Connection, str]] = []
        self._storage_lock = threading.RLock()
        self._default_tactical_tile: bytes = self._generate_tactical_base_tile()
        self._init_storage()

    def _init_storage(self) -> None:
        """Crea directorios necesarios e indexa bases de datos MBTiles locales."""
        try:
            self.maps_dir.mkdir(parents=True, exist_ok=True)
            self.tiles_dir.mkdir(parents=True, exist_ok=True)
            self.reload_mbtiles()
        except Exception as e:
            logging.warning("Error inicializando almacenamiento de mapas offline: %s", e)

    def close(self) -> None:
        with self._storage_lock:
            self._close()

    def _close(self) -> None:
        """Cierra todas las conexiones activas a bases de datos MBTiles."""
        for item in self.mbtiles_conns:
            try:
                item[1].close()
            except Exception:
                pass
        self.mbtiles_conns.clear()

    def reload_mbtiles(self) -> None:
        with self._storage_lock:
            self._reload_mbtiles()

    def _reload_mbtiles(self) -> None:
        """Cierra y vuelve a cargar los archivos .mbtiles presentes en data/maps/."""
        self.close()

        if not self.maps_dir.exists():
            return

        import urllib.request
        for mbtiles_path in self.maps_dir.glob("*.mbtiles"):
            try:
                if not mbtiles_path.resolve().is_relative_to(self.maps_dir.resolve()):
                    continue
                # Conexión SQLite de solo lectura optimizada para alto rendimiento.
                # Se utiliza pathname2url para codificar caracteres especiales como '#' o '?' en la URI.
                clean_url_path = urllib.request.pathname2url(str(mbtiles_path.resolve()))
                uri = f"file:{clean_url_path}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
                conn.execute("PRAGMA journal_mode = OFF")
                conn.execute("PRAGMA synchronous = OFF")
                conn.execute("PRAGMA cache_size = -8000")  # 8MB de cache en RAM
                # Determinar el esquema de coordenadas a partir de metadata (TMS por defecto según MBTiles 1.3)
                scheme = "tms"
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT value FROM metadata WHERE name = 'scheme'")
                    m_row = cur.fetchone()
                    if m_row and m_row[0]:
                        scheme = str(m_row[0]).strip().lower()
                except Exception:
                    pass
                self.mbtiles_conns.append((mbtiles_path, conn, scheme))
                logging.info("Mapa MBTiles offline cargado: %s", mbtiles_path.name)
            except Exception as err:
                logging.warning("No se pudo abrir archivo MBTiles '%s': %s", mbtiles_path.name, err)

    def get_tile(self, z: int, x: int, y: int) -> tuple[int, bytes, str]:
        with self._storage_lock:
            return self._get_tile(z, x, y)

    def _get_tile(self, z: int, x: int, y: int) -> tuple[int, bytes, str]:
        """
        Recupera los bytes de una tesela XYZ específica.
        Busca primero en directorios XYZ y posteriormente en archivos MBTiles indexados.
        """
        # Validación estricta de límites de zoom (0..22) y coordenadas Web Mercator
        if not (0 <= z <= 22):
            return 404, b"", "text/plain"
        max_coord = 1 << z
        if not (0 <= x < max_coord and 0 <= y < max_coord):
            return 404, b"", "text/plain"

        # 1. Búsqueda en directorio de archivos sueltos XYZ (data/maps/tiles/{z}/{x}/{y}.ext)
        for ext in ("png", "jpg", "jpeg", "webp", "pbf"):
            tile_path = self.tiles_dir / str(z) / str(x) / f"{y}.{ext}"
            if tile_path.is_file() and tile_path.resolve().is_relative_to(self.tiles_dir.resolve()):
                try:
                    data = tile_path.read_bytes()
                    mime = self._detect_mime(data, ext)
                    return 200, data, mime
                except Exception as e:
                    logging.debug("Error leyendo archivo de tesela %s: %s", tile_path, e)

        # 2. Búsqueda en bases de datos SQLite MBTiles
        # MBTiles utiliza la convención TMS (Tile Map Service) donde el eje Y está invertido respecto a XYZ
        tms_y = (1 << z) - 1 - y

        for mbtiles_path, conn, scheme in self.mbtiles_conns:
            try:
                row_y = y if scheme == "xyz" else tms_y
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ? LIMIT 1",
                    (z, x, row_y),
                )
                row = cursor.fetchone()

                if row and row[0]:
                    tile_bytes = bytes(row[0])
                    mime = self._detect_mime(tile_bytes)
                    return 200, tile_bytes, mime
            except Exception as err:
                logging.debug("Error consultando MBTiles '%s': %s", mbtiles_path.name, err)

        # Si no se encuentra en MBTiles ni archivos sueltos, se retorna la tesela táctica offline predeterminada
        return 200, self._default_tactical_tile, "image/png"

    @staticmethod
    def _generate_tactical_base_tile() -> bytes:
        """
        Genera una tesela base PNG táctica en memoria (256x256 px).
        Garantiza que la aplicación funcione 100% offline y sin descargas de internet,
        proporcionando una grilla de referencia táctica con bordes de tesela y retícula.
        """
        width, height = 256, 256
        raw = bytearray()
        for y in range(height):
            raw.append(0)  # Filtro PNG: None (0)
            for x in range(width):
                is_border = (x == 0 or y == 0 or x == 255 or y == 255)
                is_subgrid = (x % 64 == 0 or y % 64 == 0)
                is_crosshair = (x in (127, 128) and 122 <= y <= 133) or (y in (127, 128) and 122 <= x <= 133)
                if is_crosshair:
                    raw.extend((52, 72, 98, 255))
                elif is_border:
                    raw.extend((42, 54, 71, 255))
                elif is_subgrid:
                    raw.extend((26, 35, 48, 255))
                else:
                    raw.extend((18, 24, 33, 255))

        def chunk(tag: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        idat = chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        iend = chunk(b"IEND", b"")
        return sig + ihdr + idat + iend

    def _detect_mime(self, data: bytes, default_ext: str = "png") -> str:
        """Detecta el tipo MIME de los datos a partir de sus números mágicos."""
        if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        if len(data) >= 2 and data[:2] == b"\x1f\x8b":
            return "application/x-protobuf"  # Vector tiles comprimidas con gzip

        mime_map = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
            "pbf": "application/x-protobuf",
        }
        return mime_map.get(default_ext.lower(), "image/png")

    def get_status(self) -> dict[str, Any]:
        with self._storage_lock:
            return self._get_status()

    def _get_status(self) -> dict[str, Any]:
        """Devuelve el estado del almacenamiento de mapas locales y MBTiles detectados."""
        mbtiles_info = []
        for path, conn, _scheme in self.mbtiles_conns:
            try:
                size_mb = round(path.stat().st_size / (1024 * 1024), 2)
                cursor = conn.cursor()
                metadata: dict[str, str] = {}
                try:
                    cursor.execute("SELECT name, value FROM metadata")
                    metadata = dict(cursor.fetchall())
                except Exception:
                    pass

                mbtiles_info.append({
                    "filename": path.name,
                    "size_mb": size_mb,
                    "name": metadata.get("name", path.stem),
                    "format": metadata.get("format", "raster"),
                    "min_zoom": metadata.get("minzoom", "0"),
                    "max_zoom": metadata.get("maxzoom", "18"),
                    "description": metadata.get("description", ""),
                })
            except Exception as e:
                logging.debug("Error extrayendo metadatos de %s: %s", path.name, e)

        loose_tiles_found = any(self.tiles_dir.glob("*/*/*.*")) if self.tiles_dir.exists() else False

        return {
            "has_local_maps": True,
            "maps_directory": str(self.maps_dir.resolve()),
            "tiles_directory": str(self.tiles_dir.resolve()),
            "mbtiles_count": len(mbtiles_info),
            "mbtiles_files": mbtiles_info,
            "has_loose_tiles": loose_tiles_found,
            "tactical_fallback": True,
        }
