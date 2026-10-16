"""Domain persistence regressions with isolated station databases.

These tests must only run under the explicit authorization in AGENTS.md.
"""

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from src.bridge_core import MeshCoreBridge
from src.contact_manager import NodeRegistry
from src.rate_limiter import AirtimeTracker
from src.repeater_manager import RepeaterManager
from src.services_config import load_services_config, save_services_config
from src.station_database import StationDatabase


def test_nodes_import_once_and_keep_local_contact_exclusion(tmp_path: Path) -> None:
    legacy = tmp_path / "nodes.json"
    key = "aa" * 32
    legacy.write_text(json.dumps({"local_pubkey": key, "nodes": [
        {"public_key": key, "is_local": True, "role": "LOCAL", "name": "Station"},
        {"public_key": "bb" * 32, "role": "REPEATER", "name": "Router", "vendor_metadata": {"revision": "v1"}},
    ], "error_categories": {"CRC_MISMATCH": 4}}), encoding="utf-8")
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    registry = NodeRegistry(database=database)
    assert registry.load_from_file(legacy) == 2
    assert registry.list_client_contacts() == []
    assert registry.error_categories["CRC_MISMATCH"] == 4
    assert registry.save_to_file(force=True)
    legacy.write_text("{}", encoding="utf-8")
    restored = NodeRegistry(database=database)
    assert restored.load_from_file(legacy) == 2
    assert restored.error_categories["CRC_MISMATCH"] == 4
    snapshot = database.read_document("nodes")
    assert isinstance(snapshot, dict)
    repeater = next(node for node in snapshot["nodes"] if node["public_key"] == "bb" * 32)
    assert repeater["vendor_metadata"] == {"revision": "v1"}


def test_services_credentials_survive_sqlite_roundtrip(tmp_path: Path) -> None:
    legacy = tmp_path / "services.json"
    legacy.write_text(json.dumps({"version": 1, "external_mqtt": {
        "password": "private-password", "token": "private-token"
    }, "local_mqtt": {}, "tcp_server": {}}), encoding="utf-8")
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    settings = load_services_config(legacy, database=database)
    settings.external_mqtt.host = "broker.example"
    save_services_config(settings, legacy, database=database)
    restored = load_services_config(legacy, database=database)
    assert restored.external_mqtt.password == "private-password"
    assert restored.external_mqtt.token == "private-token"
    assert restored.external_mqtt.host == "broker.example"
    assert json.loads(legacy.read_text())["external_mqtt"].get("host") is None


def test_airtime_import_preserves_cutoff_and_lifetime_totals(tmp_path: Path) -> None:
    legacy = tmp_path / "airtime.json"
    legacy.write_text(json.dumps({"records": [], "total_airtime_ms": 9876,
        "total_packets": 14, "cutoff_active": True,
        "channel_utilization_pct": 40}), encoding="utf-8")
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    tracker = AirtimeTracker(history_file=str(legacy), database=database)
    assert tracker.total_airtime_ms == 9876
    assert tracker.total_packets == 14
    assert tracker.is_cutoff_active()


@pytest.mark.asyncio
async def test_repeater_cooldowns_keep_original_wall_timestamps(tmp_path: Path) -> None:
    legacy = tmp_path / "cooldown.json"
    observed = time.time()
    legacy.write_text(json.dumps({"schema": 1, "timestamps": {
        "ping": {"cc" * 32: observed}}}), encoding="utf-8")
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    manager = RepeaterManager(storage_path=legacy, database=database)
    await manager.load_state()
    snapshot = database.read_document("repeater_cooldowns")
    assert isinstance(snapshot, dict)
    assert snapshot["timestamps"]["ping"]["cc" * 32] == observed
    allowed, remaining = manager.check_ping_cooldown("cc" * 32)
    assert not allowed
    assert remaining > 0


@pytest.mark.asyncio
async def test_chat_is_durable_without_a_browser_or_web_server(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    bridge = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge.database = database
    bridge.node_registry = NodeRegistry(database=database)
    bridge.web_server = None
    await bridge.publish_chat_event({"type": "public", "sender": "dd" * 32,
        "text": "Keep this message", "channel_idx": 0})
    assert database.history()["messages"][0]["text"] == "Keep this message"


def _headless_sender(database: StationDatabase) -> MeshCoreBridge:
    bridge: Any = MeshCoreBridge.__new__(MeshCoreBridge)
    bridge.database = database
    bridge.node_registry = NodeRegistry(database=database)
    bridge.web_server = None
    bridge.packet_buffer = None
    bridge.serial_adapter = SimpleNamespace(is_connected=True, send_message=AsyncMock(return_value={
        "status": "sent", "expected_ack": "a1b2c3d4"}))
    bridge._tx_metrics_lock = asyncio.Lock()
    bridge.tx_count = bridge.tx_error_count = 0
    bridge._pending_acks = {}
    bridge.publish_mqtt_safe = lambda *args, **kwargs: True
    return cast(MeshCoreBridge, bridge)


@pytest.mark.asyncio
async def test_headless_send_and_ack_survive_restart(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    bridge = _headless_sender(database)
    result = await bridge._execute_tx({"request_id": "out-1", "text": "Hello", "to": "ee" * 32})
    assert result["status"] == "sent"
    assert database.history()["messages"][0]["status"] == "sent"
    restored = _headless_sender(database)
    restored._pending_acks = database.load_pending_acks()
    for pending in restored._pending_acks.values():
        pending["registered_at"] = time.monotonic() - (time.time() - pending["timestamp"])
    correlation = await restored.consume_pending_ack("a1b2c3d4", 42)
    assert correlation is not None
    assert correlation["req_id"] == "out-1"
    message = database.history()["messages"][0]
    assert message["status"] == "delivered"
    assert message["trip_time_ms"] == 42
    assert await restored.consume_pending_ack("a1b2c3d4", 42) is None


@pytest.mark.asyncio
async def test_storage_failure_after_radio_send_does_not_report_radio_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    bridge = _headless_sender(database)
    original_record = database.record_message

    def fail_final_commit(payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("status") == "sent":
            raise OSError("Database disk full")
        return original_record(payload)

    monkeypatch.setattr(database, "record_message", fail_final_commit)
    result = await bridge._execute_tx({"request_id": "out-2", "text": "Hello", "to": "ee" * 32})
    assert result["status"] == "sent"
    assert result["storage_error"] is True
    cast(AsyncMock, bridge.serial_adapter.send_message).assert_awaited_once()


def test_invalid_node_import_keeps_legacy_file_and_allows_repair(tmp_path: Path) -> None:
    legacy = tmp_path / "nodes.json"
    original = '{"nodes": [{"public_key": "invalid-node"}]}'
    legacy.write_text(original, encoding="utf-8")
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    registry = NodeRegistry(database=database)
    with pytest.raises(ValueError):
        registry.load_from_file(legacy)
    assert database.read_document("nodes") is None
    assert legacy.read_text(encoding="utf-8") == original
    legacy.write_text('{"nodes": []}', encoding="utf-8")
    assert registry.load_from_file(legacy) == 0
