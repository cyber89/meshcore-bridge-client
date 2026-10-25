# Pruebas y verificación de MeshCore Bridge

> **AI Context & Machine Contract**:
> - **Domain**: Test Automation, Fixture Isolation & QA Guardrails
> - **Authority Level**: Level 4 (Living SSoT for QA & Testing)
> - **Primary Rule**: Automatic execution of test suites (pytest, Playwright, Bandit, fuzzing) is STRICTLY PROHIBITED unless explicitly requested by the user.
> - **Isolation Invariant**: Tests MUST use temporary directories, mock hardware/transceivers, and loopback ports. NEVER touch operational databases or transmit over physical radio.

Esta guía describe la suite mantenida y cómo obtener evidencia reproducible. El inventario y clasificación detallada de los 147 módulos de prueba, fixtures y scripts auxiliares se encuentra en [TEST_INVENTORY.md](TEST_INVENTORY.md). Las
pruebas se ejecutan bajo petición explícita del usuario, según [AGENTS.md](../AGENTS.md).
La autorización del 2026-09-29 corresponde a la revisión histórica descrita más abajo;
no autoriza tareas posteriores. La auditoría inicial del 2026-10-09 se realizó sin
suites. La revisión histórica de modernización registró autorización para
pytest/cobertura, mypy, Ruff y navegador en entornos aislados; no autoriza suites
en tareas posteriores. El cambio de baseline descrito en ADR 0016 no ejecuta
suites ni autoriza radio física, SSH operativo o consultas a producción.

## Entorno de QA

La integración SQLite (ADR 0017) añade regresiones en `test_station_database.py`,
`test_chat_history.py`, `test_sqlite_domain.py` y `test_sqlite_history_api.py`.
`isolated_state` redirige también `DATABASE_PATH` a un directorio temporal.
Estas regresiones se prepararon sin ejecutar pytest ni navegador; los checks
estáticos no acreditan migración real, concurrencia bajo carga ni UI en ejecución.

Las afirmaciones de la revisión anterior y sus límites por plataforma se conservan
en el [informe histórico Python 3.14.8](audits/2026-10-10-python-314-modernization-report.md).

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

Registrar la versión real del binario. El perfil dev vigente fija Playwright
1.64.0 en `requirements-dev.txt` y `pyproject.toml`; el registro anterior de
Playwright 1.63.0 / Node.js 24.21.0 es histórico y no describe el entorno actual.
Las pruebas de navegador requieren también las
bibliotecas del sistema de Chromium. En QA WSL se extrajeron paquetes oficiales
Ubuntu dentro de `artifacts` y se usó `LD_LIBRARY_PATH` del proceso; eso no instala
dependencias globales ni acredita otro destino. Los temporales de pytest en WSL
deben estar en su filesystem nativo: la captura sobre DrvFS produjo un fallo
`tmpfile.truncate()` en esta revisión.

La fixture compartida `browser_page` limita las acciones de Playwright a diez
segundos, antes del watchdog global de pytest de treinta segundos. Así, un
control bloqueado produce un fallo de prueba con diagnóstico y permite continuar
la suite. Las pruebas de envío esperan también HTTP 200 de `/api/tx`; mostrar
un mensaje optimista en el feed no acredita que el backend lo haya aceptado.
Los nodos virtuales usan identidades completas de 32 bytes, idénticas a las
que devuelve su serialización Companion; los prefijos siguen siendo selectores.

## Suite mantenida y aislamiento

`pyproject.toml` configura la colección en `tests/`. Todas sus pruebas forman parte
de la suite; los módulos E2E no deben depender de una estación ya activa en
`localhost:8080`. Las fixtures deben usar configuración y datos temporales,
adaptadores virtuales, mocks de MQTT/SDK y servicios propios en loopback.

Los argumentos `db_path` y `data_dir` de `MeshCoreBridge` aíslan SQLite y el
directorio de almacenamiento. Desde código asíncrono, usar
`await MeshCoreBridge.create(db_path=..., data_dir=...)` para inicializar fuera
del event loop. Las fixtures deben configurar rutas actuales de datos temporales. Cerrar servidores, navegadores, tareas
y archivos aun cuando falle una expectativa.

Áreas cubiertas por módulos de la suite (su existencia no acredita una ejecución): framing y CRC del fallback, enums oficiales, CayenneLPP,
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

Los scripts `inspect_all_views.py` y `check_frontend_health.py` comparten
`scripts/isolated_frontend_station.py`: bloquea la carga de `.env`, crea cuenta,
SQLite, mapas y logs temporales, usa radio virtual y loopback con puerto cero,
autentica el navegador y cierra recursos incluso ante fallos. Ejecutarlos sigue
requiriendo autorización de navegador. El contrato SENSOR de fuente se llama
`test_sensor_subscriptions_static_contract.py`; no acredita ejecución de UI.

CI prepara Leaflet 1.9.4 con hashes SHA-256 fijados antes de las pruebas de mapa;
su ausencia falla en CI y solo permite skip local explícito. El runner de
categorías rechaza rutas ausentes y calcula el porcentaje real. Los nombres de
sus categorías agrupan regresiones; no certifican por sí solos que se ejecutó
una herramienta de mutación, un benchmark o una prueba con hardware.

Comprobaciones estáticas independientes de pytest:

```bash
python scripts/check_layer_contracts.py
node scripts/check_frontend_syntax.cjs
node scripts/build_frontend.cjs --check
python -m pip check
```

`python scripts/inventory_verification.py` regenera el inventario Python y
CommonJS sin importar la aplicación ni ejecutar escenarios. Distingue scripts
operativos, inspecciones aisladas e históricos. Los XML/coberturas que encuentre
en `tests/artifacts/` son evidencia local existente: no los atribuye al checkout
actual ni acredita que las suites pasen.

`generate_sample_mbtiles.py` crea teselas sintéticas de zoom 0–2 en
`tests/artifacts/maps/overview_sample.mbtiles`, sin sobrescribir archivos.
No genera cartografía real ni escribe en `data/maps/`. Los helpers
`setup_auth.py`, `reset_web_password.py` y `staged_update.py` modifican la
instalación o su estado; no son comprobaciones y no se ejecutan por una auditoría.
`audit_frontend_browser.py` y `audit_frontend_inspection.py` conservan puertos
fijos y aislamiento parcial; usar las fixtures mantenidas o los dos inspectores
que comparten `isolated_frontend_station.py` para una revisión aislada autorizada.

`check_frontend_health.py` devuelve código 1 ante excepciones JS, errores de
consola, respuestas HTTP 4xx/5xx, peticiones fallidas o controles/paneles
obligatorios ausentes. Su código 0 requiere completar la inspección sin esos
fallos; no certifica accesibilidad o rendimiento.

`inspect_web.py` inspecciona un destino elegido explícitamente; no crea una
estación temporal. La autorización de navegador y el destino seguro deben
resolverse antes de ejecutarlo. Para una SPA autenticada admite
`--storage-state <archivo-local>` con una sesión Playwright ya autorizada; el
archivo contiene cookies y debe tratarse como secreto, fuera de Git. No crea
cuentas ni convierte tokens Bearer en sesiones de navegador. Cada viewport
comprueba sesión, estación visible, componentes obligatorios, consola y red;
una pantalla de login o un fallo móvil hace fallar el resultado global.

`export_logs.py --json` devuelve código 1 si no obtiene diagnósticos válidos y
conserva un archivo de salida anterior; no guarda un objeto de error como si
fuera una exportación válida. `build_diagrams.py` falla si falta cualquiera de
sus fuentes JSON requeridas o no completa todas las entregas. Las regresiones
de estos contratos están en `tests/test_deep_tools_fixes.py`; no se ejecutan
automáticamente por modificar las herramientas.

El comprobador de imports expande los orígenes de paquete a todos sus módulos
descendientes, aunque no se exporten desde `__init__.py`, y recorre ASTs e imports locales transitivos para los
contratos `forbidden` declarados en `pyproject.toml`, sin importar la aplicación.
No sustituye una verificación completa de cinco capas ni detecta imports
dinámicos. El diagrama vigente permite que L3 use persistencia L5; ese import
por sí solo no es una infracción.

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
