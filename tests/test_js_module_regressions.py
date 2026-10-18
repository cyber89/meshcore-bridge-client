"""Observable module regressions on the isolated browser station."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect


@pytest.mark.parametrize("outcome", ["http_error", "network_error", "ok"])
async def test_favorite_commits_only_after_server_confirmation(browser_page: Page, outcome: str) -> None:
    await browser_page.locator('[data-tab="tab-contacts"]').click()
    button = browser_page.locator("#contactsGridUi .btn-toggle-fav").first
    await expect(button).to_be_visible()
    initial = await button.get_attribute("aria-pressed")
    await browser_page.evaluate("""() => {
        const original = window.fetch;
        window.__qaFavoriteFetch = original;
        window.fetch = (input, options) => {
            if (new URL(String(input), location.href).pathname === '/api/contacts' && options?.method === 'POST') {
                return new Promise((resolve, reject) => { window.__qaFinishFavorite = {resolve, reject}; });
            }
            return original(input, options);
        };
    }""")
    try:
        await button.click()
        await browser_page.wait_for_function("Boolean(window.__qaFinishFavorite)")
        pending = await button.get_attribute("aria-pressed")
        pending_toasts = await browser_page.locator(".toast-message").all_text_contents()
        await browser_page.evaluate("""outcome => {
            if (outcome === 'network_error') window.__qaFinishFavorite.reject(new Error('QA offline'));
            else window.__qaFinishFavorite.resolve(new Response(JSON.stringify(
                outcome === 'ok' ? {status: 'ok', data: {}} : {status: 'error', detail: 'QA denied'}
            ), {status: outcome === 'ok' ? 200 : 503, headers: {'Content-Type': 'application/json'}}));
        }""", outcome)
        await expect(browser_page.locator(".toast-message").last).to_be_visible()
        expected = ("false" if initial == "true" else "true") if outcome == "ok" else initial
        await expect(button).to_have_attribute("aria-pressed", expected)
        await expect(button).to_be_enabled()
        assert pending == initial, "Favorite state must wait for the POST response"
        assert not pending_toasts, "Pending changes must not announce success"
        toast = browser_page.locator("#toastContainer .toast").last
        assert await toast.evaluate("element => element.dataset.toastType === 'error'") == (outcome != "ok")
    finally:
        await browser_page.evaluate("() => { window.fetch = window.__qaFavoriteFetch; }")


@pytest.mark.parametrize("kind", ["qr", "hex", "json"])
@pytest.mark.parametrize("clipboard_available", [True, False])
async def test_copy_failure_never_announces_success(
    browser_page: Page, kind: str, clipboard_available: bool,
) -> None:
    await browser_page.evaluate("""({kind, available}) => {
        window.__qaCopyRejections = [];
        window.addEventListener('unhandledrejection', event => {
            window.__qaCopyRejections.push(String(event.reason));
            event.preventDefault();
        });
        Object.defineProperty(navigator, 'clipboard', {configurable: true, value: available ? {
            writeText: () => Promise.reject(new DOMException('QA denied', 'NotAllowedError'))
        } : undefined});
        if (kind === 'qr') bridgeApp.settingsModule.showQrModal('QA share', 'meshcore://QA', '{}');
        else bridgeApp.snifferModule.openPacketInspector({packet_id: 77, direction: 'rx', raw_hex: '0102'});
    }""", {"kind": kind, "available": clipboard_available})
    selector = {"qr": "#btnCopyQrUri", "hex": "#btnCopyHexDump", "json": "#btnCopyJsonDump"}[kind]
    if kind != "qr":
        await browser_page.evaluate("kind => bridgeApp.snifferModule.switchInspectorTab(kind)", kind)
    await browser_page.locator(selector).click()
    await browser_page.wait_for_timeout(150)
    result = await browser_page.evaluate("""selector => ({
        rejections: window.__qaCopyRejections,
        button: document.querySelector(selector).textContent,
        success: [...document.querySelectorAll('#toastContainer [data-toast-type=success]')].length,
        errors: [...document.querySelectorAll('#toastContainer [data-toast-type=error]')].length,
    })""", selector)
    assert not result["rejections"], result
    assert "Copiado" not in result["button"] and "Copied" not in result["button"], result
    assert result["success"] == 0 and result["errors"] == 1, result


@pytest.mark.parametrize("kind", ["qr", "hex", "json"])
async def test_copy_success_waits_for_clipboard_confirmation(browser_page: Page, kind: str) -> None:
    await browser_page.evaluate("""kind => {
        Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
            writeText: () => new Promise(resolve => { window.__qaFinishCopy = resolve; })
        }});
        if (kind === 'qr') bridgeApp.settingsModule.showQrModal('QA share', 'meshcore://QA', '{}');
        else bridgeApp.snifferModule.openPacketInspector({packet_id: 77, direction: 'rx', raw_hex: '0102'});
        if (kind !== 'qr') bridgeApp.snifferModule.switchInspectorTab(kind);
    }""", kind)
    selector = {"qr": "#btnCopyQrUri", "hex": "#btnCopyHexDump", "json": "#btnCopyJsonDump"}[kind]
    button = browser_page.locator(selector)
    await button.click()
    await browser_page.wait_for_function("Boolean(window.__qaFinishCopy)")
    pending = await button.text_content()
    assert pending is not None
    pending_toasts = await browser_page.locator(".toast-message").count()
    await browser_page.evaluate("window.__qaFinishCopy()")
    if kind == "qr":
        await expect(browser_page.locator("#toastContainer [data-toast-type=success]")).to_have_count(1)
    else:
        await expect(button).to_have_text("✓ ¡Copiado!")
    assert "Copiado" not in pending and "Copied" not in pending
    assert pending_toasts == 0


async def test_channel_save_toast_preserves_literal_name(browser_page: Page) -> None:
    await browser_page.evaluate("""() => {
        const original = window.fetch;
        window.__qaChannelFetch = original;
        window.fetch = (input, options) => {
            if (new URL(String(input), location.href).pathname === '/api/channels' && options?.method === 'POST') {
                return Promise.resolve(new Response(JSON.stringify({status: 'ok', data: {}}),
                    {status: 200, headers: {'Content-Type': 'application/json'}}));
            }
            return original(input, options);
        };
    }""")
    try:
        await browser_page.locator("#btnAddChannel").click()
        await browser_page.locator("#chModalIndex").select_option("4")
        await browser_page.locator("#chModalName").fill("QA <&> channel")
        await browser_page.locator('label[for="chModalIsEncrypted"]').click()
        await browser_page.locator("#btnSaveChannel").click()
        await expect(browser_page.locator(".toast-message").last).to_have_text("✅ Canal #4 (QA <&> channel) guardado y sincronizado")
        assert await browser_page.locator(".toast-message b").count() == 0
    finally:
        await browser_page.evaluate("() => { window.fetch = window.__qaChannelFetch; }")


@pytest.mark.parametrize("reopen", [False, True])
async def test_traceroute_discards_response_after_dialog_context_changes(browser_page: Page, reopen: bool) -> None:
    await browser_page.evaluate("""() => {
        const original = window.fetch;
        window.__qaTraceFetch = original;
        window.fetch = (input, options) => {
            if (new URL(String(input), location.href).pathname === '/api/repeater/traceroute') {
                return new Promise(resolve => { window.__qaFinishTrace = resolve; });
            }
            return original(input, options);
        };
        bridgeApp.mapModule.openTracerouteModal('11'.repeat(32), 'QA node A');
    }""")
    try:
        await browser_page.locator("#btnExecuteTrace").click()
        await browser_page.wait_for_function("Boolean(window.__qaFinishTrace)")
        await browser_page.keyboard.press("Escape")
        await expect(browser_page.locator("#tracerouteModal")).not_to_be_visible()
        if reopen:
            await browser_page.evaluate("bridgeApp.mapModule.openTracerouteModal('22'.repeat(32), 'QA node B')")
            await expect(browser_page.locator("#tracerouteModal")).to_be_visible()
        await browser_page.evaluate("""async () => {
            window.__qaFinishTrace(new Response(JSON.stringify({status: 'ok', data: {
                total_hops: 1, total_rtt_ms: 125,
                hops_breakdown: [{name: 'QA stale node A', pubkey: '11'.repeat(32), snr: 4}]
            }}), {status: 200, headers: {'Content-Type': 'application/json'}}));
            await new Promise(resolve => setTimeout(resolve, 50));
        }""")
        graph_text = await browser_page.locator("#traceVisualGraph").text_content()
        assert graph_text is not None
        assert "QA stale node A" not in graph_text
        await expect(browser_page.locator(".toast-message")).to_have_count(0)
        if reopen:
            await expect(browser_page.locator("#traceTargetNameDisplay")).to_have_text("QA node B")
            await expect(browser_page.locator("#btnExecuteTrace")).to_be_enabled()
    finally:
        await browser_page.evaluate("() => { window.fetch = window.__qaTraceFetch; }")


async def test_heatmap_off_stays_off_when_pending_response_arrives(browser_page: Page) -> None:
    await browser_page.evaluate("""() => {
        const original = window.fetch;
        window.__qaHeatmapFetch = original;
        window.fetch = (input, options) => {
            if (new URL(String(input), location.href).pathname === '/api/rf/heatmap') {
                return new Promise(resolve => { window.__qaFinishHeatmap = resolve; });
            }
            return original(input, options);
        };
        window.__qaHeatmapOperation = bridgeApp.mapModule.setRfHeatmap(true);
    }""")
    try:
        await browser_page.wait_for_function("Boolean(window.__qaFinishHeatmap)")
        result = await browser_page.evaluate("""async () => {
            const module = bridgeApp.mapModule;
            await module.setRfHeatmap(false);
            window.__qaFinishHeatmap(new Response(JSON.stringify({status: 'ok', data: {points: [{
                lat: 40, lon: -74, name: 'QA stale heatmap', rssi: -85, snr: 4, role: 'CLIENT'
            }]}}), {status: 200, headers: {'Content-Type': 'application/json'}}));
            await window.__qaHeatmapOperation;
            return {active: module.rfHeatmapActive, timer: module.rfHeatmapInterval,
                layers: module.rfHeatmapGroup?.getLayers().length || 0,
                successToasts: document.querySelectorAll('#toastContainer [data-toast-type=success]').length};
        }""")
        assert result == {"active": False, "timer": None, "layers": 0, "successToasts": 0}, result
    finally:
        await browser_page.evaluate("""async () => {
            window.fetch = window.__qaHeatmapFetch;
            await bridgeApp.mapModule.setRfHeatmap(false);
        }""")


async def test_map_constructor_tolerates_blocked_preferences(browser_page: Page) -> None:
    result = await browser_page.evaluate("""() => {
        const getItem = Storage.prototype.getItem;
        Storage.prototype.getItem = () => { throw new DOMException('QA blocked storage', 'SecurityError'); };
        try {
            const module = new bridgeApp.mapModule.constructor(bridgeApp.context);
            return {url: module.localTileUrl, mode: module.mapLayerMode};
        } catch (error) {
            return {error: error.message};
        } finally { Storage.prototype.getItem = getItem; }
    }""")
    assert result == {"url": "/api/map/tiles/{z}/{x}/{y}.png", "mode": "auto"}, result


async def test_traceroute_keeps_response_for_current_dialog(browser_page: Page) -> None:
    await browser_page.evaluate("""() => {
        const original = window.fetch;
        window.__qaTraceSuccessFetch = original;
        window.fetch = (input, options) => {
            if (new URL(String(input), location.href).pathname === '/api/repeater/traceroute') {
                return Promise.resolve(new Response(JSON.stringify({status: 'ok', data: {
                    total_hops: 1, total_rtt_ms: 125,
                    hops_breakdown: [{name: 'QA current trace', pubkey: '11'.repeat(32), snr: 4}]
                }}), {status: 200, headers: {'Content-Type': 'application/json'}}));
            }
            return original(input, options);
        };
        bridgeApp.mapModule.openTracerouteModal('11'.repeat(32), 'QA current node');
    }""")
    try:
        await browser_page.locator("#btnExecuteTrace").click()
        await expect(browser_page.locator("#traceVisualGraph")).to_contain_text("QA current trace")
        await expect(browser_page.locator("#toastContainer [data-toast-type=success]")).to_have_count(1)
        await expect(browser_page.locator("#btnExecuteTrace")).to_be_enabled()
    finally:
        await browser_page.evaluate("() => { window.fetch = window.__qaTraceSuccessFetch; }")


async def test_heatmap_keeps_current_response_when_still_enabled(browser_page: Page) -> None:
    result = await browser_page.evaluate("""async () => {
        const original = window.fetch;
        window.fetch = (input, options) => {
            if (new URL(String(input), location.href).pathname === '/api/rf/heatmap') {
                return Promise.resolve(new Response(JSON.stringify({status: 'ok', data: {points: [{
                    lat: 40, lon: -74, name: 'QA current heatmap', rssi: -85, snr: 4, role: 'CLIENT'
                }]}}), {status: 200, headers: {'Content-Type': 'application/json'}}));
            }
            return original(input, options);
        };
        const module = bridgeApp.mapModule;
        try {
            await module.setRfHeatmap(true);
            return {active: module.rfHeatmapActive, hasTimer: Boolean(module.rfHeatmapInterval),
                layers: module.rfHeatmapGroup.getLayers().length,
                successToasts: document.querySelectorAll('#toastContainer [data-toast-type=success]').length};
        } finally {
            window.fetch = original;
            await module.setRfHeatmap(false);
        }
    }""")
    assert result == {"active": True, "hasTimer": True, "layers": 2, "successToasts": 1}, result
