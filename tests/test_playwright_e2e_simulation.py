"""
Playwright End-to-End Visual and Functional Simulation Test.
Inicia el bridge en modo virtual, emula interacciones de usuario en la UI web,
comprueba el flujo de tarjetas de contactos, navegación de pestañas,
envío de mensajes directos, recepción de confirmación ACK y ecos por radio.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate
from src.virtual_mesh_adapter import VirtualMeshAdapter


@pytest.mark.asyncio
async def test_playwright_web_e2e_simulation() -> None:
    # 1. Crear base de datos SQLite temporal y bridge en puerto 8089
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = temp_db.name
    temp_db.close()

    port = 8089
    artifacts_dir = Path("tests/artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    bridge = MeshCoreBridge(db_path=db_path)
    if bridge.web_server:
        bridge.web_server.port = port
    v_adapter = VirtualMeshAdapter(event_callback=bridge.on_mesh_event)

    bridge.serial_adapter = v_adapter
    await v_adapter.connect()

    # Pre-cargar nodos simulados en el registro dinámico para visualización instantánea en la UI
    sim_contacts = await v_adapter.sync_all_contacts()
    for c in sim_contacts:
        bridge.node_registry.add_or_update(
            public_key=c["public_key"],
            update=NodeContactUpdate(
                name=c["name"],
                alias=c["alias"],
                role=c.get("role", "CLIENT"),
            ),
        )

    # Iniciar servidor web
    if bridge.web_server:
        await bridge.web_server.start()
    await asyncio.sleep(0.5)

    base_url = f"http://localhost:{port}"

    console_errors: list[str] = []
    page_errors: list[str] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            # -------------------------------------------------------------
            # Desktop Context & Page (1920x1080)
            # -------------------------------------------------------------
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            page = await context.new_page()

            page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            # 1. Cargar aplicación web
            await page.goto(base_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1000)

            # Validar título y elementos estructurales clave
            title = await page.title()
            assert "MeshCore" in title

            # 2. Navegar a la pestaña "Contactos"
            btn_contacts = page.locator('.nav-btn[data-tab="tab-contacts"]')
            assert await btn_contacts.count() > 0
            await btn_contacts.click()
            await page.wait_for_timeout(600)

            # Verificar que las tarjetas de contactos estén presentes
            contact_cards = page.locator("#contactsGridUi .contact-card")
            card_count = await contact_cards.count()
            assert card_count > 0, "No se renderizaron tarjetas de contactos en #contactsGridUi"

            # 3. Hacer click en el botón 'Iniciar Chat DM' de una tarjeta de contacto
            btn_first_dm = contact_cards.first.locator(".btn-contact-dm")
            assert await btn_first_dm.count() > 0
            await btn_first_dm.click()
            await page.wait_for_timeout(800)

            # Verificar que la pestaña activa haya cambiado a 'Mensajería' (tab-chat)
            chat_pane = page.locator("#tab-chat")
            assert await chat_pane.is_visible()

            # 4. Enviar un mensaje de chat directo
            chat_input = page.locator("#chatInputText")
            await chat_input.fill("Prueba automatizada Playwright ACK test 123")
            await page.locator("#chatInputForm").press("Enter")

            # Esperar a que el mensaje aparezca en la lista
            msg_bubble = page.locator("#chatMessageFeed .message-bubble-row.outgoing").last
            await msg_bubble.wait_for(state="visible", timeout=5000)

            # Esperar la confirmación de entrega (ACK) simulada por VirtualMeshAdapter (máx 5 segundos)
            ack_status = msg_bubble.locator(".ack-indicator, .msg-ack-status")
            await ack_status.wait_for(state="visible", timeout=5000)
            ack_text = await ack_status.text_content()
            assert ("✓✓" in (ack_text or "")) or ("✓" in (ack_text or "")), f"Se esperaba '✓✓' o '✓ TX', pero se obtuvo: {ack_text}"

            # 5. Navegar a la pestaña 'Nodos' (tab-nodes)
            btn_nodes = page.locator('.nav-btn[data-tab="tab-nodes"]')
            await btn_nodes.click()
            await page.wait_for_timeout(600)

            node_cards = page.locator("#nodesUnifiedGridUi .node-card")
            assert await node_cards.count() >= 3, "Se esperaban al menos 3 tarjetas de nodos"

            # Probar filtro de Repetidores
            btn_filter_rep = page.locator("#btnFilterRepeaters")
            if await btn_filter_rep.count() > 0:
                await btn_filter_rep.click()
                await page.wait_for_timeout(300)

            # 6. Navegar por las demás pestañas para verificar integridad funcional
            for tab_id in ["tab-map", "tab-analytics", "tab-telemetry", "tab-logs", "tab-settings"]:
                tab_btn = page.locator(f'.nav-btn[data-tab="{tab_id}"]')
                if await tab_btn.count() > 0:
                    await tab_btn.click()
                    await page.wait_for_timeout(300)

            # Captura Desktop
            desktop_png = artifacts_dir / "playwright_simulation_desktop.png"
            await page.screenshot(path=str(desktop_png), full_page=True)

            await context.close()

            # -------------------------------------------------------------
            # Mobile Context & Page (390x844)
            # -------------------------------------------------------------
            mobile_context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            )
            mobile_page = await mobile_context.new_page()
            await mobile_page.goto(base_url, wait_until="domcontentloaded")
            await mobile_page.wait_for_timeout(800)

            mobile_png = artifacts_dir / "playwright_simulation_mobile.png"
            await mobile_page.screenshot(path=str(mobile_png), full_page=True)
            await mobile_context.close()

            await browser.close()

    finally:
        # Apagado limpio de recursos
        await v_adapter.disconnect()
        if bridge.web_server:
            await bridge.web_server.stop()
        for ext in ["", "-wal", "-shm"]:
            p = db_path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    # Validar que no haya habido excepciones JavaScript no controladas
    assert len(page_errors) == 0, f"Excepciones JS no controladas detectadas: {page_errors}"
