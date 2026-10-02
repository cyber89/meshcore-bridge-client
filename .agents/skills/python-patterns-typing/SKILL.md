---
name: python-patterns-typing
description: Mantener Python 3.10 compatible, tipos estrictos y modelos de dominio de MeshCore Bridge; usar al modificar Python del proyecto.
---

# Python del bridge

Respetar [AGENTS.md](../../../AGENTS.md), [CONTEXT.md](../../../CONTEXT.md) y
[pyproject.toml](../../../pyproject.toml). El mínimo soportado es Python 3.10.

- Anotar interfaces públicas y funciones nuevas; usar Protocol para adaptadores y
  reservar Any para límites externos que todavía no tienen esquema validado.
- Los enums de protocolo son IntEnum; usar dataclasses frozen para valores inmutables
  y slots cuando corresponda. No congelar indiscriminadamente estado operativo mutable.
- `typing.Self` y `assert_never` son de Python 3.11. En 3.10 usar TypeVar/patrones
  compatibles; un backport requiere dependencia explícita y justificación.
- Mantener cancelación, referencias a tareas propias y limpieza de recursos.
  Ver [async-concurrency-engineering](../async-concurrency-engineering/SKILL.md).
- Pruebas autorizadas: fixtures temporales, mocks del SDK y adaptadores virtuales;
  expectativas sobre comportamiento, no detalles privados accidentales.

```bash
python -m mypy --strict src
python -m ruff check src tests scripts
python .agents/skills/python-patterns-typing/scripts/verify_python_standards.py
```

El script propio es una inspección AST orientativa; mypy es el comprobador de tipos.
No presentar ninguno como demostración de funcionamiento en hardware.
