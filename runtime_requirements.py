"""Reject unsupported runtimes before loading configuration or infrastructure."""

import sys


def require_stable_python(version: tuple[int, int, int, str, int] | None = None) -> None:
    """Require stable Python 3.12 or newer; 3.13.5 is recommended."""
    current = sys.version_info if version is None else version
    if current[:2] < (3, 12) or current[3] != "final":
        raise SystemExit(
            f"MeshCore Bridge requires stable Python >= 3.12 (detected {current[0]}.{current[1]}.{current[2]} {current[3]}); "
            "Python 3.13.5 is recommended; later stable versions are also accepted."
        )


require_stable_python()
