"""HTTP tile contracts using a temporary MBTiles database and ephemeral loopback port."""

import asyncio
import json
import sqlite3
import urllib.error
import urllib.request

from src.bridge_core import MeshCoreBridge


def fetch_url(url: str) -> tuple[int, str | None, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "TileTester/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.headers.get("Content-Type"), response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type"), error.read()


async def test_tile_server(virtual_bridge: MeshCoreBridge) -> None:
    server = virtual_bridge.web_server
    assert server is not None and server.server is not None
    tile_bytes = b"\x89PNG\r\n\x1a\nFixtureTile"
    database = server.tile_service.maps_dir / "fixture.mbtiles"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
        connection.execute("INSERT INTO metadata VALUES ('name', 'Fixture'), ('format', 'png')")
        connection.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
        connection.execute("INSERT INTO tiles VALUES (0, 0, 0, ?)", (tile_bytes,))
    server.tile_service.reload_mbtiles()
    origin = f"http://127.0.0.1:{server.server.sockets[0].getsockname()[1]}"

    status, _, body = await asyncio.to_thread(fetch_url, origin + "/api/map/status")
    assert status == 200
    assert json.loads(body)["data"]["has_local_maps"] is True
    assert json.loads(body)["data"]["mbtiles_count"] == 1

    status, mime, body = await asyncio.to_thread(fetch_url, origin + "/api/map/tiles/0/0/0.png")
    assert (status, mime, body) == (200, "image/png", tile_bytes)
    status, _, _ = await asyncio.to_thread(fetch_url, origin + "/api/map/tiles/18/999/999.png")
    assert status == 404
