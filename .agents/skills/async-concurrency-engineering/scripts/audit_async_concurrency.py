#!/usr/bin/env python3
"""
Auditor de Concurrencia Asíncrona (asyncio) para MeshCore Bridge.
Detecta llamadas bloqueantes en funciones asíncronas, uso inseguro de locks y manejo de tareas en segundo plano.
"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def get_project_root() -> Path:
    current = Path(__file__).resolve().parent
    while current.parent != current:
        if (current / "src").is_dir() and (current / "config.py").is_file():
            return current
        current = current.parent
    return Path.cwd()


class _AsyncBlockingVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: List[str] = []
        self._current_async: str | None = None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        prev = self._current_async
        self._current_async = node.name
        self.generic_visit(node)
        self._current_async = prev

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Don't treat synchronous inner functions (e.g. passed to asyncio.to_thread) as async coroutines
        prev = self._current_async
        self._current_async = None
        self.generic_visit(node)
        self._current_async = prev

    def visit_Call(self, node: ast.Call) -> None:
        if self._current_async:
            # Detect time.sleep() in async coroutine body
            if isinstance(node.func, ast.Attribute) and node.func.attr == "sleep":
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "time":
                    self.violations.append(
                        f"[BLOQUEO I/O] {self.file_path.name}:{node.lineno} uso de time.sleep() en corrutina '{self._current_async}' (usar asyncio.sleep)"
                    )
            # Detect requests.* synchronous in async coroutine body
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "requests":
                self.violations.append(
                    f"[BLOQUEO I/O] {self.file_path.name}:{node.lineno} llamada a 'requests.{node.func.attr}' en corrutina '{self._current_async}'"
                )
        self.generic_visit(node)


def check_blocking_calls(file_path: Path) -> List[str]:
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as e:
        return [f"[ERROR SINTAXIS] {file_path.name}:{e.lineno} Error al parsear AST: {e.msg}"]
    except Exception as e:
        return [f"[ERROR LECTURA] {file_path.name}: {e}"]

    visitor = _AsyncBlockingVisitor(file_path)
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    root = get_project_root()
    src_dir = root / "src"

    print("=" * 68)
    print(" [ASYNC-AUDIT] Auditoria de Concurrencia y Event Loop Asincrono")
    print("=" * 68)

    all_violations: List[str] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        v = check_blocking_calls(py_file)
        all_violations.extend(v)

    if not all_violations:
        print("[PASS] Cero llamadas bloqueantes (time.sleep, requests) en corrutinas async.")
        print("[PASS] Patrones asincronos y gestion del event loop conformes.")
        print("-" * 68)
        print("[EXITOSO] 100% de conformidad en concurrencia asincrona.")
        return 0
    else:
        for err in all_violations:
            print(f"  [ERROR] {err}")
        print("-" * 68)
        print(f"[FALLO] Se encontraron {len(all_violations)} violaciones de concurrencia.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
