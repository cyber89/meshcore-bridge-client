# Pruebas y verificación de MeshCore Bridge

Esta guía describe la suite mantenida y cómo obtener evidencia reproducible. Las
pruebas se ejecutan bajo petición explícita del usuario, según [AGENTS.md](../AGENTS.md).
La solicitud del 2026-09-29 autoriza la revisión, ejecución y ampliación de pruebas
de esta tarea. No autoriza transmisiones por radio física ni consultas a producción.

## Entorno de QA

Python 3.10 es el mínimo del proyecto. La revisión local usa Python 3.12.14 y el
entorno `.venv`; su launcher fue reparado porque apuntaba a un Python eliminado,
conservando los paquetes instalados. En una instalación nueva:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m playwright install chromium
```

Pytest, pytest-asyncio, pytest-cov, mypy, ruff, Bandit y Playwright son herramientas
de desarrollo. No son dependencias necesarias del bridge operativo. Chromium se
utiliza en modo headless. La CI instala también sus dependencias de sistema.

## Suite mantenida y aislamiento

`pyproject.toml` configura la colección en `tests/`. Todas sus pruebas forman parte
de la suite; los módulos E2E no deben depender de una estación ya activa en
`localhost:8080`. Las fixtures deben usar configuración y datos temporales,
adaptadores virtuales, mocks de MQTT/SDK y servicios propios en loopback.

El argumento antiguo `MeshCoreBridge(db_path=...)` no aísla la persistencia JSON:
el constructor lo acepta mediante kwargs de compatibilidad y lo ignora. Configurar
las rutas actuales de datos en las fixtures. Cerrar servidores, navegadores, tareas
y archivos aun cuando falle una expectativa.

Áreas verificadas: framing y CRC del fallback, enums oficiales, CayenneLPP,
registro de nodos/roles, deduplicación, cola TX y airtime, SDK/watchdog,
administración/autenticación, MQTT, handlers RX, REST, HTTP/WebSocket, mapas
MBTiles, simulación y frontend. Las regresiones deben comprobar comportamiento
observable y preservar la exclusión de REPEATER/LOCAL y la protección de secretos.

## Comandos reproducibles

```bash
python -m pytest tests -ra
python -m pytest tests --junitxml=tests/artifacts/junit.xml --cov-report=xml:tests/artifacts/coverage.xml
python -m mypy --strict src
python -m ruff check src tests scripts
python scripts/validate_project_docs.py
python scripts/run_quality_checks.py --report tests/artifacts/quality.json
```

En Windows sin activar el entorno, sustituir `python` por `.venv/Scripts/python.exe`.
Para seleccionar pruebas y pasar flags sin perderlos:

```bash
python scripts/run_quality_checks.py --only-tests -- tests/test_quality_tools.py -q
python scripts/run_quality_checks.py --only-types
python scripts/run_quality_checks.py --only-lint
python scripts/run_quality_checks.py --only-docs
```

El punto de entrada de la skill `bridge-test-runner` delega en el mismo ejecutor.
El runner utiliza el intérprete actual y falla si una herramienta falta, pytest no
colecciona pruebas, una suite falla o hay timeout. No sustituye silenciosamente
pytest por unittest. El informe JSON conserva comando, salida, errores y duración.

## Scripts auxiliares e históricos

Los scripts de `scripts/` y `scratch/` no entran automáticamente en pytest. Antes
de ejecutarlos, comprobar si crean procesos, usan datos del operador, requieren
MQTT externo o consultan servicios existentes. Los simuladores no acreditan RF
físico; los analizadores regex/AST son señales, no pruebas completas de contratos,
seguridad o rendimiento.

`scratch/` contiene reproducciones puntuales; promover las regresiones necesarias
a `tests/`. Las pruebas incluidas en `reference/` y los bundles de terceros de
`.agents/skills/archify` y `ui-ux-pro-max` pertenecen a esos proyectos y no forman
parte de la suite del bridge.

## Evidencia de la revisión del 2026-09-29

La ejecución inicial del backend registró 270 pruebas aprobadas y siete fallidas;
se detectaron fixtures y expectativas obsoletas. Esta cifra es una línea de base,
no el resultado de aceptación de los cambios. La ejecución completa final y las
limitaciones se incorporarán después de integrar las correcciones.

La evidencia generada se conserva en `tests/artifacts/` (ignorada en Git). El
resumen final debe incluir conteos, cobertura, skips y resultados separados de
tipado, lint y navegador; los reportes históricos de agosto no prueban el estado
actual. La CI ejecuta la suite en Python 3.10 y 3.12; sus resultados remotos deben
consultarse por separado de la validación local.
