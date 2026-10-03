"""Record focused static diagnostics; never import the application."""
from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
FILES = [
    "src/admin/local_config_executor.py", "src/admin/repeater_executor.py",
    "src/admin/sdk_commands.py", "src/protocol_types.py", "src/repeater_manager.py",
    "src/routers/advert_handler.py", "src/web/controllers/base.py",
    "src/web/controllers/config_controller.py", "src/web/controllers/repeater_controller.py",
]


def main() -> None:
    checks = []
    for module, flags in (("ruff", ["check"]), ("mypy", ["--strict"])):
        command = [sys.executable, "-m", module, *flags, *FILES]
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            record = {
                "tool": module, "command": command, "exit_code": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired as error:
            record = {"tool": module, "command": command, "timeout": str(error)}
        checks.append(record)
        print(json.dumps(record))
    Path(__file__).with_name("static-results.json").write_text(
        json.dumps({
            "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "python": sys.version, "versions": {name: version(name) for name in ("ruff", "mypy")},
            "scope": FILES, "checks": checks,
        }, indent=2) + "\n", encoding="utf-8",
    )


if __name__ == "__main__":
    main()
