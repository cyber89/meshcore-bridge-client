"""Real browser contracts against a fresh virtual bridge, never a running radio."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect


async def send_message(page: Page, text: str) -> None:
    await page.locator("#chatInputText").fill(text)
    await page.locator("#chatInputForm").dispatch_event("submit")
    await expect(page.locator("#chatMessageFeed")).to_contain_text(text)


async def test_e2e_page_loads_and_has_title(browser_page: Page) -> None:
    await expect(browser_page).to_have_title("MeshCore Web Client - Base Station & RF Command Center")
    await expect(browser_page.locator("header.app-header")).to_be_visible()
    await expect(browser_page.locator("#chatInputText")).to_be_visible()


@pytest.mark.parametrize("tab", ["chat", "contacts", "nodes", "map", "analytics", "logs", "settings"])
async def test_e2e_navigation_all_tabs(browser_page: Page, tab: str) -> None:
    button = browser_page.locator(f'.nav-btn[data-tab="tab-{tab}"]')
    await button.click()
    await expect(browser_page.locator(f"#tab-{tab}")).to_be_visible()
    await expect(button).to_have_attribute("aria-selected", "true")


async def test_e2e_channel_switching_and_isolated_feed(browser_page: Page) -> None:
    channel_one = browser_page.locator('#channelListUi [data-channel-idx="1"]')
    await channel_one.click()
    await send_message(browser_page, "Solo canal privado E2E")
    await browser_page.locator('#channelListUi [data-channel-idx="0"]').click()
    await expect(browser_page.locator("#chatMessageFeed")).not_to_contain_text("Solo canal privado E2E")
    await channel_one.click()
    await expect(browser_page.locator("#chatMessageFeed")).to_contain_text("Solo canal privado E2E")


async def test_e2e_dm_multi_recipient_isolation(browser_page: Page) -> None:
    async def open_contact(name: str) -> None:
        await browser_page.locator('[data-tab="tab-contacts"]').click()
        await browser_page.locator('#contactsGridUi .contact-card').filter(has_text=name).locator('.btn-contact-dm').click()

    await open_contact("Bravo")
    await send_message(browser_page, "Privado Bravo E2E")
    await open_contact("Delta")
    await expect(browser_page.locator("#chatMessageFeed")).not_to_contain_text("Privado Bravo E2E")
    await open_contact("Bravo")
    await expect(browser_page.locator("#chatMessageFeed")).to_contain_text("Privado Bravo E2E")


async def test_e2e_protected_nodes_cannot_open_dm(browser_page: Page) -> None:
    await browser_page.locator('[data-tab="tab-nodes"]').click()
    repeater = browser_page.locator('#nodesUnifiedGridUi .node-card[data-role="REPEATER"]').first
    await expect(repeater).to_be_visible()
    assert await repeater.locator('.btn-dm-node').count() == 0


async def test_e2e_contacts_exclude_repeater_and_local(browser_page: Page) -> None:
    await browser_page.locator('[data-tab="tab-contacts"]').click()
    contacts = browser_page.locator("#contactsGridUi")
    await expect(contacts).to_contain_text("Bravo")
    await expect(contacts).not_to_contain_text("Echo Gateway Repeater")
    await expect(contacts).not_to_contain_text("MeshCore_Base_Station")


async def test_e2e_chat_escapes_markup(browser_page: Page) -> None:
    message = '<img src=x onerror="window.xssExecuted=true">'
    await send_message(browser_page, message)
    assert await browser_page.evaluate("window.xssExecuted === undefined")
    assert await browser_page.locator("#chatMessageFeed img[src=x]").count() == 0


async def test_e2e_command_palette_keyboard(browser_page: Page) -> None:
    await browser_page.keyboard.press("Control+k")
    await expect(browser_page.locator("#commandPaletteModal")).to_be_visible()
    await browser_page.keyboard.press("Escape")
    await expect(browser_page.locator("#commandPaletteModal")).not_to_be_visible()
