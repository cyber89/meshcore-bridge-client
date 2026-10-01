"""End-to-end delivery and responsive SPA evidence with no hardware or CDN traffic."""

import re
from pathlib import Path

import pytest
from playwright.async_api import Page, expect


async def test_playwright_delivery_ack_and_echo(browser_page: Page) -> None:
    await browser_page.locator('[data-tab="tab-contacts"]').click()
    await browser_page.locator('#contactsGridUi .contact-card').filter(has_text="Bravo").locator('.btn-contact-dm').click()
    message = "Entrega y eco virtual E2E"
    await browser_page.locator("#chatInputText").fill(message)
    await browser_page.locator("#chatInputForm").dispatch_event("submit")
    bubble = browser_page.locator(".message-bubble-row.outgoing").filter(has_text=message)
    await expect(bubble.locator(".ack-delivered")).to_have_text("✓✓", timeout=10000)
    await expect(browser_page.locator(".message-bubble-row.incoming").last).to_contain_text(message)


@pytest.mark.parametrize("width,height", [(1920, 1080), (390, 844)])
async def test_playwright_responsive_layout(browser_page: Page, width: int, height: int) -> None:
    await browser_page.set_viewport_size({"width": width, "height": height})
    await expect(browser_page.locator("header.app-header")).to_be_visible()
    if width < 900:
        await browser_page.locator("#btnBackToChannelsMobile").click()
        await browser_page.locator('#channelListUi [data-channel-idx="1"]').click()
        await expect(browser_page.locator("#sidebarChannelList")).not_to_have_class(re.compile(r".*\bmobile-open\b.*"))
        await expect(browser_page.locator("#chatInputText")).to_be_visible()
    overflow = await browser_page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not overflow, f"Horizontal overflow at {width}x{height}"
    send_box = await browser_page.locator("#btnSendMsg").bounding_box()
    assert send_box is not None
    assert send_box["x"] >= 0 and send_box["x"] + send_box["width"] <= width, f"Send control clipped at {width}x{height}: {send_box}"
    artifacts = Path("tests/artifacts")
    artifacts.mkdir(exist_ok=True)
    await browser_page.screenshot(path=str(artifacts / f"qa_spa_{width}x{height}.png"), full_page=True, animations="disabled")
