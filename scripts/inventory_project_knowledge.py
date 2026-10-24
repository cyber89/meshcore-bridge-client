"""Read-only inventory of documentation, source, skills and reference provenance.

Print JSON to stdout; never import application modules, read operator data, fetch
repositories or execute their code. A reference needs its own .git marker: Git's
upward discovery would otherwise misattribute the parent project's commit.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = {"meshcore", "meshcore_py", "meshcore_cli"}
VENDORS = {
    "archify",
    "ui-ux-pro-max",
    "code-review",
    "diagnosing-bugs",
    "improve-codebase-architecture",
    "systematic-debugging",
    "verification-before-completion",
    "test-driven-development",
}


def git_value(directory: Path, *arguments: str) -> str | None:
    """Run bounded read-only Git metadata queries, with errors made explicit."""
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(directory), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def documents() -> list[dict[str, object]]:
    paths = sorted((ROOT / "docs").rglob("*.md"))
    paths += [ROOT / name for name in ("README.md", "AGENTS.md", "CONTEXT.md", "nuevo.md")]
    paths += [ROOT / name for name in (
        "data/maps/README.md", ".agents/README.md", "tools/ssh_mcp/README.md",
        "tools/ssh_mcp/QA_REPORT.md", "src/web/docs_ui/README.md",
        "src/web/static/VENDOR_PROVENANCE.md",
    )]
    result: list[dict[str, object]] = []
    for path in paths:
        if not path.is_file():
            continue
        content = path.read_bytes()
        historical = "audits" in path.parts or path.name.startswith("PHASE_") or path.name in {
            "HISTORICAL_PROPOSAL.md", "QA_REPORT.md",
            "AUDIT_REPORT_2026-08-17.md", "FINAL_PROJECT_REPORT.md"
        }
        result.append({
            "path": relative(path),
            "category": "historical-ledger-or-report" if historical else "maintained-or-decision",
            "sha256": hashlib.sha256(content).hexdigest(),
            "lines": len(content.splitlines()),
        })
    return result


def scripts() -> list[dict[str, object]]:
    """Hash maintained helpers and entrypoints without running their code."""
    paths = {path for path in (ROOT / "scripts").rglob("*")
             if path.is_file() and path.suffix in {".py", ".cjs", ".js", ".sh", ".ps1"}}
    paths.update(path for path in ROOT.iterdir()
                 if path.is_file() and path.suffix in {".py", ".sh", ".ps1", ".service"})
    paths.update((ROOT / ".github/workflows").glob("*.yml"))
    paths.update((ROOT / ".github/workflows").glob("*.yaml"))
    paths.update((ROOT / "tools/ssh_mcp").glob("*.py"))
    for directory in (ROOT / ".agents/skills").iterdir():
        if directory.is_dir() and directory.name not in VENDORS:
            paths.update(directory.glob("scripts/*.py"))
    return [
        {"path": relative(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
         "review_scope": "static inventory only; inspect side effects before execution"}
        for path in sorted(paths)
    ]


def references() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    catalogue = (ROOT / "reference/README.md").read_text(encoding="utf-8")
    for directory in sorted((ROOT / "reference").iterdir()):
        if not directory.is_dir():
            continue
        marker = (directory / ".git").exists()
        row = next((line for line in catalogue.splitlines()
                    if f"/reference/{directory.name}/" in line), "")
        urls = re.findall(r"https://github\.com/[^\s`|)]+", row)
        readme = directory / "README.md"
        content = readme.read_text(encoding="utf-8-sig") if readme.exists() else ""
        clone = re.search(r"git clone(?: --[\w-]+)* (https://github\.com/[^\s`]+)", content)
        badge = re.search(r"https://github\.com/([^/\s]+)/([^/\s)]+)/actions/", content)
        declared = urls[0] if urls else clone.group(1) if clone else (
            f"https://github.com/{badge.group(1)}/{badge.group(2)}" if badge else None
        )
        origin = git_value(directory, "remote", "get-url", "origin") if marker else None
        status = git_value(directory, "status", "--porcelain") if marker else None
        result.append({
            "path": relative(directory),
            "authority": "official-protocol" if directory.name in OFFICIAL else "third-party-comparison",
            "own_git_marker": marker,
            "origin": origin,
            "declared_origin": declared,
            "declared_origin_evidence": "reference/README.md" if urls else relative(readme) if declared else None,
            "commit": git_value(directory, "rev-parse", "HEAD") if marker else None,
            "description": git_value(directory, "describe", "--tags", "--always") if marker else None,
            "commit_date": git_value(directory, "show", "-s", "--format=%cI", "HEAD") if marker else None,
            "working_tree_clean": status == "" if status is not None else None,
            "revision_evidence": "local-git-only" if marker else "unversioned-copy; origin/revision not accredited",
            "readme": relative(readme) if readme.exists() else None,
            "license_files": [relative(path) for path in sorted(directory.iterdir())
                              if path.is_file() and path.name.lower().startswith(("license", "copying"))],
            "documentation_files": [relative(path) for path in sorted(directory.rglob("*.md"))
                                    if not {".git", "node_modules", ".venv"}.intersection(path.parts)],
        })
    return result


def skills() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for path in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")):
        content = path.read_text(encoding="utf-8")
        description = re.search(r"^description:\s*(.*?)(?=\n\S|\n---)", content, re.M | re.S)
        result.append({
            "name": path.parent.name,
            "path": relative(path),
            "ownership": "vendor" if path.parent.name in VENDORS else "project",
            "description": description.group(1).strip() if description else None,
            "ui_metadata": relative(path.parent / "agents/openai.yaml")
                           if (path.parent / "agents/openai.yaml").exists() else None,
            "scripts": [relative(script) for script in sorted(path.parent.glob("scripts/*.py"))]
                       if path.parent.name not in VENDORS else [],
        })
    return result


def inventory() -> dict[str, object]:
    docs = documents()
    refs = references()
    catalogue = skills()
    helpers = scripts()
    source = [relative(path) for path in sorted((ROOT / "src").rglob("*"))
              if path.is_file() and path.suffix in {".py", ".js", ".css", ".html"}
              and "__pycache__" not in path.parts]
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "project_head": git_value(ROOT, "rev-parse", "HEAD"),
        "project_branch": git_value(ROOT, "branch", "--show-current"),
        "project_origin": git_value(ROOT, "remote", "get-url", "origin"),
        "scope": "checkout snapshot including existing uncommitted work; structural inventory, not runtime certification",
        "excluded": [".env", "operator data and logs", "application imports", "suite execution",
                     "reference updates", "remote HEAD comparisons", "vendor code execution"],
        "counts": {"documents": len(docs), "references": len(refs), "source_files": len(source),
                   "project_skills": sum(skill["ownership"] == "project" for skill in catalogue),
                   "vendor_skills": sum(skill["ownership"] == "vendor" for skill in catalogue),
                   "scripts_and_entrypoints": len(helpers)},
        "documents": docs,
        "references": refs,
        "skills": catalogue,
        "source_files": source,
        "scripts_and_entrypoints": helpers,
        "root_entrypoints": [name for name in ("config.py", "runtime_requirements.py", "run_interactive_demo.py", ".env.example", "meshcore_bridge.py",
                              "install.sh", "install.ps1", "meshcore-bridge.service", "requirements.txt",
                              "requirements-dev.txt", "requirements-web.txt", "requirements-core.txt", "requirements-mqtt.txt", "pyproject.toml", "n8n_workflow_meshcore.json",
                              "opencode.json", "skills-lock.json") if (ROOT / name).is_file()],
    }


if __name__ == "__main__":
    import sys
    if "--write" in sys.argv:
        target = ROOT / "docs/PROJECT_INVENTORY.json"
        target.write_text(
            json.dumps(inventory(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )
    else:
        encoding = getattr(sys.stdout, "encoding", "") or ""
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if encoding.lower() != "utf-8" and callable(reconfigure):
            reconfigure(encoding="utf-8")
        print(json.dumps(inventory(), indent=2, ensure_ascii=False))
