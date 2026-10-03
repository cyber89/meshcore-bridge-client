"""Regressions for untranslated errors, stale palette results and QA resource policy."""

from __future__ import annotations

import pytest
from frontend_browser_resources import is_expected_remote_map_tile
from playwright.async_api import Page, expect


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://tile.openstreetmap.org/12/1192/1813.png", True),
        ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/12/1813/1192", True),
        ("https://example.org/12/1192/1813.png", False),
        ("https://tile.openstreetmap.org.evil.example/12/1192/1813.png", False),
        ("https://tile.openstreetmap.org/other.png", False),
        ("http://tile.openstreetmap.org/12/1192/1813.png", False),
        ("https://tile.openstreetmap.org/12/1192/1813.png?redirect=elsewhere", False),
    ],
)
def test_virtual_map_resource_policy(url: str, allowed: bool) -> None:
    assert is_expected_remote_map_tile(url) is allowed


async def test_palette_search_uses_translated_roles(browser_page: Page) -> None:
    await browser_page.keyboard.press("Control+k")
    await browser_page.locator("#cmdPaletteInput").fill("repetidor")
    await expect(browser_page.locator(".cmd-node-match")).to_have_count(3)
    await expect(browser_page.locator(".cmd-node-match").first).to_contain_text("Repetidor")


async def test_palette_refilters_without_editing_query_on_language_change(
    browser_page: Page,
) -> None:
    await browser_page.keyboard.press("Control+k")
    query = browser_page.locator("#cmdPaletteInput")
    await query.fill("Go to")
    await expect(browser_page.locator(".cmd-item:visible")).to_have_count(0)
    await browser_page.evaluate("I18n.toggle()")
    await expect(query).to_have_value("Go to")
    await expect(query).to_be_focused()
    await expect(browser_page.locator(".cmd-item:visible").first).to_contain_text("Go to")
    await browser_page.evaluate("I18n.toggle()")
    await expect(browser_page.locator(".cmd-item:visible")).to_have_count(0)


# Independent expected UI copy: these scenarios previously displayed Spanish in EN.
ERROR_CASES = [
    ("channel_save", "/api/channels", "network", "Error de red al guardar canal", "Network error saving channel"),
    ("contact_add", "/api/contacts", "network", "Error de red al agregar contacto", "Network error adding contact"),
    ("channel_export", "/api/channels/export", "network", "Error obteniendo datos del canal", "Error obtaining channel data"),
    ("channel_delete", "/api/channels", "network", "Error de red al eliminar canal", "Network error deleting channel"),
    ("radio", "/api/config/radio", "network", "Error de red guardando radio", "Network error saving radio settings"),
    ("radio", "/api/config/radio", "response", "Error guardando radio", "Error saving radio settings"),
    ("identity", "/api/config/identity", "network", "Error de red", "Network error"),
    ("identity", "/api/config/identity", "response", "Error guardando identidad", "Error saving identity"),
    ("logs", "/api/logs/download", "network", "Error descargando archivo de logs", "Error downloading log file"),
]


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("action,endpoint,failure,es,en", ERROR_CASES)
async def test_error_messages_use_selected_language_and_preserve_detail(
    browser_page: Page, lang: str, action: str, endpoint: str, failure: str, es: str, en: str
) -> None:
    await browser_page.evaluate("lang => { if (I18n.lang !== lang) I18n.toggle(); }", lang)
    detail = "QA detail <b>original</b>"
    # Inject an error at the browser boundary; no save/query is sent to the radio.
    await browser_page.evaluate(
        """({endpoint, failure, detail}) => {
            const original = window.fetch;
            window.fetch = (url, options) => {
                if (new URL(String(url), location.href).pathname === endpoint) {
                    if (failure === 'network') return Promise.reject(new Error(detail));
                    return Promise.resolve(new Response(JSON.stringify({status: 'error', message: detail}),
                        {status: 200, headers: {'Content-Type': 'application/json'}}));
                }
                return original(url, options);
            };
        }""",
        {"endpoint": endpoint, "failure": failure, "detail": detail},
    )
    expected = f"{es if lang == 'es' else en}: {detail}"
    if action == "channel_save":
        await browser_page.locator("#btnAddChannel").click()
        await browser_page.locator("#chModalName").fill("QA channel")
        # The switch's native input is visually hidden; users click its label.
        await browser_page.locator('label[for="chModalIsEncrypted"]').click()
        await expect(browser_page.locator("#chModalIsEncrypted")).not_to_be_checked()
        await browser_page.locator("#btnSaveChannel").click()
    elif action == "contact_add":
        await browser_page.locator('[data-tab="tab-contacts"]').click()
        await browser_page.locator("#btnHeaderAddContact").click()
        await browser_page.locator("#contactModalPubKey").fill("ad" * 32)
        await browser_page.locator("#contactModalName").fill("QA contact")
        await browser_page.locator("#btnSaveContact").click()
    elif action in ("channel_export", "channel_delete"):
        if action == "channel_delete":
            browser_page.once("dialog", lambda dialog: dialog.accept())
        selector = ".btn-item-qr" if action == "channel_export" else ".btn-item-delete"
        await browser_page.locator(selector).first.click()
    elif action in ("radio", "identity"):
        await browser_page.locator('[data-tab="tab-settings"]').click()
        subtab = "local-radio" if action == "radio" else "local-owner-pos"
        await browser_page.locator(f'[data-subtab="{subtab}"]').click()
        if action == "radio":
            await browser_page.locator("#btnSaveLocalRadio").click()
        else:
            await browser_page.locator("#localNodeName").fill("QA name")
            await browser_page.locator("#btnSaveLocalIdentityPos").click()
    else:
        await browser_page.locator('[data-tab="tab-logs"]').click()
        browser_page.once("dialog", lambda dialog: dialog.accept())
        async with browser_page.expect_event("dialog") as dialog_event:
            await browser_page.locator("#btnDownloadRawLogs").click()
        dialog = await dialog_event.value
        assert dialog.message == expected
        return
    message = browser_page.locator(".toast-message").last
    await expect(message).to_have_text(expected)
    assert await message.locator("b").count() == 0
