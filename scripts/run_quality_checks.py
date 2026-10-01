"""Run project QA with the current interpreter and preserve machine-readable evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    command: list[str]
    exit_code: int
    duration_sec: float
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


def _decode(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def run_command(name: str, command: list[str], cwd: Path, timeout: float) -> ToolResult:
    """Missing dependencies and timeouts fail; they never fall back to another suite."""
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
    except FileNotFoundError as exc:
        code, stdout, stderr = 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        code, stdout, stderr = 124, _decode(exc.stdout), _decode(exc.stderr)
        stderr += f"\nTimeout after {timeout:g}s; partial output retained."
    return ToolResult(name, command, code, round(time.monotonic() - start, 3), stdout, stderr)


def build_commands(pytest_args: list[str], selected: str | None) -> list[tuple[str, list[str]]]:
    pytest_args = pytest_args[1:] if pytest_args[:1] == ["--"] else pytest_args
    commands = [
        ("pytest", [sys.executable, "-m", "pytest", *(pytest_args or ["tests"])]),
        ("mypy", [sys.executable, "-m", "mypy", "--strict", "src"]),
        ("ruff", [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"]),
        ("documentation", [sys.executable, "scripts/validate_project_docs.py"]),
    ]
    return [(name, command) for name, command in commands if selected in (None, name)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--only-tests", action="store_true")
    modes.add_argument("--only-types", action="store_true")
    modes.add_argument("--only-lint", action="store_true")
    modes.add_argument("--only-docs", action="store_true")
    parser.add_argument("--timeout", type=float, default=600.0, help="Timeout per tool, in seconds")
    parser.add_argument("--json", action="store_true", help="Print the complete JSON report")
    parser.add_argument("--report", type=Path, help="Also save the JSON report at this path")
    args, pytest_args = parser.parse_known_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    selected = next(
        (
            name
            for enabled, name in (
                (args.only_tests, "pytest"),
                (args.only_types, "mypy"),
                (args.only_lint, "ruff"),
                (args.only_docs, "documentation"),
            )
            if enabled
        ),
        None,
    )
    if pytest_args and selected not in (None, "pytest"):
        parser.error("pytest arguments require --only-tests or the full run")
    results = [
        run_command(name, command, ROOT, args.timeout)
        for name, command in build_commands(pytest_args, selected)
    ]
    report = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version,
        "all_passed": all(result.passed for result in results),
        "tools": [{**asdict(result), "passed": result.passed} for result in results],
    }
    encoded = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded + "\n", encoding="utf-8")
    if args.json:
        print(encoded)
    else:
        for result in results:
            print(
                f"{'PASS' if result.passed else 'FAIL'} {result.tool_name} "
                f"({result.duration_sec}s, exit {result.exit_code})"
            )
            if not result.passed:
                print(result.stdout + result.stderr)
            elif result.stdout.strip():
                print(result.stdout.strip().splitlines()[-1])
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
