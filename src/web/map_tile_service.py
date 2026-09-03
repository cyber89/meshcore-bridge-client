"""
Servicio de Mosaicos y Mapas Offline para MeshCore Bridge.
Proporciona soporte autónomo para servir teselas cartográficas locales
desde bases de datos SQLite MBTiles (.mbtiles) o directorios XYZ en disco.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any


class MapTileService:
    """Gestiona el almacenamiento y despacho de teselas cartográficas offline."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        if data_dir:
            self.base_dir = Path(data_dir)
        else:
            self.base_dir = Path(__file__).resolve().parent.parent.parent / "data"

        self.maps_dir = self.base_dir / "maps"
        self.tiles_dir = self.maps_dir / "tiles"
        self.mbtiles_conns: list[tuple[Path, sqlite3.Connection]] = []
        self._init_storage()

    def _init_storage(self) -> None:
        """Crea directorios necesarios e indexa bases de datos MBTiles locales."""
        try:
            self.maps_dir.mkdir(parents=True, exist_ok=True)
            self.tiles_dir.mkdir(parents=True, exist_ok=True)
            self.reload_mbtiles()
        except Exception as e:
            logging.warning("Error inicializando almacenamiento de mapas offline: %s", e)

    def reload_mbtiles(self) -> None:
        """Cierra y vuelve a cargar los archivos .mbtiles presentes en data/maps/."""
        for _, conn in self.mbtiles_conns:
            try:
                conn.close()
            except Exception:
                pass
        self.mbtiles_conns.clear()

        if not self.maps_dir.exists():
            return

        for mbtiles_path in self.maps_dir.glob("*.mbtiles"):
            try:
                # Conexión SQLite de solo lectura optimizada para alto rendimiento
                uri = f"file:{mbtiles_path.resolve()}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
                conn.execute("PRAGMA journal_mode = OFF")
                conn.execute("PRAGMA synchronous = OFF")
                conn.execute("PRAGMA cache_size = -8000")  # 8MB de cache en RAM
                self.mbtiles_conns.append((mbtiles_path, conn))
                logging.info("Mapa MBTiles offline cargado: %s", mbtiles_path.name)
            except Exception as err:
                logging.warning("No se pudo abrir archivo MBTiles '%s': %s", mbtiles_path.name, err)

    def get_tile(self, z: int, x: int, y: int) -> tuple[int, bytes, str]:
        """
        Recupera los bytes de una tesela XYZ específica.
        Busca primero en directorios XYZ y posteriormente en archivos MBTiles indexados.
        """
        # 1. Búsqueda en directorio de archivos sueltos XYZ (data/maps/tiles/{z}/{x}/{y}.ext)
        for ext in ("png", "jpg", "jpeg", "webp", "pbf"):
            tile_path = self.tiles_dir / str(z) / str(x) / f"{y}.{ext}"
            if tile_path.is_file():
                try:
                    data = tile_path.read_bytes()
                    mime = self._detect_mime(data, ext)
                    return 200, data, mime
                except Exception as e:
                    logging.debug("Error leyendo archivo de tesela %s: %s", tile_path, e)

        # 2. Búsqueda en bases de datos SQLite MBTiles
        # MBTiles utiliza la convención TMS (Tile Map Service) donde el eje Y está invertido respecto a XYZ
        tms_y = (1 << z) - 1 - y

        for mbtiles_path, conn in self.mbtiles_conns:
            try:
                # Probar primero con coordenada estándar TMS
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ? LIMIT 1",
                    (z, x, tms_y),
                )
                row = cursor.fetchone()

                # Si no se encuentra, probar con coordenada directa XYZ (algunos generadores usan XYZ)
                if not row:
                    cursor.execute(
                        "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ? LIMIT 1",
                        (z, x, y),
                    )
                    row = cursor.fetchone()

                if row and row[0]:
                    tile_bytes = bytes(row[0])
                    mime = self._detect_mime(tile_bytes)
                    return 200, tile_bytes, mime
            except Exception as err:
                logging.debug("Error consultando MBTiles '%s': %s", mbtiles_path.name, err)

        return 404, b"", ""

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
        """Devuelve el estado del almacenamiento de mapas locales y MBTiles detectados."""
        mbtiles_info = []
        for path, conn in self.mbtiles_conns:
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
        has_any_local_maps = bool(mbtiles_info or loose_tiles_found)

        return {
            "has_local_maps": has_any_local_maps,
            "maps_directory": str(self.maps_dir.resolve()),
            "tiles_directory": str(self.tiles_dir.resolve()),
            "mbtiles_count": len(mbtiles_info),
            "mbtiles_files": mbtiles_info,
            "has_loose_tiles": loose_tiles_found,
        }
