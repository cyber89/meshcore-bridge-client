import asyncio, sys
from pathlib import Path

sys.path.insert(0, r"c:\Users\Ruby\Desktop\meshcore-bridge")

from playwright.async_api import async_playwright
from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate
from src.virtual_mesh_adapter import VirtualMeshAdapter
from src.web.http_server import MeshCoreWebServer

async def test_heatmap():
    bridge = MeshCoreBridge()
    adapter = VirtualMeshAdapter()
    bridge.serial_adapter = adapter
    await adapter.connect()
    
    # Asegurar que los nodos en NodeRegistry tengan coordenadas GPS para el Heatmap
    bridge.node_registry.add_or_update(
        "8d5accef196f5986567b3c7e915fc8e5fc3fe689cadca190d02523aef24b46bc",
        NodeContactUpdate(
            name="Base_Station",
            role="LOCAL",
            latitude=20.1425,
            longitude=-75.2105,
            last_snr=11.5,
            last_rssi=-70,
            noise_floor_dbm=-118,
        )
    )
    bridge.node_registry.add_or_update(
        "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0",
        NodeContactUpdate(
            name="Repeater_Alpha",
            role="REPEATER",
            latitude=20.1580,
            longitude=-75.1950,
            last_snr=7.2,
            last_rssi=-88,
            noise_floor_dbm=-115,
        )
    )
    bridge.node_registry.add_or_update(
        "f9e8d7c6b5a43210fedcba9876543210fedcba9876543210fedcba9876543210",
        NodeContactUpdate(
            name="Sensor_Sierra",
            role="SENSOR",
            latitude=20.1650,
            longitude=-75.2250,
            last_snr=-3.5,
            last_rssi=-112,
            noise_floor_dbm=-116,
        )
    )

    server = MeshCoreWebServer(bridge=bridge, host='127.0.0.1', port=8095)
    await server.start()
    out_dir = Path(r"c:\Users\Ruby\Desktop\meshcore-bridge\tests\artifacts")
    
    console_logs = []
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page(viewport={'width': 1920, 'height': 1080})
        page.on("console", lambda m: console_logs.append(f"{m.type}: {m.text}"))
        
        await page.goto('http://127.0.0.1:8095', wait_until='networkidle')
        await page.wait_for_timeout(600)

        # 1. Navegar a la pestaña de Mapa
        await page.click('button[data-tab="tab-map"]')
        await page.wait_for_timeout(600)

        # 2. Activar el Heatmap RF
        await page.click('#btnToggleHeatmap')
        await page.wait_for_timeout(1000)

        # 3. Comprobar que el grupo rfHeatmapGroup tiene capas añadidas
        heatmap_count = await page.evaluate("""() => {
            if (window.app && window.app.rfHeatmapGroup) {
                return window.app.rfHeatmapGroup.getLayers().length;
            }
            return 0;
        }""")
        print(f"Heatmap layers in map: {heatmap_count}")
        assert heatmap_count >= 2, f"Expected at least 2 circle layers, got {heatmap_count}"

        # 4. Capturar screenshot con el Heatmap activo
        await page.screenshot(path=str(out_dir / 'map_heatmap_active.png'), full_page=True)

        # 5. Simular actualización en vivo de telemetría de Sensor_Sierra (mejora de señal SNR +10dB, RSSI -65)
        bridge.node_registry.add_or_update(
            "f9e8d7c6b5a43210fedcba9876543210fedcba9876543210fedcba9876543210",
            NodeContactUpdate(
                name="Sensor_Sierra",
                role="SENSOR",
                latitude=20.1650,
                longitude=-75.2250,
                last_snr=9.8,
                last_rssi=-65,
                noise_floor_dbm=-117,
            )
        )
        
        # Emitir actualización WS
        await server.broadcast_event({
            "event": "node_update",
            "type": "node_update",
            "public_key": "f9e8d7c6b5a43210fedcba9876543210fedcba9876543210fedcba9876543210",
            "data": {
                "public_key": "f9e8d7c6b5a43210fedcba9876543210fedcba9876543210fedcba9876543210",
                "name": "Sensor_Sierra",
                "role": "SENSOR",
                "latitude": 20.1650,
                "longitude": -75.2250,
                "last_snr": 9.8,
                "last_rssi": -65,
            }
        })
        
        await page.wait_for_timeout(1200)
        await page.screenshot(path=str(out_dir / 'map_heatmap_realtime_updated.png'), full_page=True)

        await b.close()

    await server.stop()
    await adapter.disconnect()
    print('Console logs:', console_logs)
    print('HEATMAP RF VERIFICATION TEST PASSED!')

if __name__ == '__main__':
    asyncio.run(test_heatmap())
