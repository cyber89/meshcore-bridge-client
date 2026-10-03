"""Responsive/theme/language regressions against an isolated virtual station."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest
from playwright.async_api import Page, Route, expect

from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeContactUpdate

ARTIFACTS = Path("tests/artifacts/frontend-ui")
TABS = ("chat", "contacts", "nodes", "map", "analytics", "logs", "settings")


@pytest.mark.parametrize("width,height", [(320, 740), (390, 844), (768, 1024), (1920, 1080)])
@pytest.mark.parametrize("theme", ["dark", "light"])
async def test_all_views_reflow_in_both_languages(
    browser_page: Page, width: int, height: int, theme: str
) -> None:
    await browser_page.set_viewport_size({"width": width, "height": height})
    await browser_page.evaluate(
        "theme => { document.body.classList.remove('dark-theme', 'light-theme'); document.body.classList.add(theme + '-theme'); }",
        theme,
    )
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    evidence = []
    for lang in ("es", "en"):
        await browser_page.evaluate("lang => { if (I18n.lang !== lang) I18n.toggle(); }", lang)
        await expect(browser_page.locator("html")).to_have_attribute("lang", lang)
        for tab in TABS:
            await browser_page.locator(f'.nav-btn[data-tab="tab-{tab}"]').click()
            await expect(browser_page.locator(f"#tab-{tab}")).to_be_visible()
            await browser_page.evaluate("document.fonts.ready")
            geometry = await browser_page.evaluate(r"""() => ({
                width: innerWidth, scroll: document.documentElement.scrollWidth,
                clippedControls: [...document.querySelectorAll('.app-header button')]
                    .filter(el => el.checkVisibility()).map(el => ({id: el.id, ...el.getBoundingClientRect().toJSON()}))
                    .filter(rect => rect.left < -1 || rect.right > innerWidth + 1),
                rawKeys: [...document.querySelectorAll('[data-i18n]')]
                    .filter(el => el.checkVisibility() && el.textContent.trim() === el.dataset.i18n)
                    .map(el => el.dataset.i18n),
                unboundParameters: [...document.querySelectorAll('[data-i18n-params]')].flatMap(el => {
                    const params = JSON.parse(el.dataset.i18nParams);
                    return [...I18n.t(el.dataset.i18n).matchAll(/\{([a-zA-Z0-9_]+)\}/g)]
                        .filter(match => !Object.prototype.hasOwnProperty.call(params, match[1]))
                        .map(match => ({key: el.dataset.i18n, parameter: match[1]}));
                })
            })""")
            evidence.append({"lang": lang, "tab": tab, **geometry})
            assert geometry["scroll"] <= width, evidence[-1]
            assert not geometry["clippedControls"], evidence[-1]
            assert not geometry["rawKeys"], evidence[-1]
            assert not geometry["unboundParameters"], evidence[-1]
            if tab == "chat" and width <= 640:
                composer = await browser_page.locator("#chatInputText").bounding_box()
                assert composer is not None and composer["width"] >= width - 48, composer
            if width in (390, 1920):
                await browser_page.screenshot(
                    path=str(ARTIFACTS / f"{theme}-{lang}-{tab}-{width}.png"), animations="disabled"
                )
        for subtab in (
            "local-telemetry",
            "local-radio",
            "local-owner-pos",
            "local-console",
            "local-storage-maps",
            "local-security",
        ):
            await browser_page.locator(f'.local-subtab-btn[data-subtab="{subtab}"]').click()
            assert await browser_page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), (width, theme, lang, subtab)
    (ARTIFACTS / f"reflow-{theme}-{width}.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )


async def test_language_changes_preserve_form_data_and_icons(browser_page: Page) -> None:
    await browser_page.evaluate("() => { if (I18n.lang !== 'es') I18n.toggle(); }")
    await browser_page.locator("#chatInputText").fill("Mensaje propio / user draft <b>literal</b>")
    await browser_page.locator("#btnAddChannel").click()
    await expect(browser_page.locator("#createChannelModal")).to_be_visible()
    before = await browser_page.locator("#createChannelTitle").inner_text()
    await browser_page.evaluate("I18n.toggle()")
    await expect(browser_page.locator("#createChannelTitle")).not_to_have_text(before)
    await expect(browser_page.locator("#chatInputText")).to_have_value(
        "Mensaje propio / user draft <b>literal</b>"
    )
    assert await browser_page.locator("#createChannelTitle svg").count() == 1
    await browser_page.keyboard.press("Escape")
    await expect(browser_page.locator("#createChannelModal")).not_to_be_visible()
    await browser_page.reload()
    await expect(browser_page.locator("html")).to_have_attribute("lang", "en")


async def test_navigation_keyboard_selection_and_focus(browser_page: Page) -> None:
    await browser_page.locator('[data-tab="tab-chat"]').focus()
    await browser_page.keyboard.press("ArrowRight")
    contacts = browser_page.locator('[data-tab="tab-contacts"]')
    await expect(contacts).to_be_focused()
    await expect(contacts).to_have_attribute("aria-selected", "true")
    await browser_page.keyboard.press("End")
    await expect(browser_page.locator('[data-tab="tab-settings"]')).to_be_focused()
    await browser_page.keyboard.press("Home")
    await expect(browser_page.locator('[data-tab="tab-chat"]')).to_be_focused()
    assert await browser_page.locator('.nav-btn[tabindex="0"]').count() == 1


async def test_language_switch_keeps_nodes_and_user_names(
    browser_page: Page, virtual_bridge: MeshCoreBridge
) -> None:
    key = "cb" * 32
    virtual_bridge.node_registry.add_or_update(
        key, NodeContactUpdate(name="Sin GPS", role="CLIENT")
    )
    await browser_page.reload()
    await browser_page.locator('[data-tab="tab-nodes"]').click()
    cards = browser_page.locator("#nodesUnifiedGridUi .node-card")
    user_node = browser_page.locator(f'#nodesUnifiedGridUi .node-card[data-pk="{key}"]')
    await expect(user_node).to_contain_text("Sin GPS")
    count = await cards.count()
    await browser_page.evaluate("I18n.toggle()")
    await expect(cards).to_have_count(count)
    await expect(user_node).to_contain_text("Sin GPS")


async def test_client_role_is_independent_of_repeater_like_name(
    browser_page: Page, virtual_bridge: MeshCoreBridge
) -> None:
    key = "cd" * 32
    virtual_bridge.node_registry.add_or_update(
        key, NodeContactUpdate(name="REP-Legitimate Repeater fan", role="CLIENT")
    )
    await browser_page.reload()
    await browser_page.locator('[data-tab="tab-nodes"]').click()
    card = browser_page.locator(f'#nodesUnifiedGridUi .node-card[data-pk="{key}"]')
    await expect(card).to_have_attribute("data-role", "CLIENT")
    await expect(card.locator(".btn-dm-node")).to_be_visible()
    assert await card.locator(".btn-manage-repeater").count() == 0
    await browser_page.locator('[data-tab="tab-contacts"]').click()
    await expect(
        browser_page.locator(f'#contactsGridUi .contact-card[data-pk="{key}"]')
    ).to_be_visible()


async def test_packet_inspector_language_preserves_payload_and_selected_tab(
    browser_page: Page,
) -> None:
    await browser_page.locator('[data-tab="tab-logs"]').click()
    await browser_page.locator("#btnSubtabSniffer").click()
    await browser_page.evaluate("""async () => {
        const {eventBus, EVENTS} = await import('/js/core/eventbus.js');
        eventBus.emit(EVENTS.RF_PACKET, {packet_id: 777, direction: 'rx',
            packet_type: 'CHAT', channel_idx: 2, sender: 'ab'.repeat(32),
            sender_name: 'Sin GPS', target: 'broadcast', snr: 8.5, rssi: -70,
            size_bytes: 4, raw_hex: '000102ff', text: '<b>Mensaje original</b>'});
    }""")
    await browser_page.locator('[data-pkt-id="777"]').click()
    await expect(browser_page.locator("#packetInspectorModal")).to_be_visible()
    await expect(browser_page.locator("#inspFieldDecoded")).to_contain_text(
        "<b>Mensaje original</b>"
    )
    await browser_page.locator("#inspectorTabHex").click()
    before = await browser_page.locator("#inspHexDumpView").inner_text()
    await browser_page.evaluate("I18n.toggle()")
    await expect(browser_page.locator("#inspectorPanelHex")).to_be_visible()
    await expect(browser_page.locator("#inspHexDumpView")).to_have_text(before)
    await browser_page.locator("#inspectorTabSemantic").click()
    await expect(browser_page.locator("#inspFieldDecoded")).to_contain_text(
        "<b>Mensaje original</b>"
    )
    await expect(browser_page.locator("#inspFieldChannel")).to_have_text("Channel #2")
    await browser_page.locator("#inspectorTabJson").click()
    await expect(browser_page.locator("#inspJsonDumpView")).to_contain_text('"raw_hex": "000102ff"')


@pytest.mark.parametrize("theme", ["dark", "light"])
async def test_mobile_modals_fit_viewport(browser_page: Page, theme: str) -> None:
    await browser_page.set_viewport_size({"width": 390, "height": 844})
    await browser_page.evaluate(
        "theme => { document.body.classList.remove('dark-theme', 'light-theme'); document.body.classList.add(theme + '-theme'); }",
        theme,
    )
    await browser_page.locator('[data-tab="tab-contacts"]').click()
    openers = [
        ("#btnHeaderAddContact", "#createContactModal"),
        ("#btnHeaderImportContact", "#importModal"),
        (".btn-contact-qr", "#qrShareModal"),
    ]
    for opener, modal_id in openers:
        await browser_page.locator(opener).first.click()
        modal = browser_page.locator(modal_id)
        await expect(modal).to_be_visible()
        for lang in ("es", "en"):
            await browser_page.evaluate("lang => { if (I18n.lang !== lang) I18n.toggle(); }", lang)
            card = await modal.locator(".modal-card").bounding_box()
            assert card is not None and card["x"] >= 0 and card["x"] + card["width"] <= 390, card
            assert card["y"] >= 0 and card["y"] + card["height"] <= 844, card
            await browser_page.screenshot(
                path=str(ARTIFACTS / f"modal-{modal_id[1:]}-{theme}-{lang}-390.png"),
                animations="disabled",
            )
        await modal.locator(".modal-close").first.click()
        await expect(modal).not_to_be_visible()
    await browser_page.locator('[data-tab="tab-nodes"]').click()
    await browser_page.locator(".btn-manage-repeater").first.click()
    await expect(browser_page.locator("#repeaterAuthGate")).to_be_visible()
    await browser_page.screenshot(
        path=str(ARTIFACTS / f"modal-repeater-{theme}-390.png"), animations="disabled"
    )
    await browser_page.locator("#btnCloseRepeaterAdminModal").click()


async def test_palette_escapes_node_names_and_protects_repeaters(
    browser_page: Page, virtual_bridge: MeshCoreBridge
) -> None:
    malicious_name = '<img src=x onerror="window.paletteXss=true"> QA'
    key = "ca" * 32
    virtual_bridge.node_registry.add_or_update(
        key, NodeContactUpdate(name=malicious_name, role="CLIENT")
    )
    await browser_page.reload()
    await browser_page.locator('[data-tab="tab-nodes"]').click()
    await expect(browser_page.locator("#nodesUnifiedGridUi")).to_contain_text(malicious_name)
    await browser_page.keyboard.press("Control+k")
    await browser_page.locator("#cmdPaletteInput").fill("paletteXss")
    await expect(browser_page.locator(".cmd-node-match")).to_contain_text(malicious_name)
    await expect(browser_page.locator('.cmd-node-match [data-i18n="node.role_client"]')).to_have_text("Cliente")
    await browser_page.evaluate("I18n.toggle()")
    await expect(browser_page.locator('.cmd-node-match [data-i18n="node.role_client"]')).to_have_text("Client")
    await expect(browser_page.locator('.cmd-node-match [data-i18n="app.node_match"]')).to_have_text("Node")
    await expect(browser_page.locator(".cmd-node-match strong")).to_have_text(malicious_name)
    assert await browser_page.locator("#cmdPaletteResults img").count() == 0
    assert await browser_page.evaluate("window.paletteXss === undefined")
    repeater = next(
        node for node in virtual_bridge.node_registry.list_nodes() if node["role"] == "REPEATER"
    )
    repeater_key = repeater["public_key"]
    await browser_page.locator("#cmdPaletteInput").fill(repeater_key[:12])
    await browser_page.locator(f'.cmd-node-match[data-pubkey="{repeater_key}"]').click()
    await expect(browser_page.locator("#tab-nodes")).to_be_visible()
    await expect(browser_page.locator("#commandPaletteModal")).not_to_be_visible()


@pytest.mark.skipif(
    not (ARTIFACTS / "leaflet-1.9.4.js").exists(),
    reason="Optional map visual QA needs the application's pinned Leaflet JS/CSS in artifacts",
)
async def test_leaflet_map_with_cached_library_and_virtual_tiles(browser_page: Page) -> None:
    """Render actual Leaflet offline, with neutral tiles rather than online terrain."""
    js = (ARTIFACTS / "leaflet-1.9.4.js").read_bytes()
    css = (ARTIFACTS / "leaflet-1.9.4.css").read_bytes()
    assert (
        base64.b64encode(hashlib.sha256(js).digest()).decode()
        == "20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
    )
    assert (
        base64.b64encode(hashlib.sha256(css).digest()).decode()
        == "p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
    )
    origin = browser_page.url.rstrip("/")
    tile = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg=="
    )

    async def offline_map(route: Route) -> None:
        url = route.request.url
        if url.startswith(origin + "/"):
            if route.request.resource_type == "document":
                response = await route.fetch()
                html = await response.text()
                html = re.sub(
                    r'<link\b[^>]*href="https://[^>]*>',
                    lambda match: match[0] if "leaflet" in match[0] else "",
                    html,
                )
                await route.fulfill(response=response, body=html)
            else:
                await route.continue_()
        elif url.endswith("/leaflet.js"):
            await route.fulfill(body=js, content_type="application/javascript")
        elif url.endswith("/leaflet.css"):
            await route.fulfill(body=css, content_type="text/css")
        elif route.request.resource_type == "image":
            await route.fulfill(body=tile, content_type="image/png")
        else:
            raise AssertionError(f"Unexpected external dependency: {url}")

    await browser_page.route("**/*", offline_map)
    await browser_page.reload()
    await browser_page.locator('[data-tab="tab-map"]').click()
    await expect(browser_page.locator(".leaflet-container")).to_be_visible()
    await expect(browser_page.locator(".leaflet-marker-icon").first).to_be_visible()
    await browser_page.wait_for_load_state("networkidle")
    for width, height in ((1920, 1080), (390, 844)):
        await browser_page.set_viewport_size({"width": width, "height": height})
        await browser_page.wait_for_load_state("networkidle")
        for theme in ("dark", "light"):
            await browser_page.evaluate(
                "theme => { document.body.classList.remove('dark-theme', 'light-theme'); document.body.classList.add(theme + '-theme'); }",
                theme,
            )
            for lang in ("es", "en"):
                await browser_page.evaluate(
                    "lang => { if (I18n.lang !== lang) I18n.toggle(); }", lang
                )
                await browser_page.wait_for_load_state("networkidle")
                assert await browser_page.locator(".leaflet-tile").evaluate_all(
                    "images => images.length > 0 && images.every(image => image.complete && image.naturalWidth > 0)"
                ), "Visible virtual map tiles must finish loading"
                await browser_page.screenshot(
                    path=str(ARTIFACTS / f"map-leaflet-{theme}-{lang}-{width}.png"),
                    animations="disabled",
                )
            assert await browser_page.evaluate("document.documentElement.scrollWidth <= innerWidth")


async def test_text_token_contrast(browser_page: Page) -> None:
    """Measure real resolved tokens; this is not a complete WCAG certification."""
    report = await browser_page.evaluate("""() => {
        function rgb(value) {
            const probe = document.createElement('span');
            probe.style.color = value; document.body.append(probe);
            const color = getComputedStyle(probe).color.match(/[\\d.]+/g).map(Number);
            probe.remove(); return color;
        }
        function luminance(color) {
            return color.slice(0, 3).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
                .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
        }
        const report = [];
        const previous = document.body.className;
        for (const theme of ['dark', 'light']) {
            document.body.classList.remove('dark-theme', 'light-theme');
            document.body.classList.add(theme + '-theme');
            const css = getComputedStyle(document.body);
            for (const [alias, target] of [['--border-color', '--border-subtle'], ['--bg-surface-secondary', '--bg-surface-elevated'], ['--color-text-secondary', '--text-muted'], ['--bg-tertiary', '--bg-surface-elevated']]) {
                if (css.getPropertyValue(alias).trim() !== css.getPropertyValue(target).trim()) {
                    throw new Error(`${theme}: ${alias} does not resolve to ${target}`);
                }
            }
            for (const text of ['--text-main', '--text-muted', '--text-dim', '--accent-primary', '--accent-success', '--accent-warning', '--accent-danger', '--accent-purple']) {
                for (const surface of ['--bg-canvas', '--bg-surface', '--bg-surface-elevated']) {
                    const a = luminance(rgb(css.getPropertyValue(text)));
                    const b = luminance(rgb(css.getPropertyValue(surface)));
                    report.push({theme, text, surface, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05)});
                }
            }
        }
        document.body.className = previous; return report;
    }""")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "contrast.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert not [pair for pair in report if pair["ratio"] < 4.5], report
