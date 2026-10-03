"""Exercise the read-only i18n auditor against UI error paths and exceptions."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

AUDITOR = Path(__file__).resolve().parents[1] / "scripts" / "audit_frontend_i18n.cjs"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is needed by the i18n auditor")


def _scan(source: str) -> tuple[int, dict[str, Any]]:
    assert NODE is not None
    result = subprocess.run(
        [NODE, str(AUDITOR), "--scan-source"],
        input=source,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert not result.stderr, result.stderr
    return result.returncode, json.loads(result.stdout)


@pytest.mark.parametrize(
    "source,literal",
    [
        ('_notify("Error guardando radio: " + I18n.t("settings.unknown"));', "guardando radio"),
        ('try {} catch (e) { showToast(`Error de red al guardar canal: ${e.message}`); }', "guardar canal"),
        ('appendTerminalLine("Selecciona primero un repetidor objetivo.");', "Selecciona primero"),
        ('appendLocalTerminalLine("Fallo al guardar identidad.");', "guardar identidad"),
        ('throw new Error("Fallo al guardar identidad");', "guardar identidad"),
        ('alert(\n  "Error descargando archivo de logs"\n);', "descargando archivo"),
        ('element.innerHTML = `<span>${I18n.t("settings.unknown")}</span> Selecciona primero`;', "Selecciona primero"),
    ],
)
def test_own_ui_error_literals_are_findings(source: str, literal: str) -> None:
    exit_code, report = _scan(source)
    assert exit_code == 1
    assert len(report["untranslatedCandidates"]) == 1
    assert literal in report["untranslatedCandidates"][0]["literal"]


@pytest.mark.parametrize(
    "source",
    [
        'showToast(I18n.t("settings.unknown"));',
        'showToast(I18n.t("settings.network_error", { p0: err.message }));',
        'throw new Error(`HTTP ${response.status}`);',
        '// alert("Selecciona primero");\nconst expression = /alert("Selecciona primero")/;',
    ],
)
def test_translated_and_technical_content_is_preserved(source: str) -> None:
    exit_code, report = _scan(source)
    assert exit_code == 0
    assert not report["untranslatedCandidates"]


def test_exact_catalogue_fallback_is_explained() -> None:
    exit_code, report = _scan('showToast(I18n.t("settings.unknown") || "desconocido");')
    assert exit_code == 0
    assert report["reviewedExclusions"][0]["key"] == "settings.unknown"
    assert report["reviewedExclusions"][0]["reason"] == "Exact Spanish catalogue fallback"


def test_auditor_self_test_reports_every_case() -> None:
    assert NODE is not None
    result = subprocess.run(
        [NODE, str(AUDITOR), "--self-test"],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert not result.stderr, result.stderr
    report = json.loads(result.stdout)
    assert result.returncode == 0
    assert report["passed"]
    assert all(case["passed"] for case in report["selfTest"])
