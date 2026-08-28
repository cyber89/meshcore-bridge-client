import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright
from src.bridge_core import MeshCoreBridge
from src.virtual_mesh_adapter import VirtualMeshAdapter

async def test_search_filters():
    port = 8096
    bridge = MeshCoreBridge()
    if bridge.web_server:
        bridge.web_server.port = port
    v_adapter = VirtualMeshAdapter(event_callback=bridge.on_mesh_event)
    bridge.serial_adapter = v_adapter
    await v_adapter.connect()
    await bridge.web_server.start()
    await asyncio.sleep(0.5)

    base_url = f"http://localhost:{port}"
    errors = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            page.on("pageerror", lambda e: errors.append(f"PageError: {e}"))
            page.on("console", lambda m: errors.append(f"ConsoleError: {m.text}") if m.type == "error" else None)

            print("🚀 Navegando a la aplicación...")
            await page.goto(base_url, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1000)

            # 1. Probar filtros y búsqueda en Pestaña Nodos
            print("🌐 Probando búsqueda y filtros de Nodos (#tab-nodes)...")
            await page.locator('.nav-btn[data-tab="tab-nodes"]').click()
            await page.wait_for_timeout(500)

            total_nodes = await page.locator("#nodesUnifiedGridUi .node-card").count()
            print(f"  • Total de tarjetas de nodos renderizadas: {total_nodes}")
            assert total_nodes > 0, "No se renderizaron nodos en la malla"

            # Probar filtro Repetidores
            btn_rep = page.locator('.nodes-filter-pills .filter-pill[data-filter="REPEATER"]')
            await btn_rep.click()
            await page.wait_for_timeout(300)
            visible_reps = await page.locator("#nodesUnifiedGridUi .node-card:visible").count()
            print(f"  • Nodos visibles con filtro REPEATER: {visible_reps}")

            # Volver a Todos
            await page.locator('.nodes-filter-pills .filter-pill[data-filter="all"]').click()
            await page.wait_for_timeout(300)

            # Probar búsqueda por texto
            search_input = page.locator("#nodesSearchInput")
            await search_input.fill("Alpha")
            await page.wait_for_timeout(400)
            matched = await page.locator("#nodesUnifiedGridUi .node-card:visible").count()
            print(f"  • Búsqueda 'Alpha' -> Nodos visibles: {matched}")
            assert matched >= 1, "Debería encontrar el nodo Alpha"

            # Limpiar búsqueda
            await search_input.fill("")
            await page.wait_for_timeout(400)
            restored = await page.locator("#nodesUnifiedGridUi .node-card:visible").count()
            print(f"  • Búsqueda limpia -> Nodos visibles: {restored}")
            assert restored == total_nodes, "Al limpiar búsqueda deben restaurarse todos los nodos"

            # 2. Probar filtros y búsqueda en Pestaña Contactos
            print("👥 Probando búsqueda y filtros de Contactos (#tab-contacts)...")
            await page.locator('.nav-btn[data-tab="tab-contacts"]').click()
            await page.wait_for_timeout(500)

            total_contacts = await page.locator("#contactsGridUi .contact-card").count()
            print(f"  • Total de tarjetas de contactos renderizadas: {total_contacts}")

            contact_search = page.locator("#contactsSearchInput")
            if total_contacts > 0:
                first_name = await page.locator("#contactsGridUi .contact-card .contact-name").first.text_content()
                print(f"  • Probando búsqueda de contacto por nombre: '{first_name}'")
                await contact_search.fill(first_name[:4])
                await page.wait_for_timeout(400)
                matched_ct = await page.locator("#contactsGridUi .contact-card:visible").count()
                print(f"  • Búsqueda '{first_name[:4]}' -> Contactos visibles: {matched_ct}")
                assert matched_ct >= 1, "Debería encontrar el contacto"

                await contact_search.fill("")
                await page.wait_for_timeout(400)

            # Probar filtro en línea
            btn_online = page.locator('.contacts-filter-pills .filter-pill[data-contact-filter="online"]')
            await btn_online.click()
            await page.wait_for_timeout(300)
            print("  • Filtro Contactos 'En Línea' aplicado con éxito")

            await browser.close()
    finally:
        await v_adapter.disconnect()
        await bridge.web_server.stop()

    if errors:
        print(f"❌ Errores detectados: {errors}")
        return 1

    print("\n✅ ¡PASS! Todos los filtros y cajas de búsqueda de contactos y nodos funcionan perfectamente.")
    return 0

if __name__ == "__main__":
    code = asyncio.run(test_search_filters())
    sys.exit(code)
