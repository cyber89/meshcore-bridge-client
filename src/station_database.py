"""Durable station state and chat storage using the standard-library SQLite driver.

Methods are synchronous worker boundaries: callers on asyncio must use to_thread.
Connections never cross threads. A lock serializes this instance's transactions;
SQLite additionally arbitrates independent readers and processes.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = 1
_DOCUMENT_NAMES = frozenset({"nodes", "channels", "services", "airtime", "repeater_cooldowns"})
_MESSAGE_FIELDS = frozenset({
    "sender", "sender_name", "text", "is_outgoing", "channel_idx", "dm_target",
    "dm_target_name", "timestamp", "metrics", "quote", "location", "txt_type",
    "status", "delivered", "expected_ack", "trip_time_ms", "is_direct",
})
_STATUSES = frozenset({"received", "queued", "sent", "failed", "delivered"})
_SECRET_FIELDS = frozenset({"psk", "password", "api_key", "token", "secret", "private_key",
                            "mqtt_password", "bridge_api_key", "companion_token"})


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _without_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_secrets(item) for key, item in value.items()
                if str(key).lower() not in _SECRET_FIELDS}
    if isinstance(value, list):
        return [_without_secrets(item) for item in value]
    return value


def _ack(value: Any) -> str:
    code = str(value or "").strip().lower().removeprefix("0x")
    return code if re.fullmatch(r"[0-9a-f]+", code) and any(char != "0" for char in code) else ""


def _timestamp(value: Any) -> str:
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        result = datetime.fromtimestamp(value / 1000 if value > 1e11 else value, UTC)
    elif isinstance(value, str) and value:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=UTC)
        result = result.astimezone(UTC)
    else:
        result = datetime.now(UTC)
    return result.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class StationIdentityMismatch(ValueError):
    """The operator's history snapshot belongs to a different station database."""


class StationDatabase:
    """An explicitly initialized local SQLite repository; construction does no I/O."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._initialized = False

    def _restrict_files(self) -> None:
        for path in (self.path, Path(f"{self.path}-wal"), Path(f"{self.path}-shm")):
            if path.is_symlink():
                raise ValueError("Station database files must not be symbolic links")
            if path.exists():
                try:
                    os.chmod(path, 0o600)
                except FileNotFoundError:
                    # Other SQLite repositories can retire these sidecars.
                    if path == self.path:
                        raise
                except PermissionError:
                    # Windows deletion can surface as access denied. Verify loss.
                    if path == self.path or path.exists():
                        raise

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        if not self._initialized:
            raise RuntimeError("Station database has not been initialized")
        with self._lock:
            connection = sqlite3.connect(self.path, timeout=30)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA synchronous = FULL")
                connection.execute("PRAGMA foreign_keys = ON")
                self._restrict_files()
                with connection:
                    yield connection
            finally:
                connection.close()
                self._restrict_files()

    def initialize(self) -> None:
        """Create schema atomically; refuse databases from newer application versions."""
        with self._lock:
            if self._initialized:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.is_symlink():
                raise ValueError("Station database must not be a symbolic link")
            descriptor = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(descriptor)
            self._restrict_files()
            connection = sqlite3.connect(self.path, timeout=30)
            try:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version > _SCHEMA_VERSION:
                    raise RuntimeError("Station database schema is newer than this application")
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = FULL")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute("INSERT OR IGNORE INTO metadata VALUES ('station_id', ?)", (str(uuid.uuid4()),))
                connection.execute("""CREATE TABLE IF NOT EXISTS documents (
                    name TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS legacy_imports (
                    name TEXT PRIMARY KEY, source TEXT NOT NULL, digest TEXT NOT NULL, imported_at TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS messages (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, msg_id TEXT NOT NULL UNIQUE,
                    feed_key TEXT NOT NULL, timestamp TEXT NOT NULL, direction TEXT NOT NULL,
                    status TEXT NOT NULL, expected_ack TEXT NOT NULL DEFAULT '', payload TEXT NOT NULL)""")
                connection.execute("CREATE INDEX IF NOT EXISTS messages_feed_seq ON messages(feed_key, seq)")
                connection.execute("CREATE INDEX IF NOT EXISTS messages_ack ON messages(expected_ack)")
                connection.execute("""CREATE TABLE IF NOT EXISTS delivery_events (
                    event_key TEXT PRIMARY KEY, payload TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS pending_acks (
                    ack_code TEXT PRIMARY KEY, req_id TEXT NOT NULL, target TEXT NOT NULL,
                    timestamp REAL NOT NULL)""")
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                connection.commit()
                self._initialized = True
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()
                self._restrict_files()

    @staticmethod
    def _document_name(name: str) -> None:
        if name not in _DOCUMENT_NAMES:
            raise ValueError(f"Unknown station document: {name}")

    def read_document(
        self, name: str, legacy_path: str | Path | None = None,
        validator: Callable[[Any], None] | None = None,
    ) -> Any | None:
        """Import a validated legacy JSON document once, leaving its file untouched."""
        self._document_name(name)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM documents WHERE name = ?", (name,)).fetchone()
            if row is not None:
                data = json.loads(row[0])
                if validator is not None:
                    validator(data)
                return data
            imported = connection.execute("SELECT 1 FROM legacy_imports WHERE name = ?", (name,)).fetchone()
            if imported or legacy_path is None or not Path(legacy_path).exists():
                return None
            path = Path(legacy_path)
            raw = path.read_bytes()
            data = json.loads(raw.decode("utf-8-sig"))
            if validator is not None:
                validator(data)
            now = _timestamp(None)
            connection.execute("INSERT INTO documents VALUES (?, ?, ?)", (name, _json(data), now))
            connection.execute("INSERT INTO legacy_imports VALUES (?, ?, ?, ?)",
                               (name, str(path.resolve()), hashlib.sha256(raw).hexdigest(), now))
            return data

    def write_document(self, name: str, data: Any) -> None:
        self._document_name(name)
        payload = _json(data)
        with self._connection() as connection:
            connection.execute("INSERT INTO documents VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE "
                               "SET payload=excluded.payload, updated_at=excluded.updated_at",
                               (name, payload, _timestamp(None)))

    @staticmethod
    def _normalize(payload: dict[str, Any], *, legacy: bool = False) -> dict[str, Any]:
        data = dict(payload)
        if isinstance(data.get("data"), dict):
            data = {**data, **data["data"]}
        if legacy and (isinstance(data.get("timestamp"), bool) or
                       not isinstance(data.get("timestamp"), (str, int, float)) or data.get("timestamp") == ""):
            raise ValueError("Imported message requires a stable timestamp")
        text = data.get("text", data.get("message", ""))
        if not isinstance(text, str):
            raise ValueError("Message text must be a string")
        outgoing = data.get("is_outgoing", data.get("direction") == "outgoing")
        if not isinstance(outgoing, bool):
            raise ValueError("Message direction must be boolean")
        sender = str(data.get("sender", data.get("from", data.get("public_key", "local" if outgoing else "unknown")))).lower().strip()
        dm_target = str(data.get("dm_target") or "").lower().strip()
        direct = bool(data.get("is_direct") or dm_target or data.get("type") in {"direct", "DIRECT_MSG", "CONTACT_MSG_RECV"})
        feed_key = data.get("feed_key")
        channel = data.get("channel_idx", data.get("channel_index", data.get("channel", 0)))
        if isinstance(channel, bool) or not isinstance(channel, int) or channel < 0:
            raise ValueError("Message channel must be a nonnegative integer")
        if not feed_key:
            feed_key = f"dm_{dm_target if outgoing else sender}" if direct else f"ch_{channel}"
        if not isinstance(feed_key, str) or not re.fullmatch(r"(?:ch_[0-9]+|dm_[0-9a-f]{8,64})", feed_key):
            raise ValueError("Invalid conversation key")
        status = str(data.get("status") or ("sent" if outgoing else "received"))
        if status not in _STATUSES:
            raise ValueError("Invalid message status")
        delivered = bool(data.get("delivered") or status == "delivered")
        if outgoing and delivered:
            status = "delivered"
        record = {key: _without_secrets(value) for key, value in data.items() if key in _MESSAGE_FIELDS}
        record.update(text=text, sender=sender, channel_idx=channel, is_outgoing=outgoing,
                      feed_key=feed_key, timestamp=_timestamp(data.get("timestamp")),
                      status=status, delivered=delivered, expected_ack=_ack(data.get("expected_ack")))
        if direct:
            record["dm_target"] = dm_target if outgoing else sender
            record["is_direct"] = True
        record["source"] = "browser_import" if legacy else "station"
        if legacy:
            # Browser history is evidence of content, not proof of an RF ACK.
            record.update(delivered=False, expected_ack="", trip_time_ms=0)
            if outgoing and status == "delivered":
                record["status"] = "sent"
            elif not outgoing:
                record["status"] = "received"
        identifier = data.get("msg_id", data.get("request_id", data.get("id")))
        if legacy and (not isinstance(identifier, str) or identifier.isdecimal() or identifier.startswith("rx_")):
            identifier = None
        if identifier is not None and not isinstance(identifier, str):
            identifier = str(identifier)
        if not identifier:
            identity = {key: record.get(key) for key in ("feed_key", "timestamp", "sender", "text", "is_outgoing")}
            identifier = "history_" + hashlib.sha256(_json(identity).encode()).hexdigest()
        if len(identifier) > 256:
            raise ValueError("Message identifier is too long")
        record["msg_id"] = identifier
        record["id"] = identifier
        _json(record)
        return record

    @staticmethod
    def _station_id(connection: sqlite3.Connection) -> str:
        row = connection.execute("SELECT value FROM metadata WHERE key='station_id'").fetchone()
        if row is None:
            raise RuntimeError("Station database identity is missing")
        identity = str(row[0])
        try:
            uuid.UUID(identity)
        except ValueError as error:
            raise RuntimeError("Station database identity is invalid") from error
        return identity

    def _result(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(row["payload"])
        result.update(seq=row["seq"], station_id=self._station_id(connection))
        return result

    def _write_message(self, connection: sqlite3.Connection, record: dict[str, Any], *, legacy: bool = False) -> tuple[dict[str, Any], bool]:
        existing = connection.execute("SELECT * FROM messages WHERE msg_id = ?", (record["msg_id"],)).fetchone()
        if existing is not None:
            if legacy:
                return self._result(connection, existing), False
            previous: dict[str, Any] = json.loads(existing["payload"])
            if any(previous.get(key) != record.get(key) for key in ("feed_key", "text", "is_outgoing")):
                raise ValueError("Message identifier belongs to a different message")
            record = {**previous, **record}
            record["timestamp"] = previous["timestamp"]
            if not record.get("expected_ack"):
                record["expected_ack"] = previous.get("expected_ack", "")
            if previous.get("delivered") or previous.get("status") == "delivered":
                record.update(delivered=True, status="delivered")
                if not record.get("trip_time_ms"):
                    record["trip_time_ms"] = previous.get("trip_time_ms", 0)
        event_keys = () if legacy else (f"id:{record['msg_id']}", f"ack:{record.get('expected_ack', '')}")
        for event_key in event_keys:
            event = connection.execute("SELECT payload FROM delivery_events WHERE event_key = ?", (event_key,)).fetchone()
            if event is not None:
                ack_event = json.loads(event[0])
                if event_key.startswith("ack:") and time.time() - ack_event.get("received_at", 0) >= 3600:
                    continue
                record.update(delivered=True, status="delivered")
                record["trip_time_ms"] = ack_event.get("trip_time_ms") or record.get("trip_time_ms", 0)
        connection.execute("""INSERT INTO messages(msg_id,feed_key,timestamp,direction,status,expected_ack,payload)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(msg_id) DO UPDATE SET status=excluded.status,
            expected_ack=excluded.expected_ack,payload=excluded.payload""",
                           (record["msg_id"], record["feed_key"], record["timestamp"],
                            "outgoing" if record["is_outgoing"] else "incoming", record["status"],
                            record.get("expected_ack", ""), _json(record)))
        row = connection.execute("SELECT * FROM messages WHERE msg_id = ?", (record["msg_id"],)).fetchone()
        return self._result(connection, row), existing is None

    def record_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = self._normalize(payload)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self._write_message(connection, record)[0]

    def update_delivery(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Apply delivery/status events, retaining early ACKs across restart."""
        data = {**payload, **payload.get("data", {})} if isinstance(payload.get("data"), dict) else payload
        identifier = str(data.get("msg_id") or data.get("request_id") or "")
        code = _ack(data.get("ack_code", data.get("code", "")))
        expected = _ack(data.get("expected_ack"))
        status = data.get("status", "delivered" if code else None)
        if status is not None and status not in _STATUSES:
            raise ValueError("Invalid delivery status")
        trip = data.get("trip_time_ms", data.get("trip_time", data.get("rtt_ms", 0))) or 0
        if isinstance(trip, bool) or not isinstance(trip, (int, float)) or not math.isfinite(trip) or trip < 0:
            raise ValueError("Invalid delivery trip time")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if status == "delivered":
                # An explicitly correlated ID must never acknowledge another colliding code.
                keys = [f"id:{identifier}"] if identifier else ([f"ack:{code}"] if code else [])
                for key in keys:
                    connection.execute("INSERT INTO delivery_events VALUES (?,?) ON CONFLICT(event_key) DO UPDATE SET payload=excluded.payload",
                                       (key, _json({"trip_time_ms": trip, "received_at": time.time()})))
                if identifier:
                    connection.execute("DELETE FROM pending_acks WHERE req_id=?", (identifier,))
            if identifier:
                rows = connection.execute("SELECT * FROM messages WHERE msg_id=?", (identifier,)).fetchall()
            elif code:
                rows = connection.execute("SELECT * FROM messages WHERE expected_ack=? AND direction='outgoing'", (code,)).fetchall()
                if len(rows) > 1:
                    raise ValueError("Ambiguous delivery acknowledgement")
            else:
                rows = []
            updated = []
            for row in rows:
                record = json.loads(row["payload"])
                if expected:
                    record["expected_ack"] = expected
                if not record.get("delivered") and record.get("status") != "delivered":
                    if status is not None:
                        record["status"] = status
                    if status == "delivered":
                        record.update(delivered=True, trip_time_ms=trip)
                elif status == "delivered" and trip:
                    record["trip_time_ms"] = trip
                updated.append(self._write_message(connection, record)[0])
            return updated

    @staticmethod
    def _prune_acks(connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM pending_acks WHERE timestamp <= ?", (time.time() - 3600,))
        connection.execute("""DELETE FROM pending_acks WHERE req_id IN
            (SELECT msg_id FROM messages WHERE status='delivered') OR ('id:' || req_id) IN
            (SELECT event_key FROM delivery_events)""")

    def save_pending_ack(self, expected_ack: str, req_id: str, target: str, epoch: float) -> str:
        """Retain the existing one-hour/200-entry delivery correlation contract."""
        code = _ack(expected_ack)
        if len(code) != 8:
            return "invalid_ack"
        if not isinstance(epoch, (int, float)) or isinstance(epoch, bool) or not math.isfinite(epoch):
            raise ValueError("Pending ACK timestamp must be an epoch number")
        if epoch <= time.time() - 3600:
            return "expired"
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._prune_acks(connection)
            delivered = connection.execute("SELECT 1 FROM delivery_events WHERE event_key=? UNION ALL "
                                           "SELECT 1 FROM messages WHERE msg_id=? AND status='delivered' LIMIT 1",
                                           (f"id:{req_id}", req_id)).fetchone()
            if delivered is not None:
                return "already_delivered"
            previous = connection.execute("SELECT req_id,target FROM pending_acks WHERE ack_code=?", (code,)).fetchone()
            if previous is not None:
                return "registered" if previous["req_id"] == req_id and previous["target"] == target else "collision"
            if connection.execute("SELECT COUNT(*) FROM pending_acks").fetchone()[0] >= 200:
                return "capacity_exceeded"
            connection.execute("INSERT INTO pending_acks VALUES (?,?,?,?)", (code, req_id, target, epoch))
            return "registered"

    def load_pending_acks(self) -> dict[str, dict[str, Any]]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._prune_acks(connection)
            rows = connection.execute("SELECT * FROM pending_acks ORDER BY timestamp DESC LIMIT 200").fetchall()
            return {row["ack_code"]: {"req_id": row["req_id"], "target": row["target"],
                                      "timestamp": row["timestamp"]} for row in rows}

    def consume_pending_ack(self, ack_code: str, trip_time_ms: int | float | None = None) -> dict[str, Any] | None:
        """Consume correlation and commit delivery atomically before web notifications."""
        code = _ack(ack_code)
        if len(code) != 8:
            return None
        trip = trip_time_ms or 0
        if isinstance(trip, bool) or not isinstance(trip, (int, float)) or not math.isfinite(trip) or trip < 0:
            raise ValueError("Invalid delivery trip time")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._prune_acks(connection)
            row = connection.execute("SELECT * FROM pending_acks WHERE ack_code=?", (code,)).fetchone()
            if row is None:
                return None
            connection.execute("INSERT INTO delivery_events VALUES (?,?) ON CONFLICT(event_key) DO UPDATE SET payload=excluded.payload",
                               (f"id:{row['req_id']}", _json({"trip_time_ms": trip, "received_at": time.time()})))
            message = connection.execute("SELECT * FROM messages WHERE msg_id=?", (row["req_id"],)).fetchone()
            if message is not None:
                record = json.loads(message["payload"])
                record.update(delivered=True, status="delivered", trip_time_ms=trip)
                self._write_message(connection, record)
            connection.execute("DELETE FROM pending_acks WHERE ack_code=?", (code,))
            return {"req_id": row["req_id"], "target": row["target"], "timestamp": row["timestamp"]}

    def resolve_delivery_ack(self, ack_code: str) -> dict[str, Any] | None:
        return self.consume_pending_ack(ack_code)

    def history(self, feed_key: str | None = None, limit: int = 100, before: int | None = None) -> dict[str, Any]:
        if feed_key is not None and (not isinstance(feed_key, str) or
                                    not re.fullmatch(r"(?:ch_[0-9]+|dm_[0-9a-f]{8,64})", feed_key)):
            raise ValueError("Invalid conversation key")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("History limit must be between 1 and 1000")
        if before is not None and (isinstance(before, bool) or not isinstance(before, int) or before < 1):
            raise ValueError("Invalid history cursor")
        clauses = []
        values: list[Any] = []
        if feed_key is not None:
            clauses.append("feed_key=?")
            values.append(feed_key)
        if before is not None:
            clauses.append("seq<?")
            values.append(before)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connection() as connection:
            rows = connection.execute(f"SELECT * FROM messages{where} ORDER BY seq DESC LIMIT ?", (*values, limit + 1)).fetchall()
            has_more = len(rows) > limit
            rows = rows[:limit]
            messages = [self._result(connection, row) for row in reversed(rows)]
            return {"messages": messages, "next_before": rows[-1]["seq"] if has_more else None,
                    "has_more": has_more, "station_id": self._station_id(connection)}

    def conversations(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("""SELECT m.*, c.message_count FROM messages m JOIN
                (SELECT feed_key, MAX(seq) last_seq, COUNT(*) message_count FROM messages GROUP BY feed_key) c
                ON m.seq=c.last_seq ORDER BY m.seq DESC""").fetchall()
            result = []
            for row in rows:
                message = self._result(connection, row)
                result.append({"feed_key": row["feed_key"], "last_seq": row["seq"],
                               "message_count": row["message_count"], "timestamp": row["timestamp"],
                               "last_message": message, "station_id": message["station_id"]})
            return result

    def import_messages(self, messages: list[dict[str, Any]], station_id: str | None = None) -> dict[str, Any]:
        """Import a browser snapshot atomically without modifying authoritative records."""
        records = [self._normalize(message, legacy=True) for message in messages]
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_station = self._station_id(connection)
            if station_id is not None and station_id != current_station:
                raise StationIdentityMismatch("Station identity changed before importing browser history")
            imported = sum(self._write_message(connection, record, legacy=True)[1] for record in records)
            return {"imported": imported, "duplicates": len(records) - imported,
                    "station_id": current_station}

    def backup(self, path: str | Path) -> None:
        """Produce a consistent snapshot through SQLite's online backup API."""
        destination = Path(path)
        if destination.resolve() == self.path.resolve() or destination.exists():
            raise ValueError("Backup destination must be a new file")
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with self._connection() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
                os.chmod(destination, 0o600)
