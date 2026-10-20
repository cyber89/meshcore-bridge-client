"""Isolated audit regressions: no broker, radio or operational station files."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.external_mqtt_client import ExternalBridgeMQTTClient
from src.mqtt_client import AsyncBridgeMQTTClient, MQTTConfig
from src.services_config import (
    MASKED_PASSWORD,
    ExternalMqttConfig,
    ServicesConfig,
    load_services_config,
    update_services_config,
)
from src.services_manager import ServicesManager


def test_external_tls_failure_never_starts_plaintext_connection() -> None:
    with patch("src.external_mqtt_client.mqtt.Client") as factory:
        factory.return_value.tls_set_context.side_effect = ValueError("bad TLS context")
        with pytest.raises(ValueError, match="bad TLS context"):
            ExternalBridgeMQTTClient(ExternalMqttConfig(enabled=True, tls_enabled=True))
    factory.return_value.connect_async.assert_not_called()
    factory.return_value.loop_start.assert_not_called()


def test_external_tls_loads_custom_ca_and_disables_key_logging() -> None:
    context = MagicMock()
    with patch("src.external_mqtt_client.ssl.create_default_context", return_value=context) as create:
        with patch("src.external_mqtt_client.mqtt.Client") as factory:
            ExternalBridgeMQTTClient(ExternalMqttConfig(enabled=True, tls_enabled=True, tls_ca_file="private-ca.pem"))
    create.assert_called_once_with(cafile="private-ca.pem")
    assert context.keylog_filename is None
    factory.return_value.tls_set_context.assert_called_once_with(context)


def test_resolved_local_key_updates_will_before_connect() -> None:
    with patch("src.external_mqtt_client.mqtt.Client") as factory:
        client = ExternalBridgeMQTTClient(ExternalMqttConfig(enabled=True, topic_mode="hierarchical"))
        client.set_local_pubkey("a" * 64)
    will_topic, will_payload = factory.return_value.will_set.call_args.args
    assert will_topic == client.build_topic("state")
    assert json.loads(will_payload)["gateway_id"] == "a" * 64


def test_hierarchical_connection_waits_for_identity_before_sending_connect() -> None:
    with patch("src.external_mqtt_client.mqtt.Client") as factory:
        client = ExternalBridgeMQTTClient(ExternalMqttConfig(enabled=True, host="broker.invalid", topic_mode="hierarchical"))
        client.start()
        factory.return_value.connect_async.assert_not_called()
        client.set_local_pubkey("b" * 64)
    factory.return_value.connect_async.assert_called_once()
    assert factory.return_value.will_set.call_args.args[0] == client.build_topic("state")


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.asyncio
async def test_sync_mqtt_start_failure_is_observable_by_reload(external: bool) -> None:
    module = "src.external_mqtt_client" if external else "src.mqtt_client"
    with patch(module + ".mqtt.Client") as factory:
        factory.return_value.loop_start.side_effect = RuntimeError("network thread failed")
        if external:
            client = ExternalBridgeMQTTClient(ExternalMqttConfig(enabled=True, host="broker.invalid"))
        else:
            client = AsyncBridgeMQTTClient(MQTTConfig())
        with pytest.raises(RuntimeError, match="network thread failed"):
            client.start(loop=asyncio.get_running_loop())


def test_rejected_buffer_publish_preserves_order_and_retries_on_next_drain() -> None:
    with patch("src.external_mqtt_client.mqtt.Client") as factory:
        client = ExternalBridgeMQTTClient(ExternalMqttConfig(enabled=True))
    client._send_or_buffer("one", "first")
    client._send_or_buffer("two", "second")
    client.is_connected = True
    factory.return_value.publish.return_value.rc = 1
    client._drain_ring_buffer()
    assert client.total_published == 0
    assert client.total_dropped_buffer == 0
    factory.return_value.publish.return_value.rc = 0
    client._drain_ring_buffer()
    assert [call.args[:2] for call in factory.return_value.publish.call_args_list] == [
        ("one", "first"), ("one", "first"), ("two", "second"),
    ]
    assert client.total_published == 2


def test_credentials_require_explicit_clear_flags() -> None:
    config = ServicesConfig()
    config.external_mqtt.password = "external-secret"
    config.external_mqtt.token = "external-token"
    config.local_mqtt.password = "local-secret"
    kept = update_services_config(config, {"external_mqtt": {"password": "", "token": MASKED_PASSWORD}})
    assert kept.external_mqtt.password == "external-secret"
    assert kept.external_mqtt.token == "external-token"
    cleared = update_services_config(config, {
        "external_mqtt": {"clear_password": True, "clear_token": True},
        "local_mqtt": {"clear_password": True},
    })
    assert not cleared.external_mqtt.password
    assert not cleared.external_mqtt.token
    assert not cleared.local_mqtt.password
    assert config.external_mqtt.password == "external-secret"


@pytest.mark.parametrize("updates", [
    {"qos": 9}, {"qos": True}, {"keepalive": -1}, {"keepalive": 65536},
    {"enabled": "false"}, {"port": 0}, {"transport": "invalid"},
])
def test_invalid_external_domains_are_rejected_before_applying(updates: dict) -> None:
    config = ServicesConfig()
    with pytest.raises(ValueError):
        update_services_config(config, {"external_mqtt": updates})
    assert config.external_mqtt == ExternalMqttConfig()


def test_zero_keepalive_is_a_valid_mqtt_domain_value() -> None:
    updated = update_services_config(ServicesConfig(), {"external_mqtt": {"keepalive": 0}})
    assert updated.external_mqtt.keepalive == 0


def test_corrupt_explicit_json_fails_without_replacing_original(tmp_path: Path) -> None:
    path = tmp_path / "services_config.json"
    original = b'{"external_mqtt":'
    path.write_bytes(original)
    with pytest.raises(ValueError, match="original file was preserved"):
        load_services_config(path)
    assert path.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_reload_disk_failure_restores_previous_clients_and_configuration(cleanup_fails: bool) -> None:
    manager = ServicesManager.__new__(ServicesManager)
    old_config = ServicesConfig()
    old_config.tcp_server.enabled = False
    manager.services_config = old_config
    manager.local_mqtt = old_local = MagicMock()
    manager.external_mqtt = old_external = MagicMock(local_pubkey="")
    manager.tcp_server = None
    manager.bridge = SimpleNamespace(mqtt=old_local, external_mqtt=old_external, tcp_server=None)
    manager.is_running = True
    manager._loop = asyncio.get_running_loop()
    candidate = MagicMock()
    if cleanup_fails:
        candidate.stop.side_effect = OSError("candidate cleanup failed")
    updated = copy.deepcopy(old_config)
    updated.local_mqtt.host = "next.invalid"
    with patch.object(manager, "_create_local_mqtt_client", return_value=candidate):
        with patch.object(manager, "persist_configuration", new=AsyncMock(side_effect=OSError("disk full"))):
            with pytest.raises(OSError, match="disk full"):
                await manager._apply_reload(updated)
    assert manager.services_config is old_config
    assert manager.local_mqtt is manager.bridge.mqtt is old_local
    assert manager.external_mqtt is old_external
    candidate.stop.assert_called_once()
    old_local.start.assert_called_once_with(loop=manager._loop)


@pytest.mark.asyncio
async def test_failed_tcp_binding_keeps_mqtt_and_reopens_previous_listener() -> None:
    manager = ServicesManager.__new__(ServicesManager)
    manager.services_config = old_config = ServicesConfig()
    manager.local_mqtt = MagicMock()
    manager.external_mqtt = MagicMock(local_pubkey="")
    manager.tcp_server = old_tcp = MagicMock(start=AsyncMock(), stop=AsyncMock())
    manager.bridge = SimpleNamespace(tcp_server=old_tcp)
    manager.is_running = True
    manager._loop = asyncio.get_running_loop()
    updated = copy.deepcopy(old_config)
    updated.tcp_server.port += 1
    async def fail_start() -> None:
        assert manager.tcp_server is manager.bridge.tcp_server is candidate
        raise OSError("address in use")

    candidate = MagicMock(start=AsyncMock(side_effect=fail_start), stop=AsyncMock())
    with patch.object(manager, "_create_tcp_server", return_value=candidate):
        with patch.object(manager, "persist_configuration", new=AsyncMock()) as persist:
            with pytest.raises(OSError, match="address in use"):
                await manager._apply_reload(updated)
    persist.assert_not_awaited()
    manager.local_mqtt.stop.assert_not_called()
    manager.external_mqtt.stop.assert_not_called()
    old_tcp.start.assert_awaited_once()
    assert manager.tcp_server is manager.bridge.tcp_server is old_tcp


@pytest.mark.asyncio
async def test_multiple_caller_cancellations_do_not_cancel_owned_reload() -> None:
    ready, finish = asyncio.Event(), asyncio.Event()

    async def operation() -> str:
        ready.set()
        await finish.wait()
        return "committed"

    transaction = asyncio.create_task(operation())
    waiter = asyncio.create_task(ServicesManager._finish_owned_transaction(transaction))
    await ready.wait()
    waiter.cancel()
    await asyncio.sleep(0)
    waiter.cancel()
    await asyncio.sleep(0)
    assert not waiter.done()
    assert not transaction.cancelled()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert transaction.result() == "committed"


@pytest.mark.asyncio
async def test_changed_gateway_identity_replaces_session_after_stopping_old_will() -> None:
    manager = ServicesManager.__new__(ServicesManager)
    manager.services_config = ServicesConfig()
    manager.services_config.external_mqtt.enabled = True
    manager.external_mqtt = previous = MagicMock(local_pubkey="a" * 64)
    manager.bridge = SimpleNamespace(external_mqtt=previous)
    manager.is_running = True
    manager._loop = asyncio.get_running_loop()
    manager.on_incoming_external_downlink = None
    replacement = MagicMock(local_pubkey="b" * 64)

    def create_replacement(**kwargs: object) -> MagicMock:
        previous.stop.assert_called_once()
        assert kwargs["local_pubkey"] == "b" * 64
        return replacement

    with patch("src.services_manager.ExternalBridgeMQTTClient", side_effect=create_replacement):
        await manager._synchronize_local_pubkey("b" * 64)
    replacement.start.assert_called_once_with(loop=manager._loop)
    assert manager.external_mqtt is manager.bridge.external_mqtt is replacement


@pytest.mark.asyncio
async def test_identity_replacement_failure_leaves_old_gateway_stopped() -> None:
    manager = ServicesManager.__new__(ServicesManager)
    manager.services_config = ServicesConfig()
    manager.external_mqtt = previous = MagicMock(local_pubkey="a" * 64)
    manager.on_incoming_external_downlink = None
    with patch("src.services_manager.ExternalBridgeMQTTClient", side_effect=ValueError("bad TLS")):
        with pytest.raises(ValueError, match="bad TLS"):
            await manager._synchronize_local_pubkey("b" * 64)
    previous.stop.assert_called_once()
    previous.start.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("persist_fails", [False, True])
async def test_reload_callbacks_use_candidate_clients_before_configuration_commit(persist_fails: bool) -> None:
    manager = ServicesManager.__new__(ServicesManager)
    manager.services_config = old_config = ServicesConfig()
    old_config.tcp_server.enabled = False
    old_config.external_mqtt.enabled = True
    old_config.external_mqtt.host = "old.invalid"
    manager.local_mqtt = old_local = MagicMock()
    manager.external_mqtt = old_external = MagicMock(local_pubkey="")
    manager.tcp_server = None
    router_context = SimpleNamespace(mqtt=old_local, external_mqtt=old_external)
    dispatcher_context = SimpleNamespace(mqtt=old_local)
    manager.bridge = SimpleNamespace(
        mqtt=old_local, external_mqtt=old_external, tcp_server=None,
        rx_router=SimpleNamespace(_ctx=router_context),
        mqtt_dispatcher=SimpleNamespace(_ctx=dispatcher_context),
    )
    manager.on_incoming_external_downlink = None
    manager.is_running = True
    manager._loop = asyncio.get_running_loop()
    updated = copy.deepcopy(old_config)
    updated.local_mqtt.host = updated.external_mqtt.host = "next.invalid"
    next_local, next_external = MagicMock(), MagicMock(local_pubkey="")

    def local_start(**kwargs: object) -> None:
        old_local.stop.assert_called_once()
        assert manager.local_mqtt is manager.bridge.mqtt is next_local
        assert dispatcher_context.mqtt is router_context.mqtt is next_local

    def external_start(**kwargs: object) -> None:
        old_external.stop.assert_called_once()
        assert manager.external_mqtt is manager.bridge.external_mqtt is next_external
        assert router_context.external_mqtt is next_external

    async def persist(snapshot: ServicesConfig) -> None:
        assert manager.services_config is old_config
        assert snapshot == updated
        assert manager.bridge.mqtt is dispatcher_context.mqtt is router_context.mqtt is next_local
        assert manager.bridge.external_mqtt is router_context.external_mqtt is next_external
        if persist_fails:
            raise OSError("disk full")

    next_local.start.side_effect = local_start
    next_external.start.side_effect = external_start
    with patch.object(manager, "_create_local_mqtt_client", return_value=next_local):
        with patch("src.services_manager.ExternalBridgeMQTTClient", return_value=next_external):
            with patch.object(manager, "persist_configuration", new=AsyncMock(side_effect=persist)):
                if persist_fails:
                    with pytest.raises(OSError, match="disk full"):
                        await manager._apply_reload(updated)
                else:
                    await manager._apply_reload(updated)
    expected_local = old_local if persist_fails else next_local
    expected_external = old_external if persist_fails else next_external
    assert manager.local_mqtt is manager.bridge.mqtt is dispatcher_context.mqtt is router_context.mqtt is expected_local
    assert manager.external_mqtt is manager.bridge.external_mqtt is router_context.external_mqtt is expected_external
