---
name: bridge-test-runner
description: >-
  Orquestador de verificación estática y dinámica para MeshCore Bridge. Ejecuta en secuencia
  pytest (pruebas unitarias/fuzzing), mypy --strict (comprobación estricta de tipos) y ruff
  (linter y estilo de código), generando un informe unificado de calidad. Usar siempre antes de
  finalizar cambios o para depurar fallos en el parser/bridge.
---

# MeshCore Bridge Test & Quality Runner Skill

Esta skill permite al **Protocol QA & Fuzzing Agent** y al **Python Bridge Architect Agent** validar de forma automatizada que los cambios cumplan con los estándares de robustez, tipado estricto y ausencia de regresiones.

## Scripts y Herramientas

El script principal de verificación se encuentra en:
[run_checks.py](./scripts/run_checks.py)

## Modos de Uso

### 1. Ejecución Completa (Pytest + Mypy + Ruff)
```bash
python .agents/skills/bridge-test-runner/scripts/run_checks.py
```

### 2. Ejecutar Solo Suites de Pruebas (Pytest)
```bash
python .agents/skills/bridge-test-runner/scripts/run_checks.py --only-tests
```

### 3. Pasar Argumentos Específicos a Pytest (ej. ejecutar solo un archivo de prueba)
```bash
python .agents/skills/bridge-test-runner/scripts/run_checks.py --only-tests tests/test_protocol_types.py
```

### 4. Ejecutar Solo Verificación Estricta de Tipos (Mypy)
```bash
python .agents/skills/bridge-test-runner/scripts/run_checks.py --only-types
```

### 5. Salida en Formato JSON
```bash
python .agents/skills/bridge-test-runner/scripts/run_checks.py --json
```
