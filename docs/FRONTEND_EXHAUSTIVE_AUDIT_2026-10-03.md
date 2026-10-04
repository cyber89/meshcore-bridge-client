# Auditoría y corrección exhaustiva del frontend — 2026-10-03

## Plan de trabajo

Base inicial: `942ccd8`. Petición: corregir logs en tema claro y comprobar el frontend, incoherencias y código obsoleto, con agentes y solución. La petición de comprobación exhaustiva autoriza suites dirigidas y navegador durante esta tarea. Todo se ejecuta sobre adaptador virtual, datos temporales, MQTT simulado y loopback propio, sin hardware ni estación operativa.

1. **Inventario y reproducción**: revisar las 7 vistas, subpestañas, diálogos, CSS/DOM, JS, contratos REST/WS, idiomas y recursos; capturar una línea de base del defecto de logs.
2. **Corrección visual**: alinear logs y diagnósticos con tokens de tema, clases realmente renderizadas, contraste y responsive; depurar estilos obsoletos sólo después de comprobar consumidores estáticos/dinámicos.
3. **Corrección de interacción**: validar respuestas HTTP y estados visibles, preservar datos ante errores, revisar foco/teclado/concurrencia de diálogos y sanitización.
4. **Integración y regresiones**: ejecutar suite frontend mantenida y regresiones por defectos observables; matriz ES/EN, claro/oscuro, móvil/tablet/escritorio, errores de red y exclusiones de roles. Revisar visualmente capturas específicas de esta versión.
5. **Cierre**: documentar fallos iniciales y resultados finales separados, cobertura parcial Python, ruff/mypy y límites; revisar diff, commit y publicación de archivos propios según AGENTS.md.

## Responsables y propiedad

| Agente | Área | Skills |
|---|---|---|
| Dirigente/integrador | Plan, QA en navegador, regresiones, contratos, documentación, integración y publicación | `bridge-test-runner`, `web-browser-inspection`, `contract-openapi-sync`, `domain-adr-keeper` |
| Visual | `admin.css`, `tokens.css`: logs, terminales, traceroute y temas | `web-ui-design-system`, `html-css-modern-js` |
| Interacción | JS e HTML: respuestas, estado, logs y diálogos | `contract-openapi-sync`, `html-css-modern-js`, `security-code-auditor` |
| Calidad CSS | `components.css`, `chat.css`, `nodes.css`: cascada, duplicados, botones y responsive | `clean-code-solid`, `web-ui-design-system`, `html-css-modern-js` |

## Evidencia inicial

El override claro `.system-logs-box` conserva el fondo oscuro `#0B192C`, mientras el texto de mensajes/tiempos usa tokens oscuros del tema claro. Además, el renderer usa `.log-mod`/`.log-trace`, pero la hoja de estilos define `.log-source`/`.log-traceback`. Chromium reproduce el defecto en 390 y 1920 px: mensaje **1,486:1**, fecha **2,670:1**. Ambas regresiones fallan en la base antes de editar.

[Captura anterior, escritorio claro](audits/frontend-exhaustive-2026-10-03/screenshots/logs-before-light-desktop.png).

## Resultados finales

Se completan las cinco fases. La suite dirigida final pasa **108 casos, cero fallos/errores/skips**; cuatro casos adicionales de logs también pasan con fondos de red, radio y tráfico sospechoso. Esos cuatro repiten casos de la matriz con datos ampliados: no son 112 casos únicos. Hay **83 casos de navegador, 24 de auditoría estática/política de URL y uno de contrato HTTP/cache**. No se afirma que todo el proyecto carezca de errores: mypy/ruff globales detectan problemas Python fuera de los archivos de producción modificados.

### Correcciones consolidadas

| Área | Problema reproducido | Solución y evidencia |
|---|---|---|
| Logs claros | Fondo oscuro con textos oscuros; clases del renderer sin estilos correspondientes. | Tokens del tema; `.log-mod`/`.log-trace` reales; grid, excepción a ancho completo, cadenas largas y filtros adaptables. Contraste computado mínimo final **4,859:1 claro / 6,149:1 oscuro**, incluidos badges y fondos especiales. |
| Acciones de logs | Borrar con 403 perdía el búfer; DEBUG con 403 quedaba activado; descargar con 403 generaba archivo vacío. | Validar HTTP/estado, conservar datos y estado confirmado, avisar del detalle escapado, recuperar botones en `finally`, evitar Blob en fallo. Node y Chromium reproducen los rechazos sintéticos. |
| Filtros y origen | `source` se ignoraba; `warn`/`warning` no coincidían con filtro; fechas ISO ocupaban demasiado. | Fallback module/logger/source, búsqueda por source, normalización del nivel y hora compacta. |
| Diálogos | Enter sobre Cancelar confirmaba; llamadas concurrentes compartían listeners/resultados; foco inicial podía ir a botón oculto. | Activación nativa de botones, Enter del input de prompt, cola FIFO, resultados independientes, foco visible/restaurado y guarda del foco diferido. Tab/Escape/Enter comprobados. |
| Idiomas de diálogos | Un cambio de idioma sobrescribía etiquetas personalizadas; retirar todos los bindings dejaba defaults sin traducir. | Bindings sólo para títulos/botones predeterminados; textos explícitos y borradores se conservan. Comprobación del diálogo abierto en ambos modos. |
| Administración remota y cabecera | En 844×390 el modal cabía, pero la cabecera global ensanchaba el documento hasta 1057 px; tema/idioma salían del viewport. | Cabecera compacta hasta 1200 px, estado/logo truncables, métricas duplicadas en analítica ocultas en compacto; controles tema/idioma y búsqueda por icono accesibles. Se prueban ocho anchos y ambos idiomas/temas. |
| Subpestañas | Barra contraída/recortada; badge de paquetes `10` partido en dos líneas en móvil. | Evitar contracción, botones de tema/foco y wrap; logs usa filas completas en móvil y badge intrínseco sin wrap. Las seis pestañas remotas mantienen su distribución propia. |
| Estados visuales | Hover de switches claro oscurecía el fondo; opacidad offline reducía contraste; botón destructivo con extremo insuficiente. | Superficies semánticas, offline con borde/badge y opacidad 1, tokens de peligro. Contrastes declarados antes/después en anexo CSS; hover/opacidad/borde renderizados en ambos temas. |
| Diagnósticos | Traceroute esperaba clases distintas a las emitidas; dumps/map-status/consola tenían superficies oscuras inline/fijas. | Estados running/success/error y tokens en superficies, metadatos y placeholders. Se conservan colores funcionales de cartografía y marcadores. |
| Contexto y traducciones | `ctx.fetchNodes` sin proveedor; ocho claves faltantes, dos claves duplicadas y seis literales de UI sin localizar. | Proxy a GET del registro cacheado; claves ES/EN y literales localizados, duplicados retirados preservando valor efectivo. Escape del texto vacío de gráficos. |

Detalle con fuentes/reproducciones: [visual](audits/frontend-exhaustive-2026-10-03/visual.md), [interacciones](audits/frontend-exhaustive-2026-10-03/interaction.md), [calidad CSS](audits/frontend-exhaustive-2026-10-03/css-quality.md).

### Limpieza y contratos

Se retiran **159 líneas** de bloques CSS de terminal/traceroute antiguos o duplicados, cinco imports nombrados sin uso y siete overrides redundantes del tema claro. Los estilos de botones compartidos se trasladan de chat a componentes; no se duplica el bloque. El balance final de las tres hojas asignadas al agente CSS es 11 líneas menos, aunque incluye los nuevos ajustes de cabecera. Los wrappers/exportaciones sin llamadas literales se conservan cuando esa ausencia no demuestra obsolescencia.

El contrato REST/WS de producción no cambia. La inspección léxica encuentra 101 rutas backend y 66 llamadas JS, con 66 coincidencias; además se cotejan semánticamente GET/DELETE logs, POST nivel, GET descarga y WS `system_log`. El proxy `fetchNodes` lee `/api/nodes` del registro, sin consultas RF. Las pruebas mantienen LOCAL y REPEATER excluidos de contactos/DM. Los cambios no añaden paquetes, temporizadores, reintentos ni intervalos de radio; no hay valores RF nuevos elegidos por el equipo.

El helper i18n confundía `series: [{key:'rx'}]` con una traducción. Se restringe la extracción de `options.key` a la API real `showQrModal` y se añaden cuatro regresiones que distinguen campos de datos de claves QR. No se añaden traducciones ficticias para silenciarlo. Resultado actual: **1348 claves por idioma, 1191 referenciadas, cero claves/duplicados/interpolaciones discrepantes y cero candidatos léxicos de UI sin traducir**. Los accesos dinámicos se listan para revisión; esto no prueba todas las cadenas posibles.

Inventario JS/DOM: **16 archivos con sintaxis válida, 488 IDs únicos**, cero `getElementById` literales ausentes, imports nombrados léxicamente sin uso o métodos de contexto detectados sin proveedor. [Inventario](audits/frontend-exhaustive-2026-10-03/interactions-inventory.json). No resuelve todos los selectores construidos dinámicamente.

### Matriz y resultados conservados

| Comprobación | Resultado | Alcance |
|---|---|---|
| Reproducción inicial logs | 2 fallos reales | Tema claro, 390/1920; ratios computados y capturas antes de corregir. |
| Primera suite ampliada | 74 pasan / 16 fallan, 90 total | Expectativas de texto anteriores a esta tarea; se actualizan a literales independientes de los catálogos, sin relajar escape/error. |
| Segunda suite ampliada | 100 pasan / 2 fallan, 102 total | Desbordamiento real de cabecera en paisaje, claro y oscuro. |
| Reproducción dirigida paisaje | 2 fallos | Rectángulos identifican cabecera global; modal ya dentro del viewport. |
| Suite dirigida final | **108 pasan**, 207,98 s pytest | Siete módulos mantenidos; cero fallos, errores o skips. |
| Ampliación de datos logs | **4 pasan**, 5,72 s pytest | Cinco niveles, trazas, HTML literal y fondos sospechoso/red/RF, ambos temas y anchos. |
| Node con DOM/fetch simulado | Base 1/13; final **13/13** | Errores HTTP, source/niveles y resultados de diálogos; no acredita layout. |
| Ruff de archivos Python propios | **Aprueba** | Cinco archivos QA y dos helpers del anexo. |
| Ruff global `src tests scripts` | **Falla: 9 incidencias** | Tres módulos Python sin modificar en esta tarea. |
| Mypy `--strict src` | **Falla: 8 errores en 2 archivos** | 60 archivos revisados; ambos executors sin modificar aquí. |
| Cobertura Python dirigida | **36,73%**, 5247/14286 líneas | Mide `src` parcialmente; no es cobertura JS ni suite backend completa. |

La vista general recorre las siete pestañas en **320×740, 390×844, 768×1024, 844×390 y 1920×1080**, claro/oscuro y ES/EN. La administración remota desbloqueada recorre sus **seis paneles × dos idiomas × dos temas × tres resoluciones** (320, 844 paisaje y 1920). Sus respuestas de autenticación/telemetría son sintéticas mediante `window.fetch`; botones Guardar se comprueban con `click(trial=True)` para verificar acceso, sin envío ni certificación de escrituras de parámetros remotos. El scroll de capturas de RF está situado en las acciones inferiores por esa comprobación.

Se comprueban errores de red y detalle escapado, cambio de idioma preservando formularios/paquetes, teclado y paleta, ACK/eco virtual y aislamiento de canales/DM, roles protegidos, modal de paquetes, logs y configuración, mapa Leaflet 1.9.4 cacheado con integridad y tiles virtuales neutros, recursos y cache HTTP. No se omite el mapa; no se prueba terreno real ni disponibilidad del CDN. Fuentes externas se sustituyen por fallback local.

La fixture de navegador ahora cierra sus WebSockets reales con código 1000 antes de cerrar Chromium, evitando el reset TCP Win10054 observado en la reproducción inicial. Un primer intento de reproducción también tuvo dos errores de setup por directorio temporal padre ausente; el reintento creó el padre y produjo los dos fallos de contraste reales. Esas incidencias de harness no se contabilizan como defectos de frontend. Las dos suites ampliadas posteriores y la final terminan sin ese error de teardown.

### Evidencia visual y reproducción

[Resumen verificable](audits/frontend-exhaustive-2026-10-03/verification-summary.json) conserva resultados, comandos, diagnósticos globales, ratios computados y SHA256 de todas las hojas/JS/HTML normalizados a LF. [Recolector](audits/frontend-exhaustive-2026-10-03/collect_evidence.py) vuelve a archivar resultados locales ya existentes sin importar configuración de la app. Los reportes crudos/JUnit/cobertura y capturas completas quedan en `tests/artifacts/frontend-exhaustive/` y `tests/artifacts/frontend-ui/`; no se añaden datos operativos ni temporales al repositorio.

Capturas revisadas del código final: [logs claro escritorio](audits/frontend-exhaustive-2026-10-03/screenshots/logs-final-light-desktop.png), [logs móvil](audits/frontend-exhaustive-2026-10-03/screenshots/logs-final-light-mobile.png), [remoto móvil](audits/frontend-exhaustive-2026-10-03/screenshots/remote-final-light-mobile.png), [remoto horizontal](audits/frontend-exhaustive-2026-10-03/screenshots/remote-final-light-landscape.png), [diálogo horizontal](audits/frontend-exhaustive-2026-10-03/screenshots/dialog-final-light-landscape.png), [ajustes claros](audits/frontend-exhaustive-2026-10-03/screenshots/settings-final-light-desktop.png), [nodos oscuros](audits/frontend-exhaustive-2026-10-03/screenshots/nodes-final-dark-mobile.png). Logs móvil conserva auto-scroll, por lo que la captura queda al final de una excepción larga.

Entorno: Windows, Python **3.12.14**, Node **24.19.0**, pytest **9.1.1**, Playwright **1.62.0**, pytest-asyncio **1.4.0**, ruff **0.16.3**, mypy **2.3.1**. No se instalan dependencias de producción nuevas. La ejecución usa Chromium instalado para Playwright; no valida otros motores ni ejecuta Python 3.10 en esta máquina.

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:FRONTEND_AUDIT_PHASE='final'
# Usar un basetemp nuevo dentro de tests/artifacts, nunca datos de la instalación.
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-tests --timeout 600 --report tests/artifacts/frontend-exhaustive/recheck.json -- tests/test_frontend_ui_audit.py tests/test_frontend_followup.py tests/test_frontend_i18n_audit.py tests/test_e2e_playwright.py tests/test_playwright_e2e_simulation.py tests/test_frontend_exhaustive_audit.py tests/test_http_cache_contract.py -q --tb=short -p no:cacheprovider --basetemp=tests/artifacts/frontend-exhaustive/final/tmp-recheck --junitxml=tests/artifacts/frontend-exhaustive/final/junit-recheck.xml --cov-report=xml:tests/artifacts/frontend-exhaustive/final/coverage-recheck.xml
node docs/audits/frontend-exhaustive-2026-10-03/check_interactions.mjs --require-pass
node scripts/audit_frontend_i18n.cjs
.venv/Scripts/python.exe docs/audits/frontend-exhaustive-2026-10-03/inventory_interactions.py
.venv/Scripts/python.exe scripts/validate_project_docs.py
git diff --check
```

El comando amplio anterior recoge ahora los fondos especiales de logs añadidos después de la colección de los 108 casos. La ejecución final de cuatro casos demuestra ese último cambio de datos; no cambió producción tras la suite completa.

### Pendientes fuera del frontend y pasos siguientes

1. **Tipos backend**: `repeater_executor.py` tiene cuatro retornos Any y dos argumentos `str | None` donde se requiere str; `local_config_executor.py` convierte dos `Any | None` a int. Posible solución: validar presencia/tipo de campos y devolver diccionarios tipados antes de construir comandos; añadir regresiones de campos ausentes. Se conservan diagnósticos exactos en el resumen, sin modificar rutas RF fuera del alcance.
2. **Lint backend**: imports no usados en `contact_manager.py`, import/order y cinco comprensiones sustituibles por `dict.fromkeys` en `metrics_aggregator.py`, variable no usada en `contacts_controller.py`. Posible solución: retirar bindings/variable y simplificar inicializadores con revisión separada del comportamiento.
3. **Validación ampliada opcional**: Firefox/WebKit, lector de pantalla, teclado con distintos IME, medición de rendimiento y contraste de estados adicionales. Requiere una tarea específica; esta matriz no acredita accesibilidad o seguridad completas.
4. **Nodo físico**: lectura/escritura de todos los parámetros locales/remotos sigue siendo un alcance distinto. El [informe de configuración](NODE_CONFIGURATION_VERIFICATION_2026-10-03.md) conserva su base histórica y pendientes; esta corrección visual no certifica interoperabilidad ni roundtrips de hardware.
5. **Entrega y seguimiento**: revisar el diff de los archivos propios, conservar anexos/fixtures, publicar en `origin/main` sin incorporar scratch ajeno. Tras actualizar el checkout desplegado mediante el procedimiento vigente, comprobar visualmente los logs claros y los modales en el navegador del usuario; no se inicia ni actualiza una estación operativa durante esta auditoría.
