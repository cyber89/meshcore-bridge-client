import asyncio
import sys
import json
import urllib.request
import urllib.error

sys.path.insert(0, r"c:\Users\Ruby\Desktop\meshcore-bridge")

from src.bridge_core import MeshCoreBridge
from src.virtual_mesh_adapter import VirtualMeshAdapter
from src.web.http_server import MeshCoreWebServer

def fetch_url(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "TileTester/1.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, resp.headers.get("Content-Type"), resp.read()

async def test_tile_server():
    bridge = MeshCoreBridge()
    adapter = VirtualMeshAdapter()
    bridge.serial_adapter = adapter
    await adapter.connect()
    server = MeshCoreWebServer(bridge=bridge, host='127.0.0.1', port=8092)
    await server.start()

    # 1. Test /api/map/status
    status, content_type, data = await asyncio.to_thread(fetch_url, "http://127.0.0.1:8092/api/map/status")
    status_data = json.loads(data.decode())
    print("STATUS DATA:", json.dumps(status_data, indent=2))
    assert status == 200
    assert status_data["status"] == "ok"
    assert status_data["data"]["has_local_maps"] is True
    assert status_data["data"]["mbtiles_count"] >= 1

    # 2. Test /api/map/tiles/0/0/0.png
    status, mime, tile_bytes = await asyncio.to_thread(fetch_url, "http://127.0.0.1:8092/api/map/tiles/0/0/0.png")
    assert status == 200
    assert mime == "image/png"
    print(f"TILE 0/0/0 bytes: {len(tile_bytes)}, PNG header: {tile_bytes[:4] == b'\x89PNG'}")
    assert tile_bytes[:4] == b'\x89PNG'

    # 3. Test non-existing tile
    def fetch_404():
        try:
            return fetch_url("http://127.0.0.1:8092/api/map/tiles/18/999/999.png")
        except urllib.error.HTTPError as e:
            return e.code, None, None
            
    code, _, _ = await asyncio.to_thread(fetch_404)
    print(f"Non-existing tile returned expected code: {code}")
    assert code == 404

    await server.stop()
    await adapter.disconnect()
    print("ALL MAP TILE SERVER TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(test_tile_server())
