"""Archive this audit's local reports without importing application configuration."""
from __future__ import annotations

import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEST = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "tests/artifacts/frontend-exhaustive"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def junit(name: str) -> dict:
    root = ET.parse(ARTIFACTS / name).getroot()
    cases = list(root.iter("testcase"))
    return {
        "artifact": name,
        "tests": len(cases),
        "failures": len(list(root.iter("failure"))),
        "errors": len(list(root.iter("error"))),
        "skipped": len(list(root.iter("skipped"))),
        "modules": dict(Counter(case.get("classname") for case in cases)),
    }


def main() -> None:
    tools = {}
    for name in ("final-quality", "log-states-final", "types", "lint"):
        result = read_json(ARTIFACTS / f"{name}.json")
        # Keep failed diagnostics; omit the large pytest output/table from this summary.
        entries = result["tools"]
        tools[name] = [
            {k: v for k, v in tool.items() if k != "stdout" or not tool["passed"]}
            for tool in entries
        ]
    coverage = ET.parse(ARTIFACTS / "final/coverage-final.xml").getroot().attrib
    contrasts = {}
    for phase in ("baseline", "final"):
        contrasts[phase] = {}
        for path in (ARTIFACTS / phase).glob("logs-*.json"):
            report = read_json(path)
            contrasts[phase][path.stem] = {
                "minimum_ratio": min(item["ratio"] for item in report["colors"]),
                "by_class_minimum": {
                    cls: min(item["ratio"] for item in report["colors"] if item["class"] == cls)
                    for cls in sorted({item["class"] for item in report["colors"]})
                },
                "box_background": report["boxBackground"],
                "scroll_width": report["scroll"],
                "viewport_width": report["width"],
                "message_widths": report.get("messageWidths"),
                "injected_images": report["injectedImages"],
            }
    screenshots = {
        "logs-before-light-desktop.png": ARTIFACTS / "baseline/logs-light-1920.png",
        "logs-final-light-desktop.png": ARTIFACTS / "final/logs-light-1920.png",
        "logs-final-light-mobile.png": ARTIFACTS / "final/logs-light-390.png",
        "remote-final-light-mobile.png": ARTIFACTS / "final/remote-rep-radio-light-es-320.png",
        "remote-final-light-landscape.png": ARTIFACTS / "final/remote-rep-radio-light-es-844.png",
        "dialog-final-light-landscape.png": ARTIFACTS / "final/dialog-light-844.png",
        "settings-final-light-desktop.png": ROOT / "tests/artifacts/frontend-ui/light-es-settings-1920.png",
        "nodes-final-dark-mobile.png": ROOT / "tests/artifacts/frontend-ui/dark-en-nodes-390.png",
    }
    image_dir = DEST / "screenshots"
    image_dir.mkdir(exist_ok=True)
    for name, source in screenshots.items():
        shutil.copyfile(source, image_dir / name)
    files = sorted((ROOT / "src/web/static").rglob("*.css")) + sorted((ROOT / "src/web/static").rglob("*.js")) + [ROOT / "src/web/static/index.html"]
    hashes = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in files
    }
    summary = {
        "baseline": "942ccd80b6d8af1d9c22cb9eef91c2cd75aa5702",
        "scope": "Chromium + virtual station; no physical radio or production broker",
        "versions": {"python": "3.12.14", "node": "24.19.0", "pytest": "9.1.1", "playwright": "1.62.0", "pytest_asyncio": "1.4.0", "ruff": "0.16.3", "mypy": "2.3.1"},
        "runs": [junit(name) for name in (
            "baseline/junit-repro.xml", "final/junit-first.xml", "final/junit-verified.xml",
            "final/junit-landscape-repro.xml", "final/junit-final.xml", "final/junit-log-states.xml",
        )],
        "quality_tools": tools,
        "python_coverage": coverage,
        "computed_logs": contrasts,
        "screenshots": list(screenshots),
        "frontend_sha256_normalized_lf": hashes,
        "limitations": [
            "Python coverage is partial and does not measure JavaScript coverage.",
            "Error responses and authenticated remote-admin payloads are synthetic browser fetch responses.",
            "Static route/key/selector checks are lexical and not complete semantic verification.",
            "No cross-browser, screen-reader, performance, RF or universal parameter roundtrip certification.",
        ],
    }
    (DEST / "verification-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Archived verification-summary.json and 8 screenshots")


if __name__ == "__main__":
    main()
