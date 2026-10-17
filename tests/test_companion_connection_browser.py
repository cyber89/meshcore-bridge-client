"""Companion transport preferences in the isolated SPA (execution on request)."""

from __future__ import annotations

from typing import Any

import pytest
from playwright.async_api import Page, Route, expect


async def connection_settings(page: Page, posts: list[dict[str, Any]], *, failure: bool = False) -> None:
    configured = ""

    async def services(route: Route) -> None:
        nonlocal configured
        if route.request.method == "POST":
            posts.append({"body": route.request.post_data_json, "csrf": bool(route.request.headers.get("x-csrf-token"))})
            configured = route.request.post_data_json.get("companion_port", configured)
        await route.fulfill(json={"status": "ok", "data": {
            "companion_port": configured,
            "companion_connection": {
                "configured_port": configured, "effective_port": configured or "AUTO",
                "active_port": "COM7", "restart_required": bool(configured),
            },
        }})

    await page.route("**/api/services/config", services)
    await page.reload()
    if failure:
        await page.evaluate("""() => {
            const orig = window.fetch;
            window.fetch = async (url, opts = {}) => {
                if (String(url).includes('/api/services/config') && opts.method === 'POST') {
                    const body = opts.body ? JSON.parse(opts.body) : {};
                    window.__qaFailurePosts = window.__qaFailurePosts || [];
                    window.__qaFailurePosts.push({body, csrf: Boolean(opts.headers && (opts.headers['X-CSRF-Token'] || opts.headers['x-csrf-token']))});
                    return new Response(JSON.stringify({detail: "Rejected <b>literal</b>"}), {
                        status: 422,
                        headers: {'Content-Type': 'application/json'}
                    });
                }
                return orig(url, opts);
            };
        }""")
    menu = page.locator('[data-bs-toggle="offcanvas"][data-bs-target="#appSidebar"]')
    if await menu.is_visible():
        await menu.click()
    await page.locator('[data-tab="tab-settings"]').click()
    await page.locator('[data-subtab="local-services"]').click()
    await expect(page.locator("#companionConnectionSave")).to_be_enabled()


async def test_services_refresh_preserves_unsaved_connection(browser_page: Page) -> None:
    page = browser_page
    posts: list[dict[str, Any]] = []
    await connection_settings(page, posts)
    await page.locator("#companionConnectionMode").select_option("tcp")
    await page.locator("#companionConnectionHost").fill("unsaved.example")
    await page.locator("#companionConnectionPort").fill("4321")
    await page.locator("#btnSaveServicesConfig").click()
    await expect(page.locator("#btnSaveServicesConfig")).to_be_enabled()
    await expect(page.locator("#companionConnectionMode")).to_have_value("tcp")
    await expect(page.locator("#companionConnectionHost")).to_have_value("unsaved.example")
    await expect(page.locator("#companionConnectionPort")).to_have_value("4321")
    assert len(posts) == 1
    assert "companion_port" not in posts[0]["body"]


@pytest.mark.parametrize("width,height", [(1920, 1080), (390, 844)])
async def test_tcp_preference_saves_only_endpoint_without_reconnecting(browser_page: Page, width: int, height: int) -> None:
    page = browser_page
    await page.set_viewport_size({"width": width, "height": height})
    posts: list[dict[str, Any]] = []
    reconnects: list[str] = []

    async def reconnect(route: Route) -> None:
        reconnects.append(route.request.url)
        await route.fulfill(json={"status": "ok"})

    await page.route("**/api/config/reconnect", reconnect)
    await connection_settings(page, posts)
    await page.locator("#companionConnectionMode").select_option("tcp")
    await page.locator("#companionConnectionHost").fill("radio.example")
    await page.locator("#companionConnectionPort").fill("4000")
    assert posts == []
    await page.locator("#companionConnectionSave").click()
    await expect(page.locator("#companionConnectionEffective")).to_have_text("tcp://radio.example:4000")
    await expect(page.locator("#companionConnectionActive")).to_have_text("COM7")
    assert posts == [{"body": {"companion_port": "tcp://radio.example:4000"}, "csrf": True}]
    assert reconnects == []
    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")


async def test_tcp_validation_and_server_error_keep_draft(browser_page: Page) -> None:
    page = browser_page
    posts: list[dict[str, Any]] = []
    await connection_settings(page, posts, failure=True)
    await page.locator("#companionConnectionMode").select_option("tcp")
    await page.locator("#companionConnectionHost").fill("user:password@radio.example")
    await page.locator("#companionConnectionPort").fill("4000")
    await page.locator("#companionConnectionSave").click()
    assert posts == []
    await page.locator("#companionConnectionHost").fill("radio.example")
    await page.locator("#companionConnectionSave").click()
    await expect(page.locator("#companionConnectionStatus")).to_have_text("Rejected <b>literal</b>")
    assert await page.locator("#companionConnectionStatus b").count() == 0
    await expect(page.locator("#companionConnectionHost")).to_have_value("radio.example")
    await expect(page.locator("#companionConnectionSave")).to_be_enabled()
