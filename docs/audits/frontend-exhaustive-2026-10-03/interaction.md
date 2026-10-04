# Auditoría de interacciones y contratos del frontend — 2026-10-03

Responsable: agente especializado en interacciones, coordinado por el agente principal.
Base examinada: `942ccd80b6d8af1d9c22cb9eef91c2cd75aa5702`. Este informe describe
hallazgos en esa revisión y las correcciones del checkout; la integración y las
pruebas de navegador mantenidas se registran en el informe principal.

## Plan ejecutado

1. Leer las skills `contract-openapi-sync`, `html-css-modern-js` y
   `security-code-auditor`, las restricciones de `AGENTS.md` y el contrato de QA.
2. Seguir el recorrido Logs → SnifferModule → REST / WebSocket → DOM, cotejando
   campos con `LogsController`, `WebAPIRouter` y los registros de diagnóstico.
3. Examinar diálogos y coordinación con navegación/foco/idiomas; buscar
   discrepancias de IDs, proveedores del contexto y bindings de importación.
4. Reproducir errores con módulos reales en Node y dobles de DOM/fetch. Corregir
   sólo comportamiento concreto y eliminar bindings demostrablemente sin uso.
5. Revisar syntax/diff y entregar los cambios al principal para validación
   Chromium con estación virtual, sin conexión a radio o broker operativo.

Propiedad de cambios: `src/web/static/js/**` y `src/web/static/index.html`. Este
agente no ha modificado CSS/backend/referencias, iniciado servicios ni ejecutado
pytest. Las peticiones del script de reproducción son mocks, no peticiones HTTP.

## Fallos encontrados y soluciones implementadas

| ID | Prioridad | Reproducción / consecuencia en la base | Solución |
|---|---|---|---|
| INT-01 | P2 | `DELETE /api/system/logs` devuelve 403; la lista local se borra igualmente y la interfaz aparenta éxito. | Comprobar `res.ok`, conservar el búfer, mostrar detalle del error y desbloquear el botón en `finally`. |
| INT-02 | P2 | Activar DEBUG con POST 403 deja `isDebugMode=true` y checkbox marcado; el servidor conserva INFO. | Mantener el estado confirmado hasta respuesta válida, respetar el nivel devuelto, restaurar control/badge y mostrar error en fallo. Deshabilitar durante la petición. |
| INT-03 | P2 | Descargar .log con HTTP 403/JSON de error genera un archivo vacío y no avisa. | Comprobar HTTP y `status`; presentar el error antes de construir el Blob. |
| INT-04 | P2 | El backend genera `{source: "bridge.audit"}`; la vista lo muestra como `core` y buscar `bridge.audit` lo excluye. | Usar `module → logger → source → core` para etiqueta/tooltip e incluir `source` en búsqueda. Conservar el escape HTML. |
| INT-05 | P2 | `WARN` genera clase `badge-lvl-warn` inexistente; `warning` no entra en filtro WARNING. Fechas ISO con `T` muestran fecha completa. | Normalizar nivel para filtros y clase WARNING, presentar HH:MM:SS para fecha ISO o formato con espacio. |
| INT-06 | P1 | En un diálogo peligroso, enfocar Cancelar y pulsar Enter resuelve `true`; el listener global confirma ignorando el botón enfocado. | Permitir activación nativa de cada botón. Sólo interceptar Enter en el input del prompt. |
| INT-07 | P1 | Dos `showConfirm()` concurrentes comparten DOM/listeners; la segunda reemplaza el mensaje y un clic confirma ambas promesas. | Cola FIFO de promesas que muestra un único diálogo hasta resolver el actual; resultados independientes. |
| INT-08 | P2 | El sistema y el gestor general manejan el mismo Tab/Escape; una tecla puede afectar más de un diálogo. El foco inicial de un alert peligroso apunta al Cancelar oculto. Un timeout antiguo puede mover el foco tras cerrar. | Respetar `defaultPrevented`, detener propagación de Escape, enfocar botón visible para alert y comprobar `settled` antes del foco diferido. Revisión de código; prueba de integración a cargo del principal. |
| INT-09 | P2 | Los bindings estáticos `data-i18n="modal.confirm"` sobrescriben títulos y botones personalizados del diálogo cuando se aplica otro idioma. | Distinguir etiquetas predeterminadas mediante `titleKey`/`confirmKey`/`cancelKey`, mantener sus bindings para el cambio de idioma con el diálogo abierto y retirar sólo los bindings de textos explícitos personalizados. Mensajes y borradores del prompt se conservan. Los nuevos errores de logs tienen claves ES/EN. |
| INT-10 | P2 | `ctx.fetchNodes` se consulta en settings/map/analytics pero nunca se proporciona; el refresco después de importar/contactar o abrir mapa puede omitirse. | Añadir proxy al método existente `NodesModule.fetchNodes` desde el composition root. Consume GET `/api/nodes` del caché del bridge. |
| INT-11 | P3 | Cinco imports nombrados sólo aparecen en su declaración: `buildMeshCoreContactUri` en chat y `getHardwarePowerLimits`, `debounce`, `buildMeshCoreContactUri`, `buildMeshCoreChannelUri` en settings. | Retirar los bindings; mantener funciones de utilidades exportadas, que pueden tener otros consumidores. |
| INT-12 | P2 | Tarjeta de estado de mapas y dumps hex/JSON del inspector contienen fondos oscuros inline aun en tema claro. | Sustituir por `--bg-surface-elevated`, `--bg-canvas`, `--accent-primary`, `--text-main` y borde semántico; conservar padding, tipografía monoespaciada y scroll. Coordinación con agente visual. |
| INT-13 | P2 | Ocho claves de traducción llamadas por UI no existen en ES/EN: títulos/reinicio/sobrescritura, total y aviso de PSK. `I18n.t` retorna la clave como cadena válida y no activa fallback; la confirmación de PSK público pierde el texto explicativo. Dos claves `analytics.bridge_sub` duplicadas ocultan definiciones anteriores. Seis literales de gráficos/toasts quedan en español. | Completar las ocho claves en ambos idiomas, traducir estados pendientes y vacíos de gráficos, usar catálogo para toasts, retirar la duplicación preservando valor vigente; traducir título/label del prompt. Escapar `options.emptyText` antes de interpolarlo en el gráfico. |

No se han agregado consultas RF, reintentos o schedulers: los cambios corrigen
presentación, confirmaciones y el estado frente a respuestas HTTP. Los wrappers
sin llamadas internas (`toggleDebugMode`, `toggleLogsScroll`, `toggleSnifferPause`)
se conservan: su falta de uso léxico no demuestra que deban borrarse como basura.

## Evidencia reproducible

[`check_interactions.mjs`](check_interactions.mjs) importa el SnifferModule real y
evalúa los métodos de MeshCoreApp con un DOM mínimo; intercepta `fetch` devolviendo
403 y mensajes sintéticos. No importa Python/config ni toca almacenamiento operativo.
Registra [`interactions-before.json`](interactions-before.json) y
[`interactions-after.json`](interactions-after.json): 13 comprobaciones,
1 correcta / 12 fallidas en la base y **13 correctas / 0 fallidas** después.
Son manifestaciones observables agrupadas en hallazgos, no trece defectos diferentes.
La comprobación de escape HTML ya pasaba en la base.

```powershell
# Leer la revisión base conservada en Git sin resetear el checkout:
node docs/audits/frontend-exhaustive-2026-10-03/check_interactions.mjs --baseline
# Comprobar el código actual con salida distinta de cero si falla:
node docs/audits/frontend-exhaustive-2026-10-03/check_interactions.mjs --require-pass
.venv/Scripts/python.exe docs/audits/frontend-exhaustive-2026-10-03/inventory_interactions.py
```

El flag `--baseline` lee el SHA arriba indicado, conservado en el script, sin
modificar el checkout. `--revision=SHA` permite seleccionar explícitamente otra
base. La ejecución actual importa los módulos del árbol de trabajo.

[`interactions-inventory.json`](interactions-inventory.json) recoge 16 archivos JS
con `node --check` correcto, 488 IDs únicos en HTML, ninguna búsqueda literal
`getElementById` ausente, ningún import nombrado léxicamente sin uso tras limpieza
y ningún método `ctx` detectado sin proveedor. El inventario no resuelve accesos
computados ni prueba que todas las funciones sean necesarias.

La herramienta de `contract-openapi-sync` detecta 101 rutas backend y 66 llamadas
en ocho archivos JS; 66/66 tienen correspondencia léxica. Se ha cotejado
semánticamente, además, GET/DELETE `/api/system/logs`, POST `/api/system/logs/level`,
GET `/api/logs/download` y el evento WS `system_log` con payload directo/en `data`.
Las escrituras de nivel requieren respuesta `status: ok` con `level` del router;
la descarga retorna JSON con `raw_logs`, no directamente un stream .log.

`lint_frontend_standards.py` aprueba sus comprobaciones estructurales de metadatos,
h1, roles tabs, tokens, movimiento reducido, foco y referencias JS. Su mensaje
"100%" sólo describe esas heurísticas: no acredita accesibilidad, contratos,
seguridad o compatibilidad completos. El reporte principal separa la prueba real
en navegador de estas señales.

La revisión adicional del auditor `audit_frontend_i18n.cjs` encontró los problemas
de INT-13. Tras corregirlos, hay 1348 claves por idioma y cero candidatos de UI sin
traducir. El helper original también clasificaba `series: [{key: "rx"}, {key:
"tx"}]` de analítica como traducciones: son campos de datos. Se informó al
principal para corregir la extracción, conservando los problemas reales; no se
han inventado claves `rx`/`tx` para silenciar ese falso positivo. La evidencia de
este agente previa a corregir el helper está en
[`interactions-i18n.json`](interactions-i18n.json).
Después de integrar la corrección del helper del principal,
[`interactions-i18n-final.json`](interactions-i18n-final.json) confirma **0 findings,
0 candidatos de UI y 1191 claves referenciadas**. Esto sigue siendo una
comprobación léxica, no una prueba de todas las traducciones en ejecución.

## Límites y aceptación pendiente de integración

Node usa un DOM simulado y no acredita layout, estilos computados, orden real de
eventos/foco del navegador ni rendimiento. La verificación final debe cubrir
ambos temas, móvil/escritorio, ES/EN, logs con errores/trazas/source, filtros,
rechazos HTTP y diálogos concurrentes con Tab/Escape/Enter. Las pruebas de
administración remota deben usar respuestas sintéticas y preservar exclusión
LOCAL/REPEATER de chat/contactos y secretos fuera de logs. No se afirma ausencia
absoluta de errores o vulnerabilidades ni interoperabilidad con hardware.
