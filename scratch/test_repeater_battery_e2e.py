import asyncio, sys
from pathlib import Path

sys.path.insert(0, r"c:\Users\Ruby\Desktop\meshcore-bridge")

from playwright.async_api import async_playwright
from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate
from src.virtual_mesh_adapter import VirtualMeshAdapter
from src.web.http_server import MeshCoreWebServer

async def test_repeater_battery_flow():
    bridge = MeshCoreBridge()
    adapter = VirtualMeshAdapter()
    bridge.serial_adapter = adapter
    await adapter.connect()

    repeater_pk = "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0"
    
    # 1. Registrar el repetidor inicialmente sin batería (batería pendiente)
    bridge.node_registry.add_or_update(
        repeater_pk,
        NodeContactUpdate(
            name="Repeater_Alpha",
            role="REPEATER",
            latitude=20.1580,
            longitude=-75.1950,
            last_snr=7.2,
            last_rssi=-88,
        )
    )

    server = MeshCoreWebServer(bridge=bridge, host='127.0.0.1', port=8098)
    await server.start()
    out_dir = Path(r"c:\Users\Ruby\Desktop\meshcore-bridge\tests\artifacts")
    
    console_logs = []
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page(viewport={'width': 1920, 'height': 1080})
        page.on("console", lambda m: console_logs.append(f"{m.type}: {m.text}"))
        
        await page.goto('http://127.0.0.1:8098', wait_until='networkidle')
        await page.wait_for_timeout(600)

        # 1. Ir a la pestaña de Nodos
        await page.click('button[data-tab="tab-nodes"]')
        await page.wait_for_timeout(500)

        # 2. Hacer clic en "Administrar" del repetidor
        await page.click(f'.node-card[data-pk="{repeater_pk}"] .btn-manage-node-repeater')
        await page.wait_for_timeout(500)

        # 3. Verificar que la subpestaña de terminal dice "Terminal" y no "Terminal Linux"
        term_tab_text = await page.inner_text('button[data-subtab="rep-console"]')
        print(f"Subtab Terminal Text: '{term_tab_text.strip()}'")
        assert "Terminal" in term_tab_text, "Terminal tab should contain 'Terminal'"
        assert "Terminal Linux" not in term_tab_text, "Terminal tab should NOT say 'Terminal Linux'"

        # 4. Desbloquear la vista de administración simulando autenticación previa exitosa
        await page.evaluate(f"""() => {{
            window.app.authenticatedRepeaters.add("{repeater_pk}");
            window.app.unlockRepeaterAdminView("{repeater_pk}");
        }}""")
        await page.wait_for_timeout(400)

        # 5. Simular respuesta del repetidor al comando 'bat' o advert con batería
        await server.broadcast_event({
            "type": "repeater_response",
            "event_type": "repeater_response",
            "sender": repeater_pk,
            "text": "Battery: 4120mV (92%)",
            "telemetry": {
                "battery_pct": 92,
                "voltage_v": 4.12,
                "solar_v": 5.10,
                "uptime": "14d 6h 32m",
                "noise_floor_dbm": -118,
            }
        })
        await page.wait_for_timeout(800)

        # 6. Comprobar que el valor de batería en el modal se actualizó
        bat_text = await page.inner_text('#repBatValue')
        volt_text = await page.inner_text('#repVoltValue')
        print(f"Modal Battery: {bat_text}, Voltage: {volt_text}")
        assert "91%" in bat_text or "92%" in bat_text, f"Expected 91-92% in battery, got {bat_text}"
        assert "4.12" in volt_text, f"Expected 4.12 V in voltage, got {volt_text}"

        # 7. Cambiar a la subpestaña Terminal
        await page.click('button[data-subtab="rep-console"]')
        await page.wait_for_timeout(400)

        # 8. Escribir comando 'bat' en la consola terminal
        await page.fill('#repeaterTerminalInput', 'bat')
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(400)

        # Simular respuesta directa tipo bootmv: "> 4180 mV"
        await server.broadcast_event({
            "type": "repeater_response",
            "event_type": "repeater_response",
            "sender": repeater_pk,
            "text": "> 4180 mV",
        })
        await page.wait_for_timeout(600)

        # Comprobar que la respuesta del terminal actualizó la batería a ~98% (4180mV)
        bat_text_updated = await page.inner_text('#repBatValue')
        volt_text_updated = await page.inner_text('#repVoltValue')
        print(f"Updated Battery after terminal response: {bat_text_updated}, Voltage: {volt_text_updated}")
        assert "98%" in bat_text_updated or "97%" in bat_text_updated, f"Expected ~98% in battery, got {bat_text_updated}"

        await page.screenshot(path=str(out_dir / 'repeater_admin_battery_live.png'), full_page=True)

        await b.close()

    await server.stop()
    await adapter.disconnect()
    print('Console logs:', console_logs)
    print('REPEATER BATTERY & TERMINAL VERIFICATION TEST PASSED!')

if __name__ == '__main__':
    asyncio.run(test_repeater_battery_flow())
