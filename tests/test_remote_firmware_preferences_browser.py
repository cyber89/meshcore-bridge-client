"""Remote preference controls use isolated responses and one request per click."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest
from playwright.async_api import Page, Route, expect


async def open_remote_preferences(page: Page, requests: list[dict[str, Any]], *, dispatched: bool = False) -> None:
    async def remote(route: Route) -> None:
        body = route.request.post_data_json
        action = body.get("action")
        target = body.get("target_node", "")
        data: dict[str, Any] = {"status": "ok", "target_node": target, "telemetry": {"tx_power": 17}}
        if route.request.url.endswith("/login"):
            data = {"authenticated": True}
        elif action in {"get_cad", "get_rx_gain", "set_cad"}:
            requests.append({"body": body, "csrf": bool(route.request.headers.get("x-csrf-token"))})
            data = {"status": "ok", "target_node": target, "hardware_verified": False}
            if dispatched and action == "set_cad":
                data["status"] = "dispatched"
            elif action == "set_cad":
                data.update({"saved_preferences": {"cad": body["params"]["enabled"]}, "acknowledged": True})
            else:
                data.update({"preferences": {"cad" if action == "get_cad" else "rx_gain": False}, "preferences_source": "saved_preferences"})
        await route.fulfill(json={"status": "ok", "data": data})

    await page.route("**/api/repeater/remote/**", remote)
    sidebar = page.locator("#appSidebar")
    nav = page.locator('[data-tab="tab-nodes"]')
    if not await nav.is_visible():
        await page.locator('[data-bs-toggle="offcanvas"][data-bs-target="#appSidebar"]').click()
    await nav.click()
    if page.viewport_size is not None and page.viewport_size["width"] < 992:
        await expect(sidebar).not_to_be_visible()
    await page.locator(".btn-manage-repeater").first.click()
    await page.locator("#repeaterGatePassword").fill("virtualpass")
    await page.locator("#btnRepeaterGateSubmit").click()
    await expect(page.locator("#repeaterAdminModalCard")).to_have_class(re.compile(r".*\bunlocked\b.*"))
    await page.locator('#repeaterAdminModal [data-subtab="rep-radio"]').click()
    await expect(page.locator("#remoteCadRead")).to_be_enabled()


@pytest.mark.parametrize("width,height", [(1920, 1080), (390, 844)])
async def test_remote_cad_read_save_and_explicit_readback(browser_page: Page, width: int, height: int) -> None:
    page = browser_page
    await page.set_viewport_size({"width": width, "height": height})
    requests: list[dict[str, Any]] = []
    await open_remote_preferences(page, requests)
    assert requests == []
    await expect(page.locator("#remoteCadSave")).to_be_disabled()
    await page.locator("#remoteCadRead").click()
    await expect(page.locator("#remoteCadSave")).to_be_enabled()
    await page.locator("#remoteCadValue").select_option("on")
    await page.locator("#remoteCadSave").click()
    await expect(page.locator("#remoteCadSave")).to_be_disabled()
    await expect(page.locator("#remotePreferencesStatus")).to_contain_text("CAD")
    assert [request["body"]["action"] for request in requests] == ["get_cad", "set_cad"]
    assert requests[-1]["body"]["params"] == {"enabled": True}
    assert all(request["csrf"] for request in requests)
    await page.locator("#remoteRxGainRead").click()
    await expect(page.locator("#remoteRxGainObserved")).not_to_have_text("—")
    assert len(requests) == 3
    assert await page.locator("#remoteRxGainSave").count() == 0
    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")


async def test_dispatched_cad_is_unconfirmed_and_does_not_retry(browser_page: Page) -> None:
    page = browser_page
    requests: list[dict[str, Any]] = []
    await open_remote_preferences(page, requests, dispatched=True)
    await page.locator("#remoteCadRead").click()
    await expect(page.locator("#remoteCadSave")).to_be_enabled()
    await page.locator("#remoteCadSave").click()
    await expect(page.locator("#remotePreferencesStatus")).to_contain_text("CAD")
    await expect(page.locator("#remoteCadSave")).to_be_disabled()
    assert len(requests) == 2
    await page.locator("#btnCloseRepeaterAdminModal").click()
    await expect(page.locator("#remoteCadValue")).to_have_value("")


async def test_late_cad_reply_does_not_reenable_closed_modal(browser_page: Page) -> None:
    page = browser_page
    requests: list[dict[str, Any]] = []
    await open_remote_preferences(page, requests)
    gate = asyncio.Event()
    sent = asyncio.Event()

    async def delayed(route: Route) -> None:
        body = route.request.post_data_json
        sent.set()
        await gate.wait()
        await route.fulfill(json={"status": "ok", "data": {
            "status": "ok", "target_node": body["target_node"], "preferences": {"cad": True},
            "preferences_source": "saved_preferences", "hardware_verified": False,
        }})

    await page.route("**/api/repeater/remote/action", delayed)
    await page.locator("#remoteCadRead").click()
    await asyncio.wait_for(sent.wait(), timeout=5)
    await page.locator("#btnCloseRepeaterAdminModal").click()
    gate.set()
    await page.wait_for_load_state("networkidle")
    await expect(page.locator("#remoteCadSave")).to_be_disabled()
    await expect(page.locator("#remoteCadValue")).to_have_value("")
