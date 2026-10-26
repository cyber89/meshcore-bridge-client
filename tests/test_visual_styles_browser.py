"""Rendered style regressions on the isolated station, without physical radio."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.async_api import Page, expect
from test_frontend_ui_audit import TABS, _apply_theme, _navigate

ARTIFACTS = Path("tests/artifacts/visual-styles")

# Measure text against composited CSS backgrounds. This does not audit images,
# canvas charts, pseudo elements or certify complete WCAG conformance.
TEXT_CONTRAST = r"""() => {
    const parse = value => value.match(/[\d.]+/g).map(Number);
    const blend = (a, b) => a.slice(0, 3)
        .map((v, i) => v * (a[3] ?? 1) + b[i] * (1 - (a[3] ?? 1))).concat(1);
    function background(element) {
        const chain = [];
        for (let p = element; p; p = p.parentElement) chain.push(p);
        return chain.reverse().reduce((color, p) =>
            blend(parse(getComputedStyle(p).backgroundColor), color), [255,255,255,1]);
    }
    const luminance = color => color.slice(0, 3).map(v => v / 255)
        .map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
        .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
    return [...document.querySelectorAll('body *')].filter(element =>
        element.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) &&
        [...element.childNodes].some(node => node.nodeType === 3 && node.textContent.trim()) &&
        !element.closest('script, style, option, button:disabled, input:disabled')
    ).map(element => {
        const style = getComputedStyle(element), bg = background(element);
        const a = luminance(blend(parse(style.color), bg)), b = luminance(bg);
        return {id: element.id, class: element.getAttribute('class'),
            text: element.textContent.trim().slice(0, 60), color: style.color, background: bg,
            ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05)};
    });
}"""


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("width,height", [(390, 844), (1920, 1080)])
async def test_rendered_text_contrast_across_views(
    browser_page: Page, theme: str, width: int, height: int,
) -> None:
    page = browser_page
    await page.set_viewport_size({"width": width, "height": height})
    await _apply_theme(page, theme)
    await page.evaluate("""async () => {
        const {eventBus, EVENTS} = await import('/js/core/eventbus.js');
        for (const level of ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']) {
            eventBus.emit(EVENTS.SYSTEM_LOG, {level, module: 'visual.audit',
                message: 'Visual audit ' + level, exception: level === 'ERROR' ? 'Traceback: audit' : ''});
        }
    }""")
    report = []
    for tab in TABS:
        await _navigate(page, tab)
        await page.evaluate("document.fonts.ready")
        samples = await page.evaluate(TEXT_CONTRAST)
        assert samples, f"No visible text measured in {tab}"
        report.append({"tab": tab, "samples": samples})
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        await page.screenshot(
            path=str(ARTIFACTS / f"{theme}-{tab}-{width}.png"), animations="disabled",
        )
    (ARTIFACTS / f"contrast-{theme}-{width}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8",
    )
    failures = [{"tab": view["tab"], **sample} for view in report
                for sample in view["samples"] if sample["ratio"] < 4.5]
    assert not failures, failures


@pytest.mark.parametrize("width", [320, 390, 768])
async def test_touch_controls_and_keyboard_focus(browser_page: Page, width: int) -> None:
    page = browser_page
    await page.set_viewport_size({"width": width, "height": 844})
    session = await page.context.new_cdp_session(page)
    try:
        await session.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
        assert await page.evaluate("matchMedia('(pointer: coarse)').matches")
        for selector in ("#themeToggleBtn", "#langToggleBtn", "#btnToggleSidebarMobile",
                         ".auth-account-button", "#btnSendMsg",
                         "#btnEmojiPicker", "#btnChatAttach", ".btn-back-channels-mobile"):
            control = page.locator(selector)
            await expect(control).to_be_visible()
            box = await control.bounding_box()
            assert box is not None and box["width"] >= 44 and box["height"] >= 44, (selector, box)
            assert 0 <= box["x"] < box["x"] + box["width"] <= width, (selector, box)
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        await page.locator("#themeToggleBtn").focus()
        ring = await page.locator("#themeToggleBtn").evaluate("""element => {
            const style = getComputedStyle(element);
            return {style: style.outlineStyle, width: parseFloat(style.outlineWidth)};
        }""")
        assert ring["style"] != "none" and ring["width"] >= 2, ring
        await _navigate(page, "settings")
        for control in await page.locator(".local-subtab-btn").all():
            box = await control.bounding_box()
            assert box is not None and box["height"] >= 44, box
        await page.emulate_media(reduced_motion="reduce")
        assert await page.locator(".local-subtab-btn").first.evaluate(
            "element => parseFloat(getComputedStyle(element).transitionDuration) < 0.001"
        )
    finally:
        await session.detach()
