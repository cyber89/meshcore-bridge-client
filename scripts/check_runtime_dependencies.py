"""Verify core minimum versions and the evaluated ASGI pins with this interpreter."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import os
import re
import sys
from collections.abc import Callable

DEPENDENCIES = (
    ("paho-mqtt", "paho.mqtt.client", (2, 1, 0)),
    ("meshcore", "meshcore", (2, 3, 15)),
    ("pyserial", "serial", (3, 5, 0)),
    ("python-dotenv", "dotenv", (1, 2, 4)),
)

WEB_DEPENDENCIES = (
    ("fastapi", "fastapi", (0, 143, 0)),
    ("uvicorn", "uvicorn", (0, 54, 0)),
    ("pydantic", "pydantic", (2, 14, 0)),
    ("websockets", "websockets", (17, 2)),
    ("starlette", "starlette", (1, 7, 0)),
    ("h11", "h11", (0, 16, 0)),
)

# ASGI hooks use these versions' protocol and middleware interfaces. A newer
# importable distribution is not evidence that those interfaces are compatible.
WEB_PINNED_VERSIONS = {
    distribution: ".".join(map(str, release))
    for distribution, _module, release in WEB_DEPENDENCIES
}

PROFILES: dict[str, tuple[tuple[str, str, tuple[int, ...]], ...]] = {
    "core": DEPENDENCIES,
    "web": DEPENDENCIES + WEB_DEPENDENCIES,
}

MIN_PYTHON_VERSION = (3, 14, 8)


def _stable_release(version: str) -> tuple[int, ...] | None:
    """Normalize final numeric releases without accepting pre/post/local suffixes."""
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", version) is None:
        return None
    parts = tuple(int(part) for part in version.split("."))
    while len(parts) > 1 and parts[-1] == 0:
        parts = parts[:-1]
    return parts


def check_dependencies(
    importer: Callable[[str], object] = importlib.import_module,
    version_reader: Callable[[str], str] = importlib.metadata.version,
    dependencies: tuple[tuple[str, str, tuple[int, ...]], ...] | None = None,
    profile: str | None = None,
) -> list[str]:
    """Return all failures; importing one package never certifies another."""
    failures = []
    if sys.version_info[:3] < MIN_PYTHON_VERSION or sys.version_info.releaselevel != "final":
        return ["Python requiere >=3.14.8 estable"]
    if dependencies is None:
        selected_profile = (
            profile if profile is not None else os.getenv("MESHCORE_PROFILE", "web")
        ).strip().lower()
        dependencies = PROFILES.get(selected_profile)
        if dependencies is None:
            failures.append("Perfil de dependencias inválido; use core o web")
            return failures
    for distribution, module, minimum in dependencies:
        try:
            importer(module)
            version = version_reader(distribution)
            pinned = WEB_PINNED_VERSIONS.get(distribution)
            if pinned is not None:
                if _stable_release(version) != _stable_release(pinned):
                    failures.append(f"{distribution}: {version}, requiere == {pinned}")
                continue
            match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", version)
            if match is None:
                failures.append(f"{distribution}: versión no verificable")
                continue
            release = tuple(int(part or 0) for part in match.groups())
            prerelease_at_minimum = release == minimum and bool(re.search(r"(?:a|b|rc|dev)\d*", version[match.end():]))
            if release < minimum or prerelease_at_minimum:
                failures.append(f"{distribution}: {version}, requiere >= {'.'.join(map(str, minimum))}")
        except Exception as exc:
            failures.append(f"{distribution}: {type(exc).__name__}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verificador de dependencias de MeshCore Bridge por perfil.")
    parser.add_argument(
        "--profile",
        choices=["core", "web"],
        default=os.getenv("MESHCORE_PROFILE", "web"),
        help="Perfil de dependencias a verificar (core: headless mínimo; web: core + stack ASGI).",
    )
    args = parser.parse_args(argv)
    failures = check_dependencies(profile=args.profile)
    for failure in failures:
        print(f"[ERROR] {failure}", file=sys.stderr)
    if not failures:
        print(f"Dependencias del perfil '{args.profile}' verificadas con {sys.executable}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
