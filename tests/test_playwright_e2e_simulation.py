"""End-to-end delivery and responsive SPA evidence with no hardware or CDN traffic."""

import json
import re
from pathlib import Path

import pytest
from playwright.async_api import Page, expect


async def _wait_for_mobile_sidebar_closed(page: Page) -> None:
    # Removing the class starts a CSS transition; it does not finish closing it.
    await expect(page.locator("#sidebarChannelList")).not_to_have_class(re.compile(r".*\bmobile-open\b.*"))
    await page.wait_for_function("""() => {
        const sidebar = document.querySelector('#sidebarChannelList');
        return sidebar && sidebar.getBoundingClientRect().right <= 0 &&
            sidebar.getAnimations().every(animation => animation.playState !== 'running');
    }""")


async def test_mobile_sidebar_waits_for_visible_transition(browser_page: Page) -> None:
    await browser_page.set_viewport_size({"width": 390, "height": 844})
    sidebar = browser_page.locator("#sidebarChannelList")
    await sidebar.evaluate("element => element.style.transitionDuration = '1s'")
    await browser_page.locator("#btnBackToChannelsMobile").click()
    await browser_page.wait_for_function("""() => {
        const sidebar = document.querySelector('#sidebarChannelList');
        return sidebar.classList.contains('mobile-open') &&
            sidebar.getAnimations().every(animation => animation.playState !== 'running');
    }""")
    await browser_page.locator('#channelListUi [data-channel-idx="1"]').click()
    await expect(sidebar).not_to_have_class(re.compile(r".*\bmobile-open\b.*"))
    assert await sidebar.evaluate("element => element.getBoundingClientRect().right > 0"), "Class removal must precede the visible closing transition"
    await _wait_for_mobile_sidebar_closed(browser_page)
    assert await sidebar.evaluate("element => element.getBoundingClientRect().right <= 0")


async def test_playwright_delivery_ack_and_echo(browser_page: Page) -> None:
    await browser_page.locator('[data-tab="tab-contacts"]').click()
    await browser_page.locator('#contactsGridUi .contact-card').filter(has_text="Bravo").locator('.btn-contact-dm').click()
    message = "Entrega y eco virtual E2E"
    await browser_page.locator("#chatInputText").fill(message)
    await browser_page.locator("#chatInputForm").dispatch_event("submit")
    bubble = browser_page.locator(".message-bubble-row.outgoing").filter(has_text=message)
    await expect(bubble.locator(".ack-delivered")).to_have_text("✓✓", timeout=10000)
    await expect(browser_page.locator(".message-bubble-row.incoming").last).to_contain_text(message)


async def test_mobile_header_with_wider_fallback_font(browser_page: Page) -> None:
    """Platform font metrics must not push theme/language controls off screen."""
    await browser_page.set_viewport_size({"width": 390, "height": 844})
    await browser_page.locator("header.app-header").evaluate("""element => {
        element.style.fontFamily = 'monospace';
        element.style.letterSpacing = '1px';
    }""")
    await browser_page.evaluate("document.fonts.ready")
    # Serial ports may be persistent /dev/serial/by-id paths, not only ttyUSB0.
    await browser_page.locator("#radio-status .status-text").evaluate("""element => {
        element.textContent = window.I18n.t('app.radio_online').replace(
            '{port}', '/dev/serial/by-id/usb-MeshCore_Companion_123456789');
    }""")
    geometry = await browser_page.evaluate("""() => ({
        viewport: innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        header: document.querySelector('header.app-header').getBoundingClientRect().toJSON(),
        actions: ['themeToggleBtn', 'langToggleBtn'].map(id => ({
            id, ...document.getElementById(id).getBoundingClientRect().toJSON()
        }))
    })""")
    assert geometry["scrollWidth"] <= geometry["viewport"], json.dumps(geometry)
    for action in geometry["actions"]:
        assert 0 <= action["left"] < action["right"] <= geometry["viewport"], json.dumps(geometry)
        await expect(browser_page.locator(f"#{action['id']}")).to_be_visible()
    # The controls remain usable rather than merely hidden to satisfy the bounds.
    await browser_page.locator("#themeToggleBtn").click()
    await expect(browser_page.locator("body")).to_have_class(re.compile(r".*\blight-theme\b.*"))
    await browser_page.locator("#langToggleBtn").click(trial=True)


@pytest.mark.parametrize("width,height", [(1920, 1080), (390, 844)])
async def test_playwright_responsive_layout(browser_page: Page, width: int, height: int) -> None:
    await browser_page.set_viewport_size({"width": width, "height": height})
    await expect(browser_page.locator("header.app-header")).to_be_visible()
    if width < 900:
        await browser_page.locator("#btnBackToChannelsMobile").click()
        await browser_page.locator('#channelListUi [data-channel-idx="1"]').click()
        await _wait_for_mobile_sidebar_closed(browser_page)
        await expect(browser_page.locator("#chatInputText")).to_be_visible()
    await browser_page.evaluate("document.fonts.ready")
    geometry = await browser_page.evaluate("""() => ({
        viewport: innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        sidebar: document.querySelector('#sidebarChannelList').getBoundingClientRect().toJSON(),
        header: document.querySelector('header.app-header').getBoundingClientRect().toJSON(),
        send: document.querySelector('#btnSendMsg').getBoundingClientRect().toJSON(),
        outside: [...document.querySelectorAll('body *')].map(element => {
            const rect = element.getBoundingClientRect();
            return {tag: element.tagName, id: element.id, className: String(element.className),
                x: rect.x, right: rect.right, width: rect.width};
        }).filter(rect => rect.width > 0 && rect.right > innerWidth)
    })""")
    artifacts = Path("tests/artifacts")
    artifacts.mkdir(exist_ok=True)
    (artifacts / f"qa_spa_{width}x{height}-geometry.json").write_text(json.dumps(geometry, indent=2), encoding="utf-8")
    assert geometry["scrollWidth"] <= geometry["viewport"], f"Horizontal overflow at {width}x{height}: {json.dumps(geometry)}"
    send_box = await browser_page.locator("#btnSendMsg").bounding_box()
    assert send_box is not None
    assert send_box["x"] >= 0 and send_box["x"] + send_box["width"] <= width, f"Send control clipped at {width}x{height}: {send_box}"
    await browser_page.screenshot(path=str(artifacts / f"qa_spa_{width}x{height}.png"), full_page=True, animations="disabled")
