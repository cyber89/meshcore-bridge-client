"""CAD preference writes require a manual observation on the isolated SPA."""

from __future__ import annotations

from typing import Any

import pytest
from playwright.async_api import Page, Route, expect


async def preference_settings(page: Page) -> None:
    menu = page.locator('[data-bs-toggle="offcanvas"][data-bs-target="#appSidebar"]')
    if await menu.is_visible():
        await menu.click()
    await page.locator('[data-tab="tab-settings"]').click()
    await page.locator('[data-subtab="local-telemetry"]').click()
    await page.wait_for_load_state("networkidle")
    await page.evaluate("""async () => {
      const {eventBus, EVENTS} = await import('/js/core/eventbus.js');
      eventBus.emit(EVENTS.METRICS_UPDATE, {serial_connected:true, radio_connected:true});
      eventBus.emit(EVENTS.RX_PACKET, {type:'self_info',data:{serial_connected:true,radio_connected:true,
        capabilities:{firmware_cli:{state:'present',reason:'available',companion_protocol:14,session_generation:1,
          safe_commands:['get radio','get freq','get cad','get radio.rxgain','get path.hash.mode'],
          writable_preferences:['cad']}}}});
    }""")


@pytest.mark.parametrize("width,height", [(1920, 1080), (390, 844)])
async def test_cad_requires_manual_read_and_never_automatically_reads_back(browser_page: Page, width: int, height: int) -> None:
    page = browser_page
    await page.set_viewport_size({"width": width, "height": height})
    calls: list[dict[str, Any]] = []

    async def admin(route: Route) -> None:
        body = route.request.post_data_json
        calls.append({"body": body, "csrf": bool(route.request.headers.get("x-csrf-token"))})
        result = {"status": "ok", "scope": "firmware", "result": "> off"} if body["action"] == "cli" else {
            "status": "ok", "scope": "firmware", "action": "set_preference", "preference": "cad",
            "value": True, "acknowledged": True, "hardware_verified": False,
        }
        await route.fulfill(json={"status": "ok", "result": result})

    await page.route("**/api/admin", admin)
    await preference_settings(page)
    await expect(page.locator("#firmwareCadSave")).to_be_disabled()
    await page.locator("#firmwareCliCommand").select_option("get cad")
    await page.locator("#firmwareCliReadButton").click()
    await expect(page.locator("#firmwareCadSave")).to_be_enabled()
    await page.locator("#firmwareCadValue").select_option("on")
    await page.locator("#firmwareCadSave").click()
    await expect(page.locator("#firmwareCadSave")).to_be_disabled()
    await expect(page.locator("#firmwareCadStatus")).to_contain_text("CAD")
    assert calls == [
        {"body": {"action": "cli", "scope": "firmware", "command": "get cad"}, "csrf": True},
        {"body": {"action": "set_preference", "scope": "firmware", "preference": "cad", "value": True}, "csrf": True},
    ]
    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")


async def test_disconnect_invalidates_cad_observation(browser_page: Page) -> None:
    page = browser_page

    async def read(route: Route) -> None:
        await route.fulfill(json={"status": "ok", "result": {"status": "ok", "scope": "firmware", "result": "> on"}})

    await page.route("**/api/admin", read)
    await preference_settings(page)
    await page.locator("#firmwareCliCommand").select_option("get cad")
    await page.locator("#firmwareCliReadButton").click()
    await expect(page.locator("#firmwareCadSave")).to_be_enabled()
    await page.evaluate("""async () => {
      const {eventBus, EVENTS} = await import('/js/core/eventbus.js');
      eventBus.emit(EVENTS.METRICS_UPDATE,{serial_connected:false,radio_connected:false});
    }""")
    await expect(page.locator("#firmwareCadSave")).to_be_disabled()


async def test_new_generation_invalidates_cad_without_disconnected_sample(browser_page: Page) -> None:
    page = browser_page

    async def read(route: Route) -> None:
        await route.fulfill(json={"status": "ok", "result": {"status": "ok", "scope": "firmware", "result": "> on"}})

    await page.route("**/api/admin", read)
    await preference_settings(page)
    await page.locator("#firmwareCliCommand").select_option("get cad")
    await page.locator("#firmwareCliReadButton").click()
    await expect(page.locator("#firmwareCadSave")).to_be_enabled()
    await page.evaluate("""async () => {
      const {eventBus, EVENTS} = await import('/js/core/eventbus.js');
      eventBus.emit(EVENTS.RX_PACKET,{type:'self_info',data:{serial_connected:true,radio_connected:true,
        capabilities:{firmware_cli:{state:'present',reason:'available',companion_protocol:14,session_generation:2,
          safe_commands:['get radio','get freq','get cad','get radio.rxgain','get path.hash.mode'],
          writable_preferences:['cad']}}}});
    }""")
    await expect(page.locator("#firmwareCadSave")).to_be_disabled()
