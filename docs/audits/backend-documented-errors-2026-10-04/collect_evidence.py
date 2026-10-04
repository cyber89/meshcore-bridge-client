"""Collect isolated QA evidence for the documented backend corrections."""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEST = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "tests/artifacts/backend-documented-errors"


def junit(filename: str) -> dict:
    root = ET.parse(ARTIFACTS / filename).getroot()
    cases = list(root.iter("testcase"))
    return {
        "artifact": filename,
        "tests": len(cases),
        "failures": [
            {"module": case.get("classname"), "name": case.get("name"), "message": case.find("failure").get("message")}
            for case in cases if case.find("failure") is not None
        ],
        "errors": len(list(root.iter("error"))),
        "skipped": [
            {"name": case.get("name"), "reason": case.find("skipped").get("message")}
            for case in cases if case.find("skipped") is not None
        ],
        "modules": dict(Counter(case.get("classname") for case in cases)),
    }


def main() -> None:
    tools = {}
    for name in ("pytest-accepted", "mypy-final", "ruff-final", "docs-final", "legacy-baseline", "runtime-baseline"):
        report = json.loads((ARTIFACTS / f"{name}.json").read_text(encoding="utf-8"))
        tools[name] = [{
            **{key: value for key, value in entry.items() if key != "stdout"},
            "stdout_summary": entry["stdout"].strip().splitlines()[-1],
        } for entry in report["tools"]]
    files = [
        "src/admin/local_config_executor.py", "src/admin/repeater_executor.py",
        "src/contact_manager.py", "src/metrics_aggregator.py", "src/protocol_types.py",
        "src/web/controllers/contacts_controller.py", "tests/test_admin_executor_type_boundaries.py",
        "tests/test_sensitive_mapping.py", "tests/test_admin_official_compatibility.py",
        "tests/test_node_and_repeater_config.py", "tests/test_repeater_manager_unit.py",
    ]
    summary = {
        "baseline": "6b2480c4bb9cbf8c93e26a0d11fb6e51d2783849",
        "versions": {"python": "3.12.14", "pytest": "9.1.1", "mypy": "2.3.1", "ruff": "0.16.3"},
        "scope": "SDK/MQTT mocks, temporary JSON, virtual adapters, OS-assigned loopback ports; no physical RF",
        "runs": [junit(name) for name in (
            "junit.xml", "junit-legacy-baseline.xml", "junit-runtime-baseline.xml",
            "junit-final.xml", "junit-accepted.xml",
        )],
        "quality_tools": tools,
        "python_coverage": ET.parse(ARTIFACTS / "coverage-accepted.xml").getroot().attrib,
        "tested_sha256_normalized_lf": {
            path: hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for path in files
        },
        "limitations": [
            "Selected 14 backend test modules, not the full maintained suite.",
            "One symlink test is skipped because this Windows platform cannot create its symlink fixture.",
            "No new browser run, hardware roundtrip, performance or interoperability certification.",
            "Runtime used Python 3.12; mypy/ruff target Python 3.10, not a Python 3.10 runtime execution.",
        ],
    }
    (DEST / "verification-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Archived verification-summary.json")


if __name__ == "__main__":
    main()
