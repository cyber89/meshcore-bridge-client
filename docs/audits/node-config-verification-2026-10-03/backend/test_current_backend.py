"""Directed audit reproductions at 9f56193; assertions describe observed defects.

These are diagnostic evidence cases outside tests/, not acceptance tests for the
future fixes. All commands terminate in AsyncMock; fixtures isolate dotenv,
JSON, channels and maps. No
bridge start, physical transport, broker or network request is involved.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from meshcore.events import Event, EventType

with patch("dotenv.load_dotenv", return_value=False):
    import config

from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.repeater_manager import RepeaterManager
from src.web.api_router import WebAPIRouter
from src.web.map_tile_service import MapTileService

LOCAL = "11" * 32
REMOTE = "22" * 32
EVIDENCE = Path(__file__).resolve().parent


@pytest.fixture
def audit_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Same isolation mechanism reviewed in tests/conftest.py, kept self-contained
    # because this diagnostic script must not enter the maintained suite.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    paths = {
        "DATA_DIR": str(tmp_path),
        "NODE_REGISTRY_STORAGE_PATH": str(tmp_path / "nodes.json"),
        "AIRTIME_HISTORY_FILE": str(tmp_path / "airtime.json"),
        "CHANNELS_JSON_PATH": str(tmp_path / "channels.json"),
        "CHANNELS_FILE": str(tmp_path / "channels.json"),
        "LOG_DIR": str(tmp_path / "logs"),
        "LOG_FILE_PATH": str(tmp_path / "logs/bridge.log"),
        "LOG_ERROR_FILE_PATH": str(tmp_path / "logs/error.log"),
    }
    for name, value in paths.items():
        monkeypatch.setattr(config, name, value)
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CHANNELS_STORAGE_PATH", paths["CHANNELS_JSON_PATH"])
    map_init = MapTileService.__init__
    monkeypatch.setattr(MapTileService, "__init__", lambda self, data_dir=None: map_init(self, tmp_path))
    commands = SimpleNamespace(**{
        name: AsyncMock(return_value=Event(EventType.OK, {}))
        for name in (
            "set_name", "set_tx_power", "set_radio", "set_coords",
            "set_devicepin", "set_tuning", "set_path_hash_mode", "set_custom_var",
            "set_other_params_from_infos",
        )
    })
    commands.send_cmd = AsyncMock(return_value=Event(EventType.MSG_SENT, {}))
    commands.send_login_sync = AsyncMock(return_value=Event(
        EventType.LOGIN_SUCCESS, {"is_admin": True, "pubkey_prefix": REMOTE[:12]},
    ))
    mc = SimpleNamespace(
        commands=commands,
        self_info={
            "public_key": LOCAL, "name": "FixtureLocal", "tx_power": 20,
            "radio_freq": 868.0, "bw": 125.0, "sf": 7, "cr": 6,
            "adv_lat": 40.0, "adv_lon": -3.0,
        },
        contacts={REMOTE: {"public_key": REMOTE, "adv_name": "FixtureRepeater", "type": 2}},
    )
    registry = NodeRegistry()
    registry.set_local_pubkey(LOCAL)
    registry.add_or_update(REMOTE, NodeContactUpdate(name="FixtureRepeater", role="REPEATER"))
    mqtt = SimpleNamespace(publish_safe=Mock())
    ctx = AdminContext(
        mc_provider=lambda: mc, node_registry=registry,
        repeater_manager=RepeaterManager(min_cmd_interval_s=0, min_telemetry_interval_s=0),
        mqtt=mqtt, execute_tx=AsyncMock(side_effect=AssertionError("No TX fallback allowed")),
    )
    admin = AdminCommandHandler(ctx)
    # Explicit host cache deliberately differs from device SELF_INFO.
    admin._local_config.update(frequency=915.0, bandwidth=250.0, spreading_factor=11, coding_rate=5)
    bridge = SimpleNamespace(
        admin_handler=admin, handle_admin=admin.handle, node_registry=registry,
        serial_adapter=None, rate_limiter=None, start_time=time.time(),
    )
    router = WebAPIRouter(bridge)
    monkeypatch.setattr("src.admin.repeater_executor.asyncio.sleep", AsyncMock())
    rig = SimpleNamespace(mc=mc, registry=registry, mqtt=mqtt, ctx=ctx, admin=admin, router=router)
    yield rig
    router.map_tile_service.close()
    assert ctx.execute_tx.await_count == 0
    assert not admin._cmd_waiters
    assert not admin._ping_waiters


def record(case: str, *, request: dict, response: object, calls: object = None) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    payload = {"base_head": "9f561932d648470e8c8bd23fc789a66bdb378d0e", "case": case,
               "request": request, "response": response, "sdk_calls": calls}
    (EVIDENCE / f"{case}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8",
    )


@pytest.mark.parametrize("key,value,command", [
    ("name", "VerifiedName", "set_name"), ("tx_power", 22, "set_tx_power"),
    ("frequency", 869.0, "set_radio"), ("bandwidth", 500, "set_radio"),
    ("spreading_factor", 9, "set_radio"), ("coding_rate", 8, "set_radio"),
    ("repeat", True, "set_radio"), ("path_hash_mode", 2, "set_path_hash_mode"),
    ("rx_delay", 0.125, "set_tuning"), ("airtime_factor", 1.5, "set_tuning"),
    ("telemetry_mode_base", 2, "set_other_params_from_infos"),
    ("telemetry_mode_loc", 2, "set_other_params_from_infos"),
    ("telemetry_mode_env", 2, "set_other_params_from_infos"),
    ("adv_loc_policy", 1, "set_other_params_from_infos"),
    ("multi_acks", 1, "set_other_params_from_infos"),
    ("manual_add_contacts", 1, "set_other_params_from_infos"),
    ("custom_vars", {"audit.key": "audit-value"}, "set_custom_var"),
], ids=lambda value: str(value))
async def test_local_positive_dispatch_and_host_read(audit_rig, key, value, command):
    code, response = await audit_rig.router.handle_request("POST", "/api/config", {key: value})
    get_code, readback = await audit_rig.router.handle_request("GET", "/api/config")
    assert code == get_code == 200
    assert response["data"]["applied"][key] == value
    assert getattr(audit_rig.mc.commands, command).await_count == 1
    # GET is a host/SDK snapshot, not independent physical readback.
    record("positive_local_" + key, request={key: value}, response={"post": response, "get": readback},
           calls=str(getattr(audit_rig.mc.commands, command).await_args))


async def test_local_coords_pair_positive(audit_rig):
    request = {"latitude": 41.0, "longitude": -2.0}
    code, response = await audit_rig.router.handle_request("POST", "/api/config/identity", request)
    assert code == 200
    audit_rig.mc.commands.set_coords.assert_awaited_once_with(lat=41.0, lon=-2.0)
    assert response["data"]["config"]["latitude"] == 41.0
    record("positive_local_coords", request=request, response=response)


async def test_current_local_radio_baseline_still_overwrites_self_info(audit_rig):
    code, response = await audit_rig.router.handle_request("POST", "/api/config/radio", {"bandwidth": 500})
    assert code == 200
    audit_rig.mc.commands.set_radio.assert_awaited_once_with(915.0, 500.0, 11, 5, 0)
    record("bug_local_radio_host_baseline", request={"bandwidth": 500}, response=response,
           calls={"device_before": [868, 125, 7, 6], "sdk_set_radio": [915, 500, 11, 5, 0]})


async def test_current_local_memory_only_applied(audit_rig):
    request = {"owner_info": "Synthetic owner", "altitude": 123, "beacon_interval": 600,
               "telemetry_interval": 120, "hop_limit": 4}
    code, response = await audit_rig.router.handle_request("POST", "/api/config", request)
    assert code == 200 and set(request) <= set(response["data"]["applied"])
    assert all(command.await_count == 0 for command in vars(audit_rig.mc.commands).values())
    recreated = AdminCommandHandler(audit_rig.ctx).get_local_config()
    assert recreated["beacon_interval"] == 300 and recreated["telemetry_interval"] == 60
    record("bug_local_memory_only", request=request, response={"post": response, "new_handler": recreated})


async def test_current_local_single_coordinate_errors_despite_self_info_pair(audit_rig):
    code, response = await audit_rig.router.handle_request("POST", "/api/config", {"latitude": 41})
    assert code == 400
    audit_rig.mc.commands.set_coords.assert_not_awaited()
    record("bug_local_single_coord_baseline", request={"latitude": 41}, response=response,
           calls={"device_known_longitude": -3})


async def test_fixed_local_path_hash_prevalidates_before_name(audit_rig):
    code, response = await audit_rig.router.handle_request("POST", "/api/config", {"name": "Rejected", "path_hash_mode": 3})
    assert code == 400
    audit_rig.mc.commands.set_name.assert_not_awaited()
    record("fixed_local_prevalidation_path_hash", request={"name": "Rejected", "path_hash_mode": 3}, response=response)


async def test_current_local_late_validation_still_partially_applies(audit_rig):
    code, response = await audit_rig.router.handle_request("POST", "/api/config", {"name": "AlreadyChanged", "tx_power": "invalid"})
    assert code == 400 and response["partial"] is True
    assert response["applied"] == {"name": "AlreadyChanged"}
    audit_rig.mc.commands.set_name.assert_awaited_once()
    record("bug_local_partial_validation", request={"name": "AlreadyChanged", "tx_power": "invalid"}, response=response)


@pytest.mark.parametrize("reply", [False, Event(EventType.DISABLED, {}), Event(EventType.ERROR, {})], ids=["False", "DISABLED", "ERROR"])
async def test_fixed_local_failed_sdk_replies_rejected(audit_rig, reply):
    audit_rig.mc.commands.set_name.return_value = reply
    code, response = await audit_rig.router.handle_request("POST", "/api/config", {"name": "Rejected"})
    assert code == 400 and audit_rig.admin.get_local_config()["name"] == "FixtureLocal"
    record("fixed_local_reply_" + ("False" if reply is False else reply.type.name), request={"name": "Rejected"}, response=response)


async def test_current_pin_redacted_write_but_leaked_get(audit_rig):
    code, response = await audit_rig.router.handle_request("POST", "/api/config", {"pin": 123456})
    get_code, readback = await audit_rig.router.handle_request("GET", "/api/config")
    published = json.loads(audit_rig.mqtt.publish_safe.call_args.args[1])
    assert code == get_code == 200
    assert "123456" not in json.dumps(response) and "123456" not in json.dumps(published)
    assert readback["data"]["pin"] == 123456
    record("bug_pin_get_leak", request={"pin": "synthetic 123456"}, response={"post": response, "get": readback, "mqtt": published})


async def test_current_refresh_connected_all_queries_fail_falsely_fresh(audit_rig):
    code, response = await audit_rig.router.handle_request("GET", "/api/config?refresh=true")
    assert code == 200 and response["data"]["stale"] is False and response["data"]["cached"] is False
    assert "refresh_error" not in response["data"]
    record("bug_refresh_queries_unavailable_fresh", request={"refresh": True}, response=response)


async def test_fixed_refresh_offline_reports_stale(audit_rig):
    audit_rig.ctx.mc_provider = lambda: None
    code, response = await audit_rig.router.handle_request("GET", "/api/config?refresh=true")
    assert code == 200 and response["data"]["stale"] is True and "refresh_error" in response["data"]
    record("fixed_refresh_offline_stale", request={"refresh": True}, response=response)


@pytest.mark.parametrize("key,value", [("bogus_setting", 42), ("tx_power", "invalid"), ("bandwidth", 500)])
async def test_fixed_remote_prevalidation_no_dispatch(audit_rig, key, value):
    request = {"target_node": REMOTE, "params": {"name": "NoChange", key: value}}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", request)
    assert code == 400
    audit_rig.mc.commands.send_cmd.assert_not_awaited()
    record("fixed_remote_prevalidation_" + key, request=request, response=response)


@pytest.mark.parametrize("target", ["FixtureClient", "33" * 32, "FixtureLocal", LOCAL])
async def test_fixed_remote_client_and_local_guards(audit_rig, target):
    client = "33" * 32
    audit_rig.registry.add_or_update(client, NodeContactUpdate(name="FixtureClient", role="CLIENT"))
    audit_rig.registry.add_or_update(LOCAL, NodeContactUpdate(name="FixtureLocal", role="LOCAL", is_local=True))
    audit_rig.mc.contacts[client] = {"public_key": client, "adv_name": "FixtureClient", "type": 1}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", {"target_node": target, "params": {"name": "NoChange"}})
    assert code == 400
    audit_rig.mc.commands.send_cmd.assert_not_awaited()
    record("fixed_role_" + target, request={"target_node": target}, response=response)


@pytest.mark.parametrize("key,value,expected", [
    ("name", "NewRemote", "set name NewRemote"), ("tx_power", 22, "set tx 22"),
    ("repeat", True, "set repeat on"), ("owner_info", "Synthetic owner", "set owner.info Synthetic owner"),
    ("lat", 41, "set lat 41.000000"), ("lon", -2, "set lon -2.000000"),
    ("advert_interval", 120, "set advert.interval 120"),
    ("flood_advert_interval", 6, "set flood.advert.interval 6"),
    ("admin_password", "SYNTHETIC_PWD", "password SYNTHETIC_PWD"),
])
async def test_remote_positive_dispatch(audit_rig, key, value, expected):
    request = {"target_node": REMOTE, "params": {key: value}}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", request)
    assert code == 200 and response["data"]["status"] == "dispatched"
    audit_rig.mc.commands.send_cmd.assert_awaited_once_with(audit_rig.mc.contacts[REMOTE], expected)
    if key == "admin_password":
        assert value not in json.dumps(response)
    record("positive_remote_" + key, request=request, response=response, calls=[expected])


async def test_remote_full_radio_positive_pending_reboot(audit_rig):
    request = {"target_node": REMOTE, "params": {"frequency": 868, "bandwidth": 125, "spreading_factor": 7, "coding_rate": 6}}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", request)
    assert code == 200 and response["data"]["pending_reboot"] is True
    audit_rig.mc.commands.send_cmd.assert_awaited_once_with(audit_rig.mc.contacts[REMOTE], "set radio 868.0,125.0,7,6")
    record("positive_remote_radio", request=request, response=response)


@pytest.mark.parametrize("key,value", [("latitude", 41), ("longitude", -2), ("beacon_interval", 120), ("repeat_enabled", True), ("guest_password", "SYNTHETIC_GUEST"), ("public_key", "44" * 32), ("permission", 3), ("region", "EU")])
async def test_current_remote_allowed_fields_silently_ignored(audit_rig, key, value):
    request = {"target_node": REMOTE, "params": {key: value}}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", request)
    assert code == 200 and response["data"]["dispatched_commands"] == []
    audit_rig.mc.commands.send_cmd.assert_not_awaited()
    record("bug_remote_allowed_ignored_" + key, request=request, response=response)


async def test_current_remote_invalid_cr_silently_defaults_five(audit_rig):
    request = {"target_node": REMOTE, "params": {"frequency": 868, "bandwidth": 125, "spreading_factor": 7, "coding_rate": 99}}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", request)
    assert code == 200 and response["data"]["dispatched_commands"] == ["set radio 868.0,125.0,7,5"]
    record("bug_remote_cr_defaults", request=request, response=response)


async def test_current_remote_late_builder_failure_partial_http_ok(audit_rig):
    request = {"target_node": REMOTE, "params": {"name": "AlreadyChanged", "lat": "invalid"}}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", request)
    assert code == 200 and response["status"] == "ok" and response["data"]["status"] == "partial"
    assert response["data"]["dispatched_commands"] == ["set name AlreadyChanged"]
    record("bug_remote_partial_http_ok", request=request, response=response)


async def test_current_remote_login_spaces_trimmed_and_guest_rejected(audit_rig):
    request = {"target_node": REMOTE, "password": " synthetic "}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/login", request)
    assert code == 200 and audit_rig.mc.commands.send_login_sync.await_args.args[1] == "synthetic"
    audit_rig.mc.commands.send_login_sync.return_value = Event(EventType.LOGIN_SUCCESS, {"is_admin": False, "pubkey_prefix": REMOTE[:12]})
    denied_code, denied_response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/login", request)
    assert denied_code == 401
    record("bug_login_spaces_guest_control", request=request, response={"admin": response, "guest": denied_response})


@pytest.mark.parametrize("route,payload,command", [
    ("autoadd", {"flags": 15}, "set_autoadd_config"),
    ("path_hash_mode", {"mode": 2}, "set_path_hash_mode"),
    ("flood_scope", {"scope": "AuditScope"}, "set_default_flood_scope"),
    ("custom_vars", {"key": "audit.key", "value": "audit-value"}, "set_custom_var"),
])
async def test_dedicated_positive_set_get(audit_rig, route, payload, command):
    setattr(audit_rig.mc.commands, command, AsyncMock(return_value=Event(EventType.OK, {})))
    code, response = await audit_rig.router.handle_request("POST", "/api/config/" + route, payload)
    get_code, readback = await audit_rig.router.handle_request("GET", "/api/config/" + route)
    assert code == get_code == 200
    assert getattr(audit_rig.mc.commands, command).await_count == 1
    record("positive_dedicated_" + route, request=payload, response={"post": response, "get": readback}, calls=str(getattr(audit_rig.mc.commands, command).await_args))


async def test_current_autoadd_max_hops_rejected(audit_rig):
    audit_rig.mc.commands.set_autoadd_config = AsyncMock(return_value=Event(EventType.OK, {}))
    request = {"flags": 15, "max_hops": 1}
    code, response = await audit_rig.router.handle_request("POST", "/api/config/autoadd", request)
    assert code == 500
    audit_rig.mc.commands.set_autoadd_config.assert_not_awaited()
    record("bug_autoadd_max_hops", request=request, response=response)


async def test_current_tuning_inconsistent_domain_read_after_success(audit_rig):
    audit_rig.mc.self_info.update(rx_delay=0.2, airtime_factor=1.0)
    request = {"rx_delay": 0.125, "airtime_factor": 1.5}
    code, response = await audit_rig.router.handle_request("POST", "/api/config", request)
    assert code == 200
    audit_rig.mc.commands.set_tuning.assert_awaited_once_with(125, 1500)
    assert response["data"]["applied"]["rx_delay"] == 0.125 and response["data"]["config"]["rx_delay"] == 0.2
    record("bug_tuning_stale_self_info", request=request, response=response)


async def test_positive_refresh_with_sdk_payloads(audit_rig):
    reads = {
        "send_appstart": (EventType.SELF_INFO, dict(audit_rig.mc.self_info)),
        "send_device_query": (EventType.DEVICE_INFO, {"model": "audit", "ver": 1, "fw_ver": "synthetic", "hardware_board": "Heltec V3"}),
        "get_bat": (EventType.BATTERY, {"level": 4100}),
        "get_tuning": (EventType.TUNING_PARAMS, {"rx_delay": 125, "airtime_factor": 1500}),
        "get_time": (EventType.OK, {"time": int(time.time())}),
        "get_stats_core": (EventType.OK, {"uptime_secs": 900}),
        "get_stats_radio": (EventType.OK, {"noise_floor": -111}),
        "get_stats_packets": (EventType.OK, {"sent": 2, "recv": 3}),
        "get_self_telemetry": (EventType.OK, {"temperature_c": 24}),
        "get_custom_vars": (EventType.CUSTOM_VARS, {"audit.key": "value"}),
        "get_allowed_repeat_freq": (EventType.OK, {"allowed_freqs": [868]}),
    }
    for command, (event_type, payload) in reads.items():
        setattr(audit_rig.mc.commands, command, AsyncMock(return_value=Event(event_type, payload)))
    code, response = await audit_rig.router.handle_request("GET", "/api/config?refresh=true")
    assert code == 200 and response["data"]["stale"] is False
    assert response["data"]["temperature_c"] == 24 and response["data"]["rx_delay"] == 0.125
    assert all(getattr(audit_rig.mc.commands, command).await_count == 1 for command in reads)
    record("positive_refresh_payloads", request={"refresh": True}, response=response, calls=list(reads))


async def test_positive_clock_set_and_host_read(audit_rig):
    audit_rig.mc.commands.set_time = AsyncMock(return_value=Event(EventType.OK, {}))
    request = {"epoch": 1791060000}
    code, response = await audit_rig.router.handle_request("POST", "/api/config/sync-clock", request)
    get_code, readback = await audit_rig.router.handle_request("GET", "/api/config")
    assert code == get_code == 200 and response["data"]["epoch"] == request["epoch"]
    assert abs(readback["data"]["device_epoch_time"] - request["epoch"]) <= 1
    record("positive_clock_host_read", request=request, response={"post": response, "get": readback})


async def test_current_local_unknown_parameter_ignored_success(audit_rig):
    request = {"bogus_setting": 42}
    code, response = await audit_rig.router.handle_request("POST", "/api/config", request)
    assert code == 200 and response["data"]["applied"] == {}
    record("bug_local_unknown_ignored", request=request, response=response)


async def test_current_local_invalid_cr_sent(audit_rig):
    request = {"coding_rate": 99}
    code, response = await audit_rig.router.handle_request("POST", "/api/config/radio", request)
    assert code == 200
    assert audit_rig.mc.commands.set_radio.await_args.args[3] == 99
    record("bug_local_cr_not_prevalidated", request=request, response=response, calls=str(audit_rig.mc.commands.set_radio.await_args))


async def test_current_sdk_unknown_event_accepted(audit_rig):
    audit_rig.mc.commands.set_name.return_value = Event(EventType.SELF_INFO, {})
    request = {"name": "WrongResponseType"}
    code, response = await audit_rig.router.handle_request("POST", "/api/config", request)
    assert code == 200 and response["data"]["applied"]["name"] == request["name"]
    record("bug_sdk_positive_allowlist_missing", request=request, response=response)


async def test_current_custom_batch_partial_hidden(audit_rig):
    audit_rig.mc.commands.set_custom_var.side_effect = [Event(EventType.OK, {}), Event(EventType.ERROR, {})]
    request = {"vars": {"first": "saved", "second": "rejected"}}
    code, response = await audit_rig.router.handle_request("POST", "/api/config/custom_vars", request)
    assert code == 500 and audit_rig.admin._local_config["custom_vars"] == {"first": "saved"}
    assert "partial" not in response and "applied" not in response
    record("bug_custom_vars_partial_hidden", request=request, response=response)


async def test_positive_dedicated_reads_with_payloads(audit_rig):
    audit_rig.mc.commands.get_autoadd_config = AsyncMock(return_value=Event(EventType.AUTOADD_CONFIG, {"config": 15, "max_hops": 3}))
    audit_rig.mc.commands.get_default_flood_scope = AsyncMock(return_value=Event(EventType.DEFAULT_FLOOD_SCOPE, {"scope_name": "AuditScope"}))
    audit_rig.mc.commands.get_custom_vars = AsyncMock(return_value=Event(EventType.CUSTOM_VARS, {"audit.key": "value"}))
    output = {}
    for route in ("autoadd", "flood_scope", "custom_vars"):
        code, response = await audit_rig.router.handle_request("GET", "/api/config/" + route)
        assert code == 200
        output[route] = response
    assert output["autoadd"]["data"]["max_hops"] == 3
    assert output["flood_scope"]["data"]["scope_name"] == "AuditScope"
    assert output["custom_vars"]["data"]["audit.key"] == "value"
    record("positive_dedicated_reads_payloads", request={}, response=output)


async def test_current_local_default_string_cr_breaks_patch(audit_rig):
    fresh = AdminCommandHandler(audit_rig.ctx)
    assert fresh._local_config["coding_rate"] == "4/5"
    result = await fresh.handle({"action": "set_local_config", "params": {"bandwidth": 125}})
    assert result["status"] == "error" and "4/5" in result["message"]
    audit_rig.mc.commands.set_radio.assert_not_awaited()
    record("bug_local_default_cr_string", request={"bandwidth": 125}, response=result,
           calls={"self_info_cr": 6, "host_default_cr": "4/5"})





