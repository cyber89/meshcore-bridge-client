"""Reading position and tablet conversation navigation on a virtual station."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect


async def seed_history(page: Page) -> None:
    await expect(page.locator("#tab-analytics")).to_have_attribute("aria-busy", "false")
    await page.wait_for_load_state("networkidle")
    chat_tab = page.locator('[data-tab="tab-chat"]')
    if await chat_tab.is_visible():
        await chat_tab.click()
    await expect(page.locator("#tab-chat")).to_be_visible()
    await page.evaluate(r"""() => {
        const chat = bridgeApp.chatModule;
        chat.activeChannelIdx = 1;
        chat.activeDmTarget = null;
        chat.historyPages.delete('ch_1');
        chat._historyStates.delete('ch_1');
        chat.channelFeeds.set('ch_1', Array.from({length: 40}, (_, i) => ({
            id: 'reading-' + i, sender_name: 'Reader QA', is_outgoing: false,
            text: 'History ' + i + '\n' + 'A readable paragraph. '.repeat(8),
            timestamp: '2026-10-18T10:00:00Z', channel_idx: 1,
        })));
        chat._paintConversation('ch_1');
        const feed = document.getElementById('chatMessageFeed');
        feed.scrollTop = 120;
        feed.dispatchEvent(new Event('scroll'));
    }""")


APPEND = r"""outgoing => {
    const chat = bridgeApp.chatModule;
    const feed = document.getElementById('chatMessageFeed');
    const before = feed.scrollTop;
    const msg = {id: 'new-' + crypto.randomUUID(), is_outgoing: outgoing,
        text: 'New weather report\nTemperature: 25°C\nWind: 18.9 km/h',
        status: 'failed', channel_idx: 1, timestamp: '2026-10-18T22:00:00Z'};
    chat.channelFeeds.get('ch_1').push(msg);
    chat.appendChatMessage(msg);
    return {before, after: feed.scrollTop,
        remaining: feed.scrollHeight - feed.clientHeight - feed.scrollTop};
}"""


@pytest.mark.parametrize("outgoing", [False, True])
async def test_live_message_preserves_reading_position(browser_page: Page, outgoing: bool) -> None:
    await seed_history(browser_page)
    result = await browser_page.evaluate(APPEND, outgoing)
    assert abs(result["after"] - result["before"]) <= 1, result
    assert result["remaining"] > 100, result
    button = browser_page.locator("#btnChatNewMessages")
    await expect(button).to_be_visible()
    await expect(button).to_contain_text("1")


@pytest.mark.parametrize("direct", [False, True])
async def test_tablet_selection_closes_channel_drawer(browser_page: Page, direct: bool) -> None:
    await browser_page.set_viewport_size({"width": 950, "height": 900})
    await browser_page.wait_for_load_state("networkidle")
    await browser_page.locator("#btnBackToChannelsMobile").click()
    panel = browser_page.locator("#sidebarChannelList")
    await expect(panel).to_have_class("chat-channels-panel mobile-open")
    if direct:
        await browser_page.evaluate("bridgeApp.chatModule.openDmConversation('cd'.repeat(32), 'QA DM')")
    else:
        await panel.locator('[data-channel-idx="1"] .channel-select').click()
    await expect(panel).not_to_have_class("chat-channels-panel mobile-open")


@pytest.mark.parametrize("width", [390, 1024])
async def test_new_messages_jump_preserves_count_across_language_change(browser_page: Page, width: int) -> None:
    await browser_page.set_viewport_size({"width": width, "height": 900})
    await seed_history(browser_page)
    for _ in range(3):
        await browser_page.evaluate(APPEND, False)
    before = await browser_page.locator("#chatMessageFeed").evaluate("el => el.scrollTop")
    await browser_page.evaluate("I18n.toggle()")
    button = browser_page.locator("#btnChatNewMessages")
    await expect(button).to_be_visible()
    await expect(button).to_contain_text("3")
    bounds = await button.bounding_box()
    composer = await browser_page.locator("#chatInputForm").bounding_box()
    assert bounds and composer and bounds["y"] + bounds["height"] <= composer["y"]
    after = await browser_page.locator("#chatMessageFeed").evaluate("el => el.scrollTop")
    assert abs(after - before) <= 1
    page_top = await browser_page.evaluate("window.scrollY")
    await button.focus()
    await button.press("Enter")
    await expect(button).not_to_be_visible()
    await expect(browser_page.locator("#chatMessageFeed")).to_be_focused()
    # Check after rendering too: estimated row heights can appear correct inside the click.
    await browser_page.evaluate(
        "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    state = await browser_page.locator("#chatMessageFeed").evaluate(
        "el => ({top:el.scrollTop,client:el.clientHeight,height:el.scrollHeight})"
    )
    assert state["height"] - state["client"] - state["top"] <= 1, state
    assert await browser_page.evaluate("window.scrollY") == page_top


async def test_refresh_keeps_notice_and_explicit_send_follows_tail(browser_page: Page) -> None:
    await seed_history(browser_page)
    await browser_page.evaluate(APPEND, False)
    await browser_page.evaluate("bridgeApp.chatModule._paintConversation('ch_1', {preserveScroll:true})")
    button = browser_page.locator("#btnChatNewMessages")
    await expect(button).to_be_visible()
    await expect(button).to_contain_text("1")
    await browser_page.evaluate("""async () => {
        const chat = bridgeApp.chatModule;
        const originalFetch = window.fetch;
        try {
            window.fetch = (url, options) => url === '/api/tx'
                ? Promise.resolve(new Response(JSON.stringify({status:'ok'}))) : originalFetch(url, options);
            chat.dom.chatInputText.value = 'Explicit own send';
            await chat.sendMessage();
        } finally {window.fetch = originalFetch;}
    }""")
    await expect(button).not_to_be_visible()
    assert await browser_page.locator("#chatMessageFeed").evaluate(
        "el => el.scrollHeight - el.clientHeight - el.scrollTop <= 1"
    )


async def test_following_tail_and_manual_return_clear_notice(browser_page: Page) -> None:
    await seed_history(browser_page)
    await browser_page.evaluate(APPEND, False)
    await expect(browser_page.locator("#btnChatNewMessages")).to_be_visible()
    await browser_page.locator("#chatMessageFeed").evaluate("el => {el.scrollTop=el.scrollHeight;}")
    await expect(browser_page.locator("#btnChatNewMessages")).not_to_be_visible()
    result = await browser_page.evaluate(APPEND, False)
    assert result["remaining"] <= 1, result
    await expect(browser_page.locator("#btnChatNewMessages")).not_to_be_visible()


async def test_resize_clears_notice_when_all_messages_become_visible(browser_page: Page) -> None:
    await seed_history(browser_page)
    await browser_page.locator("#chatMessageFeed").evaluate("el => {el.scrollTop=0;}")
    await browser_page.evaluate(APPEND, False)
    button = browser_page.locator("#btnChatNewMessages")
    await expect(button).to_be_visible()
    await browser_page.set_viewport_size({"width": 1920, "height": 15000})
    assert await browser_page.locator("#chatMessageFeed").evaluate("el => el.scrollHeight <= el.clientHeight")
    await expect(button).not_to_be_visible()


@pytest.mark.parametrize("action", ["switch", "clear", "denied"])
async def test_reading_notice_resets_with_conversation_state(browser_page: Page, action: str) -> None:
    await seed_history(browser_page)
    await browser_page.evaluate(APPEND, False)
    button = browser_page.locator("#btnChatNewMessages")
    await expect(button).to_be_visible()
    await browser_page.evaluate("""action => {
        const chat = bridgeApp.chatModule;
        if (action === 'switch') chat.switchChannel(2);
        else if (action === 'denied') chat._clearProtectedHistory();
        else {
            chat.ctx.showConfirm = async () => true;
            chat.clearCurrentChat();
        }
    }""", action)
    await expect(button).not_to_be_visible()
