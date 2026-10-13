"""Real isolated ASGI/Chromium regressions for login sizing and credential forms."""

from __future__ import annotations

import json
from contextlib import AsyncExitStack
from pathlib import Path

import pytest
from playwright.async_api import Page, async_playwright, expect

from src.bridge_core import MeshCoreBridge

ARTIFACTS = Path(__file__).parent / "artifacts" / "login-audit"
VIEWPORTS = [(1920, 1080), (1366, 768), (1024, 768), (768, 1024), (390, 844),
             (360, 640), (320, 568), (844, 390), (667, 375), (640, 360)]


async def _measure(page: Page) -> dict:
    await page.mouse.move(0, 0)
    await page.wait_for_function("getComputedStyle(document.querySelector('.auth-submit')).backgroundColor === 'rgb(36, 87, 214)'")
    return await page.evaluate("""() => {
      const gate = document.getElementById('authGate'), card = gate.querySelector('.auth-card');
      const rect = card.getBoundingClientRect();
      const style = getComputedStyle(card), body = getComputedStyle(document.body);
      const main = gate.querySelector('.auth-submit'), primary = getComputedStyle(main);
      return {width: innerWidth, height: innerHeight, scrollWidth: gate.scrollWidth,
        scrollHeight: gate.scrollHeight, clientWidth: gate.clientWidth, clientHeight: gate.clientHeight,
        card: {x:rect.x,y:rect.y,right:rect.right,bottom:rect.bottom},
        font:body.fontFamily, foreground:style.color, surface:style.backgroundColor,
        primary:primary.backgroundColor, primaryText:primary.color, primaryImage:primary.backgroundImage,
        clipped: [...gate.querySelectorAll('input,button,summary,.field-error,.form-feedback-summary')]
          .filter(e=>e.getClientRects().length && !e.hidden)
          .filter(e=> {const r=e.getBoundingClientRect(); return r.x<0 || r.y<0 || r.right>innerWidth+1 || r.bottom>innerHeight+1;})
          .map(e=>e.id||e.className)};
    }""")


@pytest.mark.asyncio
async def test_login_fits_viewports_themes_languages_and_feedback(virtual_bridge: MeshCoreBridge) -> None:
    """Expanded help/errors must fit without hiding controls in normal portrait/landscape."""
    server = virtual_bridge.web_server
    assert server is not None
    origin = f"http://127.0.0.1:{server.port}"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    measurements, failures, browser_errors, http_errors = [], [], [], []
    async with async_playwright() as driver, AsyncExitStack() as cleanup:
        browser = await driver.chromium.launch(headless=True)
        cleanup.push_async_callback(browser.close)
        for theme in ("dark", "light"):
            for language in ("es", "en"):
                context = await browser.new_context()
                cleanup.push_async_callback(context.close)
                await context.add_init_script(f"localStorage.setItem('meshcore_theme','{theme}'); localStorage.setItem('mc_lang','{language}');")
                page = await context.new_page()
                page.on("pageerror", lambda error: browser_errors.append(str(error)))
                page.on("requestfailed", lambda request: browser_errors.append(f"{request.failure} {request.url}"))
                page.on("response", lambda response: http_errors.append(f"{response.status} {response.url}") if response.status >= 400 and not (response.status == 401 and response.url.endswith('/api/auth/session')) else None)
                await page.goto(origin)
                await page.locator("#loginForm").wait_for(state="visible")
                for width, height in VIEWPORTS:
                    await page.set_viewport_size({"width": width, "height": height})
                    await page.evaluate("document.querySelector('.auth-first-login').open=false")
                    await page.locator("#loginUsername").fill("")
                    await page.locator("#loginPassword").fill("")
                    # Submitting exercises the real field-linked validation errors.
                    await page.locator("#loginForm button[type=submit]").click()
                    for expanded in (False, True):
                        await page.evaluate("value=>document.querySelector('.auth-first-login').open=value", expanded)
                        result = await _measure(page)
                        result.update(theme=theme, language=language, expanded=expanded)
                        measurements.append(result)
                        if result['scrollWidth'] > result['clientWidth'] + 1 or result['scrollHeight'] > result['clientHeight'] + 1 or result['clipped']:
                            failures.append(result)
                    await page.screenshot(path=str(ARTIFACTS / f"{theme}-{language}-{width}x{height}.png"))
                await context.close()
    (ARTIFACTS / "layout.json").write_text(json.dumps(measurements, indent=2), encoding="utf-8")
    assert not browser_errors, browser_errors
    assert not http_errors, http_errors
    assert not failures, json.dumps(failures, indent=2)
    for result in measurements:
        assert "system-ui" in result['font']
        assert result['surface'] == ("rgb(20, 34, 56)" if result['theme'] == 'dark' else "rgb(255, 255, 255)")
        assert result['foreground'] == ("rgb(231, 237, 247)" if result['theme'] == 'dark' else "rgb(30, 41, 59)")
        assert result['primary'] == "rgb(36, 87, 214)"
        assert result['primaryImage'] == "none"


@pytest.mark.asyncio
async def test_login_default_profile_validation_unicode_and_logout(virtual_bridge: MeshCoreBridge) -> None:
    """Eight simple characters and 64 Unicode characters are valid; 7/65 reject."""
    server = virtual_bridge.web_server
    assert server is not None
    origin = f"http://127.0.0.1:{server.port}"
    async with async_playwright() as driver, AsyncExitStack() as cleanup:
        browser = await driver.chromium.launch(headless=True)
        cleanup.push_async_callback(browser.close)
        page = await browser.new_page(viewport={"width": 390, "height": 844})
        await page.goto(origin)
        await page.locator("#loginUsername").fill("admin")
        await page.locator("#loginPassword").fill("admin")
        await page.locator("#loginPasswordToggle").click()
        assert await page.locator("#loginPassword").get_attribute("type") == "text"
        await page.locator("#loginForm button[type=submit]").click()
        await page.locator("#accountDialog").wait_for(state="visible")
        assert await page.locator("#accountRequiredNotice").is_visible()
        assert not await page.locator("#accountCloseButton").is_visible()
        assert not await page.locator("#accountCurrentPasswordGroup").is_visible()
        for password in ("a" * 7, "😀" * 65):
            await page.locator("#accountNewPassword").fill(password)
            await page.locator("#accountConfirmPassword").fill(password)
            await page.locator("#accountCredentialsForm button[type=submit]").click()
            await expect(page.locator("#accountNewPassword")).to_have_attribute("aria-invalid", "true")
        await page.locator("#accountNewPassword").fill("a" * 8)
        await page.locator("#accountConfirmPassword").fill("a" * 8)
        await page.locator("#accountCredentialsForm button[type=submit]").click()
        await page.locator("#authGate").wait_for(state="hidden")
        await page.locator("[data-open-account]").first.click()
        await page.locator("#accountCurrentPassword").fill("a" * 8)
        await page.locator("#accountNewPassword").fill("😀" * 64)
        await page.locator("#accountConfirmPassword").fill("😀" * 64)
        await page.locator("#accountCredentialsForm button[type=submit]").click()
        await page.locator("#accountDialog").wait_for(state="hidden")
        await page.locator("[data-open-account]").first.click()
        await page.locator("#accountLogoutButton").click()
        await page.locator("#loginForm").wait_for(state="visible")
        await page.locator("#loginUsername").fill("admin")
        await page.locator("#loginPassword").fill("😀" * 64)
        await page.locator("#loginForm button[type=submit]").click()
        await page.locator("#authGate").wait_for(state="hidden")
