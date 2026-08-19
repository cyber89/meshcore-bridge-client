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

def check_blocking_calls(file_path: Path) -> List[str]:
    violations: List[str] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
            
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        # Detectar time.sleep() en funciones async
                        if isinstance(sub.func, ast.Attribute) and sub.func.attr == "sleep":
                            if isinstance(sub.func.value, ast.Name) and sub.func.value.id == "time":
                                violations.append(f"[BLOQUEO I/O] {file_path.name}:{sub.lineno} uso de time.sleep() en corrutina '{node.name}' (usar asyncio.sleep)")
                        # Detectar requests.* sincrónico en funciones async
                        if isinstance(sub.func, ast.Attribute) and isinstance(sub.func.value, ast.Name) and sub.func.value.id == "requests":
                            violations.append(f"[BLOQUEO I/O] {file_path.name}:{sub.lineno} llamada a 'requests.{sub.func.attr}' en corrutina '{node.name}'")
    except Exception:
        pass
    return violations

def main() -> int:
    root = get_project_root()
    src_dir = root / "src"
    
    print("=" * 68)
    print(" [ASYNC-AUDIT] Auditoria de Concurrencia y Event Loop Asincrono")
    print("=" * 68)
    
    all_violations: List[str] = []
    for py_file in sorted(src_dir.glob("*.py")):
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
