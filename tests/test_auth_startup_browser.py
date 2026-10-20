"""No login flash while a genuine cookie session is being checked."""

import asyncio
import json
from pathlib import Path

from playwright.async_api import Page, Route, async_playwright, expect
from test_frontend_ui_audit import _apply_theme

from src.bridge_core import MeshCoreBridge
from src.web.asgi_server import AsgiWebServer


async def test_valid_session_waits_without_showing_login(browser_page: Page) -> None:
    await expect(browser_page.locator("#tab-analytics")).to_have_attribute("aria-busy", "false")
    await browser_page.wait_for_load_state("networkidle")
    requested, release, handled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    requests = 0

    async def slow_session(route: Route) -> None:
        nonlocal requests
        requests += 1
        requested.set()
        await release.wait()
        await route.continue_()
        handled.set()

    await browser_page.add_init_script("""(() => {
        window.__loginFlashed = false;
        new MutationObserver(() => {
            const gate = document.getElementById('authGate');
            if (gate && !gate.hidden && getComputedStyle(gate).display !== 'none') window.__loginFlashed = true;
        }).observe(document, {subtree:true,childList:true,attributes:true,attributeFilter:['hidden','class']});
    })();""")
    await browser_page.route("**/api/auth/session", slow_session)
    try:
        await browser_page.reload(wait_until="domcontentloaded")
        await asyncio.wait_for(requested.wait(), 5)
        await expect(browser_page.locator("#authGate")).not_to_be_visible()
        await expect(browser_page.locator("#loginForm")).not_to_be_visible()
        await expect(browser_page.locator("#app")).not_to_be_visible()
        assert await browser_page.evaluate("(window.__qaWebSockets || []).length") == 0
        release.set()
        await expect(browser_page.locator("#app")).to_be_visible()
        assert not await browser_page.evaluate("window.__loginFlashed")
        assert requests == 1
    finally:
        release.set()
        if requested.is_set():
            await asyncio.wait_for(handled.wait(), 5)
            await expect(browser_page.locator("#app")).to_be_visible()
        await browser_page.unroute("**/api/auth/session", slow_session)


async def test_configured_station_login_hides_first_access_help(virtual_bridge: MeshCoreBridge) -> None:
    server = virtual_bridge.web_server
    assert isinstance(server, AsgiWebServer)
    origin = f"http://127.0.0.1:{server.port}"
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            login = await context.request.post(origin + "/api/auth/login", data={"username": "admin", "password": "admin"},
                                               headers={"Origin": origin})
            changed = await context.request.put(origin + "/api/auth/credentials",
                data={"username": "owner", "password": "qa-owner-password", "current_password": "admin"},
                headers={"Origin": origin, "X-CSRF-Token": (await login.json())["csrf_token"]})
            assert changed.status == 200
            await context.clear_cookies()
            page = await context.new_page()
            await page.goto(origin)
            await expect(page.locator("#loginForm")).to_be_visible()
            await expect(page.locator(".auth-first-login")).not_to_be_visible()
        finally:
            await browser.close()


async def test_session_check_starts_before_full_app_dependencies(virtual_bridge: MeshCoreBridge) -> None:
    server = virtual_bridge.web_server
    assert isinstance(server, AsgiWebServer)
    origin = f"http://127.0.0.1:{server.port}"
    dependency, release, handled, session = (asyncio.Event() for _ in range(4))
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            async def block_dependency(route: Route) -> None:
                dependency.set()
                await release.wait()
                await route.continue_()
                handled.set()

            await page.route("**/js/modules/nodes.js", block_dependency)
            page.on("request", lambda request: session.set() if request.url.endswith("/api/auth/session") else None)
            await page.goto(origin, wait_until="commit")
            await asyncio.wait_for(dependency.wait(), 5)
            await asyncio.wait_for(session.wait(), 3)
        finally:
            release.set()
            if dependency.is_set():
                await asyncio.wait_for(handled.wait(), 5)
            await browser.close()


async def test_first_access_help_disappears_after_setup_and_logout(virtual_bridge: MeshCoreBridge) -> None:
    server = virtual_bridge.web_server
    assert isinstance(server, AsgiWebServer)
    origin = f"http://127.0.0.1:{server.port}"
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(origin)
            await expect(page.locator(".auth-first-login")).not_to_be_visible()
            await page.locator("#loginUsername").fill("admin")
            await page.locator("#loginPassword").fill("admin")
            await page.locator('#loginForm button[type="submit"]').click()
            await expect(page.locator("#accountRequiredNotice")).to_be_visible()
            await page.locator("#accountCurrentPassword").fill("admin")
            await expect(page.locator("#app")).not_to_be_visible()
            await page.locator("#accountNewPassword").fill("qa-owner-password")
            await page.locator("#accountConfirmPassword").fill("qa-owner-password")
            await page.locator('#accountCredentialsForm button[type="submit"]').click()
            await expect(page.locator("#app")).to_be_visible()
            assert await page.locator(".auth-first-login").evaluate("el => el.hidden")
            await page.locator("[data-open-account]").first.click()
            await page.locator("#accountLogoutButton").click()
            await expect(page.locator("#loginForm")).to_be_visible()
            await expect(page.locator(".auth-first-login")).not_to_be_visible()
        finally:
            await browser.close()


async def test_failed_check_shows_login_without_first_access_claim(virtual_bridge: MeshCoreBridge) -> None:
    server = virtual_bridge.web_server
    assert isinstance(server, AsgiWebServer)
    origin = f"http://127.0.0.1:{server.port}"
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.route("**/api/auth/session", lambda route: route.abort("failed"))
            await page.goto(origin)
            await expect(page.locator("#loginForm")).to_be_visible()
            await expect(page.locator("#loginForm .form-feedback-summary")).to_be_visible()
            await expect(page.locator(".auth-first-login")).not_to_be_visible()
            await expect(page.locator("#app")).not_to_be_visible()
            assert not errors
        finally:
            await browser.close()


async def test_late_startup_script_reuses_module_fallback_check(virtual_bridge: MeshCoreBridge) -> None:
    server = virtual_bridge.web_server
    assert isinstance(server, AsgiWebServer)
    origin = f"http://127.0.0.1:{server.port}"
    requested, release, handled = (asyncio.Event() for _ in range(3))
    checks = []
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            async def slow_script(route: Route) -> None:
                requested.set()
                await release.wait()
                await route.continue_()
                handled.set()

            await page.route("**/js/session_startup.js", slow_script)
            page.on("request", lambda request: checks.append(request.url) if request.url.endswith("/api/auth/session") else None)
            await page.goto(origin, wait_until="domcontentloaded")
            await expect(page.locator("#loginForm")).to_be_visible()
            assert requested.is_set() and len(checks) == 1
            release.set()
            await asyncio.wait_for(handled.wait(), 5)
            await page.wait_for_load_state("load")
            assert len(checks) == 1
        finally:
            release.set()
            if requested.is_set():
                await asyncio.wait_for(handled.wait(), 5)
            await browser.close()


async def test_login_reflows_with_conditional_setup_help(virtual_bridge: MeshCoreBridge) -> None:
    server = virtual_bridge.web_server
    assert isinstance(server, AsgiWebServer)
    origin = f"http://127.0.0.1:{server.port}"
    results = []
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(origin)
            await expect(page.locator(".auth-first-login")).to_be_visible()
            for theme in ("dark", "light"):
                await _apply_theme(page, theme)
                for language in ("es", "en"):
                    await page.evaluate("lang => {if(I18n.lang !== lang) I18n.toggle();}", language)
                    for width, height in ((320, 568), (390, 844), (844, 390), (1920, 1080)):
                        await page.set_viewport_size({"width": width, "height": height})
                        for expanded in (False, True):
                            await page.locator(".auth-first-login").evaluate("(el, value) => el.open=value", expanded)
                            geometry = await page.locator("#authGate").evaluate("""el => ({
                                width:innerWidth, scrollWidth:el.scrollWidth, clientWidth:el.clientWidth,
                                horizontalClip:[...el.querySelectorAll('input,button,summary')]
                                    .filter(node => node.checkVisibility()).some(node => {
                                        const r=node.getBoundingClientRect();return r.x<0 || r.right>innerWidth+1;
                                    })})""")
                            results.append({"theme": theme, "language": language, "height": height,
                                            "expanded": expanded, **geometry})
                            assert geometry["scrollWidth"] <= geometry["clientWidth"] + 1
                            assert not geometry["horizontalClip"]
                        submit = page.locator('#loginForm button[type="submit"]')
                        await submit.scroll_into_view_if_needed()
                        await expect(submit).to_be_in_viewport()
            output = Path("tests/artifacts/auth-startup/login-reflow.json")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        finally:
            await browser.close()
