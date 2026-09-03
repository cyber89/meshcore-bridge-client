"""
Genera una base de datos MBTiles de ejemplo con metadatos estándar y teselas de vista general.
"""

import sqlite3
from pathlib import Path


def create_sample_mbtiles():
    maps_dir = Path(r"c:\Users\Ruby\Desktop\meshcore-bridge\data\maps")
    maps_dir.mkdir(parents=True, exist_ok=True)
    db_path = maps_dir / "overview_sample.mbtiles"

    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    c.execute("""
        CREATE TABLE metadata (name text, value text);
    """)
    c.execute("""
        CREATE TABLE tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob);
    """)
    c.execute("""
        CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row);
    """)

    # Insert metadata
    metadata = [
        ("name", "MeshCore Offline Tactical Overview"),
        ("type", "baselayer"),
        ("version", "1.0.0"),
        ("description", "Mosaico base offline para navegación local sin conexión"),
        ("format", "png"),
        ("minzoom", "0"),
        ("maxzoom", "5"),
        ("attribution", "MeshCore Bridge Tactical Maps"),
    ]
    c.executemany("INSERT INTO metadata VALUES (?, ?)", metadata)

    # Generar una tesela PNG 256x256 dark sólida con grícula
    # 1x1 PNG dark navy: \x89PNG\r\n\x1a\n...
    # Un PNG 256x256 válido comprimido
    import struct
    import zlib

    def make_png_tile(text="OFFLINE TILE"):
        width, height = 256, 256
        raw_rows = []
        for y in range(height):
            row = bytearray([0]) # Filter type None
            for x in range(width):
                # Dark tactical grid color
                is_grid = (x % 32 == 0) or (y % 32 == 0) or (x == 0) or (y == 0) or (x == 255) or (y == 255)
                if is_grid:
                    row.extend([20, 30, 45, 255]) # Dark slate border
                else:
                    row.extend([11, 15, 25, 255]) # Deep navy background
            raw_rows.append(bytes(row))
        raw_data = b"".join(raw_rows)
        compressed = zlib.compress(raw_data, 6)

        png = bytearray(b"\x89PNG\r\n\x1a\n")

        # IHDR
        ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
        png.extend(struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc))

        # IDAT
        idat_crc = zlib.crc32(b"IDAT" + compressed)
        png.extend(struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc))

        # IEND
        iend_crc = zlib.crc32(b"IEND")
        png.extend(struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc))

        return bytes(png)

    tile_bytes = make_png_tile()

    # Insertar teselas para zooms 0, 1, 2
    tiles_to_insert = []
    for z in range(3):
        max_coord = 1 << z
        for x in range(max_coord):
            for y in range(max_coord):
                # TMS y
                tms_y = (1 << z) - 1 - y
                tiles_to_insert.append((z, x, tms_y, tile_bytes))

    c.executemany("INSERT INTO tiles VALUES (?, ?, ?, ?)", tiles_to_insert)
    conn.commit()
    conn.close()
    print(f"Created sample MBTiles: {db_path} with {len(tiles_to_insert)} tiles.")

if __name__ == "__main__":
    create_sample_mbtiles()
