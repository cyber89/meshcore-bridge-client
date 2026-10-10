"""Local save/reload regressions with independent SDK snapshots and device state."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from meshcore.events import Event, EventType

from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeRegistry
from src.protocol_types import redact_sensitive_dict
from src.web.api_router import WebAPIRouter
from src.web.controllers.base import BaseController


def station() -> tuple[WebAPIRouter, AdminCommandHandler, Any, Any, dict[str, Any]]:
    """The mock firmware persists writes without updating SDK caches for the caller."""
    physical: dict[str, Any] = {
        "public_key": "ab" * 32, "name": "Before", "radio_freq": 915.0,
        "radio_bw": 125.0, "radio_sf": 7, "radio_cr": 5, "tx_power": 20,
        "telemetry_mode_base": 1, "telemetry_mode_loc": 2, "telemetry_mode_env": 1,
        "multi_acks": 0, "manual_add_contacts": False, "adv_loc_policy": 0,
    }

    async def set_other(infos: dict[str, Any]) -> Event:
        physical.update({key: infos[key] for key in (
            "telemetry_mode_base", "telemetry_mode_loc", "telemetry_mode_env",
            "multi_acks", "manual_add_contacts", "adv_loc_policy",
        )})
        return Event(EventType.OK, {})

    async def appstart() -> Event:
        return Event(EventType.SELF_INFO, deepcopy(physical))

    commands = SimpleNamespace(
        set_other_params_from_infos=AsyncMock(side_effect=set_other),
        set_name=AsyncMock(return_value=Event(EventType.OK, {})),
        set_radio=AsyncMock(return_value=Event(EventType.OK, {})),
        set_tx_power=AsyncMock(return_value=Event(EventType.OK, {})),
        send_appstart=AsyncMock(side_effect=appstart),
    )
    mc = SimpleNamespace(commands=commands, self_info=deepcopy(physical), _self_info=deepcopy(physical))
    adapter = SimpleNamespace(mc=mc, self_info=deepcopy(physical))
    ctx = AdminContext(
        mc_provider=lambda: mc, node_registry=NodeRegistry(),
        repeater_manager=MagicMock(), mqtt=MagicMock(), execute_tx=AsyncMock(),
        serial_adapter=adapter,
    )
    admin = AdminCommandHandler(ctx)
    bridge = SimpleNamespace(admin_handler=admin, handle_admin=admin.handle, serial_adapter=adapter)
    return WebAPIRouter(bridge), admin, mc, adapter, physical


@pytest.mark.parametrize("field,value", [
    ("telemetry_mode_base", 2), ("telemetry_mode_loc", 0), ("telemetry_mode_env", 2),
    ("multi_acks", 1), ("manual_add_contacts", True), ("adv_loc_policy", 1),
])
async def test_acknowledged_settings_survive_get_refresh_and_new_handler(field: str, value: Any) -> None:
    router, admin, mc, adapter, physical = station()
    before = dict(physical)
    code, result = await router.handle_request("POST", "/api/node/config", {field: value})
    assert code == 200
    assert result["data"]["applied"][field] == value
    assert result["data"]["config"][field] == value
    assert physical[field] == value
    assert mc.self_info[field] == adapter.self_info[field] == value
    for key, previous in before.items():
        if key != field:
            assert physical[key] == previous
    code, reloaded = await router.handle_request("GET", "/api/node/config")
    assert code == 200 and reloaded["data"][field] == value
    refreshed = await admin.fetch_device_config(force=True)
    assert refreshed[field] == value
    assert adapter.self_info[field] == value
    # Reconnect/restart hydrates a new handler from the firmware state, not from the old cache.
    mc.self_info = deepcopy(physical)
    assert AdminCommandHandler(admin._ctx).get_local_config()[field] == value
    mc.commands.set_radio.assert_not_awaited()


@pytest.mark.parametrize("response", [None, Event(EventType.ERROR, {"error_code": 2})])
async def test_rejected_other_params_preserve_all_snapshots(response: Any) -> None:
    router, admin, mc, adapter, physical = station()
    before = deepcopy(physical)
    mc.commands.set_other_params_from_infos = AsyncMock(return_value=response)
    code, result = await router.handle_request("POST", "/api/node/config", {"telemetry_mode_base": 0})
    assert code >= 400
    assert result["applied"] == {}
    assert admin.get_local_config()["telemetry_mode_base"] == 1
    assert mc.self_info == mc._self_info == adapter.self_info == physical == before


async def test_partial_save_reports_only_confirmed_writes() -> None:
    router, admin, mc, adapter, _physical = station()
    mc.commands.set_other_params_from_infos = AsyncMock(return_value=Event(EventType.ERROR, {}))
    code, result = await router.handle_request("POST", "/api/node/config", {
        "name": "Confirmed name", "telemetry_mode_base": 0,
    })
    assert code == 400 and result["partial"] is True
    assert result["applied"] == {"name": "Confirmed name"}
    assert result["config"]["name"] == adapter.self_info["name"] == "Confirmed name"
    assert admin.get_local_config()["telemetry_mode_base"] == 1


@pytest.mark.parametrize("params,command,expected", [
    ({"path_hash_mode": 2}, "set_path_hash_mode", {"path_hash_mode": 2}),
    ({"pin": 123456}, "set_devicepin", {"has_pin": True}),
    ({"rx_delay": 1.5}, "set_tuning", {"rx_delay": 1.5}),
])
async def test_advanced_acks_replace_existing_cached_values(
    params: dict[str, Any], command: str, expected: dict[str, Any],
) -> None:
    router, _admin, mc, adapter, _physical = station()
    for snapshot in (mc.self_info, mc._self_info, adapter.self_info):
        snapshot.update({"path_hash_mode": 0, "pin": 0, "rx_delay": 0, "airtime_factor": 1})
    setattr(mc.commands, command, AsyncMock(return_value=Event(EventType.OK, {})))
    code, saved = await router.handle_request("POST", "/api/node/config", params)
    assert code == 200
    code, loaded = await router.handle_request("GET", "/api/node/config")
    assert code == 200
    for key, value in expected.items():
        assert saved["data"]["config"][key] == loaded["data"][key] == value
    if "pin" in params:
        assert loaded["data"].get("pin") != 123456


async def test_phy_change_preserves_repeat_reported_by_device() -> None:
    router, _admin, mc, _adapter, _physical = station()
    mc.self_info["repeat"] = True
    code, _result = await router.handle_request("POST", "/api/node/config", {"spreading_factor": 8})
    assert code == 200
    mc.commands.set_radio.assert_awaited_once_with(915.0, 125.0, 8, 5, 1)


@pytest.mark.parametrize("field", [
    "telemetry_interval", "beacon_interval", "advert_interval", "hop_limit", "hops",
    "owner_info", "owner", "altitude", "alt", "altitude_m",
    "fixed_position", "pos_fixed",
])
async def test_unsupported_field_rejected_before_any_batch_write(field: str) -> None:
    router, admin, mc, adapter, physical = station()
    before = deepcopy(physical)
    code, result = await router.handle_request("POST", "/api/node/config", {"name": "After", field: 120})
    assert code == 422
    assert field in result["detail"]
    assert result["applied"] == {}
    assert mc.self_info == adapter.self_info == physical == before
    assert admin.get_local_config()["name"] == "Before"
    mc.commands.set_name.assert_not_awaited()
    mc.commands.set_radio.assert_not_awaited()
    mc.commands.set_other_params_from_infos.assert_not_awaited()


async def test_read_exposes_unsupported_periodic_telemetry_without_hiding_historical_values() -> None:
    router, admin, _mc, _adapter, _physical = station()
    admin._local_config["telemetry_interval"] = 60
    code, response = await router.handle_request("GET", "/api/node/config")
    assert code == 200
    assert response["data"]["telemetry_interval"] == 60
    assert response["data"]["capabilities"] == {
        "telemetry_interval": False, "beacon_interval": False, "advert_interval": False,
        "hop_limit": False, "owner_info": False, "altitude": False,
        "fixed_position": False,
    }


async def test_missing_other_params_baseline_rejects_entire_save_before_name_write() -> None:
    router, _admin, mc, adapter, _physical = station()
    for snapshot in (mc.self_info, mc._self_info, adapter.self_info):
        snapshot.pop("telemetry_mode_env")
    code, result = await router.handle_request("POST", "/api/node/config", {
        "name": "After", "telemetry_mode_base": 2,
    })
    assert code == 422 and "telemetry_mode_env" in result["detail"]
    assert result["applied"] == {}
    mc.commands.set_name.assert_not_awaited()
    mc.commands.set_other_params_from_infos.assert_not_awaited()


async def test_single_tuning_setting_preserves_observed_companion_value() -> None:
    router, _admin, mc, _adapter, _physical = station()
    mc.self_info.update({"rx_delay": 0.5, "airtime_factor": 2.5})
    mc.commands.set_tuning = AsyncMock(return_value=Event(EventType.OK, {}))
    code, _result = await router.handle_request("POST", "/api/node/config", {"rx_delay": 1.5})
    assert code == 200
    mc.commands.set_tuning.assert_awaited_once_with(1500, 2500)


async def test_missing_tuning_baseline_rejects_before_other_writes() -> None:
    router, _admin, mc, _adapter, _physical = station()
    mc.commands.set_tuning = AsyncMock(return_value=Event(EventType.OK, {}))
    code, result = await router.handle_request("POST", "/api/node/config", {"name": "After", "rx_delay": 1.5})
    assert code == 422 and "airtime_factor" in result["detail"]
    mc.commands.set_name.assert_not_awaited()
    mc.commands.set_tuning.assert_not_awaited()


@pytest.mark.parametrize("field", ["hop_limit", "unrecognized-fixture-secret"])
async def test_invalid_fields_do_not_reflect_request_values_or_unknown_names(field: str) -> None:
    router, _admin, mc, _adapter, _physical = station()
    code, result = await router.handle_request("POST", "/api/node/config", {
        "name": "After", field: "fixture-private-value",
    })
    assert code == 422
    serialized = json.dumps(result)
    assert "fixture-private-value" not in serialized
    assert "unrecognized-fixture-secret" not in serialized
    if field == "hop_limit":
        assert field in result["detail"]
    mc.commands.set_name.assert_not_awaited()


async def test_sdk_exception_text_is_not_a_public_validation_diagnostic() -> None:
    router, _admin, mc, _adapter, _physical = station()
    mc.commands.set_name.side_effect = ValueError("fixture-sdk-private-value")
    code, result = await router.handle_request("POST", "/api/node/config", {"name": "After"})
    assert code >= 400
    assert "fixture-sdk-private-value" not in json.dumps(result)
    assert "validation_fields" not in result
    assert result["applied"] == {}


@pytest.mark.parametrize("reason", ["unsupported_local_fields", "unknown-fixture-secret"])
def test_validation_metadata_cannot_echo_unknown_fields_or_sdk_text(reason: str) -> None:
    failure = BaseController.command_failure({
        "status": "error", "code": 422, "applied": {},
        "message": "fixture-sdk-private-value", "validation_reason": reason,
        "validation_fields": ["hop_limit", "token=fixture-private-value"],
    })
    assert failure is not None and failure[0] == 422
    serialized = json.dumps(failure[1])
    assert "fixture-sdk-private-value" not in serialized
    assert "fixture-private-value" not in serialized
    assert "unknown-fixture-secret" not in serialized
    if reason == "unsupported_local_fields":
        assert failure[1]["validation_fields"] == ["hop_limit"]
    else:
        assert "validation_fields" not in failure[1]


@pytest.mark.parametrize("pin", [0, 123456])
def test_pin_redaction_is_idempotent(pin: int) -> None:
    once = redact_sensitive_dict({"config": {"pin": pin}, "applied": {"pin": pin}})
    twice = redact_sensitive_dict(once)
    assert once == twice
    assert twice["config"]["has_pin"] is (pin != 0)
    assert twice["config"]["pin"] == 0


async def test_refresh_waits_for_save_before_reading_device() -> None:
    router, admin, mc, _adapter, physical = station()
    entered, release = asyncio.Event(), asyncio.Event()

    async def held_write(infos: dict[str, Any]) -> Event:
        entered.set()
        await release.wait()
        physical["telemetry_mode_base"] = infos["telemetry_mode_base"]
        return Event(EventType.OK, {})

    mc.commands.set_other_params_from_infos.side_effect = held_write
    save = asyncio.create_task(router.handle_request("POST", "/api/node/config", {"telemetry_mode_base": 0}))
    refresh: asyncio.Task[dict[str, Any]] | None = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        refresh = asyncio.create_task(admin.fetch_device_config(force=True))
        await asyncio.sleep(0)
        mc.commands.send_appstart.assert_not_awaited()
        release.set()
        assert (await asyncio.wait_for(save, timeout=2))[0] == 200
        assert (await asyncio.wait_for(refresh, timeout=2))["telemetry_mode_base"] == 0
    finally:
        release.set()
        for task in (save, refresh):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
