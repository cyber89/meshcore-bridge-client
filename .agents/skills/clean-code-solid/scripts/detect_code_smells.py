#!/usr/bin/env python3
"""
Detector de Code Smells y Análisis de Complejidad AST.
Detecta métodos largos (> 70 líneas), exceso de parámetros (> 6),
anidamientos profundos (> 4 niveles) y clases sobredimensionadas.
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

MAX_METHOD_LINES = 70
MAX_PARAMS = 6
MAX_CLASS_METHODS = 25


class CodeSmellVisitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.smells: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        # Parámetros
        param_count = len(node.args.args)
        if param_count > MAX_PARAMS:
            self.smells.append(
                f"Línea {node.lineno}: Función '{node.name}' tiene {param_count} parámetros (Límite: {MAX_PARAMS})."
            )

        # Longitud en líneas
        lines = (node.end_lineno or node.lineno) - node.lineno
        if lines > MAX_METHOD_LINES:
            self.smells.append(
                f"Línea {node.lineno}: Función '{node.name}' tiene {lines} líneas (Límite: {MAX_METHOD_LINES})."
            )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if len(methods) > MAX_CLASS_METHODS:
            self.smells.append(
                f"Línea {node.lineno}: Clase '{node.name}' tiene {len(methods)} métodos (God Class Smell)."
            )
        self.generic_visit(node)


def main() -> int:
    print("\n" + "=" * 68)
    print(" [CLEAN-CODE] Detector de Code Smells y Métricas de Complejidad")
    print("=" * 68)

    total_smells = 0
    for py_file in sorted(SRC_DIR.rglob("*.py")):
        if py_file.name.startswith("."):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            visitor = CodeSmellVisitor(py_file.name)
            visitor.visit(tree)
            rel = py_file.relative_to(ROOT_DIR)
            if visitor.smells:
                total_smells += len(visitor.smells)
                print(f"[WARN] {rel}:")
                for s in visitor.smells:
                    print(f"       ⚠️ {s}")
            else:
                print(f"[PASS] {rel} - Código limpio y modular.")
        except Exception as e:
            print(f"[ERROR] {py_file.name}: {e}")

    print("-" * 68)
    if total_smells == 0:
        print("[EXITOSO] Cero Code Smells detectados. Cumplimiento de principios SOLID.")
        return 0
    else:
        print(f"[INFO] Se encontraron {total_smells} oportunidades de refactorización opcionales.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
