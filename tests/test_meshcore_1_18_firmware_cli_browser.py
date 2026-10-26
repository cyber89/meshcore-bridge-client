"""Manual firmware getters in the real SPA, using isolated virtual responses."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Page, Route, expect


async def capability(page: Page, state: str = "present", reason: str = "available", **extra: Any) -> None:
    snapshot = {
        "state": state, "reason": reason, "companion_protocol": 14,
        "firmware_version": "1.18.0", "sdk_version": "2.3.15", "model": "QA radio <b>literal</b>",
        "transport": "tcp", "safe_commands": ["get radio", "get freq"] if state == "present" else [],
    }
    snapshot.update(extra)
    await page.evaluate("""async snapshot => {
      const { eventBus, EVENTS } = await import('/js/core/eventbus.js');
      window.__qaFirmwareCliSnapshot = snapshot;
      const connected = snapshot.reason !== 'disconnected';
      eventBus.emit(EVENTS.METRICS_UPDATE, {serial_connected:connected,radio_connected:connected});
      eventBus.emit(EVENTS.RX_PACKET, {type:'self_info',data:{serial_connected:connected,radio_connected:connected,capabilities:{firmware_cli:snapshot}}});
    }""", snapshot)


async def settings(page: Page) -> None:
    if not await page.evaluate("window.__qaFirmwareCliConfigRouted === true"):
        await page.evaluate("window.__qaFirmwareCliConfigRouted = true")

        async def reported_config(route: Route) -> None:
            response = await route.fetch()
            body = await response.json()
            snapshot = await page.evaluate("window.__qaFirmwareCliSnapshot || null")
            if snapshot is not None:
                body["data"]["capabilities"]["firmware_cli"] = snapshot
                body["data"]["serial_connected"] = snapshot["reason"] != "disconnected"
                body["data"]["radio_connected"] = snapshot["reason"] != "disconnected"
            await route.fulfill(response=response, json=body)

        await page.route(re.compile(r"/api/config(?:/refresh)?(?:\?.*)?$"), reported_config)
    if not await page.locator("#tab-settings").is_visible():
        menu = page.locator('[data-bs-toggle="offcanvas"][data-bs-target="#appSidebar"]')
        if await menu.is_visible():
            await menu.click()
        await page.locator('[data-tab="tab-settings"]').click()
    await page.locator('[data-subtab="local-telemetry"]').click()
    await page.wait_for_load_state("networkidle")
    # Finish the subtab's config sequence before a test emits its own snapshot.
    await page.evaluate("bridgeApp.settingsModule.fetchLocalNodeConfig()")


@pytest.mark.parametrize("width,height", [(1920, 1080), (390, 844)])
async def test_manual_getters_preserve_drafts_and_render_text_safely(browser_page: Page, width: int, height: int) -> None:
    page = browser_page
    await page.set_viewport_size({"width": width, "height": height})
    requests: list[dict[str, Any]] = []

    async def firmware_reply(route: Route) -> None:
        body = route.request.post_data_json
        assert isinstance(body, dict)
        requests.append({"body": body, "csrf": bool(route.request.headers.get("x-csrf-token"))})
        await route.fulfill(json={"status": "ok", "result": {"status": "ok", "scope": "firmware", "result": "> 915.0 <img src=x onerror=alert(1)>"}})

    await page.route("**/api/admin", firmware_reply)
    await settings(page)
    await expect(page.locator("#firmwareCompatibilityPanel")).to_be_visible()
    await capability(page)
    await expect(page.locator("#firmwareCliReadButton")).to_be_enabled()
    await expect(page.locator("#firmwareCliModel")).to_have_text("QA radio <b>literal</b>")
    assert await page.locator("#firmwareCompatibilityPanel b").count() == 0
    await expect(page.locator("#firmwareCliSdkVersion")).to_have_text("2.3.15")
    await expect(page.locator("#firmwareCliProtocol")).to_have_text("14")
    await page.locator('[data-subtab="local-owner-pos"]').click()
    await page.locator("#localNodeName").fill("Unsaved operator name")
    await settings(page)
    await capability(page)
    await expect(page.locator("#firmwareCliReadButton")).to_be_enabled()
    assert requests == []
    await page.locator("#firmwareCliCommand").select_option("get freq")
    await page.locator("#firmwareCliReadButton").click()
    await expect(page.locator("#firmwareCliOutput")).to_have_text("> 915.0 <img src=x onerror=alert(1)>")
    assert requests == [{"body": {"action": "cli", "scope": "firmware", "command": "get freq"}, "csrf": True}]
    assert await page.locator("#firmwareCliOutput img").count() == 0
    await page.locator('[data-subtab="local-owner-pos"]').click()
    await expect(page.locator("#localNodeName")).to_have_value("Unsaved operator name")
    await settings(page)
    await page.evaluate("I18n.toggle()")
    await expect(page.locator("#firmwareCliReadButton")).to_have_text("Read firmware")
    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    artifacts = Path("tests/artifacts/meshcore-1-18-firmware-cli")
    artifacts.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(artifacts / f"manual-{width}.png"), animations="disabled")


@pytest.mark.parametrize("state,reason", [("unknown", "awaiting_device_info"), ("absent", "protocol_unsupported")])
async def test_unavailable_capability_disables_manual_read(browser_page: Page, state: str, reason: str) -> None:
    await settings(browser_page)
    await expect(browser_page.locator("#firmwareCompatibilityPanel")).to_be_visible()
    await capability(browser_page, state, reason)
    await expect(browser_page.locator("#firmwareCompatibilityPanel")).to_have_attribute("data-state", state)
    await expect(browser_page.locator("#firmwareCliReadButton")).to_be_disabled()
    await expect(browser_page.locator("#firmwareCliReason")).not_to_be_empty()


async def test_capability_change_discards_late_firmware_reply(browser_page: Page) -> None:
    page = browser_page
    gate = asyncio.Event()
    dispatched = asyncio.Event()

    async def delayed_reply(route: Route) -> None:
        dispatched.set()
        await gate.wait()
        await route.fulfill(json={"status": "ok", "result": {"status": "ok", "scope": "firmware", "result": "OLD RADIO RESULT"}})

    await page.route("**/api/admin", delayed_reply)
    await settings(page)
    await capability(page)
    await page.locator("#firmwareCliReadButton").click()
    await asyncio.wait_for(dispatched.wait(), timeout=5)
    await capability(page, "unknown", "disconnected", companion_protocol=None)
    gate.set()
    await page.wait_for_load_state("networkidle")
    await expect(page.locator("#firmwareCliReadButton")).to_be_disabled()
    await expect(page.locator("#firmwareCliOutput")).not_to_contain_text("OLD RADIO RESULT")


@pytest.mark.parametrize("status", [422, 503])
async def test_firmware_read_errors_preserve_text_and_require_refresh_after_unavailability(browser_page: Page, status: int) -> None:
    page = browser_page
    await settings(page)
    await capability(page)
    await page.evaluate("""status => {
      const original = window.fetch;
      window.fetch = (url, options) => new URL(String(url), location.href).pathname === '/api/admin'
        ? Promise.resolve(new Response(JSON.stringify({status, detail:'Device error <b>literal</b>'}), {status,headers:{'Content-Type':'application/json'}}))
        : original(url, options);
    }""", status)
    await page.locator("#firmwareCliReadButton").click()
    await expect(page.locator("#firmwareCliOutput")).to_have_text("Device error <b>literal</b>")
    assert await page.locator("#firmwareCliOutput b").count() == 0
    if status == 503:
        await expect(page.locator("#firmwareCompatibilityPanel")).to_have_attribute("data-state", "unknown")
        await expect(page.locator("#firmwareCliReadButton")).to_be_disabled()
    else:
        await expect(page.locator("#firmwareCliReadButton")).to_be_enabled()


@pytest.mark.parametrize("change", ["meshcore:station_changed", "meshcore:credentials_changed", "disconnected", "identity_update"])
async def test_old_config_response_cannot_restore_firmware_capability_after_session_change(
    browser_page: Page, change: str,
) -> None:
    page = browser_page
    await settings(page)
    # Observe the existing production instance; preserve its implementation.
    await page.evaluate("""async () => {
      const {SettingsModule} = await import('/js/modules/settings.js');
      const render = SettingsModule.prototype._renderFirmwareCliCapability;
      SettingsModule.prototype._renderFirmwareCliCapability = function(...args) {
        window.__qaObservedSettings = this;
        SettingsModule.prototype._renderFirmwareCliCapability = render;
        return render.apply(this, args);
      };
    }""")
    await capability(page)
    await expect(page.locator("#firmwareCliReadButton")).to_be_enabled()
    await page.locator('[data-subtab="local-owner-pos"]').click()
    await page.locator("#localNodeName").fill("Draft survives station invalidation")
    await settings(page)
    dispatched = asyncio.Event()
    gate = asyncio.Event()

    async def delayed_config(route: Route) -> None:
        response = await route.fetch()
        body = await response.json()
        snapshot = await page.evaluate("window.__qaFirmwareCliSnapshot")
        snapshot["model"] = "OLD CONFIG SNAPSHOT"
        body["data"]["capabilities"]["firmware_cli"] = snapshot
        body["data"]["serial_connected"] = True
        body["data"]["radio_connected"] = True
        dispatched.set()
        await gate.wait()
        await route.fulfill(response=response, json=body)

    await page.route(re.compile(r"/api/config(?:/refresh)?(?:\?.*)?$"), delayed_config)
    try:
        await page.evaluate("void window.__qaObservedSettings.fetchLocalNodeConfig(true)")
        await asyncio.wait_for(dispatched.wait(), timeout=5)
        await page.evaluate("""async change => {
          const {eventBus, EVENTS} = await import('/js/core/eventbus.js');
          if (change === 'disconnected') {
            eventBus.emit(EVENTS.METRICS_UPDATE, {serial_connected:false,radio_connected:false});
          } else if (change === 'identity_update') {
            eventBus.emit(EVENTS.RX_PACKET, {type:'self_info',data:{public_key:'cd'.repeat(32)}});
          } else {
            window.dispatchEvent(new CustomEvent(change));
          }
        }""", change)
        await expect(page.locator("#firmwareCliReadButton")).to_be_disabled()
        gate.set()
        await page.wait_for_load_state("networkidle")
        await expect(page.locator("#firmwareCliReadButton")).to_be_disabled()
        await expect(page.locator("#firmwareCompatibilityPanel")).to_have_attribute("data-state", "unknown")
        await expect(page.locator("#firmwareCliModel")).not_to_have_text("OLD CONFIG SNAPSHOT")
        await expect(page.locator("#localNodeName")).to_have_value("Draft survives station invalidation")
        if change == "identity_update":
            assert await page.evaluate("window.__qaObservedSettings.cachedConfig.public_key") == "cd" * 32
    finally:
        gate.set()


async def test_repeated_offline_metrics_allow_fresh_config_without_enabling_cli(browser_page: Page) -> None:
    page = browser_page
    await settings(page)
    await page.evaluate("""async () => {
      const {SettingsModule} = await import('/js/modules/settings.js');
      const render = SettingsModule.prototype._renderFirmwareCliCapability;
      SettingsModule.prototype._renderFirmwareCliCapability = function(...args) {
        window.__qaObservedSettings = this;
        SettingsModule.prototype._renderFirmwareCliCapability = render;
        return render.apply(this, args);
      };
    }""")
    await capability(page, "unknown", "disconnected", companion_protocol=None)
    dispatched = asyncio.Event()
    gate = asyncio.Event()

    async def delayed_config(route: Route) -> None:
        response = await route.fetch()
        body = await response.json()
        body["data"]["serial_connected"] = False
        body["data"]["radio_connected"] = False
        body["data"]["capabilities"]["firmware_cli"] = {
            "state": "unknown", "reason": "disconnected", "safe_commands": [],
            "model": "Fresh offline configuration",
        }
        dispatched.set()
        await gate.wait()
        await route.fulfill(response=response, json=body)

    await page.route(re.compile(r"/api/config(?:/refresh)?(?:\?.*)?$"), delayed_config)
    try:
        await page.evaluate("void (window.__qaOfflineRead = window.__qaObservedSettings.fetchLocalNodeConfig(true))")
        await asyncio.wait_for(dispatched.wait(), timeout=5)
        await page.evaluate("""async () => {
          const {eventBus, EVENTS} = await import('/js/core/eventbus.js');
          eventBus.emit(EVENTS.METRICS_UPDATE, {serial_connected:false,radio_connected:false});
        }""")
        gate.set()
        await page.evaluate("window.__qaOfflineRead")
        assert await page.locator("#firmwareCliModel").inner_text() == "Fresh offline configuration"
        await expect(page.locator("#firmwareCompatibilityPanel")).to_have_attribute("data-state", "unknown")
        await expect(page.locator("#firmwareCliReadButton")).to_be_disabled()
    finally:
        gate.set()
