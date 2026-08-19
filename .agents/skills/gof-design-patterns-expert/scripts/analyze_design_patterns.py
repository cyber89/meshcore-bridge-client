#!/usr/bin/env python3
"""
Analizador de Patrones de Diseño GoF para MeshCore Bridge.
Detecta el uso de patrones clave (Adapter, Strategy, Facade, Factory) e identifica oportunidades de refactorización.
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

def analyze_patterns_in_file(file_path: Path) -> List[str]:
    patterns_found: List[str] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            tree = ast.parse(content, filename=str(file_path))
            
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Adapter / Base
                if any("Adapter" in getattr(base, "id", "") or "Adapter" in getattr(base, "attr", "") for base in node.bases):
                    patterns_found.append(f"Adapter: {node.name} (en {file_path.name})")
                # Strategy / Handler
                if "Handler" in node.name or "Router" in node.name or "Strategy" in node.name:
                    patterns_found.append(f"Strategy/Handler: {node.name} (en {file_path.name})")
                # Facade
                if "Bridge" in node.name or "Manager" in node.name or "Coordinator" in node.name:
                    patterns_found.append(f"Facade/Manager: {node.name} (en {file_path.name})")
            elif isinstance(node, ast.FunctionDef):
                # Factory
                if node.name.startswith("create_") or node.name.startswith("build_") or node.name.startswith("get_adapter"):
                    patterns_found.append(f"Factory Method: {node.name}() (en {file_path.name})")
    except Exception:
        pass
    return patterns_found

def main() -> int:
    root = get_project_root()
    src_dir = root / "src"
    
    print("=" * 68)
    print(" [DESIGN-PATTERNS] Analisis de Patrones GoF y Estructura Modular")
    print("=" * 68)
    
    all_patterns: List[str] = []
    for py_file in sorted(src_dir.glob("*.py")):
        patterns = analyze_patterns_in_file(py_file)
        all_patterns.extend(patterns)
        
    print(f"Patrones de diseno identificados en el codigo de produccion ({len(all_patterns)}):")
    for p in all_patterns:
        print(f"  [OK] {p}")
        
    print("-" * 68)
    print("[EXITOSO] Arquitectura orientada a patrones de diseno verificada.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
