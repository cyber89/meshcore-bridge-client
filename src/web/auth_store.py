"""Single-owner credentials and opaque sessions in the station SQLite database.

All methods are synchronous worker boundaries; asyncio callers use to_thread.
No plaintext password, session token or API token is stored in SQLite.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

COOKIE_NAME = "meshcore_session"
REMEMBER_SECONDS = 30 * 24 * 60 * 60
SESSION_SECONDS = 12 * 60 * 60
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_PEER_ATTEMPTS = 10
LOGIN_GLOBAL_ATTEMPTS = 100
MAX_LOGIN_PEERS = 1024


def validate_credentials(username: str, password: str, *, allow_default: bool = False) -> None:
    """Validate owner names and new passwords, with an explicit bootstrap exception."""
    if not isinstance(username, str) or re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username) is None:
        raise ValueError(
            "Username must contain 1-64 letters, numbers, underscores, dots or hyphens"
        )
    if not isinstance(password, str):
        raise ValueError("Password must be a string")
    if allow_default and username == "admin" and password == "admin":
        return
    if not 8 <= len(password) <= 64 or len(password.encode("utf-8")) > 1024:
        raise ValueError("Password must contain 8-64 characters; no complexity requirement")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash(password: str, salt: bytes) -> str:
    # OWASP's memory-constrained scrypt configuration: ~32 MiB per computation.
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=32768, r=8, p=3, maxmem=64 * 1024 * 1024, dklen=32
    ).hex()


@dataclass(frozen=True, slots=True)
class AuthSession:
    token: str
    username: str
    csrf_token: str
    expires_at: float
    remember: bool
    must_change_credentials: bool


class LoginLimited(ValueError):
    """Persistent login attempt budget is exhausted."""


class AuthStore:
    """No-I/O constructor with independent, short SQLite transactions per call."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._hash_lock = threading.Lock()

    def _restrict_files(self) -> None:
        for path in (self.path, Path(f"{self.path}-wal"), Path(f"{self.path}-shm")):
            if path.is_symlink():
                raise ValueError("Authentication database files must not be symbolic links")
            if path.exists():
                try:
                    os.chmod(path, 0o600)
                except FileNotFoundError:
                    # SQLite may remove WAL/SHM between exists() and chmod().
                    if path == self.path:
                        raise
                except PermissionError:
                    # Windows can report access denied during sidecar deletion.
                    # Only a now-absent sidecar is benign; real denials still fail.
                    if path == self.path or path.exists():
                        raise

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = sqlite3.connect(self.path, timeout=30)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()
                self._restrict_files()

    def initialize(self) -> None:
        """Create only authentication tables, without replacing station schema/version."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._restrict_files()
            descriptor = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(descriptor)
            with self._connection() as connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS auth_owner (
                    id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,
                    salt TEXT NOT NULL, password_hash TEXT NOT NULL,
                    must_change INTEGER NOT NULL, generation INTEGER NOT NULL DEFAULT 0)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS auth_sessions (
                    digest TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL,
                    remember INTEGER NOT NULL, generation INTEGER NOT NULL)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS auth_api_tokens (
                    id INTEGER PRIMARY KEY CHECK(id=1), digest TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS auth_login_attempts (
                    peer TEXT PRIMARY KEY, started REAL NOT NULL, attempts INTEGER NOT NULL)""")

    def has_account(self) -> bool:
        with self._connection() as connection:
            return connection.execute("SELECT 1 FROM auth_owner WHERE id=1").fetchone() is not None

    def bootstrap(
        self, username: str, password: str, *, must_change_credentials: bool = False
    ) -> bool:
        validate_credentials(username, password, allow_default=True)
        if self.has_account():
            return False
        salt = secrets.token_bytes(16)
        with self._hash_lock:
            password_hash = _hash(password, salt)
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO auth_owner VALUES(1,?,?,?,?,0)",
                (
                    username,
                    salt.hex(),
                    password_hash,
                    int(must_change_credentials or password == "admin"),
                ),
            )
            return cursor.rowcount == 1

    def bootstrap_default(self) -> bool:
        return self.bootstrap("admin", "admin", must_change_credentials=True)

    def _account(self) -> sqlite3.Row:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM auth_owner WHERE id=1").fetchone()
        if not isinstance(row, sqlite3.Row):
            raise RuntimeError("Authentication owner has not been initialized")
        return row

    def _matches_password(self, account: sqlite3.Row, password: str) -> bool:
        with self._hash_lock:
            actual = _hash(password, bytes.fromhex(str(account["salt"])))
        return hmac.compare_digest(actual, str(account["password_hash"]))

    def _reserve_login(self, peer: str) -> None:
        now = time.time()
        peer_key = "peer:" + _digest(peer)
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM auth_login_attempts WHERE started < ?", (now - LOGIN_WINDOW_SECONDS,)
            )
            count = int(
                connection.execute("SELECT count(*) FROM auth_login_attempts").fetchone()[0]
            )
            for key, limit in (("global", LOGIN_GLOBAL_ATTEMPTS), (peer_key, LOGIN_PEER_ATTEMPTS)):
                row = connection.execute(
                    "SELECT attempts FROM auth_login_attempts WHERE peer=?", (key,)
                ).fetchone()
                if (row is not None and int(row[0]) >= limit) or (
                    row is None and count >= MAX_LOGIN_PEERS
                ):
                    raise LoginLimited("login_rate_limited")
            for key in ("global", peer_key):
                connection.execute(
                    """INSERT INTO auth_login_attempts VALUES(?,?,1)
                    ON CONFLICT(peer) DO UPDATE SET attempts=attempts+1""",
                    (key, now),
                )

    @staticmethod
    def _new_session(
        connection: sqlite3.Connection, account: sqlite3.Row, *, remember: bool
    ) -> AuthSession:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expires = time.time() + (REMEMBER_SECONDS if remember else SESSION_SECONDS)
        connection.execute("DELETE FROM auth_sessions WHERE expires<=?", (time.time(),))
        # Bound accumulation by keeping the newest 32 sessions for a personal owner.
        connection.execute("""DELETE FROM auth_sessions WHERE digest IN
            (SELECT digest FROM auth_sessions ORDER BY expires DESC LIMIT -1 OFFSET 31)""")
        connection.execute(
            "INSERT INTO auth_sessions VALUES(?,?,?,?,?)",
            (_digest(token), csrf, expires, int(remember), account["generation"]),
        )
        return AuthSession(
            token, str(account["username"]), csrf, expires, remember, bool(account["must_change"])
        )

    def login(
        self, username: str, password: str, *, remember: bool, peer: str
    ) -> AuthSession | None:
        self._reserve_login(peer)
        account = self._account()
        valid = self._matches_password(account, password)
        if not valid or not hmac.compare_digest(
            username.encode("utf-8"), str(account["username"]).encode("utf-8")
        ):
            return None
        with self._connection() as connection:
            # A concurrent password change must not let an old password mint a session.
            current = connection.execute("SELECT * FROM auth_owner WHERE id=1").fetchone()
            if current is None or current["generation"] != account["generation"]:
                return None
            connection.execute(
                "DELETE FROM auth_login_attempts WHERE peer=?", ("peer:" + _digest(peer),)
            )
            return self._new_session(connection, current, remember=remember)

    def session(self, token: str) -> AuthSession | None:
        if not token or len(token) > 128:
            return None
        with self._connection() as connection:
            row = connection.execute(
                """SELECT s.*, o.username, o.must_change FROM auth_sessions s
                JOIN auth_owner o ON s.generation=o.generation WHERE s.digest=? AND s.expires>?""",
                (_digest(token), time.time()),
            ).fetchone()
        if row is None:
            return None
        return AuthSession(
            token,
            str(row["username"]),
            str(row["csrf"]),
            float(row["expires"]),
            bool(row["remember"]),
            bool(row["must_change"]),
        )

    def logout(self, token: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE digest=?", (_digest(token),))

    def account_ready(self) -> bool:
        return not bool(self._account()["must_change"])

    def valid_api_token(self, token: str) -> bool:
        if not token or len(token) > 1024:
            return False
        with self._connection() as connection:
            row = connection.execute("""SELECT t.digest FROM auth_api_tokens t
                JOIN auth_owner o ON o.id=t.id WHERE o.must_change=0""").fetchone()
        return row is not None and hmac.compare_digest(_digest(token), str(row["digest"]))

    def api_token_configured(self) -> bool:
        with self._connection() as connection:
            return connection.execute("SELECT 1 FROM auth_api_tokens").fetchone() is not None

    def _authorize_password(
        self, token: str, password: str | None, *, optional: bool = False
    ) -> tuple[AuthSession, sqlite3.Row]:
        self._reserve_login("account:" + _digest(token))
        session = self.session(token)
        account = self._account()
        if session is None:
            raise ValueError("session_revoked")
        if not optional or password:
            if not password or not self._matches_password(account, password):
                raise ValueError("invalid_current_password")
        return session, account

    def change_credentials(
        self, token: str, current_password: str | None, username: str, password: str
    ) -> AuthSession:
        validate_credentials(username, password)
        session = self.session(token)
        if session is None:
            raise ValueError("session_revoked")
        optional = bool(session.must_change_credentials)
        session, account = self._authorize_password(token, current_password, optional=optional)
        salt = secrets.token_bytes(16)
        with self._hash_lock:
            password_hash = _hash(password, salt)
        with self._connection() as connection:
            current = connection.execute("SELECT generation FROM auth_owner WHERE id=1").fetchone()
            valid_session = connection.execute(
                "SELECT 1 FROM auth_sessions WHERE digest=? AND expires>?",
                (_digest(token), time.time()),
            ).fetchone()
            if current is None or valid_session is None or current[0] != account["generation"]:
                raise ValueError("session_revoked")
            connection.execute(
                "UPDATE auth_owner SET username=?,salt=?,password_hash=?,must_change=0,generation=generation+1 WHERE id=1",
                (username, salt.hex(), password_hash),
            )
            connection.execute("DELETE FROM auth_sessions")
            connection.execute("DELETE FROM auth_api_tokens")
            replacement = connection.execute("SELECT * FROM auth_owner WHERE id=1").fetchone()
            if replacement is None:
                raise RuntimeError("Authentication owner disappeared during credential update")
            return self._new_session(connection, replacement, remember=session.remember)

    def rotate_api_token(self, token: str, current_password: str) -> str:
        session, account = self._authorize_password(token, current_password)
        if session.must_change_credentials:
            raise ValueError("credentials_change_required")
        value = secrets.token_urlsafe(32)
        with self._connection() as connection:
            current = connection.execute("SELECT generation FROM auth_owner WHERE id=1").fetchone()
            valid_session = connection.execute(
                "SELECT 1 FROM auth_sessions WHERE digest=? AND expires>?",
                (_digest(token), time.time()),
            ).fetchone()
            if current is None or valid_session is None or current[0] != account["generation"]:
                raise ValueError("session_revoked")
            connection.execute(
                "INSERT OR REPLACE INTO auth_api_tokens VALUES(1,?)", (_digest(value),)
            )
        return value

    def recover_credentials(self, username: str, password: str) -> None:
        """Administrative credential reset from local authority.

        Revokes all active browser sessions and API tokens, clears attempt rate limits,
        and sets must_change=0.
        """
        validate_credentials(username, password)
        salt = secrets.token_bytes(16)
        with self._hash_lock:
            password_hash = _hash(password, salt)
        with self._connection() as connection:
            connection.execute(
                "UPDATE auth_owner SET username=?,salt=?,password_hash=?,must_change=0,generation=generation+1 WHERE id=1",
                (username, salt.hex(), password_hash),
            )
            connection.execute("DELETE FROM auth_sessions")
            connection.execute("DELETE FROM auth_api_tokens")
            connection.execute("DELETE FROM auth_login_attempts")

