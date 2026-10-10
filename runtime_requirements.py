"""Reject unsupported runtimes before loading configuration or infrastructure."""

import sys


def require_stable_python(version: tuple[int, int, int, str, int] | None = None) -> None:
    """The bridge runs exclusively on stable Python 3.14.8 or newer."""
    current = sys.version_info if version is None else version
    if current[:3] < (3, 14, 8) or current[3] != "final":
        raise SystemExit(
            "MeshCore Bridge requires stable Python >= 3.14.8; "
            "older versions and prereleases are unsupported."
        )


require_stable_python()
