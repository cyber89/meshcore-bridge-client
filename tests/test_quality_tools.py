"""Regressions for trustworthy QA reporting and broken-document detection."""

from __future__ import annotations

import runpy
import subprocess
from pathlib import Path
from unittest.mock import patch

from scripts.run_quality_checks import build_commands, main, run_command
from scripts.validate_project_docs import local_link_issues, skill_issues


def test_missing_executable_is_a_failure(tmp_path: Path) -> None:
    with patch(
        "scripts.run_quality_checks.subprocess.run", side_effect=FileNotFoundError("missing")
    ):
        result = run_command("pytest", ["missing"], tmp_path, 1)
    assert result.exit_code == 127
    assert not result.passed


def test_timeout_retains_partial_output(tmp_path: Path) -> None:
    timeout = subprocess.TimeoutExpired(["pytest"], 1, output=b"collected 12", stderr=b"failure")
    with patch("scripts.run_quality_checks.subprocess.run", side_effect=timeout):
        result = run_command("pytest", ["pytest"], tmp_path, 1)
    assert result.exit_code == 124
    assert result.stdout == "collected 12"
    assert "failure" in result.stderr
    assert "partial output retained" in result.stderr


def test_pytest_no_tests_does_not_fall_back_to_unittest(tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(["pytest"], 5, "no tests ran", "")
    with patch("scripts.run_quality_checks.subprocess.run", return_value=completed) as runner:
        result = run_command("pytest", ["pytest"], tmp_path, 1)
    assert not result.passed
    assert result.exit_code == 5
    runner.assert_called_once()


def test_pytest_arguments_are_forwarded() -> None:
    commands = build_commands(
        ["--", "tests/test_quality_tools.py", "-q", "-k", "timeout"], "pytest"
    )
    assert len(commands) == 1
    assert commands[0][1][3:] == ["tests/test_quality_tools.py", "-q", "-k", "timeout"]


def test_json_report_preserves_failure_and_exit_code(tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(
        ["pytest"], 2, "collection failed", "dependency missing"
    )
    report = tmp_path / "report.json"
    with patch("scripts.run_quality_checks.subprocess.run", return_value=completed):
        code = main(["--only-tests", "--report", str(report), "--json"])
    assert code == 1
    assert '"all_passed": false' in report.read_text(encoding="utf-8")
    assert '"exit_code": 2' in report.read_text(encoding="utf-8")


def test_document_links_resolve_relative_paths_and_ignore_examples(tmp_path: Path) -> None:
    directory = tmp_path / "docs"
    directory.mkdir()
    (tmp_path / "README.md").write_text("ok", encoding="utf-8")
    document = directory / "guide.md"
    document.write_text(
        "[root](../README.md#usage)\n[missing](absent.md)\n[external](https://example.org)\n"
        "```md\n[example](illustrative.md)\n```\n",
        encoding="utf-8",
    )
    issues = local_link_issues(document, tmp_path)
    assert len(issues) == 1
    assert "absent.md" in issues[0]


def test_skill_entrypoint_requires_metadata_and_existing_resources(tmp_path: Path) -> None:
    directory = tmp_path / "sample"
    directory.mkdir()
    document = directory / "SKILL.md"
    document.write_text(
        "---\nname: wrong\ndescription: Scoped task.\n---\n[script](scripts/missing.py)\n",
        encoding="utf-8",
    )
    issues = skill_issues(document, tmp_path)
    assert len(issues) == 2
    assert any("name must match" in issue for issue in issues)
    assert any("missing.py" in issue for issue in issues)


def test_domain_helper_reports_failure_as_nonzero(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / ".agents/skills/domain-adr-keeper/scripts/audit_domain_adr.py"
    )
    entrypoint = runpy.run_path(str(script))["main"]
    entrypoint.__globals__["CONTEXT_FILE"] = tmp_path / "missing.md"
    entrypoint.__globals__["ADR_DIR"] = tmp_path / "missing_adrs"
    with patch("sys.argv", [str(script)]):
        assert entrypoint() == 1


def test_api_lexical_helper_does_not_claim_success_for_empty_inventory() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / ".agents/skills/contract-openapi-sync/scripts/verify_api_parity.py"
    )
    entrypoint = runpy.run_path(str(script))["main"]
    with patch.dict(
        entrypoint.__globals__,
        extract_backend_routes=lambda: set(),
        extract_frontend_api_calls=lambda: {},
    ):
        assert entrypoint() == 1


def test_api_route_prefix_requires_a_segment_boundary() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / ".agents/skills/contract-openapi-sync/scripts/verify_api_parity.py"
    )
    covered = runpy.run_path(str(script))["is_route_covered"]
    assert covered("/api/contacts/abc", {"/api/contacts"})
    assert not covered("/api/contacts_evil", {"/api/contacts"})
    assert not covered("/api/contact", {"/api/contacts"})
