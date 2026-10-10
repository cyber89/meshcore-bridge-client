"""Reject unsupported runtimes before loading configuration or infrastructure."""

import sys


def require_stable_python(version: tuple[int, int, int, str, int] | None = None) -> None:
    """The bridge runs on Python 3.11 or newer."""
    current = sys.version_info if version is None else version
    if current[:2] < (3, 11):
        raise SystemExit(
            f"MeshCore Bridge requires Python >= 3.11 (detected {current[0]}.{current[1]}.{current[2]}); "
            "older versions are unsupported."
        )


require_stable_python()
