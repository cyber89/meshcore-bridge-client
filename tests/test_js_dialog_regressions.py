"""Behavioral regressions for dialogs, notifications and chat dispatch."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect
from test_frontend_ui_audit import _reload_after_startup


@pytest.mark.parametrize("direct", [False, True])
async def test_fragmented_chat_keeps_original_conversation(browser_page: Page, direct: bool) -> None:
    result = await browser_page.evaluate("""async direct => {
        const {ChatModule} = await import('/js/modules/chat.js');
        const {MAX_LORA_TEXT_BYTES} = await import('/js/core/utils.js');
        const chat = new ChatModule({knownNodes: new Map(), localNodePubkey: 'ab'.repeat(32)});
        chat.dom = {chatInputText: document.createElement('textarea'),
            chatMessageFeed: document.createElement('div')};
        const firstTarget = direct ? 'cd'.repeat(32) : null;
        chat.activeDmTarget = firstTarget;
        chat.activeDmName = 'Original conversation';
        chat.activeChannelIdx = 1;
        chat.dom.chatInputText.value = 'a'.repeat(MAX_LORA_TEXT_BYTES + 25);
        const nativeFetch = window.fetch, requests = [];
        let release, started;
        const pending = new Promise(resolve => started = resolve);
        try {
            window.fetch = async (url, options) => {
                if (url !== '/api/tx') return nativeFetch(url, options);
                requests.push(JSON.parse(options.body));
                if (requests.length === 1) {
                    started(); await new Promise(resolve => release = resolve);
                }
                return new Response(JSON.stringify({status: 'ok'}));
            };
            const sending = chat.sendMessage();
            await pending;
            chat.activeDmTarget = direct ? 'ef'.repeat(32) : null;
            chat.activeDmName = 'Different conversation';
            chat.activeChannelIdx = 2;
            chat.dom.chatMessageFeed.replaceChildren();
            release(); await sending;
            return {requests, feeds: [...chat.channelFeeds.keys()],
                visibleRows: chat.dom.chatMessageFeed.querySelectorAll('.message-bubble-row').length,
                originalName: chat.channelFeeds.get(direct ? 'dm_' + firstTarget : 'ch_1')?.at(-1)?.dm_target_name};
        } finally { window.fetch = nativeFetch; release?.(); }
    }""", direct)
    assert len(result["requests"]) == 2
    assert {request["to"] for request in result["requests"]} == {"cd" * 32 if direct else "broadcast"}
    assert {request["channel_index"] for request in result["requests"]} == {1}
    assert result["feeds"] == ["dm_" + "cd" * 32 if direct else "ch_1"]
    assert result["visibleRows"] == 0
    if direct:
        assert result["originalName"] == "Original conversation"


async def test_pending_send_does_not_submit_a_second_draft(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
        const {ChatModule} = await import('/js/modules/chat.js');
        const chat = new ChatModule({knownNodes: new Map()});
        chat.dom = {chatInputText: document.createElement('textarea'),
            chatMessageFeed: document.createElement('div')};
        chat.dom.chatInputText.value = 'First draft';
        const nativeFetch = window.fetch;
        let release, started, requests = 0;
        const pending = new Promise(resolve => started = resolve);
        try {
            window.fetch = async (url, options) => {
                if (url !== '/api/tx') return nativeFetch(url, options);
                requests++;
                if (requests === 1) {started(); await new Promise(resolve => release = resolve);}
                return new Response(JSON.stringify({status: 'ok'}));
            };
            const sending = chat.sendMessage();
            await pending;
            chat.dom.chatInputText.value = 'Keep this new draft';
            await chat.sendMessage();
            release(); await sending;
            const beforeRetry = {requests, draft: chat.dom.chatInputText.value};
            await chat.sendMessage();
            return {...beforeRetry, afterRetry: requests};
        } finally {window.fetch = nativeFetch; release?.();}
    }""")
    assert result == {"requests": 1, "draft": "Keep this new draft", "afterRetry": 2}


@pytest.mark.parametrize("new_draft", [False, True])
async def test_rejected_fragment_stops_remaining_transmission(browser_page: Page, new_draft: bool) -> None:
    result = await browser_page.evaluate("""async newDraft => {
        const {ChatModule} = await import('/js/modules/chat.js');
        const chat = new ChatModule({knownNodes: new Map()});
        const originalText = 'x'.repeat(185);
        chat.dom = {chatInputText: document.createElement('textarea'),
            chatMessageFeed: document.createElement('div')};
        chat.dom.chatInputText.value = originalText;
        const nativeFetch = window.fetch;
        let requests = 0;
        try {
            window.fetch = async (url, options) => {
                if (url !== '/api/tx') return nativeFetch(url, options);
                requests++;
                if (newDraft) chat.dom.chatInputText.value = 'Keep new draft';
                return new Response(JSON.stringify({detail: 'Radio disconnected'}), {status: 503});
            };
            await chat.sendMessage();
            return {requests, draft: chat.dom.chatInputText.value};
        } finally { window.fetch = nativeFetch; }
    }""", new_draft)
    assert result == {"requests": 1, "draft": "Keep new draft" if new_draft else "x" * 185}


@pytest.mark.parametrize("key", ["Enter", "Escape"])
async def test_prompt_does_not_consume_ime_composition(browser_page: Page, key: str) -> None:
    await browser_page.evaluate("""() => {
        window.__imeResult = 'pending';
        window.__imeShown = new Promise(resolve => document.getElementById('systemDialogModal')
            .addEventListener('shown.bs.modal', () => resolve(), {once: true}));
        window.showPrompt('IME composition', '').then(value => window.__imeResult = value);
    }""")
    modal = browser_page.locator("#systemDialogModal")
    await expect(modal).to_be_visible()
    await browser_page.evaluate("window.__imeShown")
    field = browser_page.locator("#systemDialogInput")
    await field.fill("日本語")
    await field.dispatch_event("keydown", {"key": key, "isComposing": True, "bubbles": True})
    # Read after finite transitions, so a premature close cannot hide in a fade.
    await modal.evaluate("""async element => {
        await Promise.all(element.getAnimations({subtree: true})
            .filter(a => a.effect.getComputedTiming().iterations !== Infinity)
            .map(a => a.finished.catch(() => {})));
    }""")
    await expect(modal).to_be_visible()
    assert await browser_page.evaluate("window.__imeResult") == "pending"
    await field.press("Enter")
    await expect(modal).not_to_be_visible()
    assert await browser_page.evaluate("window.__imeResult") == "日本語"


async def test_toast_unknown_inherited_type_uses_info(browser_page: Page) -> None:
    result = await browser_page.evaluate("""() => {
        const results = [];
        for (const type of ['constructor', 'toString', '__proto__']) {
            bridgeApp.showToast('Literal <b>message</b>', type, 0);
            const toast = document.querySelector('#toastContainer .toast:last-child');
            results.push({info: toast.dataset.toastType === 'info',
                text: toast.querySelector('.toast-message').textContent});
        }
        return results;
    }""")
    assert all(item["info"] for item in result), result
    assert all(item["text"] == "Literal <b>message</b>" for item in result)
    assert await browser_page.locator("#toastContainer b").count() == 0


async def test_toast_close_is_large_enough_for_touch(browser_page: Page) -> None:
    await browser_page.set_viewport_size({"width": 390, "height": 844})
    session = await browser_page.context.new_cdp_session(browser_page)
    try:
        await session.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
        await browser_page.evaluate("bridgeApp.showToast('Touch close', 'info', 0)")
        close = browser_page.locator("#toastContainer [data-bs-dismiss=toast]").last
        await expect(close).to_be_visible()
        bounds = await close.bounding_box()
        assert bounds and bounds["width"] >= 44 and bounds["height"] >= 44, bounds
        await close.click()
        await expect(browser_page.locator("#toastContainer .toast")).to_have_count(0)
    finally:
        await session.detach()


async def test_repeated_toast_dismissal_has_one_lifecycle(browser_page: Page) -> None:
    await browser_page.evaluate("""async () => {
        const shown = new Promise(resolve => document.getElementById('toastContainer')
            .addEventListener('shown.bs.toast', () => resolve(), {once: true}));
        bridgeApp.showToast('Repeated dismissal', 'info', 0);
        await shown;
        const close = document.querySelector('#toastContainer [data-bs-dismiss=toast]');
        close.click(); close.click(); close.click();
    }""")
    await expect(browser_page.locator("#toastContainer .toast")).to_have_count(0)
    # Let transition listeners finish; browser_page rejects any pageerror.
    await browser_page.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


async def test_station_works_when_local_preferences_are_blocked(browser_page: Page) -> None:
    await browser_page.add_init_script("""(() => {
        Storage.prototype.getItem = () => {throw new DOMException('Blocked', 'SecurityError');};
        Storage.prototype.setItem = () => {throw new DOMException('Blocked', 'SecurityError');};
    })();""")
    await _reload_after_startup(browser_page)
    await expect(browser_page.locator('#channelListUi [data-channel-idx="1"]')).to_be_visible()
    await browser_page.locator("#themeToggleBtn").click()
    await browser_page.locator("#btnToggleSidebar").click()
    await expect(browser_page.locator("#btnToggleSidebar")).to_have_attribute("aria-expanded", "false")
