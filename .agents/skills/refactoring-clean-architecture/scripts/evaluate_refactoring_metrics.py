#!/usr/bin/env python3
"""Compatibility entry point for the maintained recursive AST metrics helper."""
import sys
from pathlib import Path

current = Path(__file__).resolve().parent
while current.parent != current:
    if (current / "src").is_dir() and (current / "config.py").is_file():
        break
    current = current.parent
sys.path.insert(0, str(current))
from scripts.evaluate_refactoring_metrics import (  # noqa: E402,F401
    analyze_file_metrics,
    calculate_cyclomatic_complexity,
    get_project_root,
)
from scripts.evaluate_refactoring_metrics import main as _main  # noqa: E402


def main() -> int:
    return _main(root=get_project_root())

if __name__ == "__main__":
    raise SystemExit(main())
