---
name: bridge-test-runner
description: Ejecutar pytest, cobertura, mypy y ruff de MeshCore Bridge cuando el usuario autoriza pruebas; conservar resultados y fallos reales.
---

# Verificación del proyecto

Leer [AGENTS.md](../../../AGENTS.md) y [TESTING.md](../../../docs/TESTING.md).
Ejecutar suites únicamente cuando el usuario lo solicite; una autorización se mantiene
durante la tarea. Las verificaciones usan radio virtual, loopback y datos temporales.

El baseline es CPython 3.12+, conforme al [ADR 0016](../../../docs/adr/0016-python-3-12-baseline.md).
Registrar intérprete, plataforma, arquitectura, pins y pip check de un entorno
aislado. Los resultados obtenidos con versiones anteriores no acreditan este baseline.

El ejecutor canónico es [run_quality_checks.py](../../../scripts/run_quality_checks.py).
[run_checks.py](scripts/run_checks.py) conserva el punto de entrada de esta skill.

```bash
python scripts/run_quality_checks.py --report tests/artifacts/quality.json
python scripts/run_quality_checks.py --only-tests -- tests/test_rx_routers.py -q
python scripts/run_quality_checks.py --only-types
python scripts/run_quality_checks.py --only-lint
python scripts/run_quality_checks.py --only-docs
python scripts/run_quality_checks.py --only-tests --timeout 900 --json
```

Usa el intérprete actual. Herramientas ausentes, colección vacía, fallos y timeouts
son resultados fallidos; no sustituir pytest por unittest ni anunciar éxito de una
suite distinta. El timeout es por herramienta; conservar stdout/stderr parciales.
Informar conteos, cobertura, skips y limitaciones de navegador o hardware por separado.
No repetir comprobaciones aprobadas salvo cambios posteriores o dudas concretas.

Versión recomendada: CPython 3.13.5. Se aceptan versiones estables >=3.12 sin límite superior.
