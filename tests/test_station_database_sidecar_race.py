"""Public station queries survive stale sidecar metadata without hiding denials."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.station_database import StationDatabase


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
@pytest.mark.parametrize("error_type", [FileNotFoundError, PermissionError])
def test_query_survives_sidecar_disappearing_during_permission_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, error_type: type[OSError],
) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    sidecar = Path(f"{database.path}{suffix}")
    removed = False
    actual_exists, actual_chmod = Path.exists, os.chmod

    def observed_exists(path: Path) -> bool:
        return not removed if path == sidecar else actual_exists(path)

    def cleanup_during_chmod(path: str | os.PathLike[str], mode: int) -> None:
        nonlocal removed
        if Path(path) == sidecar:
            removed = True
            raise error_type("sidecar disappeared")
        actual_chmod(path, mode)

    monkeypatch.setattr(Path, "exists", observed_exists)
    monkeypatch.setattr(os, "chmod", cleanup_during_chmod)
    assert database.read_document("nodes") is None
    assert removed
    assert database.path.is_file()


@pytest.mark.parametrize("suffix,error_type", [
    ("", PermissionError), ("-wal", PermissionError), ("-shm", PermissionError),
    ("", FileNotFoundError),
])
def test_query_does_not_hide_permission_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, error_type: type[OSError],
) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    protected = Path(f"{database.path}{suffix}")
    actual_exists, actual_chmod = Path.exists, os.chmod
    monkeypatch.setattr(Path, "exists", lambda path: path == protected or actual_exists(path))

    def denied(path: str | os.PathLike[str], mode: int) -> None:
        if Path(path) == protected:
            raise error_type("real denial")
        actual_chmod(path, mode)

    monkeypatch.setattr(os, "chmod", denied)
    with pytest.raises(error_type, match="real denial"):
        database.read_document("nodes")


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
def test_query_rejects_detected_dangling_sidecar_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str,
) -> None:
    database = StationDatabase(tmp_path / "station.sqlite3")
    database.initialize()
    sidecar = Path(f"{database.path}{suffix}")
    actual_exists, actual_is_symlink = Path.exists, Path.is_symlink
    monkeypatch.setattr(Path, "exists", lambda path: False if path == sidecar else actual_exists(path))
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == sidecar or actual_is_symlink(path))
    with pytest.raises(ValueError, match="must not be symbolic links"):
        database.read_document("nodes")
