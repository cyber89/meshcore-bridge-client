"""Durable chat regressions without radio or production data."""

import time
from pathlib import Path

import pytest

from src.station_database import StationDatabase, StationIdentityMismatch


def test_history_survives_restart_and_pages_without_duplicates(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    for index in range(4):
        database.record_message({"msg_id": f"message-{index}", "text": str(index),
                                 "channel_idx": 1, "timestamp": "2026-10-10T12:00:00Z"})
    restarted = StationDatabase(database.path)
    restarted.initialize()
    latest = restarted.history("ch_1", limit=2)
    assert [message["text"] for message in latest["messages"]] == ["2", "3"]
    assert latest["has_more"]
    older = restarted.history("ch_1", limit=2, before=latest["next_before"])
    assert [message["text"] for message in older["messages"]] == ["0", "1"]
    assert not older["has_more"]


def test_ack_before_message_and_failure_never_downgrades_delivery(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    database.update_delivery({"ack_code": "0xaabb", "trip_time_ms": 42})
    recorded = database.record_message({"msg_id": "tx-1", "text": "hello", "is_outgoing": True,
                                        "expected_ack": "aabb", "status": "sent"})
    assert recorded["status"] == "delivered"
    database.update_delivery({"msg_id": "tx-1", "status": "failed"})
    assert database.history()["messages"][0]["delivered"] is True
    assert database.history()["messages"][0]["trip_time_ms"] == 42


def test_browser_import_deduplicates_local_numeric_ids_and_preserves_live_status(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    first = {"id": 1, "msg_id": 1, "feed_key": "ch_0", "text": "old",
             "sender": "abc", "timestamp": "2026-10-10T10:00:00Z"}
    second = {**first, "id": 23, "msg_id": 23}
    assert database.import_messages([first])["imported"] == 1
    assert database.import_messages([second])["imported"] == 0
    live = {"msg_id": "tx-live", "text": "sent", "is_outgoing": True, "status": "delivered",
            "timestamp": "2026-10-10T11:00:00Z"}
    database.record_message(live)
    database.import_messages([{**live, "status": "failed", "delivered": False}])
    assert database.history()["messages"][-1]["status"] == "delivered"


def test_secrets_are_not_persisted_in_chat_payloads(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    record = database.record_message({"text": "hello", "psk": "secret", "api_key": "secret",
                                      "metrics": {"snr": 5, "password": "secret"}})
    assert "psk" not in record
    assert "api_key" not in record
    assert record["metrics"] == {"snr": 5}


def test_repeated_transmission_does_not_erase_ack_association(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    first = {"msg_id": "tx-1", "text": "hello", "is_outgoing": True, "expected_ack": "aabb"}
    database.record_message(first)
    database.record_message({key: value for key, value in first.items() if key != "expected_ack"})
    database.update_delivery({"ack_code": "aabb"})
    assert database.history()["messages"][0]["status"] == "delivered"


def test_invalid_import_is_atomic(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    with pytest.raises(ValueError):
        database.import_messages([{"text": "valid", "timestamp": "2026-10-10T10:00:00Z"},
                                  {"text": {"invalid": True}, "timestamp": "2026-10-10T10:00:00Z"}])
    assert database.history()["messages"] == []


def test_pending_ack_survives_restart_rejects_collision_and_is_consumed_once(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    now = time.time()
    assert database.save_pending_ack("abcd1234", "tx-1", "a" * 64, now) == "registered"
    assert database.save_pending_ack("abcd1234", "tx-2", "b" * 64, now) == "collision"
    assert database.save_pending_ack("dead1234", "expired", "a" * 64, now - 3601) == "expired"
    restarted = StationDatabase(database.path)
    restarted.initialize()
    assert list(restarted.load_pending_acks()) == ["abcd1234"]
    result = restarted.consume_pending_ack("abcd1234")
    assert result is not None and result["req_id"] == "tx-1"
    assert restarted.consume_pending_ack("abcd1234") is None


def test_correlated_delivery_never_marks_another_message_with_colliding_ack(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    for identifier in ("tx-1", "tx-2"):
        database.record_message({"msg_id": identifier, "text": identifier, "is_outgoing": True,
                                 "expected_ack": "aabb1234"})
    database.update_delivery({"msg_id": "tx-1", "ack_code": "aabb1234"})
    assert [message["status"] for message in database.history()["messages"]] == ["delivered", "sent"]


def test_late_pending_save_cannot_rearm_an_already_delivered_request(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    database.update_delivery({"msg_id": "tx-1", "ack_code": "abcd1234"})
    assert database.save_pending_ack("abcd1234", "tx-1", "a" * 64, time.time()) == "already_delivered"
    assert database.load_pending_acks() == {}


def test_imported_delivery_claim_is_not_a_server_verified_ack(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    database.import_messages([{"msg_id": "browser-tx", "text": "old", "is_outgoing": True,
                               "timestamp": "2026-10-10T10:00:00Z", "status": "delivered",
                               "delivered": True, "expected_ack": "abcd1234", "trip_time_ms": 40}])
    imported = database.history()["messages"][0]
    assert imported["status"] == "sent"
    assert not imported["delivered"]
    assert imported["source"] == "browser_import"
    assert not imported["expected_ack"]


def test_import_without_a_stable_timestamp_is_rejected(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    with pytest.raises(ValueError, match="timestamp"):
        database.import_messages([{"text": "cannot identify this historical message"}])
    assert database.history()["messages"] == []


def test_station_change_between_snapshot_and_import_cannot_mix_histories(tmp_path: Path) -> None:
    original = StationDatabase(tmp_path / "first.sqlite3")
    original.initialize()
    second = StationDatabase(tmp_path / "second.sqlite3")
    second.initialize()
    with pytest.raises(StationIdentityMismatch):
        second.import_messages([{"text": "old station", "timestamp": "2026-10-10T10:00:00Z"}],
                               station_id=original.history()["station_id"])
    assert second.history()["messages"] == []


def test_consuming_ack_commits_delivery_before_any_web_event(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    database.record_message({"msg_id": "tx-1", "text": "sent", "is_outgoing": True,
                             "expected_ack": "abcd1234"})
    database.save_pending_ack("abcd1234", "tx-1", "a" * 64, time.time())
    database.consume_pending_ack("abcd1234", 42)
    restarted = StationDatabase(database.path)
    restarted.initialize()
    message = restarted.history()["messages"][0]
    assert message["status"] == "delivered"
    assert message["trip_time_ms"] == 42
    assert restarted.consume_pending_ack("abcd1234") is None


def test_consumed_ack_before_chat_insert_is_durable_across_restart(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    database.save_pending_ack("abcd1234", "tx-1", "a" * 64, time.time())
    database.consume_pending_ack("abcd1234")
    restarted = StationDatabase(database.path)
    restarted.initialize()
    message = restarted.record_message({"msg_id": "tx-1", "text": "sent", "is_outgoing": True})
    assert message["status"] == "delivered"
    restarted.update_delivery({"msg_id": "tx-1", "ack_code": "abcd1234", "trip_time_ms": 42})
    assert restarted.history()["messages"][0]["trip_time_ms"] == 42
