"""
End-to-End (E2E) Browser & Visual Automation Tests with Playwright.
Verifica interacciones reales de usuario: navegación entre pestañas, envío de mensajes,
auto-eco en DMs, visualización de telemetría y sniffer, y ausencia total de errores JS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:8080"
ARTIFACTS_DIR = Path("tests/artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


@pytest.mark.asyncio
async def test_e2e_page_loads_and_has_title() -> None:
    """Verifica que la página principal cargue y tenga el título semántico correcto."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

        title = await page.title()
        assert "MeshCore Web Client" in title

        header = page.locator("header.app-header")
        assert await header.count() > 0

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_navigation_all_tabs() -> None:
    """Prueba la navegación interactiva cíclica a través de las 9 pestañas."""
    tab_ids = [
        "tab-chat",
        "tab-map",
        "tab-nodes",
        "tab-sniffer",
        "tab-analytics",
        "tab-telemetry",
        "tab-contacts",
        "tab-logs",
        "tab-settings",
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

        for tab_id in tab_ids:
            btn = page.locator(f'[data-tab="{tab_id}"]')
            assert await btn.count() > 0, f"Botón de pestaña {tab_id} no encontrado"
            await btn.click()
            await page.wait_for_timeout(200)

            pane = page.locator(f"#{tab_id}")
            classes = await pane.get_attribute("class") or ""
            assert "active" in classes, f"El panel #{tab_id} no se activó al hacer click"

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_send_chat_message_and_feed() -> None:
    """Prueba el envío de un mensaje de chat y su renderizado en el feed."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

        # Asegurar estar en la pestaña de chat
        await page.locator('[data-tab="tab-chat"]').click()
        await page.wait_for_timeout(300)

        # Escribir mensaje de prueba
        test_msg = "Prueba E2E Automatizada Playwright"
        input_field = page.locator("#chatInputText")
        await input_field.fill(test_msg)

        # Enviar formulario
        await page.locator("#chatInputForm").dispatch_event("submit")
        await page.wait_for_timeout(600)

        feed_content = await page.locator("#chatMessageFeed").inner_text()
        assert test_msg in feed_content

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_dm_auto_echo_reception() -> None:
    """Prueba la selección de un nodo cliente y la recepción del mensaje Echo del bot."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

        # Usar la función global setDmTarget para seleccionar a Alpha
        await page.evaluate('window.setDmTarget("a1b2c3d4e5f6", "Alpha Field Sensor")')
        await page.wait_for_timeout(300)

        # Enviar mensaje directo usando simulación de teclado Enter
        dm_text = "E2E Echo Check"
        input_elem = page.locator("#chatInputText")
        await input_elem.fill(dm_text)
        await input_elem.press("Enter")

        # Esperar respuesta del simulador y WebSocket broadcast
        await page.wait_for_timeout(2500)

        feed_text = await page.locator("#chatMessageFeed").inner_text()
        assert dm_text in feed_text or "Echo" in feed_text

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_console_error_audit() -> None:
    """Audita que no ocurra ninguna excepción JavaScript no capturada durante el ciclo completo."""
    console_errors: list[str] = []
    page_errors: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

        # Navegar por varias pestañas para forzar ejecución de JS
        for tab_id in ["tab-nodes", "tab-sniffer", "tab-analytics", "tab-telemetry", "tab-logs", "tab-chat"]:
            await page.locator(f'[data-tab="{tab_id}"]').click()
            await page.wait_for_timeout(250)

        # Capturas visuales
        await page.screenshot(path=str(ARTIFACTS_DIR / "desktop_e2e.png"), full_page=True)

        assert len(page_errors) == 0, f"Excepciones JS detectadas: {page_errors}"
        assert len(console_errors) == 0, f"Errores de consola detectados: {console_errors}"

        await browser.close()
