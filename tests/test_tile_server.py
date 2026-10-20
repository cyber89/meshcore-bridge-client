"""HTTP tile contracts using a temporary MBTiles database and ephemeral loopback port."""

import sqlite3
import struct

import httpx

from src.bridge_core import MeshCoreBridge
from src.web.asgi_server import AsgiWebServer


async def test_tile_server(virtual_bridge: MeshCoreBridge) -> None:
    server = virtual_bridge.web_server
    assert isinstance(server, AsgiWebServer)
    assert server.server is not None
    tile_bytes = b"\x89PNG\r\n\x1a\nFixtureTile"
    database = server.tile_service.maps_dir / "fixture.mbtiles"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
        connection.execute("INSERT INTO metadata VALUES ('name', 'Fixture'), ('format', 'png')")
        connection.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
        connection.execute("INSERT INTO tiles VALUES (0, 0, 0, ?)", (tile_bytes,))
    server.tile_service.reload_mbtiles()
    origin = f"http://127.0.0.1:{server.server.sockets[0].getsockname()[1]}"

    async with httpx.AsyncClient(base_url=origin, trust_env=False, timeout=5) as client:
        assert (await client.get("/api/map/status")).status_code == 401
        login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"}, headers={"Origin": origin})
        assert login.status_code == 200
        credentials = await client.put(
            "/api/auth/credentials",
            json={"username": "qa-tiles", "password": "isolated tile owner password", "current_password": "admin"},
            headers={"Origin": origin, "X-CSRF-Token": login.json()["csrf_token"]},
        )
        assert credentials.status_code == 200
        assert credentials.json()["must_change_credentials"] is False

        status = await client.get("/api/map/status")
        assert status.status_code == 200
        assert status.json()["data"]["has_local_maps"] is True
        assert status.json()["data"]["mbtiles_count"] == 1

        tile = await client.get("/api/map/tiles/0/0/0.png")
        assert (tile.status_code, tile.headers["content-type"], tile.content) == (200, "image/png", tile_bytes)
        assert tile.headers["cache-control"] == "private, max-age=86400"
        assert "Cookie" in tile.headers["vary"]
        fallback = await client.get("/api/map/tiles/18/999/999.png")
        assert fallback.status_code == 200
        assert fallback.headers["content-type"] == "image/png"
        assert fallback.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack(">II", fallback.content[16:24]) == (256, 256)
        assert (await client.get("/api/map/tiles/0/1/0.png")).status_code == 404
