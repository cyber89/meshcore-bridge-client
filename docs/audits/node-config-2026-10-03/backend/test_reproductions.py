"""Directed audit reproductions at 81f4260; assertions describe observed defects.

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
    payload = {"base_head": "81f4260eccf9bdec6c6f7ba9caca5322997f6eeb", "case": case,
               "request": request, "response": response, "sdk_calls": calls}
    (EVIDENCE / f"{case}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8",
    )


async def test_reproduce_local_tx_power_readback_stale(audit_rig):
    request = {"tx_power": 22}
    code, response = await audit_rig.router.handle_request("POST", "/api/node/config", request)
    get_code, readback = await audit_rig.router.handle_request("GET", "/api/node/config")
    audit_rig.mc.commands.set_tx_power.assert_awaited_once_with(22)
    assert code == get_code == 200
    assert response["data"]["applied"]["tx_power"] == 22
    assert response["data"]["config"]["tx_power"] == readback["data"]["tx_power"] == 20
    record("local_tx_readback_stale", request=request, response={"post": response, "get": readback}, calls=[22])


async def test_reproduce_local_radio_patch_overwrites_untouched_device_values(audit_rig):
    request = {"bandwidth": 500}
    code, response = await audit_rig.router.handle_request("POST", "/api/config/radio", request)
    assert code == 200
    audit_rig.mc.commands.set_radio.assert_awaited_once_with(915.0, 500.0, 11, 5, 0)
    assert response["data"]["config"]["frequency"] == 915.0  # device was 868 MHz
    record("local_radio_patch_defaults", request=request, response=response,
           calls={"device_before": {"freq": 868, "sf": 7, "cr": 6}, "set_radio": [915, 500, 11, 5, 0]})


async def test_reproduce_local_memory_only_parameters_report_applied(audit_rig):
    request = {"owner_info": "Synthetic owner", "altitude": 123, "beacon_interval": 600,
               "telemetry_interval": 120, "hop_limit": 4}
    code, response = await audit_rig.router.handle_request("POST", "/api/node/config", request)
    assert code == 200
    assert set(request) <= set(response["data"]["applied"])
    assert all(cmd.await_count == 0 for cmd in vars(audit_rig.mc.commands).values())
    recreated = AdminCommandHandler(audit_rig.ctx).get_local_config()
    assert recreated["beacon_interval"] == 300
    assert recreated["telemetry_interval"] == 60
    assert "owner_info" not in recreated or recreated["owner_info"] != "Synthetic owner"
    record("local_memory_only_applied", request=request, response={"post": response, "new_handler": recreated}, calls=[])


async def test_reproduce_local_single_coordinate_silently_ignored(audit_rig):
    request = {"latitude": 41.0}
    code, response = await audit_rig.router.handle_request("POST", "/api/config/identity", request)
    assert code == 200 and response["data"]["applied"] == {}
    assert response["data"]["config"]["latitude"] == 40.0
    audit_rig.mc.commands.set_coords.assert_not_awaited()
    record("local_coordinate_ignored", request=request, response=response, calls=[])


async def test_reproduce_local_partial_mutation_http_loses_applied_detail(audit_rig):
    request = {"name": "AlreadyChanged", "path_hash_mode": 3}
    code, response = await audit_rig.router.handle_request("POST", "/api/node/config", request)
    assert code == 503
    assert "applied" not in response and "data" not in response
    audit_rig.mc.commands.set_name.assert_awaited_once_with("AlreadyChanged")
    assert audit_rig.admin.get_local_config()["name"] == "AlreadyChanged"
    internal = json.loads(audit_rig.mqtt.publish_safe.call_args.args[1])
    assert internal["status"] == "partial" and internal["applied"] == {"name": "AlreadyChanged"}
    record("local_partial_hidden", request=request, response={"http": response, "internal": internal}, calls=["set_name AlreadyChanged"])


@pytest.mark.parametrize("reply", [False, Event(EventType.DISABLED, {})], ids=["false", "disabled"])
async def test_reproduce_non_success_sdk_response_accepted(audit_rig, reply):
    audit_rig.mc.commands.set_name.return_value = reply
    request = {"name": "UnconfirmedName"}
    code, response = await audit_rig.router.handle_request("POST", "/api/config/identity", request)
    assert code == 200 and response["data"]["applied"]["name"] == "UnconfirmedName"
    record(f"local_false_success_{'false' if reply is False else 'disabled'}", request=request, response=response,
           calls={"set_name_result": str(reply)})


async def test_control_sdk_error_blocks_local_cache_mutation(audit_rig):
    audit_rig.mc.commands.set_name.return_value = Event(EventType.ERROR, {"error_code": 1})
    code, response = await audit_rig.router.handle_request("POST", "/api/config/identity", {"name": "Rejected"})
    assert code == 400
    assert audit_rig.admin.get_local_config()["name"] == "FixtureLocal"
    record("control_sdk_error_rejected", request={"name": "Rejected"}, response=response)


async def test_reproduce_local_pin_exposed_in_status_mqtt(audit_rig):
    request = {"pin": 123456}  # synthetic credential, never an operator secret
    code, response = await audit_rig.router.handle_request("POST", "/api/node/config", request)
    assert code == 200
    published = json.loads(audit_rig.mqtt.publish_safe.call_args.args[1])
    assert published["applied"]["pin"] == published["config"]["pin"] == 123456
    record("local_pin_status_secret", request=request, response=published, calls=["set_devicepin synthetic PIN"])


async def test_reproduce_remote_password_exposed_in_batch_result_and_mqtt(audit_rig):
    request = {"target_node": REMOTE, "params": {"admin_password": "SYNTHETIC_PWD"}}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", request)
    assert code == 200 and response["data"]["status"] == "dispatched"
    expected = "set admin.password SYNTHETIC_PWD"
    audit_rig.mc.commands.send_cmd.assert_awaited_once_with(audit_rig.mc.contacts[REMOTE], expected)
    assert response["data"]["dispatched_commands"] == [expected]
    published = json.loads(audit_rig.mqtt.publish_safe.call_args.args[1])
    assert expected in published["dispatched_commands"]
    record("remote_batch_secret", request=request, response={"http": response, "mqtt": published}, calls=[expected])


async def test_reproduce_remote_batch_unknown_parameter_dispatched(audit_rig):
    request = {"target_node": REMOTE, "params": {"bogus_setting": 42}}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", request)
    assert code == 200
    assert response["data"]["dispatched_commands"] == ["set_bogus_setting"]
    record("remote_unknown_dispatched", request=request, response=response, calls=["set_bogus_setting"])


async def test_reproduce_remote_batch_invalid_later_parameter_after_dispatch(audit_rig):
    request = {"target_node": REMOTE, "params": {"name": "ChangedFirst", "tx_power": "invalid"}}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", request)
    assert code == 400
    audit_rig.mc.commands.send_cmd.assert_awaited_once_with(audit_rig.mc.contacts[REMOTE], "set name ChangedFirst")
    assert "dispatched_commands" not in response["data"]
    record("remote_partial_hidden", request=request, response=response, calls=["set name ChangedFirst"])


@pytest.mark.parametrize("registry_present", [True, False], ids=["null_fields", "absent_registry"])
async def test_reproduce_remote_radio_patch_uses_defaults_without_readback(audit_rig, registry_present):
    if not registry_present:
        audit_rig.registry._nodes_by_key.pop(REMOTE)
    request = {"target_node": REMOTE, "params": {"bandwidth": 500}}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", request)
    assert code == 200
    expected = "set radio None,500,None,5" if registry_present else "set radio 915.0,500,11,5"
    assert response["data"]["dispatched_commands"] == [expected]
    record(f"remote_radio_patch_{'null_fields' if registry_present else 'defaults'}",
           request=request, response=response, calls=[expected])


async def test_reproduce_remote_name_bypasses_client_role_guard(audit_rig):
    client = "33" * 32
    audit_rig.registry.add_or_update(client, NodeContactUpdate(name="FixtureClient", role="CLIENT"))
    audit_rig.mc.contacts[client] = {"public_key": client, "adv_name": "FixtureClient", "type": 1}
    request = {"target_node": "FixtureClient", "params": {"name": "ClientChanged"}}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", request)
    assert code == 200
    audit_rig.mc.commands.send_cmd.assert_awaited_once_with(audit_rig.mc.contacts[client], "set name ClientChanged")
    record("remote_client_alias_guard", request=request, response=response, calls=["send_cmd CLIENT"])


async def test_control_remote_client_pubkey_rejected(audit_rig):
    client = "33" * 32
    audit_rig.registry.add_or_update(client, NodeContactUpdate(name="FixtureClient", role="CLIENT"))
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/config", {"target_node": client, "params": {"name": "NoChange"}})
    assert code == 400
    audit_rig.mc.commands.send_cmd.assert_not_awaited()
    record("control_client_key_rejected", request={"target_node": client}, response=response, calls=[])


async def test_reproduce_remote_login_changes_password_whitespace(audit_rig):
    request = {"target_node": REMOTE, "password": " synthetic "}
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/login", request)
    assert code == 200
    assert audit_rig.mc.commands.send_login_sync.await_args.args[1] == "synthetic"
    record("remote_login_password_trimmed", request=request, response=response, calls={"sdk_password": "synthetic"})


async def test_control_remote_login_wrong_sender_rejected(audit_rig):
    audit_rig.mc.commands.send_login_sync.return_value = Event(EventType.LOGIN_SUCCESS,
        {"is_admin": True, "pubkey_prefix": "ff" * 6})
    code, response = await audit_rig.router.handle_request("POST", "/api/repeater/remote/login", {"target_node": REMOTE, "password": "synthetic"})
    assert code == 401
    record("control_login_wrong_sender", request={"target_node": REMOTE}, response=response)


async def test_reproduce_refresh_disconnected_still_returns_cached_success(audit_rig):
    audit_rig.ctx.mc_provider = lambda: None
    code, response = await audit_rig.router.handle_request("GET", "/api/node/config?refresh=true")
    assert code == 200 and response["data"]["frequency"] == 915.0
    assert response["data"]["radio_connected"] is False
    assert "refresh_error" not in response["data"] and "config_stale" not in response["data"]
    record("local_refresh_offline_cached", request={"refresh": True}, response=response, calls=[])
