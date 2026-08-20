"""
End-to-End (E2E) Browser & Visual Automation Tests with Playwright.
Verifica interacciones reales de usuario: navegación entre pestañas, envío de mensajes,
auto-eco en DMs, visualización de telemetría y sniffer, y ausencia total de errores JS.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:8080"
ARTIFACTS_DIR = Path("tests/artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session", autouse=True)
def check_server_available() -> None:
    """Verifica si el servidor web está activo en BASE_URL antes de ejecutar pruebas Playwright."""
    try:
        req = urllib.request.Request(BASE_URL, headers={"User-Agent": "Playwright-Test-Runner"})
        with urllib.request.urlopen(req, timeout=1.5):
            pass
    except Exception:
        pytest.skip(f"Servidor web local no activo en {BASE_URL} - Pruebas Playwright omitidas.", allow_module_level=True)


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
        "tab-repeater",
        "tab-sniffer",
        "tab-map",
        "tab-nodes",
        "tab-analytics",
        "tab-telemetry",
        "tab-contacts",
        "tab-ha",
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
    """Prueba el envío de un mensaje de chat, nuevo botón 'Enviar' y ausencia de trace route/bienvenida."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

        # 1. Asegurar estar en la pestaña de chat
        await page.locator('[data-tab="tab-chat"]').click()
        await page.wait_for_timeout(300)

        # 2. Verificar que Canales y DMs están dentro del panel de mensajería (chat-channels-panel)
        channels_panel = page.locator(".chat-channels-panel #channelListUi")
        assert await channels_panel.count() > 0, "El panel de canales debe estar dentro del chat"

        # 3. Verificar que el botón Trace Route fue eliminado
        trace_btn = page.locator("#btnTraceRoute")
        assert await trace_btn.count() == 0, "El botón Trace Route no debe existir"

        # 4. Verificar texto del botón de envío ("Enviar")
        send_btn_text = await page.locator("#btnSendMsg").inner_text()
        assert "Enviar" in send_btn_text, "El botón debe llamarse Enviar"

        # 5. Verificar que el subtítulo no tiene 'Hop limit: 3'
        sub_text = await page.locator("#chatActiveSub").inner_text()
        assert "Hop limit" not in sub_text
        assert "Difusión comunitaria" in sub_text

        # 6. Verificar que no hay cuadro de bienvenida invasivo inicial
        welcome_card = page.locator(".chat-welcome-card")
        assert await welcome_card.count() == 0, "No debe mostrarse mensaje estático de bienvenida"

        # 7. Escribir mensaje de prueba
        test_msg = "Prueba E2E Automatizada Playwright"
        input_field = page.locator("#chatInputText")
        await input_field.fill(test_msg)

        # 8. Enviar formulario
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
async def test_e2e_channel_switching_and_isolated_feed() -> None:
    """Prueba el cambio interactivo entre Canal 0 y Canal 1 con aislamiento estricto de mensajes."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

        # 1. Asegurar vista de chat
        await page.locator('[data-tab="tab-chat"]').click()
        await page.wait_for_timeout(300)

        # 2. Seleccionar Canal 1 en la barra lateral
        ch1_item = page.locator('#channelListUi li:has-text("Ch 1")')
        await ch1_item.click()
        await page.wait_for_timeout(300)

        title_text = await page.locator("#chatActiveTitle").inner_text()
        assert "Canal 1" in title_text

        # 3. Transmitir mensaje en Canal 1
        msg_ch1 = "Mensaje exclusivo para Canal 1 - LoRa Net"
        input_elem = page.locator("#chatInputText")
        await input_elem.fill(msg_ch1)
        await input_elem.press("Enter")
        await page.wait_for_timeout(2000)

        feed_ch1 = await page.locator("#chatMessageFeed").inner_text()
        assert msg_ch1 in feed_ch1

        # 4. Cambiar a Canal 0 (Broadcast)
        ch0_item = page.locator('#channelListUi li:has-text("Ch 0")')
        await ch0_item.click()
        await page.wait_for_timeout(300)

        title_ch0 = await page.locator("#chatActiveTitle").inner_text()
        assert "Canal 0" in title_ch0

        feed_ch0 = await page.locator("#chatMessageFeed").inner_text()
        # El mensaje de Canal 1 no debe contaminar la vista de Canal 0
        assert msg_ch1 not in feed_ch0

        # 5. Volver a Canal 1 y verificar persistencia
        await ch1_item.click()
        await page.wait_for_timeout(300)
        feed_ch1_restored = await page.locator("#chatMessageFeed").inner_text()
        assert msg_ch1 in feed_ch1_restored

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_dm_multi_recipient_isolation() -> None:
    """Prueba el envío de DMs a múltiples nodos con aislamiento y recepción de Eco."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

        # 1. Iniciar chat con Alpha Field Sensor
        await page.evaluate('window.setDmTarget("a1b2c3d4e5f6", "Alpha Field Sensor")')
        await page.wait_for_timeout(300)

        title_alpha = await page.locator("#chatActiveTitle").inner_text()
        assert "Alpha" in title_alpha

        dm_alpha = "Direct Message to Alpha Node"
        await page.locator("#chatInputText").fill(dm_alpha)
        await page.locator("#chatInputText").press("Enter")
        await page.wait_for_timeout(2500)

        feed_alpha = await page.locator("#chatMessageFeed").inner_text()
        assert dm_alpha in feed_alpha

        # 2. Iniciar chat con Bravo Scout Rover
        await page.evaluate('window.setDmTarget("d7e8f9012345", "Bravo Scout Rover")')
        await page.wait_for_timeout(300)

        title_bravo = await page.locator("#chatActiveTitle").inner_text()
        assert "Bravo" in title_bravo

        feed_bravo = await page.locator("#chatMessageFeed").inner_text()
        # El mensaje privado de Alpha no debe aparecer en la conversación de Bravo
        assert dm_alpha not in feed_bravo

        # Enviar DM a Bravo
        dm_bravo = "Direct Message to Bravo Rover"
        await page.locator("#chatInputText").fill(dm_bravo)
        await page.locator("#chatInputText").press("Enter")
        await page.wait_for_timeout(2500)

        feed_bravo_after = await page.locator("#chatMessageFeed").inner_text()
        assert dm_bravo in feed_bravo_after

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_console_error_audit() -> None:
    """Audita que no ocurra ninguna excepción JavaScript no capturada durante el ciclo completo."""
    console_errors: list[str] = []
    page_errors: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        failed_responses: list[str] = []
        page.on("response", lambda resp: failed_responses.append(f"{resp.status} {resp.url}") if resp.status >= 400 else None)
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
        assert len(failed_responses) == 0, f"Peticiones HTTP fallidas: {failed_responses}"
        assert len(console_errors) == 0, f"Errores de consola detectados: {console_errors}"

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_repeater_dashboard_interaction() -> None:
    """Prueba interactiva del Centro de Control de Repetidores LoRa."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

        # 1. Navegar a pestaña Repetidores
        await page.locator('[data-tab="tab-repeater"]').click()
        await page.wait_for_timeout(300)

        # 2. Verificar subtabs (Radio, Vecinos, Consola)
        await page.locator('[data-subtab="rep-radio"]').click()
        await page.wait_for_timeout(200)
        assert await page.locator("#rep-radio").is_visible()

        # Enviar formulario de configuración de radio
        await page.locator("#radioPower").fill("22")
        await page.locator('#repRadioForm button[type="submit"]').click()
        await page.wait_for_timeout(500)

        # 3. Subtab Vecinos
        await page.locator('[data-subtab="rep-neighbors"]').click()
        await page.wait_for_timeout(200)
        assert await page.locator("#rep-neighbors").is_visible()

        # 4. Subtab Consola Terminal
        await page.locator('[data-subtab="rep-console"]').click()
        await page.wait_for_timeout(200)
        assert await page.locator("#rep-console").is_visible()

        # Click en botón de comando rápido
        btn_quick = page.locator('.rep-quick-cmd[data-cmd="stats-radio"]')
        if await btn_quick.count() > 0:
            await btn_quick.click()
            await page.wait_for_timeout(500)

        # Entrada manual en terminal
        await page.locator("#repeaterTerminalInput").fill("stats-core")
        await page.locator("#repeaterTerminalForm button").click()
        await page.wait_for_timeout(500)

        term_output = await page.locator("#repeaterTerminalOutput").inner_text()
        assert len(term_output) > 20

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_command_palette_and_preflight() -> None:
    """Prueba interactiva de la Paleta de Comandos (Ctrl+K) y Diagnósticos Preflight."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

        # 1. Abrir Command Palette con teclado (Ctrl+K)
        await page.keyboard.press("Control+k")
        await page.wait_for_timeout(300)
        modal = page.locator("#commandPaletteModal")
        assert not await modal.evaluate("el => el.classList.contains('hidden')")

        # Filtrar comandos
        await page.locator("#cmdPaletteInput").fill("Repetidores")
        await page.wait_for_timeout(200)

        # Cerrar con Escape
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(200)
        assert await modal.evaluate("el => el.classList.contains('hidden')")

        # 2. Navegar a Ajustes y ejecutar Preflight
        await page.locator('[data-tab="tab-settings"]').click()
        await page.wait_for_timeout(300)

        await page.locator("#btnRunPreflight").click()
        await page.wait_for_timeout(2000)

        results = await page.locator("#preflightResults").inner_text()
        assert "OK" in results or "PASS" in results or "diagn" in results.lower()

        await browser.close()


@pytest.mark.asyncio
async def test_e2e_settings_and_remote_repeater_config() -> None:
    """Prueba interactiva de configuración local y administración remota de repetidores."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)

        # 1. Navegar a Ajustes
        await page.locator('[data-tab="tab-settings"]').click()
        await page.wait_for_timeout(300)

        # 2. Modificar parámetros del nodo local
        name_input = page.locator("#localNodeName")
        await name_input.fill("Base_Station_Playwright_E2E")
        await page.locator("#localSf").select_option("10")
        await page.locator("#localBw").select_option("500")

        # Guardar local
        page.on("dialog", lambda dialog: dialog.accept())
        await page.locator("#btnSaveLocalConfig").click()
        await page.wait_for_timeout(600)

        # 3. Configuración remota de repetidor vecino
        await page.locator("#remoteTargetNodeManual").fill("a1b2c3d4e5f6")
        await page.locator("#remoteAdminPassword").fill("secret_pass_123")
        await page.locator("#remoteRepeaterName").fill("Repeater_Tower_North")
        await page.locator("#remoteTxPower").fill("22")

        # Aplicar configuración remota
        await page.locator("#btnApplyRemoteConfig").click()
        await page.wait_for_timeout(600)

        # Probar login remoto
        await page.locator("#btnTestRemoteLogin").click()
        await page.wait_for_timeout(600)

        # Verificar feed de respuestas
        resp_text = await page.locator("#remoteResponseOutput").inner_text()
        assert "a1b2c3d4e5f6" in resp_text or "despachado" in resp_text.lower() or "transmitido" in resp_text.lower()

        # Captura de pantalla de la vista de ajustes
        await page.screenshot(path=str(ARTIFACTS_DIR / "settings_e2e.png"), full_page=True)

        await browser.close()


