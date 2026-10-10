"""Supported interpreters are checked before production imports."""

from pathlib import Path

import pytest

from runtime_requirements import require_stable_python
from scripts import staged_update


@pytest.mark.parametrize("version", [
    (3, 10, 99, "final", 0), (3, 11, 99, "final", 0),
    (3, 12, 0, "alpha", 1), (3, 13, 5, "candidate", 2),
    (3, 15, 0, "beta", 1),
])
def test_rejects_older_and_prerelease_python(version: tuple[int, int, int, str, int]) -> None:
    with pytest.raises(SystemExit, match="stable Python >= 3.12"):
        require_stable_python(version)


@pytest.mark.parametrize("version", [(3, 12, 0, "final", 0), (3, 13, 5, "final", 0), (3, 14, 8, "final", 0), (3, 15, 0, "final", 0)])
def test_accepts_stable_supported_python(version: tuple[int, int, int, str, int]) -> None:
    require_stable_python(version)


def test_staged_release_requires_runtime_guard(tmp_path: Path) -> None:
    source, target = tmp_path / "source", tmp_path / "installation"
    source.mkdir()
    target.mkdir()
    for name in staged_update.REQUIRED:
        if name == "runtime_requirements.py":
            continue
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("isolated fixture", encoding="utf-8")
    with pytest.raises(ValueError, match="runtime_requirements.py"):
        staged_update.prepare(source, target)
