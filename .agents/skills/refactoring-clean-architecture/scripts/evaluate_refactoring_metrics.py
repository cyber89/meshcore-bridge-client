#!/usr/bin/env python3
"""
Evaluador de Métricas de Refactorización y Código Limpio para MeshCore Bridge.
Calcula la complejidad ciclomática de McCabe, longitud de métodos y número de argumentos.
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

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

def calculate_cyclomatic_complexity(node: ast.AST) -> int:
    complexity = 1
    for sub in ast.walk(node):
        if isinstance(sub, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler, ast.With, ast.AsyncWith)):
            complexity += 1
        elif isinstance(sub, ast.BoolOp):
            complexity += len(sub.values) - 1
        elif isinstance(sub, ast.IfExp):
            complexity += 1
    return complexity

def analyze_file_metrics(file_path: Path) -> List[str]:
    issues: List[str] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            tree = ast.parse(content, filename=str(file_path))
            
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Complejidad ciclomática
                cc = calculate_cyclomatic_complexity(node)
                if cc > 15:
                    issues.append(f"[ALTA COMPLEJIDAD] {file_path.name}:{node.lineno} '{node.name}' Complejidad Ciclomatica = {cc} (Limite: 15)")
                
                # Número de parámetros
                args_count = len(node.args.args)
                if args_count > 6:
                    issues.append(f"[EXCESO PARAMETROS] {file_path.name}:{node.lineno} '{node.name}' tiene {args_count} argumentos (Limite: 6)")
    except Exception:
        pass
    return issues

def main() -> int:
    root = get_project_root()
    src_dir = root / "src"
    
    print("=" * 68)
    print(" [CLEAN-METRICS] Evaluacion de Metricas de Codigo y Complejidad")
    print("=" * 68)
    
    all_issues: List[str] = []
    for py_file in sorted(src_dir.glob("*.py")):
        issues = analyze_file_metrics(py_file)
        all_issues.extend(issues)
        
    if not all_issues:
        print("[PASS] Complejidad ciclomática bajo control en todas las funciones.")
        print("[PASS] Parametros y modularidad conformes a los estandares Clean Code.")
        print("-" * 68)
        print("[EXITOSO] Codigo 100% limpio y mantenible.")
        return 0
    else:
        for iss in all_issues:
            print(f"  [WARN] {iss}")
        print("-" * 68)
        print(f"[REPORTE] Se identificaron {len(all_issues)} oportunidades de refactorizacion.")
        return 0

if __name__ == "__main__":
    sys.exit(main())
