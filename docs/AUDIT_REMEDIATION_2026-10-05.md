# Corrección progresiva de la auditoría por capas

Fecha: 2026-10-05. Base Git: `6717e87ccdaf0ea37ae8048aeb958c3b3a399442`.
Auditoría original: [LAYERED_SYSTEM_AUDIT_2026-10-04.md](LAYERED_SYSTEM_AUDIT_2026-10-04.md).

## Resultado de la primera entrega

Se corrigen **7 de los 39 hallazgos reproducidos**: WEB-01, PI-02, RUNTIME-05,
WEB-02, RUNTIME-06, RUNTIME-04 y RUNTIME-01. De los seis P1 funcionales,
cinco quedan corregidos; RUNTIME-02 continúa abierto. **Quedan 32 hallazgos**
y los candidatos de deuda técnica adicionales. El informe histórico conserva
sus reproducciones; este documento es el registro de cambios posteriores.

Los cambios evitan secretos en capturas/admin públicas, unifican autenticación
REST/WS, comprueban el tipo de respuesta raw, conservan potencias con signo,
separan persistencia de sugerencias visuales y restauran la actualización de rutas.
No añaden sondeos RF, schedulers ni reintentos. No se ejecutan sobre hardware,
broker o JSON de una instalación operativa.

## Orquestación y método

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

## Hallazgos corregidos, uno por uno

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

## Matriz de verificación integrada

Entorno observado: Windows 11 (build 26300), Python 3.12.14, meshcore 2.3.8,
pytest 9.1.1, pytest-cov 7.1.0, Playwright 1.62.0, mypy 2.3.1 y Ruff 0.16.3.
El método GET_CONTACT_BY_KEY está presente en el SDK instalado y coincide con
el contrato examinado en la referencia. No se actualizaron dependencias.
El parseo AST de 60 módulos de producción y ocho archivos de regresión nueva
admite la gramática Python 3.10; no sustituye ejecución real bajo ese intérprete.

Resultado final de la suite mantenida: **1132 aprobadas, 1 omitida y cero
fallos**, en 347,12 s. Se incluyen las 169 regresiones nuevas. Los resultados
focalizados previos se encuentran en cada anexo.

| Verificación | Resultado actual | Alcance/limitación |
|---|---|---|
| Pytest mantenido | 1132 passed, 1 skipped | Directorios temporales, mocks y estación virtual propia. |
| Cobertura Python | 71,51% de líneas | XML final; no mide cobertura JS ni interoperabilidad física. |
| Navegador | 117 casos aprobados | Casos frontend/browser de la misma suite; no ejecución sobre estación operativa. |
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

## Registro completo del trabajo pendiente

Los detalles, fuentes y casos previos siguen en los anexos de la auditoría original.
“Pendiente” no significa corregido, verificado en hardware ni descartado.

| ID | Estado | Próxima acción y aceptación |
|---|---|---|
| RUNTIME-01 | Corregido | Regresión SDK → registro → WS; limitación de ráfagas en RUNTIME-02. |
| RUNTIME-02 | Pendiente de acuerdo | Cola/worker con capacidad y política acordadas; ráfaga+consumidor lento, sin pérdida silenciosa de ACK/admin. |
| RUNTIME-03 | Pendiente de acuerdo | Vigencia/capacidad ACK y duplicados; definir TTL/máximo antes de implementarlos. |
| RUNTIME-04 | Corregido | Persistencia cruda, reload de desconocidos y analítica con procedencia; WEB-09 sigue abierto. |
| RUNTIME-05 | Corregido | Respuestas por opcode; mismo tipo atrasado sigue ambiguo por diseño Companion. |
| RUNTIME-06 | Corregido | Normalización int8 canónica; hardware y escritura conservan sus validadores. |
| RUNTIME-07 | Pendiente | Orden prioridad+secuencia, tiempo de pared como metadato; prueba de reloj que retrocede. |
| WEB-01 | Corregido | Captura sin secretos, waiter privado intacto y auth de listado/export. |
| WEB-02 | Corregido | REST/WS con parser común, UTF-8 y comparación constante. |
| WEB-03 | Pendiente | Recarga cartográfica exclusivamente mediante POST autorizado; GET sin mutación. |
| WEB-04 | Pendiente | Rutas/métodos exactos de canales; subruta desconocida 404 sin escritura SDK. |
| WEB-05 | Pendiente | 503 conserva borrador, persiste failed y muestra error; sin reenvío automático. |
| WEB-06 | Pendiente | Generación de feed tras await; historial tardío no se dibuja en otro canal. |
| WEB-07 | Pendiente | Persistir sent/failed/ACK ordenadamente en IndexedDB; no degradar ACK concurrente. |
| WEB-08 | Pendiente | Snapshot vacío válido retira nodos; errores no vacían datos. |
| WEB-09 | Pendiente | Separar medida y capacidad del slider; mostrar 27/-9/unknown sin clamp silencioso. |
| WEB-10 | Pendiente | Tail/orden/cursor: listar capturas recientes cuando se pide límite inicial. |
| WEB-11 | Pendiente | Merge HTTP/WS por identidad/generación; snapshot tardío no elimina recepción nueva. |
| PI-01 | Pendiente | Reloj remoto desde payload LE; tag únicamente para correlación. |
| PI-02 | Corregido | Redacción en salidas públicas de admin/CLI/MQTT. |
| PI-03 | Pendiente | Validación de tipos originales antes de int; rechazar bool/fracciones en flags/modos. |
| PI-04 | Pendiente | Prevalidar lote custom completo; applied/partial en fallos posteriores. |
| PI-05 | Pendiente | Refresh diferencia despacho, respuestas reales, timeout y snapshots históricos. |
| PI-06 | Pendiente | Rol/capacidad antes del lote remoto; nunca CLI de repeater sobre CLIENT. |
| PI-07 | Pendiente | Unidades explícitas por clave y booleanos estrictos de telemetría. |
| PI-08 | Pendiente | Layout CayenneLPP 117 y tipos oficiales; preservar campos posteriores. |
| PI-09 | Pendiente | ERROR get_time no muestra hora del host como reloj confirmado del dispositivo. |
| PI-10 | Pendiente | ACL local unsupported/capacidad real; no inferir permisos del PIN BLE. |
| PI-11 | Pendiente | rx_delay como factor adimensional en consola y vista. |
| PI-12 | Pendiente | Validación CLI devuelve error estructurado, no warning con status ok. |
| PI-13 | Pendiente | Cuantizar o rechazar precisión RF antes de enviar/confirmar/cachar. |
| Q-01 | Pendiente | Herramienta recursiva con alcance verificable; skill protegida por permisos del entorno. |
| Q-02 | Pendiente | Métrica por scope documentada; no atribuir McCabe certificado al helper propio. |
| Q-03 | Pendiente | Corregir promesa <100 KB; presupuesto medido con plataforma/carga. |
| Q-04 | Pendiente | Bucket en curso en gráfico o ventana de minutos cerrados explícita. |
| Q-05 | Pendiente | Evitar reasignar paquetes fuera de retención a otro timestamp. |
| Q-06 | Pendiente | Demo con rutas propias y lifecycle; no usar configuración de estación. |
| PI-C01 | Pendiente | Simulador valida el índice resuelto de alias channel_999. |
| PI-C02 | Pendiente | RTC virtual común a set/get SDK/raw. |

RUNTIME-CODE-01 y los demás candidatos de desuso son deuda adicional, fuera
del conteo de 39. Verificar callers/contratos antes de retirar índices,
helpers o APIs legadas; no borrar scratch ni dependencias por heurística.

## Orden de las siguientes entregas

1. Cerrar RUNTIME-02 tras el acuerdo de capacidad/admisión. Medir escenario
   aislado y documentar si agrupar sólo observaciones repetidas; preservar
   respuestas críticas y apagado de workers. No reutilizar 20 como límite
   de backlog: es el límite de ejecución concurrente actual.
2. Corregir WEB-03/04 y PI-03/04/06: permisos, rutas exactas, prevalidación y roles.
3. Corregir PI-01/05/07/08/09/10/11/12/13 y RUNTIME-03/07: datos oficiales,
   vigencia, confirmación real, unidades y precisión. TTL/capacidad ACK
   requieren acuerdo; 200 era sólo disparador de poda, no máximo.
4. Corregir WEB-05…11 con navegador virtual e IndexedDB: errores de envío,
   generación, persistencia, snapshots y medidas sin clamp.
5. Corregir Q-01…06 y PI-C01/02; después simplificar deuda con callers reales.

La capacidad RX se consultó al usuario durante esta entrega. No se eligió un
nuevo máximo, TTL o intervalo. AGENTS.md exige: “NUNCA elegir un límite, umbral
o intervalo de forma unilateral — siempre preguntar al usuario”. Una respuesta
pendiente no autoriza asumir el valor.

## Límites que siguen vigentes

No se certifican todos los métodos ni interoperabilidad física mediante mocks.
Los datos históricos sin procedencia no permiten migración automática fiable.
Companion OK/SENT no identifica solicitudes: respuestas del mismo tipo tras
timeout requieren otra estrategia, sin retransmitir RF automáticamente.
WEB-09, la admisión RX y las correlaciones ACK siguen explícitamente abiertas.
Estos límites no se ocultan con una suite aprobada ni se cambian en el informe
histórico para presentar la auditoría completa como resuelta.
