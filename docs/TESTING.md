# Pruebas y verificación de MeshCore Bridge

Esta guía describe la suite mantenida y cómo obtener evidencia reproducible. Las
pruebas se ejecutan bajo petición explícita del usuario, según [AGENTS.md](../AGENTS.md).
La autorización del 2026-09-29 corresponde a la revisión histórica descrita más abajo;
no autoriza tareas posteriores. La auditoría inicial del 2026-10-09 se realizó sin
suites. La revisión histórica de modernización registró autorización para
pytest/cobertura, mypy, Ruff y navegador en entornos aislados; no autoriza suites
en tareas posteriores. El cambio de baseline descrito en ADR 0016 no ejecuta
suites ni autoriza radio física, SSH operativo o consultas a producción.

## Entorno de QA

Las afirmaciones de la revisión anterior y sus límites por plataforma se conservan
en el [informe histórico Python 3.14.8](PYTHON_314_MODERNIZATION_REPORT.md).

El baseline vigente es CPython estable 3.12 o superior, con 3.13.5 recomendado y
sin máximo, según [ADR 0016](adr/0016-python-3-12-baseline.md).
Registrar la versión real de cada ejecución sin extrapolar resultados. Crear un entorno
de QA nuevo con el intérprete elegido, sin modificar la venv de una estación operativa:

```bash
python3.13 -m venv .venv
# Windows con launcher: py -3.13 -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m playwright install chromium
```

Pytest, pytest-asyncio, pytest-cov, mypy, ruff, Bandit, Playwright, HTTPX y cryptography son herramientas
de desarrollo. No son dependencias necesarias del bridge operativo. Chromium se
utiliza en modo headless. La CI instala también sus dependencias de sistema. Registrar
`python --version`, plataforma, arquitectura, pins instalados y `python -m pip check`
en cada ejecución. La disponibilidad de wheels y navegadores se comprueba por destino;
el cambio de mínimo no demuestra soporte automático de cada SBC o build sin GIL.

`cryptography==50.0.2` genera certificados temporales para las regresiones TLS de
MQTT en loopback. Está fijado únicamente en el perfil `dev`; el cliente operativo
utiliza `ssl` de Python y Paho. Una venv parcial sin esta dependencia omite esas
regresiones y no acredita TLS.

La auditoría i18n necesita Node.js. Se puede reutilizar el binario incluido con
Playwright, sin instalar otro runtime global. En Linux, con el entorno QA activado:

```bash
node_driver_dir=$(python -c 'from pathlib import Path; import playwright; print(Path(playwright.__file__).parent / "driver")')
export PATH="$node_driver_dir:$PATH"
node --version
python -m pytest tests/test_frontend_i18n_audit.py tests/test_remaining_mqtt_tls.py -ra
```

Registrar la versión real del binario; el incluido en Playwright 1.63.0 durante
esta revisión es Node.js 24.21.0. Las pruebas de navegador requieren también las
bibliotecas del sistema de Chromium. En QA WSL se extrajeron paquetes oficiales
Ubuntu dentro de `artifacts` y se usó `LD_LIBRARY_PATH` del proceso; eso no instala
dependencias globales ni acredita otro destino. Los temporales de pytest en WSL
deben estar en su filesystem nativo: la captura sobre DrvFS produjo un fallo
`tmpfile.truncate()` en esta revisión.

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
actual. La CI de esa revisión utilizaba Python 3.10 y 3.12; esos resultados son
históricos y no acreditan el checkout actual. La configuración CI vigente usa
3.13.5 para lint y una matriz de pruebas 3.12/3.13.5; sus resultados remotos
deben consultarse por separado de la validación local. Esta configuración no
acredita ejecución exitosa en ninguna de esas versiones.
