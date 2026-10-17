"""Only authenticated web administration of identified infrastructure skips pauses."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from meshcore.events import Event, EventType

from src.admin_handler import AdminCommandHandler, AdminContext
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.repeater_manager import RepeaterManager
from src.station_database import StationDatabase
from src.web.api_router import WebAPIRouter
from src.web.asgi_server import create_asgi_app
from src.web.controllers.base import ApiContext
from src.web.controllers.repeater_controller import RepeaterController

LOCAL = "ab" * 32
REMOTE = "cd" * 32


@dataclass
class RemoteStation:
    admin: AdminCommandHandler
    manager: RepeaterManager
    controller: RepeaterController
    sent: list[tuple[str, Any]]


def station(tmp_path: Path, role: str = "REPEATER") -> RemoteStation:
    registry = NodeRegistry()
    registry.set_local_pubkey(LOCAL)
    if role != "UNKNOWN":
        registry.add_or_update(REMOTE, NodeContactUpdate(name="Remote", alias="remote-alias", role=role))
    manager = RepeaterManager(storage_path=tmp_path / "cooldowns.json")
    sent: list[tuple[str, Any]] = []

    async def send_cmd(destination: Any, command: str) -> Event:
        sent.append((command, destination))
        return Event(EventType.MSG_SENT, {})

    async def add_contact(contact: dict[str, Any]) -> Event:
        return Event(EventType.OK, {})

    async def status(destination: Any, **kwargs: Any) -> dict[str, Any]:
        sent.append(("req_status", destination))
        return {"bat": 4100}

    async def neighbours(destination: Any, **kwargs: Any) -> dict[str, Any]:
        sent.append(("req_neighbours", destination))
        return {"neighbours_count": 0, "results_count": 0, "neighbours": []}

    async def trace(**kwargs: Any) -> Event:
        sent.append(("send_trace", kwargs))
        return Event(EventType.MSG_SENT, {})

    async def trace_reply(*args: Any, **kwargs: Any) -> Event:
        return Event(EventType.TRACE_DATA, {"path": []})

    contacts = {} if role == "UNKNOWN" else {
        REMOTE: {"public_key": REMOTE, "type": {"REPEATER": 2, "ROOM": 3}.get(role, 1), "adv_name": "Remote", "out_path_len": 0},
    }
    sdk = SimpleNamespace(
        self_info={"public_key": LOCAL}, contacts=contacts,
        commands=SimpleNamespace(send_cmd=send_cmd, add_contact=add_contact, req_status_sync=status,
                                 req_neighbours_sync=neighbours, send_trace=trace),
        dispatcher=SimpleNamespace(wait_for_event=trace_reply),
    )
    admin = AdminCommandHandler(AdminContext(lambda: sdk, registry, manager, MagicMock(), MagicMock()))

    async def reply(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"text": "OK", "snr": 7, "rssi": -80}

    admin._repeater_executor._wait_for_repeater_response = reply
    bridge = SimpleNamespace(handle_admin=admin.handle, admin_handler=admin)
    controller = RepeaterController(ApiContext(bridge, deque(), deque(), lambda *args, **kwargs: None))
    return RemoteStation(admin, manager, controller, sent)


@pytest.mark.parametrize("role", ["REPEATER", "ROOM"])
@pytest.mark.parametrize("action,params,category", [
    ("set_name", {"name": "New remote"}, "command"),
    ("remote_repeater_set_config", {"name": "New remote"}, "telemetry"),
    ("req_status", {}, "command"),
    ("req_neighbours", {}, "neighbours"),
    ("ping_zero", {}, "ping"),
    ("traceroute", {}, "traceroute"),
])
async def test_two_manual_infrastructure_actions_have_no_minimum_pause_but_persist(
    tmp_path: Path, role: str, action: str, params: dict[str, Any], category: str,
) -> None:
    remote = station(tmp_path, role)
    body = {"target_node": REMOTE, "action": action, "params": params}
    first_code, _ = await remote.controller.execute_admin_command(body)
    assert first_code == 200
    second_code, second = await remote.controller.execute_admin_command(body)
    assert second_code == 200, second
    assert len(remote.sent) == 2
    # A separate process/domain instance still protects automated operations.
    restored = RepeaterManager(storage_path=tmp_path / "cooldowns.json")
    await restored.load_state()
    checks: dict[str, Callable[[str], tuple[bool, float]]] = {"command": restored.check_airtime_cooldown,
             "telemetry": lambda key: restored.check_airtime_cooldown(key, is_full_query=True),
             "ping": restored.check_ping_cooldown, "neighbours": restored.check_neighbours_cooldown,
             "traceroute": restored.check_traceroute_cooldown}
    assert checks[category](REMOTE)[0] is False


@pytest.mark.parametrize("untrusted", [{"manual": True}, {"source": "web"}, {"origin": "manual"}])
async def test_payload_cannot_remove_automatic_cooldown(tmp_path: Path, untrusted: dict[str, Any]) -> None:
    remote = station(tmp_path)
    payload = {"target_node": REMOTE, "action": "set_name", "name": "Changed", **untrusted}
    assert (await remote.admin.handle(payload))["status"] == "ok"
    assert (await remote.admin.handle(payload))["code"] == 429
    assert len(remote.sent) == 1


@pytest.mark.parametrize("role", ["CLIENT", "UNKNOWN"])
async def test_web_client_and_unknown_diagnostics_keep_pause(tmp_path: Path, role: str) -> None:
    remote = station(tmp_path, role)
    payload = {"target_node": REMOTE, "action": "ping_zero"}
    assert (await remote.controller.execute_admin_command(payload))[0] == 200
    assert (await remote.controller.execute_admin_command(payload))[0] == 429
    assert len(remote.sent) == 1


async def test_manual_room_guard_still_rejects_repeat_before_any_send(tmp_path: Path) -> None:
    remote = station(tmp_path, "ROOM")
    code, body = await remote.controller.execute_admin_command({
        "target_node": REMOTE, "action": "set_repeat", "repeat": True,
    })
    assert code == 422
    assert body["data"]["reason"] == "room_repeat_unsupported"
    assert remote.sent == []


async def test_manual_local_trace_cannot_acquire_remote_pause_exception(tmp_path: Path) -> None:
    remote = station(tmp_path)
    sdk = remote.admin._ctx.mc_provider()
    sdk.contacts[LOCAL] = {"public_key": LOCAL, "type": 2, "adv_name": "Local"}
    remote.manager.record_traceroute_sent(LOCAL)
    code, _ = await remote.controller.execute_admin_command({"target_node": LOCAL, "action": "traceroute"})
    assert code == 429
    assert remote.sent == []


@pytest.mark.parametrize("local_alias", ["local", "000000000000"])
async def test_local_configuration_alias_still_uses_local_handler(tmp_path: Path, local_alias: str) -> None:
    remote = station(tmp_path)
    code, body = await remote.controller.execute_admin_command({"target_node": local_alias, "action": "get_config"})
    assert code == 200, body
    assert "config" in body["result"]
    assert remote.sent == []


async def test_manual_trace_path_is_frozen_before_async_state_loading(tmp_path: Path) -> None:
    remote = station(tmp_path)
    registry = remote.admin._ctx.node_registry
    registry.add_or_update(REMOTE, NodeContactUpdate(out_path="11", out_path_len=1))
    original_load = remote.manager.load_state

    async def load_and_refresh_path() -> None:
        await original_load()
        registry.add_or_update(REMOTE, NodeContactUpdate(out_path="22", out_path_len=1))

    remote.manager.load_state = load_and_refresh_path  # type: ignore[method-assign]
    code, body = await remote.controller.execute_admin_command({"target_node": REMOTE, "action": "traceroute"})
    assert code == 200, body
    assert remote.sent[0][1]["path"] == "11"


async def test_conflicting_client_registry_cannot_borrow_sdk_repeater_pause_exception(tmp_path: Path) -> None:
    remote = station(tmp_path, "CLIENT")
    remote.admin._ctx.mc_provider().contacts[REMOTE]["type"] = 2
    remote.manager.record_ping_sent(REMOTE)
    code, _ = await remote.controller.execute_admin_command({"target_node": REMOTE, "action": "ping_zero"})
    assert code == 429
    assert remote.sent == []


async def test_ambiguous_registry_alias_cannot_borrow_one_sdk_contact(tmp_path: Path) -> None:
    remote = station(tmp_path)
    other = "ef" * 32
    remote.admin._ctx.node_registry.add_or_update(other, NodeContactUpdate(name="Other", alias="remote-alias", role="ROOM"))
    remote.admin._ctx.mc_provider().contacts[REMOTE]["adv_name"] = "remote-alias"
    code, _ = await remote.controller.execute_admin_command({"target_node": "remote-alias", "action": "set_name", "name": "Changed"})
    assert code == 422
    assert remote.sent == []


@pytest.mark.parametrize("contact_shape", ["mapping", "object"])
async def test_manual_destination_is_frozen_before_async_persistence(tmp_path: Path, contact_shape: str) -> None:
    remote = station(tmp_path)
    sdk = remote.admin._ctx.mc_provider()
    sdk.contacts[REMOTE]["adv_name"] = "remote-alias"
    if contact_shape == "object":
        sdk.contacts[REMOTE] = SimpleNamespace(**sdk.contacts[REMOTE])
    original_flush = remote.manager.flush_state

    async def flush_and_refresh_contact_book() -> None:
        await original_flush()
        if contact_shape == "mapping":
            sdk.contacts[REMOTE]["public_key"] = "ef" * 32
        else:
            sdk.contacts[REMOTE].public_key = "ef" * 32

    remote.manager.flush_state = flush_and_refresh_contact_book  # type: ignore[method-assign]
    code, body = await remote.controller.execute_admin_command({"target_node": "remote-alias", "action": "set_name", "name": "Changed"})
    assert code == 200, body
    destination = remote.sent[0][1]
    assert (destination["public_key"] if isinstance(destination, dict) else destination.public_key) == REMOTE
    assert remote.manager.check_airtime_cooldown("remote-alias")[0] is False


async def test_real_http_authentication_and_csrf_gate_manual_pause_exception(tmp_path: Path) -> None:
    remote = station(tmp_path)
    database = StationDatabase(tmp_path / "station.sqlite3")
    await asyncio.to_thread(database.initialize)
    bridge = remote.controller.ctx.bridge
    bridge.database, bridge.start_time = database, time.time()
    router = WebAPIRouter(bridge)
    app = create_asgi_app(router, shutdown_budget_s=1)
    store = app.state.authentication.store
    await asyncio.to_thread(store.initialize)
    await asyncio.to_thread(store.bootstrap, "qa-owner", "isolated remote password")
    body = {"target_node": REMOTE, "action": "set_name", "params": {"name": "Manual"}}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            anonymous = await client.post("/api/admin/repeater", json=body, headers={"Origin": "http://localhost"})
            assert anonymous.status_code == 401
            login = await client.post("/api/auth/login", json={"username": "qa-owner", "password": "isolated remote password"}, headers={"Origin": "http://localhost"})
            assert login.status_code == 200
            assert (await client.post("/api/admin/repeater", json=body, headers={"Origin": "http://localhost"})).status_code == 403
            assert remote.sent == []
            headers = {"Origin": "http://localhost", "X-CSRF-Token": login.json()["csrf_token"]}
            assert (await client.post("/api/admin/repeater", json=body, headers=headers)).status_code == 200
            second = await client.post("/api/admin/repeater", json=body, headers=headers)
            assert second.status_code == 200, second.text
            assert len(remote.sent) == 2
    finally:
        router.cancel_notifications()
        await asyncio.gather(*router.owned_notification_tasks(), return_exceptions=True)
        router.map_tile_service.close()
