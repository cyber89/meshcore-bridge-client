"""Local WiFi Companion UI requires a manual WiFi read and clears write-only passwords immediately."""

from __future__ import annotations

from typing import Any

import pytest
from playwright.async_api import Page, Route, expect


async def wifi_settings(page: Page) -> None:
    await page.reload()
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
          safe_commands:['get radio','get freq','get cad','get radio.rxgain','get path.hash.mode','get wifi.ssid','get wifi.enabled','get wifi.status','get wifi.ip'],
          writable_preferences:['cad','wifi']}}}});
    }""")


@pytest.mark.parametrize("width,height", [(1920, 1080), (390, 844)])
async def test_wifi_requires_manual_read_and_clears_password_field(
    browser_page: Page, width: int, height: int
) -> None:
    page = browser_page
    await page.set_viewport_size({"width": width, "height": height})
    calls: list[dict[str, Any]] = []

    async def admin(route: Route) -> None:
        body = route.request.post_data_json
        calls.append({"body": body, "csrf": bool(route.request.headers.get("x-csrf-token"))})
        if body["action"] == "cli":
            await route.fulfill(json={"status": "ok", "result": {"status": "ok", "scope": "firmware", "result": "> OldNet"}})
            return
        await route.fulfill(json={"status": "ok", "result": {
            "status": "ok", "scope": "firmware", "action": "set_wifi",
            "ssid": body.get("ssid"), "password_updated": bool(body.get("password")),
            "enabled": body.get("enabled"), "cleared": bool(body.get("clear")),
            "reboot_required": True, "acknowledged": True, "hardware_verified": False,
        }})

    await page.route("**/api/admin", admin)
    await wifi_settings(page)
    await expect(page.locator("#firmwareWifiSave")).to_be_disabled()
    await expect(page.locator("#firmwareWifiClear")).to_be_disabled()

    await page.locator("#firmwareCliCommand").select_option("get wifi.ssid")
    await page.locator("#firmwareCliReadButton").click()
    await expect(page.locator("#firmwareWifiSave")).to_be_enabled()
    await expect(page.locator("#firmwareWifiClear")).to_be_enabled()

    await page.locator("#firmwareWifiSsid").fill("MeshField")
    await page.locator("#firmwareWifiPassword").fill("WriteOnlySecret99!")
    await page.locator("#firmwareWifiEnabled").select_option("on")
    await page.locator("#firmwareWifiSave").click()

    await expect(page.locator("#firmwareWifiPassword")).to_have_value("")
    await expect(page.locator("#firmwareWifiSave")).to_be_disabled()
    await expect(page.locator("#firmwareWifiStatus")).to_contain_text("WiFi")
    assert calls == [
        {"body": {"action": "cli", "scope": "firmware", "command": "get wifi.ssid"}, "csrf": True},
        {
            "body": {
                "action": "set_wifi",
                "scope": "firmware",
                "ssid": "MeshField",
                "password": "WriteOnlySecret99!",
                "enabled": True,
            },
            "csrf": True,
        },
    ]
    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
