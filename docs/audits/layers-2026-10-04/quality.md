# Auditoría por capas: mediciones de calidad, métricas y aislamiento de la demo

Fecha: 2026-10-04, America/New_York. Anexo documental del checkout auditado tras `c9b2d3c`. No se han modificado las fuentes ni las herramientas de skills para estos hallazgos.

## Alcance y validación

Fuentes inspeccionadas: `.agents/skills/refactoring-clean-architecture/scripts/evaluate_refactoring_metrics.py`, `src/metrics_aggregator.py`, `run_interactive_demo.py`, y las rutas de inicialización/persistencia en `src/bridge_core.py` y `src/contact_manager.py`. Evidencias: seis archivos `quality-*.json` de esta carpeta y el harness `tests/audit_layer_quality_2026_10_04.py`.

Comando para repetir los escenarios aislados desde la raíz:

```powershell
.venv/Scripts/python.exe -m pytest tests/audit_layer_quality_2026_10_04.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/audit-quality-replay-tmp
```

Resultado comunicado por el orquestador: **6 passed in 0.20s**, Ruff correcto. Los casos afirman las observaciones actuales para documentarlas; no son pruebas de una solución aplicada. El nombre del archivo excluye su ejecución por la colección mantenida por defecto. El harness escribe sus seis JSON de evidencia en la carpeta de auditoría, y cualquier dato de fixture en temporales. Los imports y la persistencia se aíslan con `tests/conftest.py`; no se leen archivos `.env` operativos.

## Q-01 — P2: herramienta de métricas omite subpaquetes y anuncia limpieza completa

- **Fuente:** `.agents/skills/refactoring-clean-architecture/scripts/evaluate_refactoring_metrics.py:69`, `:77`.
- **Requisito:** inventariar todos los módulos incluidos en el alcance real antes de concluir sobre clases y métodos de la app; el mensaje debe describir las comprobaciones y limitaciones.
- **Reproducción:** `test_metrics_helper_misses_nested_production_modules` crea un `src/safe.py` sencillo y `src/admin/unsafe.py` con 20 decisiones. Sustituye únicamente la raíz del helper y ejecuta `main()` sobre ese proyecto temporal.
- **Esperado:** el módulo anidado aparece entre los hallazgos, o el informe declara expresamente que lo excluye.
- **Observado:** `unsafe.py` no aparece y se imprime `Codigo 100% limpio y mantenible`. Analizar directamente ese archivo sí devuelve problemas. Evidencia: `quality-metrics-scope.json`.
- **Causa:** `src_dir.glob('*.py')` no recorre `src/admin`, `src/serial`, `src/web` ni `src/routers`. La conclusión absoluta excede además las métricas que calcula.
- **Impacto:** falsa confianza al usar el helper para responder si todas las clases y métodos son óptimos. No es un fallo de ejecución del bridge.
- **Solución propuesta:** recorrido recursivo con exclusiones explícitas, inventario de archivos analizados/excluidos/errores, y mensaje limitado a métricas observadas. No presentar un pase heurístico como certificado de ausencia de errores o mantenibilidad universal.

## Q-02 — P3: complejidad aproximada mezcla context managers y ámbitos internos

- **Fuente:** `.agents/skills/refactoring-clean-architecture/scripts/evaluate_refactoring_metrics.py:27`, `:29`, `:30`.
- **Requisito:** calcular una métrica por función con definición reproducible, o llamarla explícitamente heurística aproximada.
- **Reproducción:** `test_metrics_helper_counts_context_managers_and_nested_decisions` analiza una función con `with manager(): return 1`, y otra que sólo define/devuelve una función interna que contiene un `if`.
- **Esperado:** con una definición de decisiones explícitas y ámbitos separados, ambas funciones exteriores tienen valor 1; la decisión de `inner` se atribuye a `inner`.
- **Observado:** `{'with': 2, 'outer': 2}`. Evidencia: `quality-metrics-definition.json`.
- **Causa:** se cuenta `With`/`AsyncWith` como decisión y `ast.walk(node)` incluye las decisiones de funciones anidadas.
- **Impacto:** ranking y umbrales de refactorización distorsionados. No se demuestra por este resultado que el método auditado sea lento, incorrecto o necesite una división.
- **Solución propuesta:** visitor que no penetre ámbitos de otras funciones/clases al medir una función, definición documentada para operadores/excepciones/comprehensions y casos de referencia. Si se conserva el algoritmo, etiquetar la métrica como score aproximado y no como McCabe exacto. La interpretación de flujos excepcionales puede variar entre herramientas; debe declararse la convención elegida.

## Q-03 — P2: afirmación de RAM menor de 100 KB contradicha por medición aislada

- **Fuente:** `src/metrics_aggregator.py:42`, `:46`, `:49`.
- **Requisito:** respaldar cifras de memoria con plataforma, carga, duración simulada y alcance; no prometer un presupuesto universal sin medición.
- **Reproducción:** `test_metrics_retained_allocations_exceed_declared_memory_budget` inicia tracemalloc después de GC, crea `MetricsAggregator(max_minutes=1440)` y registra un RX CHAT de 32 bytes por cada uno de 1440 minutos sintéticos. Conserva los 1440 buckets durante la medida.
- **Esperado según docstring:** memoria menor de 100 KB.
- **Observado:** **670624 bytes retenidos** (aprox. 655 KiB), pico adicional **671257 bytes**. Evidencia: `quality-metrics-memory.json`.
- **Causa:** 1440 objetos de bucket, contadores y diccionarios tienen coste Python mayor que el presupuesto anunciado.
- **Impacto:** documentación y supuestos de dimensionamiento erróneos. Esta medida no constituye un consumo preocupante por sí mismo ni prueba una fuga.
- **Solución propuesta:** corregir la cifra con contexto verificable, definir objetivo de memoria real y comparar representaciones compactas sólo si el objetivo lo requiere. Mantener límites y semántica de buckets.
- **Límites:** tracemalloc mide asignaciones Python del escenario en el proceso pytest aislado; no mide RSS del servicio, memoria de todas las dependencias ni un SBC. No se esperaron 24 horas: se simularon timestamps de 1440 minutos. No extrapolar esa cifra al bridge completo.

## Q-04 — P2 de contrato/UX: las series excluyen el minuto actual sin indicar ventana cerrada

- **Fuente:** `src/metrics_aggregator.py:217`, `:229`, `:237`, `:249`.
- **Requisito:** una gráfica presentada como actividad en vivo debe incluir el intervalo en curso o declarar claramente que usa sólo minutos cerrados.
- **Reproducción:** `test_metrics_current_minute_is_absent_from_all_time_series` fija el reloj en un límite de minuto, registra un RX en ese instante y consulta `1h`, `6h`, `24h`.
- **Esperado:** representación del paquete recién recibido en la gráfica, o contrato explícito de exclusión del minuto en curso.
- **Observado:** contador de sesión RX=1, suma de serie RX=0 en los tres rangos. Evidencia: `quality-metrics-current-minute.json`.
- **Causa:** el intervalo final termina en `current_minute`; la iteración de buckets usa extremo superior exclusivo.
- **Impacto:** usuario puede interpretar que el paquete no fue recibido o que la gráfica discrepa del contador. Los agregados por ventana y los totales de sesión tampoco representan necesariamente el mismo período.
- **Solución propuesta:** decidir y documentar semántica de ventana: incluir el minuto parcial con etiqueta adecuada, o conservar sólo minutos cerrados y mostrar corte/retardo de actualización. Añadir pruebas en límites de minuto y explicar qué período usa cada contador.
- **Matiz:** excluir el minuto abierto puede ser deliberado y matemáticamente válido. La reproducción confirma la exclusión; el problema es la ausencia de un contrato visible coherente con la interpretación en vivo, no un conteo incorrecto de los minutos cerrados.

## Q-05 — P2: paquete caducado reasignado a un bucket con otro timestamp

- **Fuente:** `src/metrics_aggregator.py:115`, `:119`, `:120`, `:146`, `:151`.
- **Requisito:** conservar atribución temporal; un paquete fuera del historial retenido no debe convertirse en actividad de otro minuto.
- **Reproducción:** `test_metrics_expired_packet_is_attributed_to_oldest_retained_minute` conserva cinco buckets desde t=1700000040, registra un paquete con t=1699994040, cien minutos anterior al primero, y observa el bucket más antiguo disponible.
- **Esperado:** no añadirlo a un timestamp distinto. Los totales globales pueden contabilizarlo según el contrato, pero la serie temporal no debe falsificar su fecha.
- **Observado:** el paquete de **1699994040** se asigna a **1700000040** y ese bucket pasa de RX=1 a RX=2. Evidencia: `quality-metrics-expired-packet.json`.
- **Causa:** cuando no existe bucket histórico coincidente, `_get_or_create_bucket` devuelve `self._buckets[0]`.
- **Impacto:** actividad y errores antiguos se trasladan al historial visible, contaminando gráficas y ratios de ese minuto.
- **Solución propuesta:** separar actualización de totales de sesión de atribución de ventana, permitir ausencia de bucket para fechas caducadas y manejar eventos fuera de orden dentro de la ventana retenida. No confundir este defecto con Q-04.
- **Precisión:** se atribuye al bucket **más antiguo retenido**, no necesariamente al minuto actual. La prueba no demuestra ingestión de timestamps remotos en toda ruta de producción, pero sí el defecto del contrato público del agregador cuando recibe un timestamp caducado.

## Q-06 — P1: el argumento de base de datos de la demo no aísla la persistencia JSON

- **Fuentes:** `run_interactive_demo.py:60`, `:63`, `:73`, `:93`, `:94`; `src/bridge_core.py:74`, `:77`, `:95`, `:115`, `:639`; `src/contact_manager.py:1788`.
- **Requisito:** la simulación debe separar datos, logs y servicios de la estación operativa; pasar un nombre de fichero aislado debe tener efecto verificable o rechazarse.
- **Reproducción:** `test_demo_database_argument_does_not_isolate_json_paths` intercepta la creación del bridge y sustituye `start()` por un mock que aborta antes de arrancar servicios. A continuación añade un nodo sintético y ejecuta únicamente la persistencia real del registro en las rutas temporales del fixture.
- **Esperado:** rutas efectivas propias de la demo, distintas de la configuración de una estación operativa.
- **Observado:** el supuesto aislamiento `db_path='meshcore_sim_buffer.db'` no se aplica; el registro se escribe en `config.NODE_REGISTRY_STORAGE_PATH`. El JSON temporal contiene el nodo sintético. Evidencia: `quality-demo-storage.json`.
- **Causa:** `MeshCoreBridge.__init__` acepta `**_kwargs` e ignora `db_path`; constructor y cierre usan las rutas JSON de configuración. La limpieza de la demo sólo busca el antiguo `.db`, `.db-wal` y `.db-shm`, que no son las rutas JSON actuales.
- **Impacto potencial si se ejecutara con configuración normal:** nodos simulados y otros estados podrían mezclarse con datos de la estación. Sustituir el adaptador después de construir el bridge no aísla sus archivos ni contratos ya inicializados.
- **Solución propuesta:** configuración de dependencias explícita para simulación, carpeta temporal dedicada configurada **antes** de construir componentes, paths separados para registro/airtime/canales/logs/mapa, MQTT en memoria y loopback propio. Rechazar kwargs obsoletos o migrar sus callers; eliminar limpieza del fichero legado sólo después de actualizar el contrato de la demo.
- **Límite de la reproducción:** **no arrancó servicios, broker ni radio y no escribió archivos operativos**. La ruta efectiva se demostró con la configuración redirigida del fixture. La contaminación de una instalación real se registra como consecuencia posible del código, no como daño ejecutado en esta auditoría.

## Plan de aceptación

1. Aislar la demo antes de permitir usarla como herramienta de QA; probar paths efectivos y ausencia de servicios externos.
2. Corregir atribución de paquetes caducados; revisar ventanas abiertas/cerradas con una decisión de producto explícita.
3. Sustituir afirmaciones absolutas de calidad y RAM por resultados con inventario y alcance.
4. Corregir el helper de métricas y contrastar scores antes de priorizar refactorizaciones de clases y métodos.

No ejecutar la demo completa en una estación operativa para confirmar Q-06. Las reproducciones aisladas bastan para localizar las rutas y permiten preparar regresiones sin arriesgar datos del usuario.
