"""Stage and replace only application release files, keeping rollback copies.

This helper does not control services, install dependencies or inspect .env/data.
The caller stops the service after preparation and keeps it stopped until the
multi-component switch completes. Each rename is atomic on the same filesystem;
the complete switch is transactional through explicit rollback, not one rename.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import venv
from pathlib import Path
from typing import TypedDict, cast

COMPONENTS = (
    "src", "scripts", "docs", "config.py", "runtime_requirements.py", "meshcore_bridge.py", "requirements.txt",
    "requirements-web.txt", "pyproject.toml", "meshcore-bridge.service", ".env.example",
    "run_interactive_demo.py", "install.sh", "install.ps1", "venv",
)
REQUIRED = ("src/__init__.py", "src/__main__.py", "src/bridge_core.py", "config.py",
            "runtime_requirements.py", "meshcore_bridge.py", "requirements.txt", "meshcore-bridge.service")
MARKER = "update-state.json"


class UpdateState(TypedDict):
    target: str
    moved: list[str]
    installed: list[str]


def prepare(source: Path, target: Path) -> Path:
    """Copy a complete independent release before the caller stops anything."""
    source, target = source.resolve(), target.resolve()
    if not target.is_dir() or target.parent == target:
        raise ValueError("Destino debe ser una instalación existente y no la raíz")
    for relative in REQUIRED:
        if not (source / relative).is_file():
            raise ValueError(f"Release incompleto: {relative}")
    stage = Path(tempfile.mkdtemp(prefix=".meshcore-stage-", dir=target.parent))
    try:
        release = stage / "release"
        release.mkdir()
        (stage / "backup").mkdir()
        for component in COMPONENTS:
            # A fresh venv is constructed by the caller; don't clone interpreter state.
            if component == "venv":
                continue
            item = source / component
            if item.is_dir():
                shutil.copytree(item, release / component, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            elif item.is_file():
                shutil.copy2(item, release / component)
        state: UpdateState = {"target": str(target), "moved": [], "installed": []}
        (stage / MARKER).write_text(json.dumps(state), encoding="utf-8")
        return stage
    except BaseException:
        shutil.rmtree(stage)
        raise


def _state(stage: Path) -> UpdateState:
    stage = stage.resolve()
    decoded = json.loads((stage / MARKER).read_text(encoding="utf-8"))
    if not isinstance(decoded, dict) or not isinstance(decoded.get("target"), str):
        raise ValueError("Journal de actualización inválido")
    state = cast(UpdateState, decoded)
    original_target = Path(state["target"])
    if not original_target.is_absolute() or original_target.is_symlink():
        raise ValueError("Destino de journal debe ser absoluto y no symlink")
    target = original_target.resolve()
    if not target.is_dir() or target.parent == target:
        raise ValueError("Destino de journal debe ser una instalación y no raíz")
    if not stage.name.startswith(".meshcore-stage-") or stage.parent != target.parent or stage == target:
        raise ValueError("Directorio staging no pertenece al destino verificado")
    for key in ("moved", "installed"):
        entries = decoded.get(key)
        if not isinstance(entries, list) or any(not isinstance(item, str) or item not in COMPONENTS for item in entries):
            raise ValueError("Componente de rollback inválido")
    return state


def _write_state(stage: Path, state: UpdateState) -> None:
    temporary = stage / (MARKER + ".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    os.replace(temporary, stage / MARKER)


def apply(stage: Path) -> None:
    state = _state(stage)
    target = Path(str(state["target"]))
    moved = list(state["moved"])
    installed = list(state["installed"])
    if moved or installed:
        raise ValueError("Staging ya aplicado; completar o revertir antes de repetir")
    try:
        for component in COMPONENTS:
            candidate = stage / "release" / component
            if not candidate.exists():
                continue
            previous = target / component
            if previous.exists():
                moved.append(component)
                state["moved"] = moved
                _write_state(stage, state)
                os.replace(previous, stage / "backup" / component)
            installed.append(component)
            state["installed"] = installed
            _write_state(stage, state)
            os.replace(candidate, previous)
    except BaseException:
        rollback(stage)
        raise


def rollback(stage: Path) -> None:
    """Recover existing components, preserving operational files byte for byte."""
    state = _state(stage)
    target = Path(str(state["target"]))
    for component in reversed(list(state["installed"])):
        installed = target / str(component)
        if installed.exists():
            backup = stage / "backup" / str(component)
            # If backup is missing while a prior file hasn't moved, don't remove it.
            if component in state["moved"] and not backup.exists():
                continue
            quarantine = stage / "release" / str(component)
            if quarantine.exists():
                if quarantine.is_dir():
                    shutil.rmtree(quarantine)
                else:
                    quarantine.unlink()
            os.replace(installed, quarantine)
    for component in reversed(list(state["moved"])):
        backup = stage / "backup" / str(component)
        if backup.exists():
            os.replace(backup, target / str(component))
    state["moved"], state["installed"] = [], []
    _write_state(stage, state)


def finish(stage: Path) -> None:
    _state(stage)  # Validate the exact absolute target before recursive deletion.
    shutil.rmtree(stage)


def relocate_environment(stage: Path) -> None:
    """Rebuild activation/config locally and replace relocated console shebangs.

    Installed distributions remain in place. No pip/network operation is used.
    The caller must retain rollback until this and the final dependency probe pass.
    """
    state = _state(stage)
    environment = Path(state["target"]) / "venv"
    if environment.is_symlink() or not environment.is_dir():
        raise ValueError("Entorno de release inexistente o symlink")
    previous = str(stage.resolve() / "release" / "venv")
    venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(str(environment))
    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    for entry in scripts.iterdir():
        if entry.is_symlink() or not entry.is_file():
            continue
        content = entry.read_bytes()
        if not content.startswith(b"#!"):
            continue
        updated = content.replace(previous.encode(), str(environment).encode())
        if updated != content:
            entry.write_bytes(updated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "apply", "rollback", "finish", "relocate"))
    parser.add_argument("path", type=Path)
    parser.add_argument("target", type=Path, nargs="?")
    args = parser.parse_args()
    if args.action == "prepare":
        if args.target is None:
            parser.error("prepare requiere origen y destino")
        print(prepare(args.path, args.target))
    else:
        {"apply": apply, "rollback": rollback, "finish": finish, "relocate": relocate_environment}[args.action](args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
