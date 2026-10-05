"""Administrative boundaries use typed registry data and reject absent commands."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from meshcore import EventType
from meshcore.events import Event

from src.admin import (
    LocalConfigExecutor,
    RemoteRepeaterRequest,
    RepeaterAdminExecutor,
    WaiterRegistry,
)
from src.admin_handler import AdminContext
from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.repeater_manager import RepeaterManager
from src.target_resolver import TargetResolver

LOCAL_KEY = "ab" * 32
REMOTE_KEY = "cd" * 32


@pytest.fixture
def executors() -> tuple[LocalConfigExecutor, RepeaterAdminExecutor, AdminContext, Any, dict[str, Any]]:
    commands = SimpleNamespace(**{
        name: AsyncMock(return_value=Event(EventType.OK, {}))
        for name in ("set_name", "set_devicepin", "set_tx_power", "send_cmd", "send_login_sync")
    })
    mc = SimpleNamespace(
        commands=commands,
        self_info={"public_key": LOCAL_KEY, "name": "Before", "hardware_board": "LOW_POWER"},
    )
    registry = NodeRegistry()
    registry.set_local_pubkey(LOCAL_KEY)
    ctx = AdminContext(
        mc_provider=lambda: mc,
        node_registry=registry,
        repeater_manager=RepeaterManager(),
        mqtt=MagicMock(),
        execute_tx=AsyncMock(),
    )
    # TX clamping reads the cached, confirmed hardware snapshot, not self_info.
    cfg = {"name": "Before", "public_key": LOCAL_KEY, "hardware_board": "LOW_POWER"}
    local = LocalConfigExecutor(ctx, cfg, time.time(), MagicMock())
    resolver = TargetResolver(lambda: mc, registry)
    remote = RepeaterAdminExecutor(
        ctx, WaiterRegistry({}, {}), MagicMock(),
        lambda target, length: resolver.resolve(target, length),
        AsyncMock(return_value={"text": "ok"}), lambda: cfg,
    )
    return local, remote, ctx, mc, cfg


@pytest.mark.parametrize("target", ["Alice", "MobileAlias"])
async def test_named_client_keeps_role_guard(executors: Any, target: str) -> None:
    _, remote, ctx, mc, _ = executors
    ctx.node_registry.add_or_update(
        REMOTE_KEY, NodeContactUpdate(name="Alice", alias="MobileAlias", role="CLIENT")
    )
    result = await remote.execute(RemoteRepeaterRequest({}, "reboot", "client", target, mc=mc))
    assert result["status"] == "error"
    assert "exclusivos para repetidores" in result["message"]
    mc.commands.send_cmd.assert_not_awaited()
    ctx.execute_tx.assert_not_awaited()


async def test_named_repeater_can_dispatch_a_valid_command(executors: Any) -> None:
    _, remote, ctx, mc, _ = executors
    ctx.node_registry.add_or_update(
        REMOTE_KEY, NodeContactUpdate(name="Hill Relay", alias="RelayAlias", role="REPEATER")
    )
    result = await remote.execute(
        RemoteRepeaterRequest({}, "get_clock", "clock", "RelayAlias", mc=mc)
    )
    assert result["status"] == "ok"
    assert result["cmd_dispatched"] == "clock"
    mc.commands.send_cmd.assert_awaited_once_with(REMOTE_KEY, "00|clock")
    ctx.execute_tx.assert_not_awaited()


@pytest.mark.parametrize("password", ["", "secret"])
@pytest.mark.parametrize("action,data", [
    ("unknown_command", {}),
    ("set_radio", {"frequency": 915}),
    ("set_lat", {"lat": None}),
])
async def test_uncompiled_command_does_not_login_transmit_or_consume_cooldown(
    executors: Any, password: str, action: str, data: dict[str, Any],
) -> None:
    _, remote, ctx, mc, _ = executors
    ctx.node_registry.add_or_update(REMOTE_KEY, NodeContactUpdate(name="Hill", role="REPEATER"))
    result = await remote.execute(
        RemoteRepeaterRequest(data, action, "invalid", REMOTE_KEY, password=password, mc=mc)
    )
    assert result["status"] == "error"
    assert result["code"] == 422
    assert result["message"] == "Comando remoto no compatible o parámetros inválidos"
    mc.commands.send_login_sync.assert_not_awaited()
    mc.commands.send_cmd.assert_not_awaited()
    ctx.execute_tx.assert_not_awaited()
    assert ctx.repeater_manager.check_airtime_cooldown(REMOTE_KEY) == (True, 0.0)


@pytest.mark.parametrize("key", ["pin", "devicepin", "tx_power", "power"])
async def test_null_scalar_rejects_whole_batch_before_sdk_or_cache_mutation(
    executors: Any, key: str,
) -> None:
    local, _, _, mc, cfg = executors
    before = dict(cfg)
    device_before = dict(mc.self_info)
    result = await local.set_local_config({"params": {"name": "After", key: None}}, {}, mc)
    assert result["status"] == "error"
    assert result["code"] == 422
    assert result["applied"] == {}
    assert cfg == before
    assert mc.self_info == device_before
    mc.commands.set_name.assert_not_awaited()
    mc.commands.set_devicepin.assert_not_awaited()
    mc.commands.set_tx_power.assert_not_awaited()


@pytest.mark.parametrize("key,value,command,encoded", [
    ("pin", 0, "set_devicepin", 0),
    ("devicepin", "123456", "set_devicepin", 123456),
    ("tx_power", 0, "set_tx_power", 0),
    ("power", "0", "set_tx_power", 0),
])
async def test_valid_zero_and_numeric_aliases_keep_official_sdk_contract(
    executors: Any, key: str, value: Any, command: str, encoded: int,
) -> None:
    local, _, _, mc, _ = executors
    result = await local.set_local_config({"params": {key: value}}, {}, mc)
    assert result["status"] == "ok"
    getattr(mc.commands, command).assert_awaited_once_with(encoded)
