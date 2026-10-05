"""Advanced local settings through real HTTP and a virtual Companion device."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from meshcore.events import Event, EventType
from playwright.async_api import Page, expect

from src.bridge_core import MeshCoreBridge
from tests import test_local_config_save_browser as local_config_tests

device_snapshot = local_config_tests.device_snapshot


@pytest.fixture(autouse=True)
def advanced_device(
    virtual_bridge: MeshCoreBridge, device_snapshot: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    mc = virtual_bridge.mc
    assert mc is not None
    state: dict[str, Any] = {"config": 18, "max_hops": 3, "scope": {}, "custom": {"gps": "1"}}

    async def send(frame: bytes, _events: Any) -> Event:
        if frame[0] == 58:
            state.update(config=frame[1], max_hops=frame[2])
        elif frame == b"\x3f":
            state["scope"] = {}
        else:
            assert frame[0] == 63 and len(frame) == 48
            state["scope"] = {"scope_name": frame[1:32].split(b"\0")[0].decode(), "scope_key": frame[32:].hex()}
        return Event(EventType.OK, {})

    async def flags(value: int) -> Event:
        state["config"] = value
        return Event(EventType.OK, {})

    def read_auto() -> Event:
        return Event(EventType.AUTOADD_CONFIG, {key: state[key] for key in ("config", "max_hops") if key in state})

    monkeypatch.setattr(mc.commands, "send", AsyncMock(side_effect=send), raising=False)
    monkeypatch.setattr(mc.commands, "get_autoadd_config", AsyncMock(side_effect=read_auto), raising=False)
    monkeypatch.setattr(mc.commands, "set_autoadd_config", AsyncMock(side_effect=flags), raising=False)
    monkeypatch.setattr(mc.commands, "get_default_flood_scope", AsyncMock(side_effect=lambda: Event(EventType.DEFAULT_FLOOD_SCOPE, dict(state["scope"]))), raising=False)
    monkeypatch.setattr(mc.commands, "get_custom_vars", AsyncMock(side_effect=lambda: Event(EventType.CUSTOM_VARS, dict(state["custom"]))), raising=False)
    return state


async def open_advanced(page: Page) -> None:
    await page.locator('[data-tab="tab-settings"]').click()
    await page.locator('[data-subtab="local-security"]').click()
    await expect(page.locator("#btnSaveAutoAddConfig")).to_be_enabled()


async def test_autoadd_preserves_other_flags_and_readback_after_reload(
    browser_page: Page, advanced_device: dict[str, Any],
) -> None:
    await open_advanced(browser_page)
    await expect(browser_page.locator("#numAutoAddMaxHops")).to_have_value("3")
    await browser_page.locator("#chkAutoAddOverwrite").check()
    await browser_page.locator("#numAutoAddMaxHops").fill("7")
    async with browser_page.expect_request(lambda request: request.method == "POST" and request.url.endswith("/api/config/autoadd")) as pending:
        await browser_page.locator("#btnSaveAutoAddConfig").click()
    assert (await pending.value).post_data_json == {"flags": 19, "max_hops": 7}
    await expect(browser_page.locator(".toast-message").last).to_contain_text("guardada")
    assert advanced_device["config"] == 19 and advanced_device["max_hops"] == 7
    await browser_page.reload(wait_until="domcontentloaded")
    await open_advanced(browser_page)
    await expect(browser_page.locator("#numAutoAddMaxHops")).to_have_value("7")
    await expect(browser_page.locator("#chkAutoAddOverwrite")).to_be_checked()


async def test_legacy_autoadd_omits_unknown_max_hops(
    browser_page: Page, advanced_device: dict[str, Any],
) -> None:
    advanced_device.pop("max_hops")
    await browser_page.reload(wait_until="domcontentloaded")
    await open_advanced(browser_page)
    await expect(browser_page.locator("#numAutoAddMaxHops")).to_be_disabled()
    await expect(browser_page.locator("#numAutoAddMaxHops")).to_have_value("")
    await browser_page.locator("#chkAutoAddOverwrite").check()
    async with browser_page.expect_request(lambda request: request.method == "POST" and request.url.endswith("/api/config/autoadd")) as pending:
        await browser_page.locator("#btnSaveAutoAddConfig").click()
    assert (await pending.value).post_data_json == {"flags": 19}
    await expect(browser_page.locator(".toast-message").last).to_contain_text("guardada")
    assert advanced_device["config"] == 19 and "max_hops" not in advanced_device


async def test_unicode_scope_normalized_then_reset_survives_reload(
    browser_page: Page, advanced_device: dict[str, Any],
) -> None:
    await open_advanced(browser_page)
    await browser_page.locator("#inputFloodScope").fill("región")
    await browser_page.locator("#btnSaveFloodScope").click()
    await expect(browser_page.locator("#currentFloodScopeLabel")).to_have_text("#región")
    assert advanced_device["scope"]["scope_name"] == "#región"
    await browser_page.locator("#btnResetFloodScope").click()
    await expect(browser_page.locator("#currentFloodScopeLabel")).to_have_text("Global (*)")
    assert advanced_device["scope"] == {}
    await browser_page.reload(wait_until="domcontentloaded")
    await open_advanced(browser_page)
    await expect(browser_page.locator("#inputFloodScope")).to_have_value("")
