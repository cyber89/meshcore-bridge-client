#!/usr/bin/env python3
"""Auditor Determinista de Contratos Arquitectónicos y Complejidad para MeshCore Bridge.

Analiza el AST de todos los módulos en src/ para hacer cumplir:
1. Regla de Dependencia de Clean Architecture (Dominio no importa Infraestructura).
2. Detección de acoplamiento ilegal.
3. Evaluación estática de complejidad ciclomática por función.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Asegurar encoding UTF-8 en stdout
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_DIR = ROOT_DIR / "src"

# Definición formal de capas arquitectónicas
DOMAIN_MODULES = {
    "protocol_types.py",
    "lqi_engine.py",
    "sensor_decoder.py",
    "deduplicator.py",
    "packet_buffer.py",
}

FORBIDDEN_FOR_DOMAIN = {
    "src.web",
    "src.mqtt_client",
    "src.serial_driver",
    "src.bridge_core",
    "src.http_server",
    "web",
    "mqtt_client",
    "serial_driver",
}


def compute_mccabe_complexity(node: ast.AST) -> int:
    """Calcula la complejidad ciclomática de McCabe para una función o método."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler, ast.With)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.Assert):
            complexity += 1
    return complexity


def audit_imports_and_complexity() -> tuple[list[str], list[str]]:
    """Inspecciona imports y complejidad en todos los archivos de src/."""
    contract_violations: list[str] = []
    complexity_warnings: list[str] = []

    for py_file in sorted(SRC_DIR.glob("**/*.py")):
        if "__pycache__" in py_file.parts:
            continue

        rel_path = py_file.relative_to(SRC_DIR)
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as e:
            contract_violations.append(f"Error de sintaxis en {rel_path}: {e}")
            continue

        is_domain = py_file.name in DOMAIN_MODULES

        # 1. Auditoría de Imports
        for node in ast.walk(tree):
            if is_domain:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in FORBIDDEN_FOR_DOMAIN:
                            if alias.name == forbidden or alias.name.startswith(forbidden + "."):
                                contract_violations.append(
                                    f"Violación Clean Architecture en {rel_path}: Importa '{alias.name}' prohibido para el Dominio"
                                )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    for forbidden in FORBIDDEN_FOR_DOMAIN:
                        if node.module == forbidden or node.module.startswith(forbidden + "."):
                            contract_violations.append(
                                f"Violación Clean Architecture en {rel_path}: 'from {node.module} import ...' prohibido para el Dominio"
                            )

            # 2. Auditoría de Complejidad Ciclomática
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                comp = compute_mccabe_complexity(node)
                if comp > 20:
                    complexity_warnings.append(
                        f"Función muy compleja en {rel_path}::{node.name}() -> Complejidad {comp} (Recomendado <= 15)"
                    )

    return contract_violations, complexity_warnings


def main() -> None:
    print("🏛️  [ARCHITECTURE & CLEAN CODE] Auditando contratos de capas y complejidad...\n")

    violations, warnings = audit_imports_and_complexity()

    print("=" * 65)
    if violations:
        print(f"❌ [VIOLACIONES DE CONTRATO DETECTADAS: {len(violations)}]")
        for v in violations:
            print(f"   • {v}")
    else:
        print("✅ [CLEAN ARCHITECTURE 100% OK] Núcleo de dominio desacoplado de infraestructura.")

    print("=" * 65)
    if warnings:
        print(f"\n⚠️  [FUNCIONES CANDIDATAS A REFACTORIZACIÓN ({len(warnings)})]:")
        for w in warnings[:5]:
            print(f"   • {w}")
        if len(warnings) > 5:
            print(f"   • ... y {len(warnings) - 5} funciones más.")
    else:
        print("✅ [COMPLEJIDAD OK] No se detectaron funciones con complejidad excesiva (> 20).")


if __name__ == "__main__":
    main()
