"""Check maintained Markdown links, ADR metadata and project-owned skill entrypoints.

This structural check does not prove that prose matches firmware or implementation.
Historical reports and third-party skill bundles are excluded.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = {"FINAL_PROJECT_REPORT.md", "AUDIT_REPORT_2026-08-17.md"}
VENDOR_SKILLS = {"archify", "ui-ux-pro-max"}


def local_link_issues(path: Path, root: Path) -> list[str]:
    """Inspect local Markdown targets outside fenced code blocks."""
    content = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    issues: list[str] = []
    for match in re.finditer(r"!?\[[^\]]*\]\(([^\n)]+)\)", content):
        target = match.group(1).strip()
        if target.startswith("<"):
            target = target.split(">", 1)[0][1:]
        else:
            target = target.split(' "', 1)[0]
        if not target or target.startswith("#") or re.match(r"[a-zA-Z][\w+.-]*://", target):
            continue
        target = unquote(target.split("#", 1)[0].split("?", 1)[0])
        target = re.sub(r":\d+$", "", target)
        destination = root / target.lstrip("/") if target.startswith("/") else path.parent / target
        if not destination.exists():
            issues.append(f"{path.relative_to(root)}: missing local link: {target}")
    return issues


def skill_issues(path: Path, root: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    issues: list[str] = []
    frontmatter = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", content, re.S)
    if not frontmatter:
        return [f"{path.relative_to(root)}: missing YAML frontmatter"]
    metadata = frontmatter.group(1)
    name = re.search(r"^name:\s*([^\n]+)", metadata, re.M)
    if not name or name.group(1).strip() != path.parent.name:
        issues.append(f"{path.relative_to(root)}: name must match skill directory")
    if not re.search(r"^description:\s*\S", metadata, re.M):
        issues.append(f"{path.relative_to(root)}: missing description")
    return issues + local_link_issues(path, root)


def validate(root: Path) -> tuple[int, list[str]]:
    documents = [root / "README.md", root / "CONTEXT.md", root / "AGENTS.md"]
    documents.extend(path for path in (root / "docs").rglob("*.md") if path.name not in HISTORICAL)
    if (root / ".agents" / "README.md").exists():
        documents.append(root / ".agents" / "README.md")
    issues: list[str] = []
    for path in documents:
        if not path.exists():
            issues.append(f"Missing document: {path.relative_to(root)}")
        else:
            issues.extend(local_link_issues(path, root))
    adrs = sorted((root / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
    for index, path in enumerate(adrs, 1):
        content = path.read_text(encoding="utf-8")
        if not path.name.startswith(f"{index:04d}-"):
            issues.append(f"ADR sequence mismatch: {path.name}")
        for heading in ("Contexto y Problema", "Factores de Decisión", "Decisión", "Consecuencias"):
            if f"## {heading}" not in content:
                issues.append(f"{path.name}: missing section {heading}")
        for key in ("Estado", "Fecha"):
            if not re.search(rf"\*\*{key}\*\*:\s*\S", content):
                issues.append(f"{path.name}: missing metadata {key}")
    skills = [
        path
        for path in (root / ".agents" / "skills").glob("*/SKILL.md")
        if path.parent.name not in VENDOR_SKILLS
    ]
    for path in skills:
        issues.extend(skill_issues(path, root))
    return len(documents) + len(skills), issues


def main() -> int:
    count, issues = validate(ROOT)
    for issue in issues:
        print(f"FAIL {issue}")
    print(f"Documentation structure: {count} files checked; {len(issues)} issues.")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
