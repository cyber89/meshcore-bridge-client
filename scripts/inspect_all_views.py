"""
Script to inspect all views, tabs and subtabs with Playwright,
capturing screenshots of each view to audit styles and layout.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import AsyncExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from isolated_frontend_station import isolated_frontend_station, login_inspection_context
from playwright.async_api import async_playwright


async def inspect_all_views() -> None:
    output_dir = Path("tests/artifacts/views")
    output_dir.mkdir(parents=True, exist_ok=True)

    async with isolated_frontend_station() as (_bridge, base_url):
        async with async_playwright() as p, AsyncExitStack() as cleanup:
            browser = await p.chromium.launch(headless=True)
            cleanup.push_async_callback(browser.close)
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            await login_inspection_context(context, base_url)
            page = await context.new_page()

            await page.goto(base_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1000)

            # Captura Desktop (1920x1080)
            tabs = [
                ("01_chat", "tab-chat"),
                ("02_contacts", "tab-contacts"),
                ("03_nodes", "tab-nodes"),
                ("04_map", "tab-map"),
                ("05_analytics", "tab-analytics"),
                ("06_logs", "tab-logs"),
                ("07_settings", "tab-settings"),
            ]

            for prefix, tab_id in tabs:
                btn = page.locator(f'.nav-btn[data-tab="{tab_id}"]')
                if await btn.count() > 0:
                    await btn.click()
                    await page.wait_for_timeout(800)
                    screenshot_path = output_dir / f"{prefix}_{tab_id}.png"
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"✓ Capturada vista Desktop: {screenshot_path}")

            # Capturar subpestaña Sniffer dentro de Logs
            btn_logs = page.locator('.nav-btn[data-tab="tab-logs"]')
            if await btn_logs.count() > 0:
                await btn_logs.click()
                await page.wait_for_timeout(400)
                btn_sniffer = page.locator("#btnSubtabSniffer")
                if await btn_sniffer.count() > 0:
                    await btn_sniffer.click()
                    await page.wait_for_timeout(600)
                    sniffer_path = output_dir / "06_sub_sniffer.png"
                    await page.screenshot(path=str(sniffer_path), full_page=True)
                    print(f"✓ Capturada subpestaña Sniffer: {sniffer_path}")

            # Capturar subpestañas de Ajustes
            btn_settings = page.locator('.nav-btn[data-tab="tab-settings"]')
            if await btn_settings.count() > 0:
                await btn_settings.click()
                await page.wait_for_timeout(400)

                subtabs = [
                    "local-telemetry",
                    "local-radio",
                    "local-owner-pos",
                    "local-console",
                    "local-storage-maps",
                    "local-security",
                    "local-services",
                ]

                for sub in subtabs:
                    s_btn = page.locator(f'.local-subtab-btn[data-subtab="{sub}"]')
                    if await s_btn.count() > 0:
                        await s_btn.click()
                        await page.wait_for_timeout(500)
                        sub_path = output_dir / f"07_sub_{sub}.png"
                        await page.screenshot(path=str(sub_path), full_page=True)
                        print(f"✓ Capturada subpestaña: {sub_path}")

            # Captura Móvil (390x844 - iPhone / Smartphone estándar)
            mobile_context = await browser.new_context(
                viewport={"width": 390, "height": 844}, is_mobile=True
            )
            await login_inspection_context(mobile_context, base_url)
            mobile_page = await mobile_context.new_page()
            await mobile_page.goto(base_url, wait_until="domcontentloaded")
            await mobile_page.wait_for_timeout(1000)

            mobile_tabs = [
                ("01_mobile_chat", "tab-chat"),
                ("02_mobile_contacts", "tab-contacts"),
                ("03_mobile_nodes", "tab-nodes"),
                ("04_mobile_map", "tab-map"),
                ("05_mobile_analytics", "tab-analytics"),
                ("06_mobile_logs", "tab-logs"),
                ("07_mobile_settings", "tab-settings"),
            ]

            for prefix, tab_id in mobile_tabs:
                await mobile_page.evaluate(f"""
                    const btn = document.querySelector('.nav-btn[data-tab="{tab_id}"]');
                    if (btn) btn.click();
                    const offcanvas = document.getElementById("appSidebar");
                    if (offcanvas && typeof bootstrap !== "undefined" && bootstrap.Offcanvas) {{
                        const inst = bootstrap.Offcanvas.getInstance(offcanvas);
                        if (inst) inst.hide();
                    }}
                """)
                await mobile_page.wait_for_timeout(800)
                m_path = output_dir / f"{prefix}_{tab_id}.png"
                await mobile_page.screenshot(path=str(m_path), full_page=True)
                print(f"✓ Capturada vista Móvil: {m_path}")

            await mobile_page.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(inspect_all_views())
