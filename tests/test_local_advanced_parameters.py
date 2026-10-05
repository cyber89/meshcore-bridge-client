"""Official Companion layouts, observed reads and advanced-setting round trips."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock

import pytest
from meshcore.events import Event, EventType

from tests.test_local_config_save_roundtrip import station


@pytest.mark.parametrize("scope,name", [("region", "#region"), ("#región", "#región"), ("#x", "#x")])
async def test_scope_wire_layout_and_readback(scope: str, name: str) -> None:
    router, admin, mc, _adapter, _physical = station()
    state: dict[str, Any] = {}

    async def send(frame: bytes, _events: Any) -> Event:
        assert frame[0] == 63 and len(frame) == 48
        assert frame[1:32].split(b"\0")[0] == name.encode()
        assert frame[32:] == hashlib.sha256(name.encode()).digest()[:16]
        state.update(scope_name=name, scope_key=frame[32:].hex())
        return Event(EventType.OK, {})

    mc.commands.send = AsyncMock(side_effect=send)
    mc.commands.get_default_flood_scope = AsyncMock(side_effect=lambda: Event(EventType.DEFAULT_FLOOD_SCOPE, deepcopy(state)))
    code, saved = await router.handle_request("POST", "/api/config/flood_scope", {"scope": scope})
    assert code == 200 and saved["data"]["flood_scope"]["scope_name"] == name
    admin._local_config["flood_scope"] = {"scope_name": "old"}
    code, loaded = await router.handle_request("GET", "/api/config/flood_scope")
    assert code == 200 and loaded["data"] == state


async def test_scope_reset_uses_single_opcode_and_empty_read_clears_cache() -> None:
    router, admin, mc, _adapter, _physical = station()
    mc.commands.send = AsyncMock(return_value=Event(EventType.OK, {}))
    mc.commands.get_default_flood_scope = AsyncMock(return_value=Event(EventType.DEFAULT_FLOOD_SCOPE, {}))
    admin._local_config["flood_scope"] = {"scope_name": "#old"}
    code, result = await router.handle_request("POST", "/api/config/flood_scope", {"scope": "*"})
    assert code == 200 and result["data"]["flood_scope"]["scope_name"] == ""
    assert mc.commands.send.await_args.args[0] == b"\x3f"
    admin._local_config["flood_scope"] = {"scope_name": "#old"}
    assert (await admin.get_flood_scope())["scope_name"] == ""


@pytest.mark.parametrize("scope", ["x" * 30, "#" + "é" * 15, "bad\0name", "bad\nname", 123])
async def test_scope_invalid_rejected_before_transport(scope: Any) -> None:
    router, _admin, mc, _adapter, _physical = station()
    mc.commands.send = AsyncMock(return_value=Event(EventType.OK, {}))
    assert (await router.handle_request("POST", "/api/config/flood_scope", {"scope": scope}))[0] == 422
    mc.commands.send.assert_not_awaited()


@pytest.mark.parametrize("hops", [0, 1, 64])
async def test_autoadd_optional_byte_and_readback(hops: int) -> None:
    router, admin, mc, _adapter, _physical = station()
    state = {"config": 18, "max_hops": 3}
    mc.commands.get_autoadd_config = AsyncMock(side_effect=lambda: Event(EventType.AUTOADD_CONFIG, dict(state)))

    async def send(frame: bytes, _events: Any) -> Event:
        assert frame == bytes([58, 19, hops])
        state.update(config=frame[1], max_hops=frame[2])
        return Event(EventType.OK, {})

    mc.commands.send = AsyncMock(side_effect=send)
    assert (await admin.get_autoadd_config())["max_hops_supported"] is True
    code, saved = await router.handle_request("POST", "/api/config/autoadd", {"flags": 19, "max_hops": hops})
    assert code == 200 and saved["data"]["autoadd_config"]["max_hops"] == hops
    assert (await admin.get_autoadd_config())["max_hops"] == hops


async def test_legacy_autoadd_never_fabricates_max_hops() -> None:
    router, admin, mc, _adapter, _physical = station()
    mc.commands.get_autoadd_config = AsyncMock(return_value=Event(EventType.AUTOADD_CONFIG, {"config": 18}))
    mc.commands.set_autoadd_config = AsyncMock(return_value=Event(EventType.OK, {}))
    cfg = await admin.get_autoadd_config()
    assert cfg["max_hops_supported"] is False and "max_hops" not in cfg
    assert (await router.handle_request("POST", "/api/config/autoadd", {"flags": 19, "max_hops": 3}))[0] == 422
    mc.commands.set_autoadd_config.assert_not_awaited()
    code, result = await router.handle_request("POST", "/api/config/autoadd", {"flags": 19})
    assert code == 200 and "max_hops" not in result["data"]["autoadd_config"]


@pytest.mark.parametrize("body", [{"flags": -1}, {"flags": 256}, {"flags": 2, "max_hops": 65}, {"flags": 2, "max_hops": -1}])
async def test_autoadd_range_rejected(body: dict[str, Any]) -> None:
    router, _admin, mc, _adapter, _physical = station()
    mc.commands.set_autoadd_config = AsyncMock()
    assert (await router.handle_request("POST", "/api/config/autoadd", body))[0] == 422
    mc.commands.set_autoadd_config.assert_not_awaited()


async def test_empty_custom_vars_read_clears_old_snapshot() -> None:
    _router, admin, mc, adapter, _physical = station()
    admin._local_config["custom_vars"] = {"gps": "1"}
    mc.commands.get_custom_vars = AsyncMock(return_value=Event(EventType.CUSTOM_VARS, {}))
    assert await admin.get_custom_vars() == {}
    assert mc.self_info["custom_vars"] == adapter.self_info["custom_vars"] == {}
    admin._local_config["custom_vars"] = {"gps": "1"}
    refreshed = await admin.fetch_device_config(force=True)
    assert refreshed["custom_vars"] == {}


@pytest.mark.parametrize("key,value", [("gps:bad", "1"), ("gps", "1,extra:2"), ("gps", "a:b")])
async def test_custom_vars_invalid_batch_writes_nothing(key: str, value: str) -> None:
    router, _admin, mc, _adapter, _physical = station()
    mc.commands.set_custom_var = AsyncMock(return_value=Event(EventType.OK, {}))
    assert (await router.handle_request("POST", "/api/config/custom_vars", {"vars": {"gps": "1", key: value}}))[0] == 422
    mc.commands.set_custom_var.assert_not_awaited()


async def test_custom_vars_cannot_be_deleted_by_assigning_empty_value() -> None:
    router, admin, mc, _adapter, _physical = station()
    admin._local_config["custom_vars"] = {"gps": "1"}
    mc.commands.set_custom_var = AsyncMock(return_value=Event(EventType.OK, {}))
    assert (await router.handle_request("DELETE", "/api/config/custom_vars", {"key": "gps"}))[0] == 422
    assert admin._local_config["custom_vars"] == {"gps": "1"}
    mc.commands.set_custom_var.assert_not_awaited()


@pytest.mark.parametrize("response,code", [(Event(EventType.DEVICE_INFO, {"path_hash_mode": 2}), 200), (Event(EventType.ERROR, {}), 503), (Event(EventType.DEVICE_INFO, {}), 503)])
async def test_hash_mode_requires_observed_device_query(response: Event, code: int) -> None:
    router, _admin, mc, _adapter, _physical = station()
    mc.commands.send_device_query = AsyncMock(return_value=response)
    result_code, result = await router.handle_request("GET", "/api/config/path_hash_mode")
    assert result_code == code
    if code == 200:
        assert result["path_hash_mode"] == 2


async def test_device_info_reads_pin_and_signed_self_info_power() -> None:
    router, admin, mc, _adapter, physical = station()
    mc.self_info["tx_power"] = physical["tx_power"] = 247
    mc.commands.send_device_query = AsyncMock(return_value=Event(EventType.DEVICE_INFO, {"ble_pin": 123456}))
    result = await admin.fetch_device_config(force=True)
    assert result["tx_power"] == -9 and result["has_pin"] is True
    _, public = await router.handle_request("GET", "/api/config")
    assert public["data"]["pin"] == 0 and public["data"]["has_pin"] is True


@pytest.mark.parametrize("params", [{"tx_power": 12.5}, {"spreading_factor": 7.1}, {"telemetry_mode_base": True}, {"pin": 123456.1}])
async def test_integer_parameters_do_not_silently_truncate(params: dict[str, Any]) -> None:
    router, _admin, mc, _adapter, _physical = station()
    assert (await router.handle_request("POST", "/api/config/radio", params))[0] == 422
    mc.commands.set_tx_power.assert_not_awaited()
    mc.commands.set_radio.assert_not_awaited()


@pytest.mark.parametrize("params", [
    {"repeat": "garbage"}, {"multi_acks": 5}, {"latitude": True},
    {"frequency": 915, "radio_freq": 916}, {"tx_power": 20, "power": 21},
    {"latitude": 10, "lat": 11}, {"coding_rate": "4/5", "cr": 6},
])
async def test_conflicting_aliases_and_invalid_booleans_reject_entire_batch(params: dict[str, Any]) -> None:
    router, _admin, mc, _adapter, _physical = station()
    assert (await router.handle_request("POST", "/api/config/radio", {"name": "After", **params}))[0] == 422
    mc.commands.set_name.assert_not_awaited()


async def test_coordinate_cache_matches_sdk_microdegree_precision() -> None:
    router, _admin, mc, adapter, _physical = station()
    mc.commands.set_coords = AsyncMock(return_value=Event(EventType.OK, {}))
    code, result = await router.handle_request("POST", "/api/config/identity", {"latitude": 12.12345678, "longitude": -73.98765432})
    assert code == 200
    assert result["data"]["applied"] == {"latitude": 12.123456, "longitude": -73.987654}
    assert result["data"]["config"]["latitude"] == adapter.self_info["latitude"] == 12.123456


@pytest.mark.parametrize("params", [
    {"rx_delay": 20.1}, {"rx_dly": 1e20}, {"airtime_factor": 9.1}, {"af": 1e20},
    {"rx_delay": 1, "rx_dly": 2}, {"airtime_factor": 1, "af": 2},
])
async def test_tuning_restart_limits_and_aliases_reject_before_any_write(params: dict[str, Any]) -> None:
    router, _admin, mc, _adapter, _physical = station()
    mc.self_info.update({"rx_delay": 0.5, "airtime_factor": 2.5})
    mc.commands.set_tuning = AsyncMock(return_value=Event(EventType.OK, {}))
    assert (await router.handle_request("POST", "/api/config", {"name": "After", **params}))[0] == 422
    mc.commands.set_name.assert_not_awaited()
    mc.commands.set_tuning.assert_not_awaited()


@pytest.mark.parametrize("rx,af", [(1.23456, 2.34567), (20.0, 9.0)])
async def test_tuning_applied_snapshot_matches_wire_and_reload(rx: float, af: float) -> None:
    router, admin, mc, adapter, _physical = station()
    wire = {"rx_delay": 0, "airtime_factor": 0}

    async def set_tuning(rx_wire: int, af_wire: int) -> Event:
        wire.update(rx_delay=rx_wire, airtime_factor=af_wire)
        return Event(EventType.OK, {})

    mc.commands.set_tuning = AsyncMock(side_effect=set_tuning)
    mc.commands.get_tuning = AsyncMock(side_effect=lambda: Event(EventType.TUNING_PARAMS, dict(wire)))
    code, result = await router.handle_request("POST", "/api/config", {"rx_delay": rx, "airtime_factor": af})
    assert code == 200
    expected = {key: value / 1000.0 for key, value in wire.items()}
    assert result["data"]["applied"] == expected
    assert {key: adapter.self_info[key] for key in expected} == expected
    refreshed = await admin.fetch_device_config(force=True)
    assert {key: refreshed[key] for key in expected} == expected
