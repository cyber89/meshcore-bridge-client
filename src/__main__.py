"""
Main CLI entrypoint when running `python -m src`.
"""

import sys
from pathlib import Path


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    import meshcore_bridge

    meshcore_bridge.main()


if __name__ == "__main__":
    main()
