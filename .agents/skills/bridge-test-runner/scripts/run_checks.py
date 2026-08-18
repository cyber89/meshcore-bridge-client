#!/usr/bin/env python3
"""
MeshCore Bridge Automated Test & Quality Runner.
Ejecuta de manera orquestada la suite de pruebas unitarias (pytest), verificación
estricta de tipos (mypy --strict) y linter (ruff) reportando discrepancias y fallos.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


@dataclass
class ToolResult:
    tool_name: str
    command: str
    exit_code: int
    duration_sec: float
    stdout: str
    stderr: str
    passed: bool
    summary: str

@dataclass
class CheckReport:
    timestamp: str
    total_duration_sec: float
    all_passed: bool
    tools: List[ToolResult] = field(default_factory=list)


def run_command(cmd: List[str], cwd: Path) -> Tuple[int, str, str, float]:
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        duration = time.time() - start
        return proc.returncode, proc.stdout, proc.stderr, duration
    except FileNotFoundError:
        duration = time.time() - start
        return 127, "", f"Comando '{cmd[0]}' no encontrado en el PATH del sistema.", duration
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return 124, "", f"Comando '{cmd[0]}' excedió el tiempo límite (120s).", duration
    except Exception as e:
        duration = time.time() - start
        return 1, "", f"Excepción al ejecutar comando: {e}", duration


def run_ruff(cwd: Path) -> ToolResult:
    cmd = [sys.executable, "-m", "ruff", "check", "src", "tests"]
    code, stdout, stderr, dur = run_command(cmd, cwd)
    
    # Fallback si no está instalado como módulo
    if code == 127 or "No module named ruff" in stderr:
        cmd = ["ruff", "check", "src", "tests"]
        code, stdout, stderr, dur = run_command(cmd, cwd)

    passed = (code == 0)
    summary = "0 advertencias / errores de estilo." if passed else "Errores o advertencias de lint detectadas."
    return ToolResult(
        tool_name="ruff (Linter)",
        command=" ".join(cmd),
        exit_code=code,
        duration_sec=round(dur, 2),
        stdout=stdout,
        stderr=stderr,
        passed=passed,
        summary=summary,
    )


def run_mypy(cwd: Path) -> ToolResult:
    cmd = [sys.executable, "-m", "mypy", "--strict", "src"]
    code, stdout, stderr, dur = run_command(cmd, cwd)

    if code == 127 or "No module named mypy" in stderr:
        cmd = ["mypy", "--strict", "src"]
        code, stdout, stderr, dur = run_command(cmd, cwd)

    passed = (code == 0)
    summary = "Tipado 100% estricto y consistente." if passed else "Errores de tipado estricto detectados."
    return ToolResult(
        tool_name="mypy (Type Checker)",
        command=" ".join(cmd),
        exit_code=code,
        duration_sec=round(dur, 2),
        stdout=stdout,
        stderr=stderr,
        passed=passed,
        summary=summary,
    )


def run_pytest(cwd: Path, extra_args: Optional[List[str]] = None) -> ToolResult:
    cmd = [sys.executable, "-m", "pytest", "-v"]
    if extra_args:
        cmd.extend(extra_args)
    else:
        cmd.append("tests")

    code, stdout, stderr, dur = run_command(cmd, cwd)

    if code == 127 or "No module named pytest" in stderr:
        # Fallback a unittest nativo si pytest no está instalado en el entorno
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
        code, stdout, stderr, dur = run_command(cmd, cwd)

    passed = (code == 0)
    summary = "Todas las pruebas unitarias y de integración pasaron." if passed else "Fallos en pruebas unitarias."
    return ToolResult(
        tool_name="pytest / unittest (Test Runner)",
        command=" ".join(cmd),
        exit_code=code,
        duration_sec=round(dur, 2),
        stdout=stdout,
        stderr=stderr,
        passed=passed,
        summary=summary,
    )


def print_report(report: CheckReport) -> None:
    print("\n" + "=" * 65)
    print(f" MESHCORE BRIDGE - REPORTE DE VERIFICACIÓN Y CALIDAD")
    print(f" Estado General: {'[EXITOSO] ✅' if report.all_passed else '[FALLOS DETECTADOS] ❌'}")
    print(f" Tiempo Total:   {report.total_duration_sec:.2f}s")
    print("=" * 65)

    for res in report.tools:
        icon = "✅ PASS" if res.passed else "❌ FAIL"
        print(f"\n[{icon}] {res.tool_name} ({res.duration_sec}s)")
        print(f"  Comando:  {res.command}")
        print(f"  Resumen:  {res.summary}")
        
        output = (res.stdout + ("\n" + res.stderr if res.stderr else "")).strip()
        if output:
            lines = output.splitlines()
            if not res.passed or len(lines) <= 15:
                print("  Detalles:")
                for l in lines:
                    print(f"    | {l}")
            else:
                print(f"  Detalles: {lines[-1]}")

    print("\n" + "=" * 65 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="MeshCore Bridge Automated Test & QA Runner")
    parser.add_argument("--only-tests", action="store_true", help="Ejecutar únicamente la suite de tests")
    parser.add_argument("--only-types", action="store_true", help="Ejecutar únicamente verificación mypy")
    parser.add_argument("--only-lint", action="store_true", help="Ejecutar únicamente el linter ruff")
    parser.add_argument("--json", action="store_true", help="Formato de salida JSON")
    parser.add_argument("pytest_args", nargs="*", help="Argumentos adicionales pasados a pytest")

    args = parser.parse_args()
    
    # Localizar la raíz del workspace buscando marcadores de proyecto
    current = Path(__file__).resolve().parent
    cwd = current
    for p in [current] + list(current.parents):
        if (p / "pyproject.toml").exists() or (p / "AGENTS.md").exists() or (p / ".git").exists():
            cwd = p
            break

    start_total = time.time()
    results: List[ToolResult] = []

    run_all = not (args.only_tests or args.only_types or args.only_lint)

    if run_all or args.only_lint:
        results.append(run_ruff(cwd))

    if run_all or args.only_types:
        results.append(run_mypy(cwd))

    if run_all or args.only_tests:
        results.append(run_pytest(cwd, args.pytest_args if args.pytest_args else None))

    total_dur = time.time() - start_total
    all_passed = all(r.passed for r in results)

    report = CheckReport(
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        total_duration_sec=round(total_dur, 2),
        all_passed=all_passed,
        tools=results,
    )

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print_report(report)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
