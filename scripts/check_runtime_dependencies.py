"""Verify production imports and minimum distribution versions using this interpreter."""

from __future__ import annotations

import importlib
import importlib.metadata
import re
import sys
from collections.abc import Callable

DEPENDENCIES = (
    ("paho-mqtt", "paho.mqtt.client", (2, 1, 0)),
    ("meshcore", "meshcore", (2, 3, 8)),
    ("pyserial", "serial", (3, 5, 0)),
    ("python-dotenv", "dotenv", (1, 0, 1)),
)


def check_dependencies(
    importer: Callable[[str], object] = importlib.import_module,
    version_reader: Callable[[str], str] = importlib.metadata.version,
) -> list[str]:
    """Return all failures; importing one package never certifies another."""
    failures = []
    if sys.version_info < (3, 10):  # noqa: UP036 - installer may select an unsupported host Python
        failures.append("Python requiere >=3.10")
    for distribution, module, minimum in DEPENDENCIES:
        try:
            importer(module)
            version = version_reader(distribution)
            match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", version)
            if match is None:
                failures.append(f"{distribution}: versión no verificable")
                continue
            release = tuple(int(part or 0) for part in match.groups())
            prerelease_at_minimum = release == minimum and bool(re.search(r"(?:a|b|rc|dev)\d*", version[match.end():]))
            if release < minimum or prerelease_at_minimum:
                failures.append(f"{distribution}: {version}, requiere >= {'.'.join(map(str, minimum))}")
        except Exception as exc:
            failures.append(f"{distribution}: {type(exc).__name__}: {exc}")
    return failures


def main() -> int:
    failures = check_dependencies()
    for failure in failures:
        print(f"[ERROR] {failure}", file=sys.stderr)
    if not failures:
        print(f"Dependencias de producción verificadas con {sys.executable}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
