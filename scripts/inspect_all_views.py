"""
Script to inspect all views, tabs and subtabs with Playwright,
capturing screenshots of each view to audit styles and layout.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.async_api import async_playwright

from src.bridge_core import MeshCoreBridge
from src.virtual_mesh_adapter import VirtualMeshAdapter





async def inspect_all_views() -> None:
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = temp_db.name
    temp_db.close()

    port = 8092
    output_dir = Path("tests/artifacts/views")
    output_dir.mkdir(parents=True, exist_ok=True)

    bridge = MeshCoreBridge(db_path=db_path)
    if bridge.web_server:
        bridge.web_server.port = port
    v_adapter = VirtualMeshAdapter(event_callback=bridge.on_mesh_event)
    bridge.serial_adapter = v_adapter
    await v_adapter.connect()
    await bridge.web_server.start()
    await asyncio.sleep(0.5)

    base_url = f"http://localhost:{port}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})

            await page.goto(base_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1000)

            tabs = [
                ("01_chat", "tab-chat"),
                ("02_contacts", "tab-contacts"),
                ("03_nodes", "tab-nodes"),
                ("04_map", "tab-map"),
                ("05_sniffer", "tab-sniffer"),
                ("06_analytics", "tab-analytics"),
                ("07_ha", "tab-ha"),
                ("08_logs", "tab-logs"),
                ("09_settings", "tab-settings"),
            ]

            for prefix, tab_id in tabs:
                btn = page.locator(f'.nav-btn[data-tab="{tab_id}"]')
                if await btn.count() > 0:
                    await btn.click()
                    await page.wait_for_timeout(600)
                    screenshot_path = output_dir / f"{prefix}_{tab_id}.png"
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"✓ Capturada vista: {screenshot_path}")

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
                    "local-actions",
                    "local-storage-maps",
                ]

                for sub in subtabs:
                    s_btn = page.locator(f'.local-subtab-btn[data-subtab="{sub}"]')
                    if await s_btn.count() > 0:
                        await s_btn.click()
                        await page.wait_for_timeout(400)
                        sub_path = output_dir / f"09_sub_{sub}.png"
                        await page.screenshot(path=str(sub_path), full_page=True)
                        print(f"✓ Capturada subpestaña: {sub_path}")

            await browser.close()

    finally:
        await v_adapter.disconnect()
        await bridge.web_server.stop()
        for ext in ["", "-wal", "-shm"]:
            p = db_path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


if __name__ == "__main__":
    asyncio.run(inspect_all_views())
