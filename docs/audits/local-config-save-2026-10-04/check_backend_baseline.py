"""Reproduce historical executor failures without replacing the current checkout."""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    revision = "226f8aceb17bb35fb285dc8a2f6300bb05a0a577"
    source = subprocess.run(
        ["git", "show", f"{revision}:src/admin/local_config_executor.py"],
        check=True, capture_output=True, encoding="utf-8",
    ).stdout
    with patch("dotenv.load_dotenv", return_value=False):
        import src.admin_handler as admin_module
    baseline = ModuleType("local_config_executor_baseline")
    exec(compile(source, f"{revision}:local_config_executor.py", "exec"), baseline.__dict__)
    admin_module.LocalConfigExecutor = baseline.LocalConfigExecutor
    # Pytest's maintained autouse fixture supplies temporary files and mocks.
    result = int(pytest.main([
        "tests/test_local_config_save_roundtrip.py", "-q", "--no-cov",
        "--basetemp=tests/artifacts/local-config-baseline-tmp", "-p", "no:cacheprovider",
        "-k", "acknowledged_settings or unsupported",
        "--junitxml=tests/artifacts/local-config-baseline.xml",
    ]))
    suites = ET.parse("tests/artifacts/local-config-baseline.xml").getroot()
    cases = [{"name": case.get("name"), "failed": case.find("failure") is not None,
              "error": case.find("error") is not None} for case in suites.iter("testcase")]
    receipt = {"revision": revision, "exit_code": result, "cases": cases,
               "passed": sum(not case["failed"] and not case["error"] for case in cases),
               "failed": sum(case["failed"] for case in cases),
               "errors": sum(case["error"] for case in cases)}
    Path(__file__).with_name("backend-before.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    sys.exit(main())
