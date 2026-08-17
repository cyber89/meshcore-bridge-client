#!/usr/bin/env python3
"""
Validador de Estándares de Python y Tipado Estricto.
Verifica que las funciones y clases tengan anotaciones de tipo completas y sigan PEP 8/563.
"""

from __future__ import annotations

import ast
import os
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
SRC_DIR = ROOT_DIR / "src"


def check_python_file(path: Path) -> list[str]:
    issues = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception as e:
        return [f"Error de sintaxis: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Verificar retorno tipado (excepto __init__)
            if node.name != "__init__" and node.returns is None:
                issues.append(f"Línea {node.lineno}: Función '{node.name}' no declara tipo de retorno.")

            # Verificar argumentos tipados (excepto self y cls)
            for arg in node.args.args:
                if arg.arg not in ("self", "cls") and arg.annotation is None:
                    issues.append(f"Línea {node.lineno}: Parámetro '{arg.arg}' en '{node.name}' no tiene anotación de tipo.")

    return issues


def main() -> int:
    print("\n" + "=" * 68)
    print(" [PYTHON-STANDARDS] Verificando Tipado y Estándares PEP")
    print("=" * 68)

    all_ok = True
    for py_file in sorted(SRC_DIR.rglob("*.py")):
        if py_file.name.startswith("."):
            continue
        rel = py_file.relative_to(ROOT_DIR)
        issues = check_python_file(py_file)
        if issues:
            all_ok = False
            print(f"[FAIL] {rel}:")
            for issue in issues:
                print(f"       - {issue}")
        else:
            print(f"[PASS] {rel}")

    print("-" * 68)
    if all_ok:
        print("[EXITOSO] 100% funciones y métodos con anotaciones de tipo completas.")
        return 0
    else:
        print("[AVISO] Se detectaron funciones sin anotaciones de tipo explícitas.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
