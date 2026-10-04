"""User-visible saves and reloads through the SPA and an isolated virtual station."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock

import pytest
from meshcore.events import Event, EventType
from playwright.async_api import Page, expect

from src.bridge_core import MeshCoreBridge


@pytest.fixture(autouse=True)
def device_snapshot(virtual_bridge: MeshCoreBridge, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """ACKs persist firmware state independently from the SDK's cached SELF_INFO."""
    mc = virtual_bridge.mc
    assert mc is not None
    defaults = {
        "telemetry_mode_base": 1, "telemetry_mode_loc": 1, "telemetry_mode_env": 1,
        "multi_acks": 0, "manual_add_contacts": False, "adv_loc_policy": 0,
    }
    mc.self_info.update(defaults)
    stored = deepcopy(mc.self_info)

    async def set_other(infos: dict[str, Any]) -> Event:
        stored.update({key: infos[key] for key in defaults})
        return Event(EventType.OK, {})

    async def read() -> Event:
        return Event(EventType.SELF_INFO, deepcopy(stored))

    async def set_name(name: str) -> Event:
        stored.update(name=name, adv_name=name)
        return Event(EventType.OK, {})

    async def set_tx(power: int) -> Event:
        stored["tx_power"] = power
        return Event(EventType.OK, {})

    monkeypatch.setattr(mc.commands, "set_other_params_from_infos", AsyncMock(side_effect=set_other), raising=False)
    monkeypatch.setattr(mc.commands, "send_appstart", AsyncMock(side_effect=read))
    monkeypatch.setattr(mc.commands, "set_name", AsyncMock(side_effect=set_name))
    monkeypatch.setattr(mc.commands, "set_tx_power", AsyncMock(side_effect=set_tx))
    return stored


async def open_radio(page: Page) -> None:
    await page.locator('[data-tab="tab-settings"]').click()
    await page.locator('[data-subtab="local-radio"]').click()
    await expect(page.locator("#localTxPower")).to_have_value("20")


async def test_periodic_telemetry_is_explicitly_unavailable(browser_page: Page) -> None:
    await open_radio(browser_page)
    for selector in ("#localTelemetryEnable", "#localTelemetryInterval", "#localAdvertEnable", "#localAdvertInterval"):
        await expect(browser_page.locator(selector)).to_be_disabled()
    await expect(browser_page.locator("#localTelemetryInterval")).to_have_value("")
    await expect(browser_page.locator("#localPeriodicSupportHint")).to_be_visible()
    await expect(browser_page.locator("#localPeriodicSupportHint")).to_contain_text("no programan envíos")
    await expect(browser_page.locator("#localTelemBase")).to_be_enabled()
    writes: list[str] = []
    browser_page.on("request", lambda request: writes.append(request.url) if request.method == "POST" and "/api/config/" in request.url else None)
    await browser_page.locator("#btnSaveLocalRadio").click()
    await expect(browser_page.locator(".toast-message").last).to_have_text("No hay cambios pendientes para guardar")
    assert writes == []


@pytest.mark.parametrize("field,key,value", [
    ("localTelemBase", "telemetry_mode_base", 2),
    ("localTelemLoc", "telemetry_mode_loc", 0),
    ("localTelemEnv", "telemetry_mode_env", 2),
    ("localMultiAcks", "multi_acks", True),
    ("localManualAddContacts", "manual_add_contacts", True),
    ("localAdvLocPolicy", "adv_loc_policy", True),
    ("localTxPower", "tx_power", 17),
])
async def test_supported_radio_change_survives_reload(
    browser_page: Page, virtual_bridge: MeshCoreBridge, device_snapshot: dict[str, Any],
    field: str, key: str, value: Any,
) -> None:
    await open_radio(browser_page)
    control = browser_page.locator(f"#{field}")
    if isinstance(value, bool):
        await browser_page.locator(f'label[for="{field}"]').click()
    elif field == "localTxPower":
        await control.fill(str(value))
    else:
        await control.select_option(str(value))
    async with browser_page.expect_request(lambda request: request.method == "POST" and request.url.endswith("/api/config/radio")) as pending:
        await browser_page.locator("#btnSaveLocalRadio").click()
    assert (await pending.value).post_data_json == {key: value}
    await expect(browser_page.locator(".toast-message").last).to_contain_text("guardados y aplicados")
    assert device_snapshot[key] == value
    admin = virtual_bridge.admin_handler
    await admin.fetch_device_config(force=True)
    await browser_page.reload(wait_until="domcontentloaded")
    await browser_page.locator('[data-tab="tab-settings"]').click()
    await browser_page.locator('[data-subtab="local-radio"]').click()
    if isinstance(value, bool):
        await expect(browser_page.locator(f"#{field}")).to_be_checked()
    else:
        await expect(browser_page.locator(f"#{field}")).to_have_value(str(value))


async def test_identity_save_omits_unsupported_defaults_and_survives_reload(
    browser_page: Page, device_snapshot: dict[str, Any],
) -> None:
    await browser_page.locator('[data-tab="tab-settings"]').click()
    await browser_page.locator('[data-subtab="local-owner-pos"]').click()
    await expect(browser_page.locator("#localOwnerInfo")).to_be_disabled()
    await browser_page.locator("#localNodeName").fill("Saved through SPA")
    async with browser_page.expect_request(lambda request: request.method == "POST" and request.url.endswith("/api/config/identity")) as pending:
        await browser_page.locator("#btnSaveLocalIdentityPos").click()
    assert (await pending.value).post_data_json == {"name": "Saved through SPA"}
    await expect(browser_page.locator(".toast-message").last).to_contain_text("Identidad")
    assert device_snapshot["name"] == "Saved through SPA"
    await browser_page.reload(wait_until="domcontentloaded")
    await browser_page.locator('[data-tab="tab-settings"]').click()
    await browser_page.locator('[data-subtab="local-owner-pos"]').click()
    await expect(browser_page.locator("#localNodeName")).to_have_value("Saved through SPA")
