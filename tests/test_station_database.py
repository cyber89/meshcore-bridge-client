"""SQLite migration regressions; fixtures use only temporary files."""

import json
import sqlite3
from pathlib import Path

import pytest

from src.station_database import StationDatabase


def test_legacy_document_is_imported_once_and_original_is_preserved(tmp_path: Path) -> None:
    legacy = tmp_path / "channels.json"
    legacy.write_text('{"channels": [1]}', encoding="utf-8")
    database = StationDatabase(tmp_path / "station.sqlite3")
    assert not database.path.exists()
    database.initialize()
    assert database.read_document("channels", legacy) == {"channels": [1]}
    database.write_document("channels", {"channels": [2]})
    assert json.loads(legacy.read_text(encoding="utf-8")) == {"channels": [1]}
    restarted = StationDatabase(database.path)
    restarted.initialize()
    assert restarted.read_document("channels", legacy) == {"channels": [2]}


def test_invalid_import_rolls_back_and_can_be_corrected(tmp_path: Path) -> None:
    legacy = tmp_path / "nodes.json"
    legacy.write_text('[]', encoding="utf-8")
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()

    def validate(data: object) -> None:
        if not isinstance(data, dict):
            raise ValueError("Expected an object")

    with pytest.raises(ValueError, match="Expected an object"):
        database.read_document("nodes", legacy, validate)
    legacy.write_text('{"nodes": []}', encoding="utf-8")
    assert database.read_document("nodes", legacy, validate) == {"nodes": []}


def test_truncated_legacy_import_preserves_source_and_leaves_no_partial_marker(tmp_path: Path) -> None:
    legacy = tmp_path / "airtime.json"
    original = b'{"last_fired":'
    legacy.write_bytes(original)
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    with pytest.raises(json.JSONDecodeError):
        database.read_document("airtime", legacy)
    assert legacy.read_bytes() == original
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents WHERE name=?", ("airtime",)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM legacy_imports WHERE name=?", ("airtime",)).fetchone()[0] == 0
    corrected = {"last_fired": 123, "cooldown": 456}
    legacy.write_text(json.dumps(corrected), encoding="utf-8")
    assert database.read_document("airtime", legacy) == corrected
    legacy.write_text('{"last_fired": 0}', encoding="utf-8")
    restarted = StationDatabase(database.path)
    restarted.initialize()
    assert restarted.read_document("airtime", legacy) == corrected
    assert json.loads(legacy.read_text(encoding="utf-8")) == {"last_fired": 0}


def test_future_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 999")
    with pytest.raises(RuntimeError, match="newer"):
        StationDatabase(path).initialize()


def test_backup_contains_consistent_documents_and_station_identity(tmp_path: Path) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    database.write_document("airtime", {"last": 123})
    destination = tmp_path / "backup.sqlite3"
    database.backup(destination)
    copied = StationDatabase(destination)
    copied.initialize()
    assert copied.read_document("airtime") == {"last": 123}
    assert copied.history()["station_id"] == database.history()["station_id"]
