#!/usr/bin/env python3
"""Auditor de Integridad de CONTEXT.md y Architecture Decision Records (ADR).

Verifica la estructura, numeración secuencial y secciones estándar de los ADRs
en docs/adr/, y proporciona scaffolding para nuevos registros.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

# Asegurar encoding UTF-8 en stdout
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parents[4]
CONTEXT_FILE = ROOT_DIR / "CONTEXT.md"
ADR_DIR = ROOT_DIR / "docs" / "adr"

REQUIRED_SECTIONS = [
    "Contexto y Problema",
    "Factores de Decisión",
    "Decisión",
    "Consecuencias",
]


def audit_context_file() -> list[str]:
    """Verifica la existencia y contenido básico de CONTEXT.md."""
    issues: list[str] = []
    if not CONTEXT_FILE.exists():
        issues.append(f"Falta el archivo canónico: {CONTEXT_FILE}")
        return issues

    content = CONTEXT_FILE.read_text(encoding="utf-8")
    for keyword in ["CLIENT", "REPEATER", "ROOM", "SENSOR", "LOCAL", "Airtime", "Deep Modules"]:
        if keyword not in content:
            issues.append(f"CONTEXT.md no menciona el término esencial: '{keyword}'")

    return issues


def audit_adrs() -> tuple[list[Path], list[str]]:
    """Audita la numeración y estructura de los ADRs en docs/adr/."""
    issues: list[str] = []
    if not ADR_DIR.exists():
        issues.append(f"Directorio de ADRs no existe: {ADR_DIR}")
        return [], issues

    adr_files = sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))
    if not adr_files:
        issues.append(f"No se encontraron ADRs numerados en {ADR_DIR}")
        return [], issues

    # Verificar numeración secuencial
    for i, adr_path in enumerate(adr_files, start=1):
        expected_prefix = f"{i:04d}"
        if not adr_path.name.startswith(expected_prefix):
            issues.append(f"Secuencia rota: '{adr_path.name}' debería comenzar con '{expected_prefix}'")

        content = adr_path.read_text(encoding="utf-8")
        for sec in REQUIRED_SECTIONS:
            if f"## {sec}" not in content and f"# {sec}" not in content:
                issues.append(f"'{adr_path.name}' carece de la sección obligatoria: '## {sec}'")

    return adr_files, issues


def create_new_adr(title: str, existing_adrs: list[Path]) -> Path:
    """Crea el borrador para el siguiente ADR en la secuencia."""
    next_num = len(existing_adrs) + 1
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    filename = f"{next_num:04d}-{slug}.md"
    target_path = ADR_DIR / filename

    today = time.strftime("%Y-%m-%d")
    template = f"""# ADR {next_num:04d}: {title}

- **Estado**: Propuesto
- **Fecha**: {today}
- **Autores**: Agente 0 (Lead Orchestrator), Equipo MeshCore Bridge
- **Contexto**: `CONTEXT.md`, `ARCHITECTURE.md`

---

## Contexto y Problema

Describir la situación técnica, motivación o necesidad que origina esta decisión.

## Factores de Decisión

1. **Factor 1**: Explicación del impacto técnico o de arquitectura.
2. **Factor 2**: Mantenibilidad, airtime de radio LoRa o resiliencia de red.

## Decisión

1. Detalle específico de la decisión adoptada.
2. Contratos de interfaz o restricciones que se imponen.

## Consecuencias

- **Positivas**:
  - Beneficio 1.
- **Negativas / Compensaciones**:
  - Compensación o sobrecoste asumido.
"""

    ADR_DIR.mkdir(parents=True, exist_ok=True)
    target_path.write_text(template, encoding="utf-8")
    return target_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditor de Integridad de CONTEXT.md y ADRs")
    parser.add_argument("--new", type=str, help="Crear borrador para un nuevo ADR con el título indicado")
    args = parser.parse_args()

    print("🏛️  [DOMAIN & ADR KEEPER] Verificando gobernanza de arquitectura...\n")

    context_issues = audit_context_file()
    adr_files, adr_issues = audit_adrs()

    if args.new:
        new_path = create_new_adr(args.new, adr_files)
        print(f"✨ [NUEVO ADR CREADO] Archivo: {new_path.relative_to(ROOT_DIR)}")
        return

    print(f"📄 CONTEXT.md: {'✅ Válido' if not context_issues else '⚠️  Incidencias'}")
    for ci in context_issues:
        print(f"   • {ci}")

    print(f"\n📚 ADRs registrados en docs/adr/: {len(adr_files)}")
    for adr in adr_files:
        print(f"   • {adr.name}")

    if adr_issues:
        print("\n⚠️  [ALERTAS DE INTEGRIDAD EN ADRs]:")
        for ai in adr_issues:
            print(f"   • {ai}")
    else:
        print("\n✅ [INTEGRIDAD 100% OK] Todos los ADRs cumplen con la secuencia y secciones requeridas.")


if __name__ == "__main__":
    main()
