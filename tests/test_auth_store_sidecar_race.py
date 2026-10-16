"""Authentication file permissions survive SQLite sidecar cleanup races."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.web.auth_store import AuthStore


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
def test_auth_query_survives_sidecar_removed_before_chmod(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    sidecar = Path(f"{store.path}{suffix}")
    sidecar.touch()
    actual_chmod = os.chmod

    def chmod_after_cleanup(path: str | os.PathLike[str], mode: int) -> None:
        if Path(path) == sidecar:
            sidecar.unlink()
        actual_chmod(path, mode)

    monkeypatch.setattr(os, "chmod", chmod_after_cleanup)

    assert not store.has_account()
    assert store.path.is_file()
    assert not sidecar.exists()


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm"])
def test_auth_file_permission_errors_are_not_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    protected = Path(f"{store.path}{suffix}")
    protected.touch()
    actual_chmod = os.chmod

    def chmod_denied(path: str | os.PathLike[str], mode: int) -> None:
        if Path(path) == protected:
            raise PermissionError("permissions denied")
        actual_chmod(path, mode)

    monkeypatch.setattr(os, "chmod", chmod_denied)

    with pytest.raises(PermissionError, match="permissions denied"):
        store.has_account()


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
def test_auth_query_survives_windows_sidecar_removal_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    sidecar = Path(f"{store.path}{suffix}")
    sidecar.touch()
    actual_chmod = os.chmod

    def chmod_during_removal(path: str | os.PathLike[str], mode: int) -> None:
        if Path(path) == sidecar:
            sidecar.unlink()
            raise PermissionError("Windows sidecar deletion in progress")
        actual_chmod(path, mode)

    monkeypatch.setattr(os, "chmod", chmod_during_removal)
    assert not store.has_account()
    assert store.path.is_file()


def test_auth_database_removed_before_chmod_is_not_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    store.initialize()
    actual_chmod = os.chmod

    def chmod_after_database_removal(path: str | os.PathLike[str], mode: int) -> None:
        if Path(path) == store.path:
            store.path.unlink()
        actual_chmod(path, mode)

    monkeypatch.setattr(os, "chmod", chmod_after_database_removal)

    with pytest.raises(FileNotFoundError):
        store.has_account()
    assert not store.path.exists()


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm"])
def test_auth_detected_symlink_is_rejected_before_permission_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    rejected = Path(f"{store.path}{suffix}")
    actual_is_symlink = Path.is_symlink

    def is_symlink(path: Path) -> bool:
        return path == rejected or actual_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)

    with pytest.raises(ValueError, match="must not be symbolic links"):
        store.initialize()


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm"])
@pytest.mark.parametrize("dangling", [False, True])
def test_auth_database_and_sidecar_symlinks_are_rejected(
    tmp_path: Path, suffix: str, dangling: bool
) -> None:
    store = AuthStore(tmp_path / "station.sqlite3")
    target = tmp_path / "link-target"
    if not dangling:
        target.touch()
    link = Path(f"{store.path}{suffix}")
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"Symlinks are unavailable on this filesystem: {error}")

    with pytest.raises(ValueError, match="must not be symbolic links"):
        store.initialize()
