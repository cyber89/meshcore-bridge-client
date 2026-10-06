# Correcciones Q-01 a Q-06 y PI-C01/PI-C02

Fecha: 2026-10-05. Base previa al lote: `776eed7`. Referencias MeshCore de sólo lectura; no se abrieron radio física, broker ni datos operativos. Se aplicaron las skills `clean-code-solid`, `python-patterns-typing` y `bridge-test-runner`.

Los anexos y harness de la auditoría del 2026-10-04 permanecen como evidencia histórica. Sus expectativas describen los defectos originales y no deben utilizarse como criterios de aceptación del código corregido.

## Reproducción y resultado

Se añadieron regresiones mantenidas en [test_remaining_quality_audit.py](../../../tests/test_remaining_quality_audit.py) y [test_virtual_contract_regressions.py](../../../tests/test_virtual_contract_regressions.py). La primera ejecución previa a modificar producción dio **16 fallos y 2 controles aprobados**: alcance/complejidad del helper, promesa de RAM, minuto actual, timestamps caducados/saltos y contratos virtuales. Q-06 parte además de la reproducción aislada original documentada en [quality.md](../layers-2026-10-04/quality.md), que interceptó el arranque y acreditó la ruta JSON efectiva sin iniciar servicios.

Tras aplicar las correcciones se incorporaron casos adicionales de aislamiento y cierre de la demo y equivalencia de estadísticas. Verificación conjunta final: **71 passed in 6.79s**, incluidos los escenarios de simulación existentes y el lector oficial del SDK para el subconjunto wire soportado. La revisión de tipos de los cinco archivos de implementación indicados abajo y Ruff de implementación/regresiones fueron correctos. Esto no acredita rendimiento ni interoperabilidad con radio física.

Después se migró el fixture de `test_virtual_mesh_simulation.py` al constructor de demo y cierre completo, eliminando también su argumento y limpieza `.db` obsoletos. La comprobación de los dos archivos nuevos y ese fixture dio **32 passed in 2.62s**, con Ruff correcto. No hubo otros cambios de implementación después del pase de 71 casos.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_remaining_quality_audit.py tests/test_virtual_contract_regressions.py tests/test_virtual_official_compatibility.py tests/test_virtual_mesh_simulation.py tests/test_fixture_isolation.py tests/test_packet_buffer.py tests/test_tcp_official_compatibility.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/remaining-quality-final --junitxml=tests/artifacts/remaining-quality-final.xml
.venv/Scripts/python.exe -m mypy --strict src/metrics_aggregator.py src/virtual_mesh_adapter.py src/web/map_tile_service.py scripts/evaluate_refactoring_metrics.py run_interactive_demo.py
.venv/Scripts/python.exe -m ruff check src/metrics_aggregator.py src/virtual_mesh_adapter.py src/web/map_tile_service.py scripts/evaluate_refactoring_metrics.py run_interactive_demo.py tests/test_remaining_quality_audit.py tests/test_virtual_contract_regressions.py
```

Usar otro `--basetemp` al repetir una ejecución cuyos archivos continúen abiertos en Windows. El resultado de este lote no incluye cobertura; el orquestador conserva por separado la suite completa con cobertura.

## Q-01: alcance recursivo y errores visibles — corregido

El helper anterior sólo buscaba `src/*.py`, descartaba excepciones y anunciaba limpieza universal. La implementación mantenida [evaluate_refactoring_metrics.py](../../../scripts/evaluate_refactoring_metrics.py) recorre `src/**/*.py`, imprime cada archivo analizado/excluido/error y resume los conteos. Los errores de lectura/parseo y el alcance vacío producen código de salida 1. Las advertencias de refactorización conservan salida 0: son señales, no defectos funcionales por sí mismas.

El punto de entrada de la skill ahora delega en esa implementación, conservando sus funciones públicas. Debido a que `.agents` está protegido en el entorno, el principal aplicó con permisos ampliados el reemplazo exacto inspeccionado preparado en `tests/artifacts/quality-skill.patch`. Ambos puntos de entrada se verificaron contra el mismo checkout y produjeron igual inventario: 60 archivos analizados, 0 excluidos, 0 errores y 131 señales en el momento de esa comprobación. El conteo puede variar con los demás cambios del lote; no indica que 131 funciones sean incorrectas.

Regresión: un módulo anidado con 20 decisiones aparece en el informe y un fichero de sintaxis inválida queda registrado, en lugar de producir un falso pase.

## Q-02: definición de score y ámbitos separados — corregido

Se utiliza un visitor por cuerpo de función que no entra en funciones, clases ni lambdas internas. `with` y `async with` no añaden decisiones. Convención explícita: base 1; `if`, expresión condicional, bucles y cada handler de excepción suman 1; cada operador booleano adicional, generador de comprehension y filtro suman 1. No se modelan rutas excepcionales implícitas ni el grafo completo del bytecode, por lo que se declara **score AST orientativo**, no McCabe exacto.

Se conserva el nombre de compatibilidad `calculate_cyclomatic_complexity`, con la convención documentada. Las señales existentes de 15 decisiones y 6 parámetros no se reinterpretan como requisitos universales ni se introducen nuevos umbrales. Las regresiones verifican context managers, función interna, condicionales, comprehensions y operadores booleanos.

## Q-03: promesa de memoria sin respaldo — corregido

La docstring de [MetricsAggregator](../../../src/metrics_aggregator.py) elimina el presupuesto universal `< 100 KB`. Explica retención limitada y dependencia del coste de objetos Python respecto de plataforma/carga. Mantiene 1440 minutos por defecto.

La medición histórica de 670624 bytes retenidos corresponde exclusivamente a `tracemalloc`, 1440 minutos sintéticos y un RX de 32 bytes por minuto en pytest aislado. No se presenta como RSS del servicio, medición de SBC, fuga o presupuesto universal. No se cambian límites para ajustarlos a una cifra inventada.

## Q-04: minuto actual ausente de las gráficas — corregido

Las series `1h`, `6h` y `24h` conservan respectivamente 60/72/96 puntos y pasos de 1/5/15 minutos. La ventana termina al finalizar el minuto actual, incluyendo ese minuto parcial. El último punto publica `partial: true`; `time_series.includes_current_minute: true` explica el contrato. `summary.scope: session` aclara que los acumulados no corresponden necesariamente a la ventana de la gráfica.

Los valores de los buckets se copian mientras se mantiene el lock, evitando que una modificación posterior altere el snapshot que se agrega fuera del lock. Las pruebas congelan el reloj en un límite de minuto y acreditan que el RX recién recibido aparece en los tres rangos.

## Q-05: timestamp caducado atribuido a otro minuto — corregido

`_get_or_create_bucket` puede devolver ausencia de bucket. Un evento anterior a la ventana de retención incrementa únicamente los totales de sesión, incluidos errores, sin contaminar ningún timestamp visible. Una observación fuera de orden que sí cabe en la ventana se inserta en su minuto exacto. Los saltos grandes rellenan los últimos minutos retenidos, en lugar de crear buckets cercanos al antiguo timestamp y dejar un hueco hasta el actual.

Regresiones: paquete RX caducado con error CRC y error timeout independiente conservan todos los buckets; un salto de 100 minutos con capacidad de cinco deja exactamente los últimos cinco timestamps; un TX rezagado dentro de esa ventana se cuenta en su minuto correcto.

## Q-06: aislamiento incompleto de la demo — corregido

[run_interactive_demo.py](../../../run_interactive_demo.py) inicia un subproceso desde un directorio temporal dedicado, conservado hasta que el hijo termina. El lanzador sólo importa biblioteca estándar. El hijo bloquea la carga `.env` antes del primer import de producción y recibe únicamente variables necesarias del sistema operativo y configuración explícita de simulación, sin credenciales del operador.

Antes de construir componentes se verifican las rutas efectivas de datos, registro, airtime, canales y logs. La subclase de demo construye el adaptador virtual desde el principio, de modo que el watchdog y callbacks quedan asociados al mismo adaptador. MQTT de ejecución consume publicaciones en memoria, sin conexión al broker. El arranque de demo evita preflight operativo, watchdog físico y listener TCP Companion. HTTP escucha exclusivamente en `127.0.0.1` con puerto 0 asignado por el SO; el banner muestra el puerto efectivo.

[MapTileService](../../../src/web/map_tile_service.py) usa `config.DATA_DIR` como valor por defecto, permitiendo que mapas/teselas/MBTiles queden dentro del directorio de la demo. Se elimina `db_path` del launcher y la limpieza obsoleta de `.db`, `.db-wal` y `.db-shm`. La persistencia JSON sigue el contrato actual.

El `finally` cubre también un fallo parcial de arranque y ejecuta el cierre del bridge. Las pruebas acreditan paths reales, ausencia de adaptador físico, MQTT en memoria, rechazo de ruta ajena, cierre después de un fallo del listener y un arranque/cierre real sobre loopback efímero sin tareas restantes. No se ejecutó la demo interactiva contra una instalación operativa. La demo emula el subconjunto disponible; no constituye un reemplazo completo del firmware ni un ensayo del preflight/MQTT físicos.

## PI-C01: canal virtual validado antes de resolver el alias — corregido

El destino `channel_N` se resuelve primero y se valida una única representación canónica contra la capacidad existente 0..7. Los aliases incompletos, no numéricos, negativos, Unicode no ASCII y fuera de rango devuelven ERROR sin crear eco. Los casos válidos 0 y 7 se aceptan incluso si el argumento inicial era distinto, pues el alias explícito determina el canal solicitado.

Se mantiene el límite existente de canales y MTU; no se decide ningún nuevo umbral de radio. Las tareas echo siguen registradas y canceladas por `disconnect`.

## PI-C02: reloj virtual confirmado pero no guardado — corregido

La estación conserva un epoch RTC y el instante `monotonic` del ajuste. SDK `set_time` valida uint32, `get_time` lee ese RTC y el getter/setter raw Companion usan el mismo estado. El avance es monotónico y el wire conserva la representación uint32; nunca se cambia el reloj del sistema operativo. La cadena de fecha se genera en UTC a partir del mismo valor leído.

La revisión complementaria de contradicción SDK/raw también se resuelve: SELF_INFO refleja nombre, posición, potencia TX y radio actuales del mock; BATTERY y estadísticas core/radio/packets reutilizan el mismo origen de datos que sus getters SDK. Los campos SELF_INFO conservan los layouts de Companion: coordenadas int32 LE en microgrados, frecuencia/bandwidth uint32 LE en kHz×1000 y potencia con representación de byte int8. No se altera ninguna referencia oficial ni el framing.

Regresiones: ajustar RTC a 1704067200, avanzar el monotonic 3.25 s, leer 1704067203 por SDK y raw y volver a ajustar por raw; modificar nombre/posición/TX/radio y verificar SELF_INFO/BATTERY; decodificar los tres subtipos STATS mediante `meshcore.reader.MessageReader` y comparar sus campos con el getter SDK del mismo estado.

## Impacto de malla

1. Airtime adicional: cero en radio física. Los cambios afectan contabilidad local, helpers AST y un adaptador de simulación. No se crean consultas RF nuevas.
2. Spam/feedback: no se añaden publicaciones externas; la demo usa MQTT en memoria y ecos/tareas virtuales existentes. Se mantienen las prohibiciones de chat a LOCAL y REPEATER.
3. Guardado/timers: no se modifica el scheduler real ni se seleccionan nuevos intervalos. La demo conserva la escena virtual existente, y el cierre cancela sus tareas antes de limpiar la carpeta temporal.

## Aislamiento del linter durante el cierre

La comprobación final de Ruff falló al descubrir un pyproject.toml sintético
del harness de instalación dentro de tests/artifacts, y una invocación con
configuración explícita también recorría copias históricas y fixtures Python
deliberadamente inválidas. No eran código mantenido de producción o pruebas.
Se conserva la evidencia del fallo en remaining-fixes-2026-10-05/ruff-verified.json.
La configuración de Ruff excluye ahora tests/artifacts de forma explícita,
coherente con su exclusión previa en pytest y Git. No se altera la evidencia
histórica ni se desactiva ninguna regla para src, tests mantenidos o scripts.
El runner canónico aprobó después en 0,688 s; ruff-accepted.json registra el pase.

El cierre de estos ocho IDs corresponde a los defectos reproducidos y sus contratos descritos; no afirma optimización universal de todas las clases/métodos ni cierre de otros hallazgos de la auditoría.
