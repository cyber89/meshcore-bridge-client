# Corrección progresiva de la auditoría por capas

Fecha: 2026-10-05. Base de la primera entrega: `6717e87ccdaf0ea37ae8048aeb958c3b3a399442`.
Auditoría original: [LAYERED_SYSTEM_AUDIT_2026-10-04.md](LAYERED_SYSTEM_AUDIT_2026-10-04.md).

**Estado de esta continuación:** los **39/39 IDs originales** están corregidos
y aceptados en QA aislada (7 de la primera entrega y 32 de la segunda).
Las siete observaciones complementarias PI-S01…07 también están corregidas y
aceptadas en QA virtual, registradas por separado. La batería remota utiliza ya lectura
actual de estado en lugar de voltaje de arranque.

## Primera entrega histórica — commit 776eed7

En la primera entrega se corrigieron **7 de los 39 hallazgos reproducidos**: WEB-01, PI-02, RUNTIME-05,
WEB-02, RUNTIME-06, RUNTIME-04 y RUNTIME-01. De los seis P1 funcionales,
cinco quedaron corregidos; RUNTIME-02 seguía abierto. **Quedaban 32 hallazgos**
y los candidatos de deuda técnica adicionales al finalizar ese commit. El informe histórico conserva
sus reproducciones; este documento es el registro de cambios posteriores.

Los cambios evitan secretos en capturas/admin públicas, unifican autenticación
REST/WS, comprueban el tipo de respuesta raw, conservan potencias con signo,
separan persistencia de sugerencias visuales y restauran la actualización de rutas.
No añaden sondeos RF, schedulers ni reintentos. No se ejecutan sobre hardware,
broker o JSON de una instalación operativa.

## Orquestación y método de la primera entrega

El principal integra protocolo, registro/persistencia, despacho y documentación.
Tres especialistas trabajaron en privacidad de captura/SELF_INFO, autenticación
HTTP/WS y salidas administrativas MQTT/CLI. Se acordó propiedad de archivos;
los cambios compartidos se aplicaron secuencialmente y se revisó el diff conjunto.
Ningún subagente publica Git ni cambia las referencias oficiales.

Skills aplicadas: `security-code-auditor`, `bridge-test-runner`,
`contract-openapi-sync`, `python-patterns-typing`, `meshcore-source-inspector`
y `async-concurrency-engineering`. Fuentes firmware/SDK sólo de lectura.

Por hallazgo: caso con expectativa correcta antes del cambio → reproducción
del defecto → parche mínimo en su frontera real → regresiones y controles →
documentación de contratos/limitaciones → integración y suite mantenida.
Los harness históricos `audit_layer_*` afirman el comportamiento defectuoso;
no se reejecutan como aceptación ni se maquillan sus resultados.

## Primeros siete hallazgos corregidos, uno por uno

| Orden | ID | Cambio observable | Evidencia detallada |
|---|---|---|---|
| 1 | WEB-01 | CLI sensible conserva entrega privada, pero no contenido/bytes en capturas; GET/HEAD de listado/export exige la clave configurada. | [Captura](audits/fixes-2026-10-05/WEB-01-capture.md), [autenticación](audits/fixes-2026-10-05/WEB-01-auth.md) |
| 2 | PI-02 | Config y CLI públicas redactan PIN/credenciales antes de devolver/publicar por MQTT; caché privada intacta. | [PI-02](audits/fixes-2026-10-05/PI-02.md) |
| 3 | RUNTIME-05 | BATTERY no confirma SET_NAME; respuestas por opcode, stream de contactos, ERROR/DISABLED y timeout coherentes. | [RUNTIME-05](audits/fixes-2026-10-05/RUNTIME-05.md) |
| 4 | WEB-02 | Misma clave URL-encoded funciona en REST y WS; símbolos/Unicode, prioridad de cabecera, rechazo de duplicados y logs sin query sensible. | [WEB-02](audits/fixes-2026-10-05/WEB-02.md) |
| 5 | RUNTIME-06 | SELF_INFO 247 se interpreta como -9 dBm en todas las lecturas/eventos, sin modificar el objeto SDK ni aplicar clamp. | [RUNTIME-06](audits/fixes-2026-10-05/RUNTIME-06.md) |
| 6 | RUNTIME-04 | JSON conserva None; analítica no inventa TX ni vecinos. Valores históricos ambiguos permanecen intactos. | [RUNTIME-04](audits/fixes-2026-10-05/RUNTIME-04.md) |
| 7 | RUNTIME-01 | PATH_UPDATE consulta el método SDK real y actualiza la ruta; RX_LOG conserva observación y hashes 00, sin duplicar presencia. | [RUNTIME-01](audits/fixes-2026-10-05/RUNTIME-01.md) |

Las regresiones nuevas son 169 casos: 12 captura, 27 auth de capturas,
29 admin pública, 17 raw, 42 clave WS/REST, 27 SELF_INFO, seis persistencia
y nueve rutas. Las fixtures simulan respuestas oficiales y usan temporales.
El ajuste de la fixture TCP sustituye OK genérico por SENT/BATTERY reales,
manteniendo las expectativas de comportamiento; no relaja una aserción.

## Verificación histórica de la primera entrega

Entorno observado: Windows 11 (build 26300), Python 3.12.14, meshcore 2.3.8,
pytest 9.1.1, pytest-cov 7.1.0, Playwright 1.62.0, mypy 2.3.1 y Ruff 0.16.3.
El método GET_CONTACT_BY_KEY está presente en el SDK instalado y coincide con
el contrato examinado en la referencia. No se actualizaron dependencias.
El parseo AST de 60 módulos de producción y ocho archivos de regresión nueva
admite la gramática Python 3.10; no sustituye ejecución real bajo ese intérprete.

Resultado final de la suite mantenida para la primera entrega: **1132 aprobadas, 1 omitida y cero
fallos**, en 347,12 s. Se incluyen las 169 regresiones nuevas. Los resultados
focalizados previos se encuentran en cada anexo.

| Verificación | Resultado de 776eed7 | Alcance/limitación |
|---|---|---|
| Pytest mantenido | 1132 passed, 1 skipped | Directorios temporales, mocks y estación virtual propia. |
| Cobertura Python | 71,51% de líneas | XML final; no mide cobertura JS ni interoperabilidad física. |
| Grupo frontend/browser histórico | 117 casos aprobados | Grupo mixto de la misma suite; no equivale a contar sólo tests con Page ni a ejecutar sobre estación operativa. |
| Mypy --strict src | Sin errores, 60 módulos | Tipado estático; no prueba valores de hardware. |
| Ruff src/tests/scripts | Sin incidencias | Estilo y reglas configuradas. |
| Validador documental | 90 archivos, cero incidencias | Estructura/enlaces locales, no certificado de toda afirmación técnica. |
| Gramática Python 3.10 | 68 archivos admitidos | AST; intérprete de ejecución de QA: 3.12.14. |

La única omisión es `test_map_tile_symlink_cannot_escape_map_storage`:
Windows no permitió crear un enlace simbólico. Se conserva el skip de entorno;
no se marca ese control como aprobado. Los JSON/XML finales separan esta
ejecución aprobada de la primera integración fallida.

```powershell
$env:PYTHONUTF8 = '1'
.venv/Scripts/python.exe -X utf8 scripts/run_quality_checks.py --only-tests --timeout 900 --report tests/artifacts/layers-fixes-2026-10-05/maintained-verified.json -- tests --junitxml=tests/artifacts/layers-fixes-2026-10-05/maintained-verified.xml --cov-report=xml:tests/artifacts/layers-fixes-2026-10-05/coverage-verified.xml --cov-report=term:skip-covered -q -p no:cacheprovider --basetemp tests/artifacts/layers-fixes-verified-tmp
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-types --report tests/artifacts/layers-fixes-2026-10-05/mypy-final.json
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-lint --report tests/artifacts/layers-fixes-2026-10-05/ruff-final.json
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-docs --report tests/artifacts/layers-fixes-2026-10-05/docs-final.json
```

Chromium requiere ejecución fuera del sandbox para iniciar procesos; la suite
crea su propia estación virtual y puertos de loopback. No usa localhost:8080
ni un transceptor instalado. Los XML/JSON/cobertura y temporales quedan en
`tests/artifacts/`, fuera del commit según las reglas del repositorio.

Primera integración: **1129 aprobadas, 3 fallos y 1 omitida** (355,63 s).
Los tres casos numéricos invocaban TelemetryHandler con un contexto parcial,
sin el router propietario de la observación. La fixture ahora construye el
router real sobre ese contexto; conserva sus aserciones. El grupo relacionado
aprobó 58 casos antes de repetir la suite. No se rebajó una expectativa de
producción ni se ignoraron los fallos.

La impresión del runner falló posteriormente con UnicodeEncodeError en cp1252;
el JSON anterior sí se guardó con stdout/stderr y el código real de pytest.
La segunda invocación configura UTF-8 para padre y subprocesses. Es una
incidencia de salida de QA, registrada sin afirmar que pytest había aprobado.
No se modificó la herramienta ni dependencias globales para esconder el error.

## Segunda entrega — los 32 hallazgos restantes

Base: `776eed7`. Las correcciones de código de los **32 IDs restantes** están
implementadas y cuentan con reproducciones/regresiones focalizadas. La nueva
suite integrada aprobó 1369 pruebas, con una omisión de entorno y cero fallos.
Las 1132 pruebas anteriores son evidencia
histórica y **no se atribuyen al código de esta segunda entrega**.

El principal integra recepción/colas, parsers y modelos, TLS y documentación.
Un especialista se ocupa de administración, batería, ACK y políticas; otro de
SPA/REST/IndexedDB; otro de métricas, calidad, demo/simulador e instaladores.
Se mantiene propiedad explícita de archivos, referencias oficiales de sólo
lectura y reconciliación de contratos compartidos antes del pase global.
Ningún subagente publica por su cuenta ni transmite por hardware.

Además de las skills de la primera entrega se usan `html-css-modern-js`,
`web-browser-inspection`, `clean-code-solid`, `installer-release-maintenance`
y `project-reference-audit` según especialidad. La corrección conserva Python
3.10 como mínimo de producción; el entorno de ejecución de QA se identifica
por separado de la compatibilidad gramatical.

### Evidencia focalizada de la continuación

| Grupo | Réplica inicial | Pase focalizado posterior | Informe |
|---|---|---|---|
| Administración PI-01/03/04/05/06/09/10/11/12/13 y batería | 36 fallos y 3 controles antes de corregir | 380 casos administrativos/privacidad/ACK/lifecycle/routers aprobados, 42,60 s | [admin-remaining.md](audits/fixes-2026-10-05/admin-remaining.md) |
| ACK RUNTIME-03 | 7 fallos iniciales | 101 casos ACK/core/routers aprobados, 1,35 s; el grupo ampliado está incluido también en los 380 anteriores | [Administración y ACK](audits/fixes-2026-10-05/admin-remaining.md) |
| WEB-03…11 | 10 fallos y 1 control antes de corregir; revisión posterior: 3 fallos de almacenamiento | 89 relacionados aprobados, 101,68 s; después, 7 casos de persistencia/errores/ACK aprobados. 48 regresiones nuevas en total | [web-remaining.md](audits/fixes-2026-10-05/web-remaining.md) |
| Q-01…06 y PI-C01/02 | 16 fallos y 2 controles; Q-06 añade réplica aislada histórica | 71 aprobados, 6,79 s; migración posterior de fixture/lifecycle: 32 aprobados, 2,62 s | [quality-remaining.md](audits/fixes-2026-10-05/quality-remaining.md) |
| RX, orden TX, parsers de sensores, límites observados y TTL público MQTT | Core: 24 fallos y 5 controles; admisión RX: 4 fallos antes de corregir | 119 casos de dominio/reloj/persistencia aprobados, 3,34 s; 8 RX/salud aprobados, 0,70 s | [core-remaining.md](audits/fixes-2026-10-05/core-remaining.md) |
| MQTT TLS PI-S05, observación complementaria | Ausencia de capacidad en la auditoría histórica | 11 casos TLS aislados aprobados; no conexión a broker operativo | [Core y TLS](audits/fixes-2026-10-05/core-remaining.md) |
| Instaladores PI-S01…04, observaciones complementarias | `--dev` anunciaba éxito con pip fallido; revisión posterior reprodujo 2 fallos de instalación completa | 28 casos aprobados, 4,02 s, incluyendo identidad de servicio antes del despliegue | [Instaladores](audits/fixes-2026-10-05/installer-remaining.md) |
| Admisión MQTT y cooldowns PI-S06/07, observaciones complementarias | 3 fallos reproducidos: admisión desde otro hilo, lifecycle y protección tras reiniciar | 96 casos aprobados, 1,41 s; 403 relacionados aprobados, 40,21 s | [Políticas](audits/fixes-2026-10-05/policy-remaining.md) |

Los grupos se solapan y **no se suman como si fueran casos distintos**.
Cada anexo conserva los fallos intermedios y la causa del cambio. Los XML/JSON
focalizados quedan en `tests/artifacts/`; no se reemplaza evidencia histórica.
Las 48 regresiones web nuevas se dividen en **24 casos con navegador y 24 de
REST/otros contratos**; no se presentan los 48 como pruebas de navegador.

### Batería de un nodo remoto

La obtención solicitada por el usuario se corrige dentro del flujo de PI-05.
`get bat`, `bat`, `get_bat` y `battery` consultan el estado oficial del repetidor:
`bat` es la lectura actual de batería en mV. Ya no se sustituye por
`pwrmgt.bootmv`, voltaje histórico al arrancar y dependiente del firmware.
Los datos incluyen procedencia; sin respuesta real hay error, nunca una lectura
confirmada inventada. El porcentaje derivado del voltaje se identifica como
estimación, y no como medición electroquímica.

El refresco distingue consultas despachadas, respuestas confirmadas, parcial y
error/timeout. Mantiene los controles de rol y login existentes; elimina el CLI
redundante de voltaje de arranque, sin añadir sondeo periódico ni reenvíos.
Pruebas oficiales simuladas y fuente firmware sustentan este contrato; la
certificación con un repetidor físico concreto sigue fuera del entorno de QA.

### Política de recepción y ACK acordada

Los valores fueron acordados expresamente con el usuario durante la continuación:

- **RX: 256 trabajos pendientes**, además de **20 handlers concurrentes por
  defecto**, conservando el ajuste previo de ejecución `MAX_RX_CONCURRENCY`.
  La admisión precede la creación de
  trabajo asíncrono, evitando una tarea por cada entrada sin límite de backlog.
- Sólo se agrupan snapshots de igual identidad. Un evento crítico puede
  desplazar una observación pendiente; cuando todos los pendientes son críticos,
  el nuevo trabajo se rechaza con contadores y log observable. No se promete
  que una cola llena conserve una observación
  posterior ni una respuesta administrativa pública. El waiter directo del SDK
  conserva su frontera independiente de recepción.
- **ACK: capacidad dura de 200 y TTL de 3600 segundos**, medido por monotonic.
  Se poda al registrar/resolver y en el mantenimiento ya existente; resolver
  consume una entrada una sola vez. Una entrada vencida nunca confirma entrega.
- Capacidad ACK llena o colisión conserva pendientes existentes y devuelve
  `delivery_tracking` explícito. Una transmisión confirmada continúa sent; la
  SPA avisa que no hay seguimiento y no crea un pending ACK ni reenvía.

Estos cambios no seleccionan un nuevo intervalo RF, no crean un timer periódico
que transmita, y no utilizan la cifra 20 como si fuera la capacidad de backlog.
La política de rechazo no equivale a entrega garantizada bajo saturación.

## Registro actual de los 39 hallazgos

**Estado común actual de los 39 IDs: corregidos y aceptados en QA virtual.**
Las siete correcciones de 776eed7 conservan su aceptación histórica y se
revalidan junto con los otros cambios. Esta tabla describe el comportamiento
implementado y sus criterios concretos, no una certificación de hardware.

| ID | Estado | Cambio y evidencia |
|---|---|---|
| RUNTIME-01 | Corregido; QA aceptada | Dispatch SDK → ruta y observación sin absorción genérica; [anexo](audits/fixes-2026-10-05/RUNTIME-01.md). |
| RUNTIME-02 | Corregido; QA aceptada | Admisión RX 256 pendientes/20 handlers, rechazo visible y lifecycle; [core](audits/fixes-2026-10-05/core-remaining.md). |
| RUNTIME-03 | Corregido; QA aceptada | ACK 200/3600 monotonic, poda, consumo y resultado sin tracking; [admin](audits/fixes-2026-10-05/admin-remaining.md). |
| RUNTIME-04 | Corregido; QA aceptada | Persistencia cruda conserva None; analítica distingue observación/desconocido; [anexo](audits/fixes-2026-10-05/RUNTIME-04.md). |
| RUNTIME-05 | Corregido; QA aceptada | Respuesta por opcode, stream, error y timeout; [anexo](audits/fixes-2026-10-05/RUNTIME-05.md). |
| RUNTIME-06 | Corregido; QA aceptada | Normalización int8 común y preservación de datos desconocidos; [anexo](audits/fixes-2026-10-05/RUNTIME-06.md). |
| RUNTIME-07 | Corregido; QA aceptada | Orden TX prioridad+secuencia, independiente del reloj civil; [core](audits/fixes-2026-10-05/core-remaining.md). |
| WEB-01 | Corregido; QA aceptada | Secretos fuera de captura/export/WS público y lectura autorizada; [captura](audits/fixes-2026-10-05/WEB-01-capture.md), [auth](audits/fixes-2026-10-05/WEB-01-auth.md). |
| WEB-02 | Corregido; QA aceptada | Credenciales REST/WS URL decoding compartido; [anexo](audits/fixes-2026-10-05/WEB-02.md). |
| WEB-03 | Corregido; QA aceptada | Recarga sólo POST autorizado y GET/HEAD sin mutación; [web](audits/fixes-2026-10-05/web-remaining.md). |
| WEB-04 | Corregido; QA aceptada | Rutas/métodos exactos; subruta desconocida 404 sin SDK; [web](audits/fixes-2026-10-05/web-remaining.md). |
| WEB-05 | Corregido; QA aceptada | Rechazo de chat failed, error visible y borrador recuperable; [web](audits/fixes-2026-10-05/web-remaining.md). |
| WEB-06 | Corregido; QA aceptada | Feed/generación después de await; clear no resucita historia; [web](audits/fixes-2026-10-05/web-remaining.md). |
| WEB-07 | Corregido; QA aceptada | IndexedDB sent/failed ordenado; ACK delivered nunca se degrada; [web](audits/fixes-2026-10-05/web-remaining.md). |
| WEB-08 | Corregido; QA aceptada | Snapshot vacío completo retira datos; fallo parcial conserva directorio; [web](audits/fixes-2026-10-05/web-remaining.md). |
| WEB-09 | Corregido; QA aceptada | Potencia observada 27/-9/unknown exacta, capacidad sin heurísticas de placa; [web](audits/fixes-2026-10-05/web-remaining.md), [core](audits/fixes-2026-10-05/core-remaining.md). |
| WEB-10 | Corregido; QA aceptada | order asc/desc, desc reciente para inicio del Sniffer; [web](audits/fixes-2026-10-05/web-remaining.md). |
| WEB-11 | Corregido; QA aceptada | HTTP/WS conciliados, clear/generación y session_id RF; [web](audits/fixes-2026-10-05/web-remaining.md). |
| PI-01 | Corregido; QA aceptada | RTC remoto desde payload LE, tag sólo correlación; [admin](audits/fixes-2026-10-05/admin-remaining.md). |
| PI-02 | Corregido; QA aceptada | Redacción canónica de salidas públicas admin/CLI/MQTT; [anexo](audits/fixes-2026-10-05/PI-02.md). |
| PI-03 | Corregido; QA aceptada | Tipos originales antes de conversión; bool/fracción rechazados; [admin](audits/fixes-2026-10-05/admin-remaining.md). |
| PI-04 | Corregido; QA aceptada | Prevalidación completa custom y applied/partial confirmados; [admin](audits/fixes-2026-10-05/admin-remaining.md). |
| PI-05 | Corregido; QA aceptada | Refresh diferencia despacho/respuesta y batería actual/bootmv; [admin](audits/fixes-2026-10-05/admin-remaining.md). |
| PI-06 | Corregido; QA aceptada | Rol/capacidad antes de contacto/login/lote; telemetría no inventa REPEATER; [admin](audits/fixes-2026-10-05/admin-remaining.md). |
| PI-07 | Corregido; QA aceptada | Unidades por clave y booleanos de telemetría estrictos; [core](audits/fixes-2026-10-05/core-remaining.md). |
| PI-08 | Corregido; QA aceptada | Tamaños/escala/signedness CayenneLPP oficial 117 y campos posteriores; [core](audits/fixes-2026-10-05/core-remaining.md). |
| PI-09 | Corregido; QA aceptada | ERROR get_time no se presenta como RTC del dispositivo con hora host; [admin](audits/fixes-2026-10-05/admin-remaining.md). |
| PI-10 | Corregido; QA aceptada | ACL local unsupported explícito; BLE PIN no acredita ACL repeater; [admin](audits/fixes-2026-10-05/admin-remaining.md). |
| PI-11 | Corregido; QA aceptada | rx_delay adimensional también en terminal; [admin](audits/fixes-2026-10-05/admin-remaining.md). |
| PI-12 | Corregido; QA aceptada | Validación CLI status error/422, sin escritura rechazada; [admin](audits/fixes-2026-10-05/admin-remaining.md). |
| PI-13 | Corregido; QA aceptada | Precisión RF efectiva del wire en applied/cache, sin doble truncado; [admin](audits/fixes-2026-10-05/admin-remaining.md). |
| Q-01 | Corregido; QA aceptada | Helper recursivo con alcance y errores explícitos; [quality](audits/fixes-2026-10-05/quality-remaining.md). |
| Q-02 | Corregido; QA aceptada | Score AST por ámbito, convención explícita y sin falsa certificación McCabe; [quality](audits/fixes-2026-10-05/quality-remaining.md). |
| Q-03 | Corregido; QA aceptada | Se retira promesa universal de memoria sin respaldo; [quality](audits/fixes-2026-10-05/quality-remaining.md). |
| Q-04 | Corregido; QA aceptada | Minuto parcial presente, ventana y totales sesión identificados; [quality](audits/fixes-2026-10-05/quality-remaining.md), [web](audits/fixes-2026-10-05/web-remaining.md). |
| Q-05 | Corregido; QA aceptada | Evento caducado sólo suma sesión; fuera de orden retenido conserva timestamp; [quality](audits/fixes-2026-10-05/quality-remaining.md). |
| Q-06 | Corregido; QA aceptada | Demo temporal, sin .env/broker/hardware operativo, cierre incluso fallo parcial; [quality](audits/fixes-2026-10-05/quality-remaining.md). |
| PI-C01 | Corregido; QA aceptada | Simulador valida índice después de resolver alias de canal; [quality](audits/fixes-2026-10-05/quality-remaining.md). |
| PI-C02 | Corregido; QA aceptada | RTC virtual común SDK/raw y monotonic; [quality](audits/fixes-2026-10-05/quality-remaining.md). |

## Observaciones complementarias PI-S01…07

Estas siete observaciones estaban separadas de los 39 defectos reproducidos.
La continuación amplía su revisión sin atribuirles retrospectivamente pruebas
que la auditoría original no ejecutó.

| ID | Estado actual | Trabajo/aceptación |
|---|---|---|
| PI-S01 | Corregido; QA aceptada | Instalación dev propaga fallos de dependencias y anuncia sólo herramientas que ejecuta; [instaladores](audits/fixes-2026-10-05/installer-remaining.md). |
| PI-S02 | Corregido; QA aceptada | Verificar dependencias/imports del intérprete seleccionado, no una carpeta paho; [instaladores](audits/fixes-2026-10-05/installer-remaining.md). |
| PI-S03 | Corregido; QA aceptada | Staging verificado, rollback y conservación de datos ante fallo de update; [instaladores](audits/fixes-2026-10-05/installer-remaining.md). |
| PI-S04 | Corregido; QA aceptada | Usuario de servicio dedicado, acceso serie/datos y lifecycle de grupo; [instaladores](audits/fixes-2026-10-05/installer-remaining.md). |
| PI-S05 | Corregido; QA aceptada | MQTT TLS configurable con certificado validado; 11 casos aislados aprobados, sin broker real; [core](audits/fixes-2026-10-05/core-remaining.md). |
| PI-S06 | Corregido; QA aceptada | Reserva de admisión MQTT en su loop, incluida interfaz desde otro hilo; [políticas](audits/fixes-2026-10-05/policy-remaining.md). |
| PI-S07 | Corregido; QA aceptada | Continuidad del cooldown administrativo tras reinicio, sin timer ni intervalo nuevo; [políticas](audits/fixes-2026-10-05/policy-remaining.md). |

## Decisiones de deuda y compatibilidad

- Se retira `_nodes_by_name` de NodeRegistry: las búsquedas reales usan la clave
  pública canónica y el índice redundante no resolvía nombres ambiguos.
- Se retira `_safe_int` privado del router tras comprobar ausencia de callers.
  Logs y reportes diagnósticos usan un lector/renderer canónico; la fachada
  pública `SystemController.get_logs` se conserva delegando.
- `publish_safe(ttl_seconds)` ya no promete una caducidad ignorada: un TTL
  solicitado sin soporte devuelve rechazo explícito. No añade reintento MQTT.
- `Sniffer.toggleSnifferPause`, `EventBus.once`, constantes reservadas y otras
  fachadas públicas se mantienen por compatibilidad y se documentan. Ausencia
  de uso léxico interno no acredita que todas las extensiones externas las ignoren.
- `RepeaterManager.transmit_callback` se conserva como atributo inerte de
  compatibilidad; suministrarlo emite `DeprecationWarning` porque el servicio
  no lo invoca. `TxRateLimiter.transmit_callback` sigue siendo el callback TX
  activo, necesario y conservado. No se eliminan APIs públicas por ausencia
  de coincidencias léxicas internas.

La limpieza se basa en recorridos y consumidores comprobados. No se elimina
scratch ajeno, SDK/firmware de referencia, APIs de terceros ni hooks por una
heurística de nombre. No se afirma que todas las clases/métodos sean óptimos:
los inventarios y métricas AST orientan refactorización, no miden throughput,
memoria total, complejidad McCabe certificada ni accesibilidad completa.

## Verificación global de la segunda entrega

Primera ejecución integrada de esta segunda entrega: **1363 aprobadas,
3 fallidas y 1 omitida**, 536,67 s de pytest (539,781 s del runner). Se
conservan `tests/artifacts/remaining-fixes-2026-10-05/maintained-final.json` y
`tests/artifacts/remaining-fixes-2026-10-05/maintained-final.xml`; no se sustituyen por resultados
focalizados ni por la evidencia de la primera entrega.

Los fallos se investigaron sin relajar sus aserciones. En logs había una
regresión real: DELETE limpiaba el handler canónico y lo repoblaba con su
propia confirmación. Se retiró ese registro; el grupo diagnóstico/controladores
aprobó **12 casos en 0,45 s**, con lectura GET y contadores vacíos después del
borrado. En RX, el loop configurado pero inactivo impedía consumir el trabajo:
se selecciona el loop actual cuando procede. La notificación local de un error
del worker omite su envío al mismo sink para evitar realimentación de logs.
El grupo RX relacionado aprobó **50 casos en 1,77 s**. Estos conteos focalizados
se solapan con otros grupos y no acreditan por sí solos el pase global.

Controles posteriores del principal, preservados en
`tests/artifacts/remaining-fixes-2026-10-05/`:

| Control | Resultado posterior | Evidencia |
|---|---|---|
| Mypy strict de `src` | 60 archivos, cero problemas, 8,234 s | `mypy-verified.json` |
| Ruff de `src tests scripts` | Correcto, 0,688 s | `ruff-accepted.json` |
| Estructura documental | 102 archivos, cero problemas, 0,547 s | `docs-verified.json` |
| Gramática Python 3.10 | 89 fuentes comprobadas, correcta | Comprobación AST del principal; no ejecución del servicio bajo Python 3.10 |

El primer intento de Ruff posterior, `ruff-verified.json`, encontró un
`pyproject.toml` sintético de la fixture de instalador dentro de
`tests/artifacts`. Se excluyó esa carpeta de artefactos del descubrimiento de
configuración, coherente con sus exclusiones de Git/pytest. Se mantienen todas
las reglas de Ruff y el alcance de código mantenido; el fallo se conserva.
Los 102 documentos examinados incluyen un catálogo local con seis skills
adicionales ajenas al alcance de estos parches. Esa actualización concurrente
de catálogo/inventario no forma parte de la entrega ni se revierte; no se
reutiliza el conteo histórico de 96 documentos.

La segunda ejecución integrada fue **aprobada: 1369 passed, 1 skipped,
cero fallos y cero errores**, de 1370 casos recogidos. Pytest informó
474,23 s y el runner 476,094 s, con exit 0 y `all_passed=true` en
`maintained-verified.json`. La única omisión es
`test_map_tile_symlink_cannot_escape_map_storage`: Windows no permitió crear
el enlace simbólico de la regresión. Se conserva como omitida, no como aprobada.

| Verificación final de la segunda entrega | Resultado | Alcance |
|---|---|---|
| Pytest mantenido | 1369 aprobadas, 1 omitida, 0 fallos/errores | Estación virtual, temporales y adaptadores aislados |
| Cobertura Python | 74,32%; 11161/15017 líneas | `coverage-verified.xml`; no mide cobertura JavaScript ni interoperabilidad RF |
| Navegador con Page | 136 casos aprobados | Conteo AST de tests con Page reconciliado con JUnit final; Chromium y estación propia |
| Mypy strict `src` | 60 fuentes, correcto | `mypy-verified.json`; helpers/demo adicionales, 3 módulos correctos |
| Ruff `src tests scripts` | Correcto, 0,219 s | `ruff-release.json`, posterior al ajuste de EOF no semántico de una prueba |
| Documentación | 102 archivos, cero problemas | Estructura y enlaces locales; no certifica cada afirmación técnica |
| Gramática Python 3.10 | 89 fuentes, correcta | Análisis AST; ejecución de QA bajo Python 3.12.14 |
| Bash `-n install.sh` | Exit 0 | Sólo sintaxis; no ejecuta el instalador ni modifica servicios |

Entorno final: Windows 11 build 26300, Python 3.12.14, MeshCore SDK 2.3.8,
Paho 2.1.0, pytest 9.1.1, pytest-cov 7.1.0, coverage 7.15.4, Playwright 1.62.0,
mypy 2.3.1 y Ruff 0.16.3. Cryptography 50.0.0 se utilizó para QA TLS opcional;
no se añadió como dependencia obligatoria de producción.
El primer intento de Bash dentro del sandbox falló al inicializar MSYS con
`0xC0000022`; el reintento autorizado fuera del sandbox comprobó la sintaxis
sin ejecutar el instalador. No se atribuye ese error de entorno al script.

Comandos de la verificación final, con UTF-8 para la salida del runner y sus
subprocesos. Los reportes se conservan en el mismo directorio de artefactos
que la primera ronda fallida, con nombres distintos:

```powershell
$env:PYTHONUTF8 = '1'
.venv/Scripts/python.exe -X utf8 scripts/run_quality_checks.py --only-tests --timeout 1200 --report tests/artifacts/remaining-fixes-2026-10-05/maintained-verified.json -- tests --junitxml=tests/artifacts/remaining-fixes-2026-10-05/maintained-verified.xml --cov-report=xml:tests/artifacts/remaining-fixes-2026-10-05/coverage-verified.xml --cov-report=term:skip-covered -q -p no:cacheprovider --basetemp tests/artifacts/remaining-maintained-verified-tmp
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-types --report tests/artifacts/remaining-fixes-2026-10-05/mypy-verified.json
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-lint --report tests/artifacts/remaining-fixes-2026-10-05/ruff-release.json
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-docs --report tests/artifacts/remaining-fixes-2026-10-05/docs-verified.json
```

Los resultados focalizados se solapan con la suite completa. La aceptación
integrada se acredita con esta última ejecución y no reutiliza los XML de
776eed7. El cierre incluye los 39 defectos y las siete observaciones adicionales
en el alcance virtual documentado; las limitaciones físicas se mantienen.

## Límites y riesgos que se conservan explícitos

1. QA temporal/virtual no certifica interoperabilidad con radios instaladas,
   un broker remoto TLS real, migración de una instalación Linux real ni
   rendimiento de todas las clases en SBC. Los instaladores se verifican en
   fixtures aisladas; no se ejecutan contra una estación operativa.
2. Las respuestas Companion OK/SENT carecen de ID de solicitud. Un retorno
   atrasado del mismo tipo sigue ambiguo; no se añade retransmisión RF automática.
3. Una cola RX llena rechaza trabajos de forma observable. Los límites acotan
   memoria/trabajo pendiente, pero no acreditan ausencia de pérdida bajo carga.
4. El tracker ACK requiere correlación de cuatro bytes tras el retorno del SDK;
   no equivale a autenticación criptográfica ni almacena un ACK huérfano que
   llegue antes de registrarse la confirmación de envío.
5. Los JSON históricos sin procedencia no permiten inferir qué valores fueron
   medidos o sugeridos. Se preservan datos ambiguos; no se migran adivinando.
6. Los logs sin identificador canónico se concilian por campos y multiplicidad;
   la equivalencia de productores no cubiertos necesitaría un contrato de ID.
7. Hipótesis adicionales sin réplica específica (fragmentación WS, amenazas de
   origen LAN, cada placa/hardware y certificación WCAG completa) siguen siendo
   límites de alcance. No se presentan como fallos corregidos por una suite verde.

No se modifican los informes históricos para aparentar que eran correctos.
Cada cierre corresponde al defecto/contrato descrito y su evidencia de aceptación,
no a una garantía universal de ausencia de cualquier error futuro.
