"""
Automated Browser Console and Frontend QA Auditor for MeshCore Bridge.
Tests all tabs, subtabs, modals, toggles and listens for console logs, errors and page exceptions.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.async_api import ConsoleMessage, async_playwright

from src.bridge_core import MeshCoreBridge
from src.virtual_mesh_adapter import VirtualMeshAdapter


async def run_browser_audit() -> int:
    port = 8095
    bridge = MeshCoreBridge()
    if bridge.web_server:
        bridge.web_server.port = port
    v_adapter = VirtualMeshAdapter(event_callback=bridge.on_mesh_event)
    bridge.serial_adapter = v_adapter
    await v_adapter.connect()
    await bridge.web_server.start()
    await asyncio.sleep(0.5)

    base_url = f"http://localhost:{port}"

    console_logs: list[dict[str, str]] = []
    page_errors: list[str] = []
    failed_requests: list[dict[str, Any]] = []

    def on_console(msg: ConsoleMessage) -> None:
        console_logs.append({
            "type": msg.type,
            "text": msg.text,
            "location": f"{msg.location.get('url', '')}:{msg.location.get('lineNumber', 0)}" if msg.location else ""
        })

    def on_page_error(exc: Any) -> None:
        page_errors.append(str(exc))

    exit_code = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            page = await context.new_page()

            page.on("console", on_console)
            page.on("pageerror", on_page_error)
            page.on("response", lambda r: failed_requests.append({"url": r.url, "status": r.status}) if r.status >= 400 else None)

            print(f"🚀 [AUDIT] Navegando a {base_url}...")
            await page.goto(base_url, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1000)

            # 1. Probar navegación por todas las pestañas principales
            tabs = [
                "tab-chat",
                "tab-contacts",
                "tab-nodes",
                "tab-map",
                "tab-analytics",
                "tab-logs",
                "tab-settings",
            ]

            for tab_id in tabs:
                btn = page.locator(f'.nav-btn[data-tab="{tab_id}"]')
                if await btn.count() > 0:
                    print(f"  👉 Clic en pestaña: {tab_id}")
                    await btn.click()
                    await page.wait_for_timeout(400)
                else:
                    print(f"  ⚠️ Pestaña no encontrada: {tab_id}")

            # 2. Probar subpestañas de Ajustes
            await page.locator('.nav-btn[data-tab="tab-settings"]').click()
            await page.wait_for_timeout(300)

            subtabs = [
                "local-telemetry",
                "local-radio",
                "local-owner-pos",
                "local-console",
                "local-storage-maps",
                "local-security",
            ]

            for sub in subtabs:
                s_btn = page.locator(f'.local-subtab-btn[data-subtab="{sub}"]')
                if await s_btn.count() > 0:
                    print(f"    🔧 Clic en subpestaña ajustes: {sub}")
                    await s_btn.click()
                    await page.wait_for_timeout(300)

            # 3. Probar Toggle Switches
            print("  🕹️ Probando Toggle Switches...")
            # Toggle sidebar collapse
            sidebar_btn = page.locator("#btnToggleSidebar")
            if await sidebar_btn.count() > 0:
                await sidebar_btn.click()
                await page.wait_for_timeout(150)
                await sidebar_btn.click()
                await page.wait_for_timeout(150)

            # Toggle theme (light/dark)
            theme_btn = page.locator("#themeToggleBtn")
            if await theme_btn.count() > 0:
                await theme_btn.click()
                await page.wait_for_timeout(150)
                await theme_btn.click()
                await page.wait_for_timeout(150)

            # Toggle Heatmap en Mapa
            await page.locator('.nav-btn[data-tab="tab-map"]').click()
            await page.wait_for_timeout(200)
            chk_heatmap = page.locator('label[for="chkMapHeatmap"]')
            if await chk_heatmap.count() > 0:
                print("    🔥 Probando toggle Heatmap RF...")
                await chk_heatmap.click()
                await page.wait_for_timeout(200)
                await chk_heatmap.click()
                await page.wait_for_timeout(150)

            # Toggle Debug Mode y Auto-Scroll en Logs
            await page.locator('.nav-btn[data-tab="tab-logs"]').click()
            await page.wait_for_timeout(200)
            chk_debug = page.locator('label[for="chkDebugMode"]')
            if await chk_debug.count() > 0:
                print("    🐞 Probando toggle Modo DEBUG...")
                await chk_debug.click()
                await page.wait_for_timeout(200)
                await chk_debug.click()
                await page.wait_for_timeout(150)

            chk_scroll = page.locator('label[for="chkLogsAutoScroll"]')
            if await chk_scroll.count() > 0:
                print("    📜 Probando toggle Auto-Scroll...")
                await chk_scroll.click()
                await page.wait_for_timeout(150)
                await chk_scroll.click()
                await page.wait_for_timeout(150)

            # Subpestaña Sniffer y Toggle Captura RF
            btn_sub_sniffer = page.locator("#btnSubtabSniffer")
            if await btn_sub_sniffer.count() > 0:
                await btn_sub_sniffer.click()
                await page.wait_for_timeout(200)
                chk_cap = page.locator('label[for="chkSnifferCapture"]')
                if await chk_cap.count() > 0:
                    print("    📡 Probando toggle Captura RF...")
                    await chk_cap.click()
                    await page.wait_for_timeout(150)
                    await chk_cap.click()
                    await page.wait_for_timeout(150)

            # Toggle Modo Repetidor y Posición Fija en Ajustes
            await page.locator('.nav-btn[data-tab="tab-settings"]').click()
            await page.wait_for_timeout(200)
            btn_sub_radio = page.locator('.local-subtab-btn[data-subtab="local-radio"]')
            if await btn_sub_radio.count() > 0:
                await btn_sub_radio.click()
                await page.wait_for_timeout(200)
                chk_rep = page.locator('label[for="localRepeatMode"]')
                if await chk_rep.count() > 0:
                    print("    📻 Probando toggle Modo Repetidor Local...")
                    await chk_rep.click()
                    await page.wait_for_timeout(150)
                    await chk_rep.click()
                    await page.wait_for_timeout(150)

            btn_sub_pos = page.locator('.local-subtab-btn[data-subtab="local-owner-pos"]')
            if await btn_sub_pos.count() > 0:
                await btn_sub_pos.click()
                await page.wait_for_timeout(200)
                chk_pos = page.locator('label[for="localPosFixed"]')
                if await chk_pos.count() > 0:
                    print("    📍 Probando toggle Posición GPS Fija Local...")
                    await chk_pos.click()
                    await page.wait_for_timeout(150)
                    await chk_pos.click()
                    await page.wait_for_timeout(150)

            # 4. Probar Modales y sus Toggle Switches
            print("  📦 Probando Modales y Toggles Internos...")
            # Modal Canales y Toggle Cifrado AES-128
            await page.locator('.nav-btn[data-tab="tab-chat"]').click()
            await page.wait_for_timeout(200)
            btn_add_ch = page.locator("#btnAddChannel")
            if await btn_add_ch.count() > 0:
                await btn_add_ch.click()
                await page.wait_for_timeout(200)
                chk_enc = page.locator('label[for="chModalIsEncrypted"]')
                if await chk_enc.count() > 0:
                    print("    🔐 Probando toggle Cifrado AES-128...")
                    await chk_enc.click()
                    await page.wait_for_timeout(150)
                    await chk_enc.click()
                    await page.wait_for_timeout(150)
                btn_close_ch = page.locator("#btnCancelCreateChannel")
                if await btn_close_ch.count() > 0:
                    await btn_close_ch.click()
                    await page.wait_for_timeout(150)

            # Modal Contactos y Toggle Favorito
            await page.locator('.nav-btn[data-tab="tab-contacts"]').click()
            await page.wait_for_timeout(200)
            btn_add_ct = page.locator("#btnHeaderAddContact")
            if await btn_add_ct.count() > 0:
                await btn_add_ct.click()
                await page.wait_for_timeout(200)
                chk_fav = page.locator('label[for="contactModalFavorite"]')
                if await chk_fav.count() > 0:
                    print("    ⭐ Probando toggle Favorito en Contacto...")
                    await chk_fav.click()
                    await page.wait_for_timeout(150)
                    await chk_fav.click()
                    await page.wait_for_timeout(150)
                btn_close_ct = page.locator("#btnCloseCreateContactModal")
                if await btn_close_ct.count() > 0:
                    await btn_close_ct.click()
                    await page.wait_for_timeout(150)

            # Command Palette
            btn_cmd = page.locator("#btnCommandPalette")
            if await btn_cmd.count() > 0:
                await btn_cmd.click()
                await page.wait_for_timeout(200)
                btn_close_cmd = page.locator("#btnCloseCmdPalette")
                if await btn_close_cmd.count() > 0:
                    await btn_close_cmd.click()
                    await page.wait_for_timeout(150)

            await browser.close()

    finally:
        await v_adapter.disconnect()
        await bridge.web_server.stop()

    print("\n" + "="*60)
    print("📊 RESULTADOS DE LA AUDITORÍA DE CONSOLA Y FRONTEND:")
    print("="*60)

    # Filtrar errores reales vs logs informativos
    errors = [entry for entry in console_logs if entry["type"] == "error"]
    warnings = [entry for entry in console_logs if entry["type"] == "warning"]

    print(f"Total Logs en Consola:    {len(console_logs)}")
    print(f"Excepciones de Página:    {len(page_errors)}")
    print(f"Errores en Consola:       {len(errors)}")
    print(f"Advertencias en Consola:  {len(warnings)}")
    print(f"Peticiones HTTP Fallidas: {len(failed_requests)}")

    if page_errors:
        print("\n❌ EXCEPCIONES DE JAVASCRIPT DETECTADAS:")
        for err in page_errors:
            print(f"  • {err}")
        exit_code = 1

    if errors:
        print("\n❌ ERRORES EN CONSOLA DEL NAVEGADOR:")
        for err in errors:
            print(f"  • [{err['location']}] {err['text']}")
        exit_code = 1

    if warnings:
        print("\n⚠️ ADVERTENCIAS EN CONSOLA:")
        for w in warnings:
            print(f"  • [{w['location']}] {w['text']}")

    if failed_requests:
        print("\n⚠️ PETICIONES FALLIDAS (4xx/5xx):")
        for req in failed_requests:
            print(f"  • {req['status']} -> {req['url']}")

    if exit_code == 0:
        print("\n✅ ¡PASS! Todo el frontend funciona limpiamente sin excepciones en consola.")
    else:
        print("\n❌ ¡FAIL! Se detectaron problemas en el frontend.")

    return exit_code


if __name__ == "__main__":
    code = asyncio.run(run_browser_audit())
    sys.exit(code)
