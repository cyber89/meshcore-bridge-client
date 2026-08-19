"""
Main CLI entrypoint when running `python -m src`.
"""

import logging
import sys

from src.bridge_core import MeshCoreBridge


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    bridge = MeshCoreBridge()
    bridge.run_forever()

if __name__ == "__main__":
    main()
