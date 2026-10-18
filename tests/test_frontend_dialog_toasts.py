"""Dialog ownership and fallback notifications against an isolated virtual station."""

from __future__ import annotations

from playwright.async_api import Page, expect


async def test_native_account_owns_command_shortcut_and_escape(browser_page: Page) -> None:
    opener = browser_page.locator(".app-header [data-open-account]")
    account = browser_page.locator("#accountDialog")
    try:
        await opener.click()
        await expect(account).to_be_visible()
        await browser_page.keyboard.press("Control+k")
        await browser_page.wait_for_timeout(400)
        after_shortcut = await browser_page.evaluate("""() => ({
            nativeOpen: document.getElementById('accountDialog').open,
            paletteHidden: document.getElementById('commandPaletteModal').classList.contains('hidden'),
            focusInsideNative: document.getElementById('accountDialog').contains(document.activeElement),
        })""")
        await browser_page.keyboard.press("Escape")
        await browser_page.wait_for_timeout(400)
        after_escape = await account.evaluate("element => element.open")
        assert after_shortcut == {
            "nativeOpen": True,
            "paletteHidden": True,
            "focusInsideNative": True,
        }, after_shortcut
        assert not after_escape, "Escape must dismiss the native account dialog"
        await expect(opener).to_be_focused()
    finally:
        await browser_page.evaluate("""async () => {
            document.getElementById('accountDialog').close();
            await bridgeApp.dialogController.close(document.getElementById('commandPaletteModal'));
        }""")


async def test_fallback_toast_visibility_close_and_persistence(browser_page: Page) -> None:
    await browser_page.evaluate("""() => {
        window.__qaToastBootstrap = window.bootstrap;
        window.bootstrap = null;
        bridgeApp.showToast('Fallback close <b>literal</b>', 'info', 0);
        window.__qaFallbackToast = document.querySelector('#toastContainer .toast:last-child');
    }""")
    try:
        visible = await browser_page.evaluate("() => window.__qaFallbackToast.checkVisibility()")
        assert await browser_page.locator("#toastContainer b").count() == 0
        await browser_page.evaluate("() => window.__qaFallbackToast.querySelector('button').click()")
        await browser_page.wait_for_timeout(250)
        dismissed = await browser_page.evaluate("() => !window.__qaFallbackToast.isConnected")
        await browser_page.evaluate("""() => {
            document.querySelectorAll('#toastContainer .toast').forEach(element => element.remove());
            bridgeApp.showToast('Persistent fallback', 'warning', 0);
            window.__qaPersistentToast = document.querySelector('#toastContainer .toast:last-child');
        }""")
        await browser_page.wait_for_timeout(3800)
        persistent = await browser_page.evaluate("() => window.__qaPersistentToast.isConnected")
        observed = {"visible": visible, "dismissed": dismissed, "persistent": persistent}
        assert observed == {"visible": True, "dismissed": True, "persistent": True}, observed
    finally:
        await browser_page.evaluate("""() => {
            window.bootstrap = window.__qaToastBootstrap;
            delete window.__qaToastBootstrap;
            document.querySelectorAll('#toastContainer .toast').forEach(element => element.remove());
        }""")
