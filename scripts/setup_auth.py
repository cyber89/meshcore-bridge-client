"""Prepare the restricted default web account without interactive input.

This synchronous installer helper never starts the bridge or contacts hardware.
Existing accounts are preserved. New installations start with admin:admin and
require an immediate credential change in the web profile before station access.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Installed project directory containing config.py and src/",
    )
    arguments = parser.parse_args()
    project_dir = arguments.project_dir.resolve()
    if not (project_dir / "config.py").is_file() or not (project_dir / "src").is_dir():
        parser.error("The project directory must contain config.py and src/.")
    os.chdir(project_dir)
    sys.path.insert(0, str(project_dir))
    # Resolve the same .env, DATA_DIR and DATABASE_PATH used by the installed bridge.
    import config
    from src.web.auth_store import AuthStore

    store = AuthStore(Path(config.DATABASE_PATH))
    store.initialize()
    if store.has_account():
        print("Existing web account preserved. Change credentials in the web profile.")
        return 0
    if store.bootstrap_default():
        print(
            "Default account admin:admin created. Change credentials immediately after first login before station access."
        )
    else:
        print("An account was created concurrently; its credentials were preserved.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nAccount setup cancelled.", file=sys.stderr)
        raise SystemExit(130) from None
    except Exception:
        # Do not reveal configuration or credential data in installer error output.
        print(
            "Account setup failed. Check database permissions and configuration.", file=sys.stderr
        )
        raise SystemExit(1) from None
