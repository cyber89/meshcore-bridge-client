"""Installer account regressions using only a temporary authentication database."""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scripts import setup_auth
from src.web.auth_store import AuthStore


class _ForbiddenInstallerInput(io.TextIOBase):
    def isatty(self) -> bool:
        raise AssertionError("Account provisioning must not inspect interactive input")

    def read(self, size: int | None = -1) -> str:
        raise AssertionError("Account provisioning must not read interactive input")


def _isolate_installer(monkeypatch: pytest.MonkeyPatch, database_path: Path) -> None:
    configuration = ModuleType("config")
    configuration.__dict__["DATABASE_PATH"] = str(database_path)
    monkeypatch.setitem(sys.modules, "config", configuration)
    project_dir = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(sys, "argv", ["setup_auth.py", "--project-dir", str(project_dir)])
    monkeypatch.setattr(sys, "stdin", _ForbiddenInstallerInput())
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(os, "chdir", lambda _directory: None)


def test_install_creates_default_account_without_interactive_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "station.sqlite3"
    _isolate_installer(monkeypatch, database_path)

    assert setup_auth.main() == 0

    store = AuthStore(database_path)
    session = store.login("admin", "admin", remember=True, peer="installer-regression")
    assert session is not None
    assert session.must_change_credentials
    assert not store.account_ready()


def test_reinstall_preserves_owner_sessions_and_api_token_without_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "station.sqlite3"
    store = AuthStore(database_path)
    store.initialize()
    store.bootstrap("owner", "correct horse battery staple")
    session = store.login(
        "owner", "correct horse battery staple", remember=True, peer="installer-regression"
    )
    assert session is not None
    token = store.rotate_api_token(session.token, "correct horse battery staple")
    _isolate_installer(monkeypatch, database_path)

    assert setup_auth.main() == 0

    restored = store.session(session.token)
    assert restored is not None and restored.username == "owner"
    assert not restored.must_change_credentials
    assert store.account_ready()
    assert store.valid_api_token(token)
    assert store.login("admin", "admin", remember=False, peer="default-check") is None
