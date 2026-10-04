# Corrección de errores pendientes documentados — 2026-10-04

Base: `6b2480c`. Alcance: ocho errores mypy y nueve incidencias Ruff registrados en la [auditoría frontend](FRONTEND_EXHAUSTIVE_AUDIT_2026-10-03.md). El usuario solicita corregirlos como continuación de la comprobación autorizada. Los resultados históricos se conservan; esta entrega registra su resolución por separado.

## Plan y propiedad

1. Contrastar cada diagnóstico con el contrato de datos y las llamadas reales.
2. Especialista de executors: corregir búsqueda de nodos, parámetros opcionales y construcción de comandos; añadir regresiones de comportamiento.
3. Especialista de lint: retirar imports/variable sin uso y simplificar contadores, conservando estado independiente por instancia.
4. Dirigente: extraer la rama de diccionario del redactor con contrato dict→dict, integrar, ejecutar comprobaciones globales de tipos/lint y pruebas aisladas de los subsistemas afectados, documentar y publicar sólo cambios propios.

Skills: `python-patterns-typing`, `clean-code-solid`, `bridge-test-runner`. Propiedad: executors y nueva regresión para el primer agente; contact manager, metrics aggregator y contacts controller para el segundo; redactor compartido, documentación y QA para el dirigente. Sin edición de `reference/`, nuevas dependencias o cambios del frontend.

## Cambios y causas

| Diagnóstico de la base | Causa y corrección |
|---|---|
| `repeater_executor.py:215`, retorno Any | La llamada dinámica a `find_by_name` ocultaba que retorna `NodeContactInfo`, mientras los consumidores esperan un dict. Usar el método tipado y convertir el objeto con su `to_dict()`. |
| `repeater_executor.py:444/462/470`, tres retornos Any | El redactor general declara Any→Any para estructuras arbitrarias. Extraer su rama real de diccionario como `redact_sensitive_mapping`, dict[str, Any]→dict[str, Any], y usarla en los resultados de lote. El helper general delega esa rama sin cambiar redacción, recursión ni passthrough de valores opacos. No se añaden casts, ignores, copias de resultados o guards artificiales para silenciar el diagnóstico. |
| `repeater_executor.py:1163/1176`, comando str opcional | El constructor puede retornar None por comando/parámetros inválidos. Rechazar el resultado inválido antes de registrar el envío o llamar RF/redactor. |
| `local_config_executor.py:549/561`, int sobre valor opcional | PIN/TX permiten obtener None por campo presente sin valor. Rechazarlo explícitamente en prevalidación y conservar la conversión/rango existentes. |
| Ruff, dos imports de contactos | Retirar `RouteObservation` y `decode_path_hashes`, sin consumidores. |
| Ruff, métricas: orden/espaciado y cinco C420 | Corregir separación de imports y usar `dict.fromkeys(..., 0)`. El valor cero es inmutable; `default_factory` y cada reinicio crean diccionarios propios. |
| Ruff, variable de sincronización de contactos | Retirar `now_cur` y su único import `time`; la sincronización no utilizaba ese timestamp. |

## Impacto en radio

No se implementa una nueva funcionalidad RF. Se corrige la validación de acciones ya iniciadas bajo demanda:

1. **Airtime**: ningún paquete adicional; una construcción inválida se rechaza antes de envío. Los comandos válidos conservan su recorrido.
2. **Spam/feedback**: no se añaden publicaciones automáticas, reintentos o bucles; se conservan los mecanismos existentes y el rechazo de destino local/roles.
3. **Timers**: no se crea ni rearma ningún scheduler; no cambia ningún límite, umbral, intervalo o cooldown. No se realizan transmisiones físicas.

## Verificación

Los **ocho errores de mypy y nueve de Ruff están resueltos**. La matriz final reúne **248 passed / 1 skipped / 0 failed**, en 18,93 s de pytest (20,187 s del runner). El skip corresponde a la creación de symlinks no permitida por esta plataforma Windows; no se omiten errores de configuración ni administración. Mypy `--strict src` pasa en **60 archivos**; Ruff `check src tests scripts` pasa.

| Evidencia | Resultado | Qué demuestra |
|---|---|---|
| Nuevas 17 regresiones contra `6b2480c` temporal | 9 fallos / 8 pasan | El acceso `.get` sobre `NodeContactInfo` falla por nombre/alias; los comandos inválidos no retornan el rechazo estructurado esperado. |
| Nuevas 17 regresiones finales | 17 pasan | CLIENT por nombre/alias conserva su guard; REPEATER por alias resuelve clave y consulta válida; comando no compilable se rechaza antes de login/send/cooldown. PIN/TX nulos y sus alias no mutan SDK/cache; valores válidos conservan contrato. |
| Redacción nueva/compartida | 5 pasan | Secretos anidados/PIN/comandos redactados, campos públicos e input original conservados; redactor general sigue admitiendo listas/valores opacos. |
| Suites de 14 módulos afectados | 248 pasan / 1 skip | Administración, contratos SDK, comandos, contactos, registro/telemetría, REST, seguridad de rutas/secretos y compatibilidad oficial. |
| Cobertura dirigida Python | 48,09%, 6872/14291 líneas | Parcial de `src`, sin cobertura JS ni certificación de backend completo. |

Las nuevas regresiones de PIN/TX nulos ya pasaban en la base porque se capturaba el TypeError. El cambio explicita esa validación y elimina el problema de tipos sin inventar una regresión de comportamiento. Los límites hardware existentes siguen activos: la fixture de TX cero define la placa `LOW_POWER` tanto en el SDK como en el snapshot cacheado, desde donde el executor aplica sus límites. No se modifican mínimos de potencia de producción para satisfacer la prueba.

## Fallos de QA adicionales y reparación de fixtures

La primera ejecución integrada dio **226 passed / 10 failed / 1 skipped / 1 warning**. Tres fallos correspondían a fixtures nuevas incompletas: el stub del resolver dejaba el alias sin canonizar y el snapshot hardware no representaba una placa capaz de TX cero. Se usa `TargetResolver` real y se completa el snapshot cacheado. Un reintento posterior dejó **246 passed / 2 failed / 1 skipped**, precisamente porque el hardware se había agregado sólo al SDK; la corrección del caché produce la matriz final aprobada. Se conserva evidencia de ambas ejecuciones.

Los otros siete fallos se reprodujeron, **7/7**, en una copia temporal del commit base, obtenida con `git archive` de `config.py`, `pyproject.toml`, `src`, `tests` y el runner. No se copió `.env`, no se hizo reset del checkout y no se conectó hardware. Sus causas:

- El escenario `repeat=false` carecía de baseline RF completo. Ahora proporciona frequency/BW/SF/CR y exige la llamada exacta SDK con repeat cero.
- Los mocks de configuración devolvían AsyncMocks vacíos en lugar de `Event(OK, {})`, y faltaba coding rate; generaban falsos 422 y una advertencia de coroutine no esperada. Los resultados/métodos SDK son explícitos y se conservan las comprobaciones de HTTP, caché y escrituras.
- Pruebas remotas esperaban setters incompatibles con la referencia oficial. `CommonCLI.cpp:588–605` y `Utils.h:82` requieren radio completo `set radio FREQ,BW,SF,CR`; las líneas 606–613 usan `set lat` y `set lon` separados. `set freq` existe como operación local condicionada a `sender_timestamp == 0` (línea 713), no como setter administrativo remoto. La contraseña remota usa `password ...` (línea 256), y el builder de login recibe `password`, no `pin`.
- El lote remoto antiguo incluía `hop_limit`, ya rechazado por producción. Se verifica el lote de tres operaciones admitidas y se añade una regresión separada que exige rechazar el lote con `hop_limit` antes de login/comandos. Se agregan además seis casos de rechazo de setters remotos obsoletos. No se relajan expectativas para permitir comandos inválidos.

Son **29 casos nuevos**: 17 fronteras de executors, cinco redacción, seis rechazos del builder y uno de lote `hop_limit`. Las referencias se leen sin cambios; firmware en `reference/meshcore/src/helpers/CommonCLI.cpp`, SDK en `reference/meshcore_py/src/meshcore/commands/device.py` (`set_tx_power`, `set_devicepin`).

## Evidencia, comandos y límites

[Resumen versionado](audits/backend-documented-errors-2026-10-04/verification-summary.json) incluye conteos/casos fallidos y skips de cada ejecución, comandos, resultados globales y hashes SHA256 de los seis archivos de producción y cinco de pruebas. El [recolector](audits/backend-documented-errors-2026-10-04/collect_evidence.py) sólo lee reportes existentes. Salidas crudas, JUnit, XML de cobertura y la copia temporal de la base se conservan localmente en `tests/artifacts/backend-documented-errors/`, ignorado por Git.

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-types
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-lint
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-tests --timeout 480 --report tests/artifacts/backend-documented-errors/recheck.json -- tests/test_admin_executor_type_boundaries.py tests/test_sensitive_mapping.py tests/test_admin_executors.py tests/test_admin_official_compatibility.py tests/test_node_and_repeater_config.py tests/test_recent_regressions.py tests/test_repeater_manager.py tests/test_repeater_manager_unit.py tests/test_contact_manager.py tests/test_node_registry_telemetry.py tests/test_channels_and_contacts_controllers.py tests/test_rest_controllers.py tests/test_web_official_compatibility.py tests/test_domain_official_compatibility.py -q --tb=short -p no:cacheprovider --basetemp=tests/artifacts/backend-documented-errors/tmp-recheck --junitxml=tests/artifacts/backend-documented-errors/junit-recheck.xml --cov-report=xml:tests/artifacts/backend-documented-errors/coverage-recheck.xml
.venv/Scripts/python.exe scripts/validate_project_docs.py
git diff --check
```

Herramientas: Python 3.12.14, pytest 9.1.1, mypy 2.3.1 y Ruff 0.16.3. Mypy/Ruff apuntan a compatibilidad Python 3.10; no se ejecutó runtime Python 3.10 en esta máquina. La prueba de los subsistemas está aislada por fixtures con archivos temporales, mocks MQTT/SDK y puertos de loopback propios. El despacho administrativo se observa en mocks del SDK, no en RF físico. La preparación local de contactos SDK de `_dispatch_rf_command` sigue previa al rechazo del comando unitario; el rechazo evita autenticación/transmisión del comando inválido y consumo del cooldown.

No se repite navegador porque no cambia producción HTML/CSS/JS y la matriz anterior de frontend ya pasó. No se ejecuta toda la suite mantenida ni se certifica lectura/escritura universal de parámetros. Los límites de hardware, timers, intervalos, binarios y endpoints siguen sus contratos existentes; el rechazo de comandos unitarios añade `code: 422` en el resultado administrativo interno.
