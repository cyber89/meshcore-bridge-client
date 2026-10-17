"""An open palette follows the real node fetch source without losing user focus."""

from __future__ import annotations

import asyncio
import re

from playwright.async_api import Page, Route, expect


async def test_open_palette_refreshes_after_delayed_node_fetch_and_preserves_focus(browser_page: Page) -> None:
    page = browser_page
    await expect(page.locator('#nodesUnifiedGridUi .node-card[data-role="REPEATER"]')).to_have_count(3)
    release = asyncio.Event()
    started = asyncio.Event()
    revision = 0

    async def delayed_nodes(route: Route) -> None:
        nonlocal revision
        started.set()
        await release.wait()
        response = await route.fetch()
        body = await response.json()
        revision += 1
        if revision >= 3:
            body["data"] = []
        else:
            body["data"].append({"public_key": "f7" * 32, "role": "CLIENT", "name": f"LatePaletteQA {revision}"})
        body["total_count"] = len(body["data"])
        await route.fulfill(response=response, json=body)

    async def refresh_nodes() -> None:
        await page.evaluate("""async () => {
          const {eventBus, EVENTS} = await import('/js/core/eventbus.js');
          eventBus.emit(EVENTS.WS_STATUS_CHANGE, 'connected');
        }""")

    await page.route(re.compile(r"/api/nodes\?"), delayed_nodes)
    try:
        await page.keyboard.press("Control+k")
        query = page.locator("#cmdPaletteInput")
        await query.fill("LatePaletteQA")
        await expect(page.locator(".cmd-node-match")).to_have_count(0)
        await refresh_nodes()
        await asyncio.wait_for(started.wait(), timeout=5)
        release.set()
        await expect(page.locator('#nodesUnifiedGridUi .node-card').filter(has_text="LatePaletteQA 1")).to_have_count(1)
        await expect(page.locator(".cmd-node-match")).to_have_count(1)
        await expect(query).to_have_value("LatePaletteQA")
        await expect(query).to_be_focused()
        await query.press("ArrowDown")
        await expect(page.locator(".cmd-node-match")).to_be_focused()
        await refresh_nodes()
        await expect(page.locator(".cmd-node-match")).to_contain_text("LatePaletteQA 2")
        await expect(page.locator(".cmd-node-match")).to_be_focused()
        await expect(query).to_have_value("LatePaletteQA")
        await refresh_nodes()
        await expect(page.locator("#nodesUnifiedGridUi .node-card")).to_have_count(0)
        await expect(page.locator(".cmd-node-match")).to_have_count(0)
        await expect(query).to_be_focused()
        await expect(query).to_have_value("LatePaletteQA")
    finally:
        release.set()
