#!/usr/bin/env python3
"""
Comprobaciones estáticas parciales de seguridad para MeshCore Bridge.
Ejecuta Bandit y búsqueda de indicadores de validación de rutas/escape HTML.
No realiza DAST, ataques, validación de esquemas JSON ni revisión de todo el DOM.
"""

from __future__ import annotations

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
            return True, "Bandit SAST: no reportó hallazgos de severidad media/alta en este escaneo."
        else:
            return False, f"Bandit detectó posibles problemas:\n{res.stdout or res.stderr}"
    except Exception as e:
        return False, f"Error ejecutando bandit: {e}"


def check_safe_json_storage() -> tuple[None, list[str]]:
    """No implemented schema/atomicity check: require code review and regressions."""
    return None, [
        "Revisión manual pendiente de esquemas, archivos temporales, reemplazo y durabilidad JSON."
    ]


def check_path_traversal() -> tuple[bool | None, list[str]]:
    """Find source markers only; their presence does not establish path safety."""
    issues: list[str] = []
    server_file = SRC_DIR / "web" / "http_server.py"
    if not server_file.exists():
        return None, ["No se encontró http_server.py para inspeccionar indicadores de rutas."]
    content = server_file.read_text(encoding="utf-8")
    if ".resolve()" not in content or "startswith(" not in content:
        issues.append("No se encontraron ambos indicadores .resolve()/startswith en http_server.py; revisar manualmente.")

    return len(issues) == 0, issues


def check_xss_sanitization() -> tuple[bool | None, list[str]]:
    """Find an escapeHtml definition; do not infer that every DOM sink uses it."""
    issues: list[str] = []
    js_file = STATIC_DIR / "js" / "app.js"
    utils_file = STATIC_DIR / "js" / "core" / "utils.js"
    if not any(path.exists() for path in (js_file, utils_file)):
        return None, ["No se encontraron app.js/utils.js para buscar escapeHtml."]
    found = False
    for f in (js_file, utils_file):
        if f.exists():
            content = f.read_text(encoding="utf-8")
            if "function escapeHtml" in content or "const escapeHtml" in content or "export function escapeHtml" in content:
                found = True
                break
    if not found:
        issues.append("No se encontró la función escapeHtml() en app.js o js/core/utils.js")

    return len(issues) == 0, issues


def main() -> int:
    start_time = time.time()
    print_banner("MESHCORE BRIDGE - AUDITORIA DE SEGURIDAD INFORMATICA")

    failed = False
    unverified = False

    # 1. Bandit SAST
    bandit_ok, bandit_msg = run_bandit_scan()
    if bandit_ok:
        print(f"[PASS] Bandit SAST Scanner: {bandit_msg}")
    else:
        print(f"[FAIL] Bandit SAST Scanner:\n{bandit_msg}")
        failed = True

    # 2. Persistencia Segura JSON
    json_ok, json_issues = check_safe_json_storage()
    if json_ok is None:
        print(f"[NO VERIFICADO] Persistencia JSON: {' '.join(json_issues)}")
        unverified = True

    # 3. Directory Traversal
    traversal_ok, traversal_issues = check_path_traversal()
    if traversal_ok is None:
        print(f"[NO VERIFICADO] Indicadores de rutas: {' '.join(traversal_issues)}")
        unverified = True
    elif traversal_ok:
        print("[PASS] Heurística de rutas: indicadores .resolve()/startswith presentes; aislamiento no demostrado.")
    else:
        print(f"[FAIL] Heurística de rutas: {traversal_issues}")
        failed = True

    # 4. Sanitización XSS
    xss_ok, xss_issues = check_xss_sanitization()
    if xss_ok is None:
        print(f"[NO VERIFICADO] Indicadores HTML: {' '.join(xss_issues)}")
        unverified = True
    elif xss_ok:
        print("[PASS] Heurística HTML: definición escapeHtml presente; usos/contextos DOM no verificados.")
    else:
        print(f"[FAIL] Heurística HTML: {xss_issues}")
        failed = True

    elapsed = time.time() - start_time
    print("-" * 68)
    print("Alcance parcial: no ejecuta DAST ni demuestra ausencia de vulnerabilidades.")
    if failed:
        print(f"[FALLO] Una herramienta o heurística falló en {elapsed:.2f}s; revisar la evidencia.")
        return 1
    if unverified:
        print(f"[INCOMPLETO] Comprobaciones ejecutadas sin fallos; quedan revisiones manuales ({elapsed:.2f}s).")
        return 2
    print(f"[PASS] Comprobaciones ejecutadas sin hallazgos en {elapsed:.2f}s; alcance parcial.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
