import asyncio, sys
from pathlib import Path

sys.path.insert(0, r"c:\Users\Ruby\Desktop\meshcore-bridge")

from playwright.async_api import async_playwright
from src.bridge_core import MeshCoreBridge
from src.virtual_mesh_adapter import VirtualMeshAdapter
from src.web.http_server import MeshCoreWebServer

async def test_e2e():
    bridge = MeshCoreBridge()
    adapter = VirtualMeshAdapter()
    bridge.serial_adapter = adapter
    await adapter.connect()
    server = MeshCoreWebServer(bridge=bridge, host='127.0.0.1', port=8094)
    await server.start()
    out_dir = Path(r"c:\Users\Ruby\Desktop\meshcore-bridge\tests\artifacts")
    
    console_logs = []
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page(viewport={'width': 1920, 'height': 1080})
        page.on("console", lambda m: console_logs.append(f"{m.type}: {m.text}"))
        
        await page.goto('http://127.0.0.1:8094', wait_until='networkidle')
        await page.wait_for_timeout(500)

        # 1. Inspect Settings tab -> Mapas Offline subtab
        await page.click('button[data-tab="tab-settings"]')
        await page.wait_for_timeout(300)
        await page.click('button[data-subtab="local-storage-maps"]')
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(out_dir / 'settings_map_offline_subtab.png'), full_page=True)

        # 2. Inspect Map tab -> Click Local Layer and Zoom 2 to see sample MBTiles rendered
        await page.click('button[data-tab="tab-map"]')
        await page.wait_for_timeout(500)
        await page.click('button[data-layer="local"]')
        await page.evaluate("() => { if (window.app && window.app.map) window.app.map.setView([0, 0], 2); }")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(out_dir / 'map_local_sample_rendered.png'), full_page=True)

        await b.close()

    await server.stop()
    await adapter.disconnect()
    print('Console logs:', console_logs)
    print('LOCAL MAPS E2E TEST COMPLETED!')

if __name__ == '__main__':
    asyncio.run(test_e2e())
