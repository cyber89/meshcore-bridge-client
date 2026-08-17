#!/usr/bin/env python3
"""
Linter Estático para Estándares Frontend (HTML5, CSS3 y JavaScript).
Verifica presencia de etiquetas semánticas, variables CSS, sanitización HTML
y buenas prácticas en el cliente web SPA.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# UTF-8 en terminal Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[4]
WEB_STATIC_DIR = ROOT_DIR / "src" / "web" / "static"


def check_html() -> list[str]:
    issues = []
    html_file = WEB_STATIC_DIR / "index.html"
    if not html_file.exists():
        return ["No se encontró index.html"]

    content = html_file.read_text(encoding="utf-8")

    # 1. Verificar un único <h1>
    h1_count = len(re.findall(r"<h1\b", content, re.IGNORECASE))
    if h1_count != 1:
        issues.append(f"Se esperaba exactamente un <h1> por página, se encontraron {h1_count}.")

    # 2. Verificar meta description y viewport
    if '<meta name="description"' not in content:
        issues.append("Falta la etiqueta <meta name=\"description\"> para SEO y accesibilidad.")
    if '<meta name="viewport"' not in content:
        issues.append("Falta la etiqueta <meta name=\"viewport\"> para diseño responsivo.")

    # 3. Verificar roles ARIA
    if 'role="tablist"' not in content or 'role="tab"' not in content:
        issues.append("Faltan atributos de accesibilidad ARIA role='tablist' o role='tab'.")

    return issues


def check_css() -> list[str]:
    issues = []
    css_file = WEB_STATIC_DIR / "css" / "app.css"
    if not css_file.exists():
        return ["No se encontró app.css"]

    content = css_file.read_text(encoding="utf-8")

    # 1. Variables CSS en :root
    if ":root" not in content or "--bg-" not in content:
        issues.append("No se encontró la definición de tokens de diseño en :root.")

    # 2. prefers-reduced-motion
    if "prefers-reduced-motion" not in content:
        issues.append("Falta la media query @media (prefers-reduced-motion: reduce) para accesibilidad.")

    # 3. focus-visible
    if ":focus-visible" not in content:
        issues.append("Falta la regla de foco accesible :focus-visible.")

    return issues


def check_js() -> list[str]:
    issues = []
    js_file = WEB_STATIC_DIR / "js" / "app.js"
    if not js_file.exists():
        return ["No se encontró app.js"]

    content = js_file.read_text(encoding="utf-8")

    # 1. Función de escape HTML
    if "escapeHtml" not in content:
        issues.append("Falta la función de sanitización escapeHtml().")

    # 2. Uso de WebSocket
    if "WebSocket" not in content:
        issues.append("No se encontró la conexión WebSocket en app.js.")

    return issues


def main() -> int:
    print("\n" + "=" * 68)
    print(" [FRONTEND-LINT] Verificando Estándares HTML5, CSS3 y JavaScript")
    print("=" * 68)

    all_passed = True

    html_issues = check_html()
    if html_issues:
        print("[FAIL] HTML5 Semántico y Accesibilidad:")
        for i in html_issues:
            print(f"       - {i}")
        all_passed = False
    else:
        print("[PASS] HTML5 Semántico: Estructura, meta tags, jerarquía h1 y ARIA conformes.")

    css_issues = check_css()
    if css_issues:
        print("[FAIL] CSS3 Moderno y Design System:")
        for i in css_issues:
            print(f"       - {i}")
        all_passed = False
    else:
        print("[PASS] CSS3 Moderno: Variables en :root, :focus-visible y prefers-reduced-motion conformes.")

    js_issues = check_js()
    if js_issues:
        print("[FAIL] JavaScript Moderno y Seguridad DOM:")
        for i in js_issues:
            print(f"       - {i}")
        all_passed = False
    else:
        print("[PASS] JavaScript Moderno: async/await, WebSocket y sanitización escapeHtml conformes.")

    print("-" * 68)
    if all_passed:
        print("[EXITOSO] 100% de cumplimiento en estándares web frontend.")
        return 0
    else:
        print("[FALLO] Se detectaron incumplimientos en los estándares web frontend.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
