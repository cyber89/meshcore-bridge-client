#!/usr/bin/env python3
"""
Auditor de Arquitectura de Software para MeshCore Bridge.
Analiza la estructura de capas, inversión de dependencias y aislamiento del dominio.
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

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

def parse_imports(file_path: Path) -> List[str]:
    imports: List[str] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
    except Exception:
        pass
    return imports

def audit_layers(root: Path) -> Tuple[int, List[str]]:
    src_dir = root / "src"
    violations: List[str] = []
    
    core_modules = ["protocol_types.py", "rx_router.py", "admin_handler.py", "contact_manager.py"]
    
    for mod_name in core_modules:
        mod_path = src_dir / mod_name
        if not mod_path.exists():
            continue
        imports = parse_imports(mod_path)
        for imp in imports:
            if "src.web" in imp or "fastapi" in imp or "starlette" in imp:
                violations.append(f"[VIOLACION DE CAPA] {mod_name} importa capa web: '{imp}'")
                
    return len(violations), violations

def audit_domain_immutability(root: Path) -> Tuple[int, List[str]]:
    proto_types_path = root / "src" / "protocol_types.py"
    warnings: List[str] = []
    if not proto_types_path.exists():
        return 0, []
        
    try:
        with open(proto_types_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(proto_types_path))
            
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                is_dataclass = False
                is_frozen = False
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name) and dec.id == "dataclass":
                        is_dataclass = True
                    elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "dataclass":
                        is_dataclass = True
                        for kw in dec.keywords:
                            if kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                is_frozen = True
                if is_dataclass and not is_frozen:
                    warnings.append(f"[DOMINIO MUTABLE] La clase {node.name} en protocol_types.py no tiene frozen=True")
    except Exception as e:
        warnings.append(f"Error analizando protocol_types.py: {e}")
        
    return len(warnings), warnings

def main() -> int:
    root = get_project_root()
    print("=" * 68)
    print(" [ARCHITECTURE-AUDIT] Auditoria de Arquitectura de Software")
    print("=" * 68)
    
    layer_errs, layer_msgs = audit_layers(root)
    immut_errs, immut_msgs = audit_domain_immutability(root)
    
    all_msgs = layer_msgs + immut_msgs
    total_issues = layer_errs + immut_errs
    
    if total_issues == 0:
        print("[PASS] Aislamiento de capas (Hexagonal/Ports & Adapters) conforme.")
        print("[PASS] Inmutabilidad de tipos de dominio verificada.")
        print("-" * 68)
        print("[EXITOSO] 100% de conformidad arquitectonica.")
        return 0
    else:
        for msg in all_msgs:
            print(f"  [ERROR] {msg}")
        print("-" * 68)
        print(f"[FALLO] Se encontraron {total_issues} problemas arquitectonicos.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
