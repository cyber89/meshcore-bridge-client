"""Compatibility entrypoint for the canonical project QA runner."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from scripts.run_quality_checks import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
