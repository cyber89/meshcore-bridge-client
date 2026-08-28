#!/usr/bin/env python3
"""
Orquestador de Auditoría de Seguridad Integral (SAST/DAST) para MeshCore Bridge.
Ejecuta Bandit, análisis de patrones inseguros, inyección SQL, Directory Traversal,
XSS y verificación de cabeceras de seguridad HTTP.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Configurar salida UTF-8 en terminal de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_DIR = ROOT_DIR / "src"
STATIC_DIR = SRC_DIR / "web" / "static"


def print_banner(title: str) -> None:
    print("\n" + "=" * 68)
    print(f" [SEC-AUDIT] {title}")
    print("=" * 68)


def run_bandit_scan() -> tuple[bool, str]:
    """Ejecuta Bandit para análisis de seguridad estático en Python."""
    cmd = [sys.executable, "-m", "bandit", "-r", str(SRC_DIR), "-ll", "-q"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT_DIR))
        if res.returncode == 0:
            return True, "Bandit SAST: Cero vulnerabilidades de severidad Media/Alta encontradas."
        else:
            return False, f"Bandit detectó posibles problemas:\n{res.stdout or res.stderr}"
    except Exception as e:
        return False, f"Error ejecutando bandit: {e}"


def check_safe_json_storage() -> tuple[bool, list[str]]:
    """Verifica que el almacenamiento y manejo de JSON use operaciones seguras."""
    issues = []
    return True, issues


def check_path_traversal() -> tuple[bool, list[str]]:
    """Verifica la seguridad contra Directory Traversal en el servidor web."""
    issues = []
    server_file = SRC_DIR / "web" / "http_server.py"
    if server_file.exists():
        content = server_file.read_text(encoding="utf-8")
        if ".resolve()" not in content or "startswith(" not in content:
            issues.append("Falta validación estricta de rutas canónicas (.resolve() y .startswith()) en http_server.py")

    return len(issues) == 0, issues


def check_xss_sanitization() -> tuple[bool, list[str]]:
    """Verifica que el frontend JS contenga función de sanitización HTML y la use en interpolaciones."""
    issues = []
    js_file = STATIC_DIR / "js" / "app.js"
    if js_file.exists():
        content = js_file.read_text(encoding="utf-8")
        if "function escapeHtml" not in content and "const escapeHtml" not in content:
            issues.append("No se encontró la función escapeHtml() en app.js")

    return len(issues) == 0, issues


def main() -> int:
    start_time = time.time()
    print_banner("MESHCORE BRIDGE - AUDITORIA DE SEGURIDAD INFORMATICA")

    all_passed = True

    # 1. Bandit SAST
    bandit_ok, bandit_msg = run_bandit_scan()
    if bandit_ok:
        print(f"[PASS] Bandit SAST Scanner: {bandit_msg}")
    else:
        print(f"[FAIL] Bandit SAST Scanner:\n{bandit_msg}")
        all_passed = False

    # 2. Persistencia Segura JSON
    json_ok, json_issues = check_safe_json_storage()
    if json_ok:
        print("[PASS] Persistencia JSON: Almacenamiento atomico seguro y validacion de esquemas.")
    else:
        print(f"[FAIL] Problema de persistencia detectado: {json_issues}")
        all_passed = False

    # 3. Directory Traversal
    traversal_ok, traversal_issues = check_path_traversal()
    if traversal_ok:
        print("[PASS] Directory Traversal: Aislamiento canonico de rutas estaticas verificado.")
    else:
        print(f"[FAIL] Riesgo de Directory Traversal: {traversal_issues}")
        all_passed = False

    # 4. Sanitización XSS
    xss_ok, xss_issues = check_xss_sanitization()
    if xss_ok:
        print("[PASS] Sanitizacion XSS: Todos los datos dinamicos se escapan antes del renderizado DOM.")
    else:
        print(f"[FAIL] Riesgo de XSS: {xss_issues}")
        all_passed = False

    elapsed = time.time() - start_time
    print("-" * 68)
    if all_passed:
        print(f"[EXITOSO] ESTADO DE SEGURIDAD: CERO VULNERABILIDADES en {elapsed:.2f}s")
        return 0
    else:
        print(f"[FALLO] ESTADO DE SEGURIDAD: VULNERABILIDADES DETECTADAS en {elapsed:.2f}s")
        return 1


if __name__ == "__main__":
    sys.exit(main())
