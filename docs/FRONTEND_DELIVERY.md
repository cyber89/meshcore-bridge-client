# Entrega del frontend y compresión HTTP

Implementación: 2026-10-10. La SPA conserva HTML, Bootstrap, CSS y módulos ES
nativos. Los contratos REST/WebSocket, roles de nodos y operaciones RF no cambian.

## Construcción reproducible

Node.js >=18 y esbuild 0.28.1 son herramientas de construcción, no dependencias
del servicio Python. Desde la raíz:

```sh
npm --prefix tools/frontend ci
npm --prefix tools/frontend run build
npm --prefix tools/frontend run check
```

`scripts/build_frontend.cjs` transforma cada JS/CSS propio por separado, conserva
imports relativos y globals de scripts clásicos, y escribe variantes `.min.js` /
`.min.css`. Los originales siguen siendo las fuentes editables. El build crea
gzip nivel 9 para HTML, CSS y JS; verifica su descompresión contra los bytes que
se sirven y publica `src/web/static/asset-manifest.json` al final. `--check`
reconstruye en memoria y compara los artefactos sin escribir archivos.

Los artefactos están incluidos en Git y en los package-data de `src.web`; un SBC
no necesita Node ni compilar al instalar o arrancar. Las reglas LF de
`.gitattributes` conservan los hashes entre Windows y Linux. Después de modificar
fuentes hay que ejecutar build antes de publicar; check detecta recibos obsoletos.
No se usan regex para minimizar código JS/CSS.

El tema Zephyr servido es una copia derivada sin su import de Google Fonts:
`bootstrap-zephyr.local.min.css`. El vendor original y sus licencias/hashes
permanecen conservados. El HTML y CSS propios usan fuentes del sistema.

## Retoque visual del 2026-10-10

Los tokens reales se mantienen en `css/app.css`: superficies de ambos temas,
radios de controles/tarjetas/diálogos, bordes interactivos y sombras compartidas.
Los botones diferencian acciones principales, secundarias y destructivas; los
iconos usan Bootstrap Icons local y `brand.svg` es un vector propio sin librerías
adicionales. Las etiquetas de confirmación/cancelación viven en spans traducibles
para conservar sus iconos al abrir diálogos o cambiar el idioma. Los prompts
incluyen etiqueta visible. Se mantienen foco, Escape, cola de diálogos y foco
inicial en Cancelar para confirmaciones destructivas.

Los diálogos pequeños tienen icono de estado, encabezado sin separador y acciones
al pie; los formularios mantienen divisiones y cuerpo desplazable. En móvil las
acciones se apilan y los controles táctiles conservan sus áreas mínimas.

Contraste estático calculado con luminancia sRGB: blanco sobre azul `#2457d6`
6,16:1; blanco sobre rojo `#b4233b` 6,47:1; texto secundario de diálogo oscuro
`#afbdd1` sobre `#142238` 8,38:1; claro `#526176` sobre blanco 6,31:1. Bordes de
controles oscuros `#657893` sobre `#1b2c44` 3,13:1 y claros `#75849a` sobre
`#e2e8f0` 3,08:1. Estas combinaciones no acreditan accesibilidad de toda la SPA.
Build/check, sintaxis JS y el linter heurístico HTML/CSS/JS se verificaron; no se
ejecutaron suites ni inspección de navegador durante este retoque.

## Selección y caché

### First modernization delivery — 2026-10-11

The first implementation block of [the modernization plan](FRONTEND_MODERNIZATION_PLAN.md)
adds a local `js/core/dialog_controller.js` module to the existing asset build.
Public module URLs remain unchanged; the manifest also serves this module through
its minimized/precompressed representation. Removed application/repeater focus
and Escape handlers are replaced by one dialog lifecycle owner.

Chat and analytics expose loading/error/authorization states and reject stale
responses; recoverable refresh failures retain available data. Storage blocks
offline history access after credential changes or denied access until online
history validation succeeds. Form grids and terminal styles now have shared
contracts, and traceroute headers match their generated cells. This delivery
adds no backend routes, radio traffic, retries or radio timers.

Source/build checks do not establish browser behavior. At this first delivery,
keyboard selectors and field-linked validation remained pending; the second
delivery implements them. Broader component/layout migration and runtime
acceptance remain tracked in the plan.

### Second modernization delivery — 2026-10-11

The build includes two additional local modules: `js/core/tabs.js` and
`js/core/form_feedback.js`, with minimized/gzip variants selected by the same
manifest. Native selection controls cover channel/DM lists, sharing pickers and
map nodes. Secondary actions remain separate buttons; updates retain focus by
stable item identity. Local/admin/logs/inspector tabs share manual keyboard
activation: arrow/Home/End navigation does not execute their action callbacks.

Channel/contact creation keeps rejected input, links persistent errors to fields
and hints, focuses the first invalid field and blocks duplicate submission.
Validation mirrors existing controller/SDK constraints, including the 31-byte
UTF-8 name limit; HTTP field errors and general/network failures have distinct
feedback. Failures arriving after a dialog closes also produce a notification.
Shared styles define selection cards, focus-compatible native controls and
theme-specific field errors. README feature descriptions remain in English.

Build/check verifies 25 assets: 2,000,647 source bytes, 1,717,210 served bytes and
336,357 gzip bytes. JavaScript syntax, source references, static ARIA targets,
existing DOM-ID preservation and the heuristic linter were checked. No browser,
suite, service or radio operation was run; this is not runtime accessibility or
performance evidence. See the plan for remaining Phase 2–3 work and acceptance.

### Compact card delivery — 2026-10-11

Node/contact directories, statistics/telemetry and all seven local settings
panels now use shared density and alignment rules. Base desktop buttons are
32px high and small variants 30px, while coarse-pointer targets remain at least
44px. With the usual 16px root, names/body use 14px, metadata 12.5px and KPI
values 22px. Root sizing respects browser preferences; phone inputs use 16px.
Card padding/gaps are 14px/12px, avatars 36px. Bounded grids, full-name wrapping,
independent badge/tool rows and protected field widths support narrow layouts.

Directory markup retains event/data selectors and live GPS/battery updates;
favorites expose state and icon-only actions have contextual names. Local
icons replace presentation glyphs. Statistics headings, label/value rows and
sparklines have explicit alignment; settings headings/actions wrap and technical
tables retain local scrolling. Removed 136 inline presentation attributes from
HTML; all functional attributes and text remain unchanged. The English README
and the modernization plan describe this delivery and remaining acceptance.

Build/check verifies 25 assets: 2,011,354 source bytes, 1,726,281 served bytes and
337,659 gzip bytes. Static verification includes 37 JS syntax checks, 560
preserved unique IDs, ARIA/import/icon references, HTML attribute comparison,
declared color-pair calculations and the heuristic linter. No runtime browser
or suites were executed, and no performance or complete accessibility result
is claimed. Existing APIs and manual radio operations retain their behavior.

### Smaller node-card structure — 2026-10-11

Node cards now group name/role, battery/activity and main actions/QR. Distance
and last advertisement share the overview row; RX/TX paths, hop provenance and
hash width remain available in the native route disclosure. Live updates,
directory refreshes and language changes preserve disclosure state and focused
route controls. Explicit LQI targeting prevents updates to unrelated values.

Node-only padding/gaps/avatars are 12px/8px/32px; bounded columns begin at
16rem (normally 256px). Name and metadata sizes stay at 14px/12.5px with the
usual root, and touch targets retain 44px. Contact presentation is unchanged.
Actual card heights depend on content and open details; no browser reduction
percentage is claimed.

Build/check verifies 25 assets: 2,016,026 source bytes, 1,729,566 served bytes and
338,404 gzip bytes. Static syntax, six retained metric fields, unchanged API
references, imports/icons and the heuristic linter were verified. No suites,
browser, service or radio operation was run.

### Chat presentation delivery — 2026-10-11

Chat text uses 14px and relative timestamps 12px at the usual root size.
Absolute timestamps remain available through `time` metadata/title. Centered
Today/Hoy and natural date labels have lines extending across the feed in both
themes. The ready empty conversation contains only the centered input hint and
removes it on message arrival; loading/auth/error/offline notices stay explicit.
`Clear` still clears local conversation cache, while server history is preserved.
The conversation subtitle and its unused translations were removed; public
channel 0 uses the globe icon in both the header and refreshed sidebar.

Emoji/sharing popovers have headings, labelled categories, sharing descriptions,
visible focus and touch controls. Expanded state, contextual Escape, focus
return and mutually exclusive opening share one implementation. A geometry
helper bounds them to the actual conversation and visible viewport, including
keyboard occlusion, without timers. A duplicated location listener was removed;
the existing manually initiated sharing flow runs once per selection.

Build/check verifies 25 assets: 2,025,086 source bytes, 1,737,470 served bytes and
339,951 gzip bytes. Syntax, ID changes, ARIA/import/icon references, translation
parity, API references, the heuristic linter and declared color pairs were
checked. Dividers calculate to 4.00:1 dark and 3.50:1 light; timestamp text pairs
exceed 5.12:1. Browser/menu/date-boundary acceptance and full accessibility remain
pending; no suites, service or radio operation were run.

### Asset selection and cache implementation

`AssetsAdapter` mantiene las URLs originales. Selecciona la variante minimizada
cuando coinciden los SHA256 de fuente y destino registrados en el manifest;
selecciona gzip solo si también coincide su digest y el navegador lo acepta.
No comprime archivos durante las peticiones. La lectura y los hashes se ejecutan
fuera de asyncio y se cachean por ruta, tamaño y mtime; cambiar el manifest lo
invalida. Los límites de ruta y symlinks siguen confinados al directorio estático.

Sin manifest válido o tras editar una fuente, sirve el original sin gzip. Si solo
el gzip es inválido, sirve el minificado sin compresión. Cada representación
tiene su ETag y `Vary: Accept-Encoding`; se conserva el cache-control existente
(HTML no-store; otros estáticos 300 segundos). La negociación respeta `gzip;q=0`
incluso cuando existe un wildcard. HEAD conserva la supresión de cuerpo del
perímetro de seguridad.

## Presupuesto de CPU de compresión dinámica

`BridgeCompressionMiddleware` está dentro del perímetro de seguridad. Solo
comprime respuestas JSON GET 200, no transmitidas como stream, de 1 KiB a 1 MiB
en estas rutas de métricas:

- `/api/analytics` y `/api/metrics/analytics`
- `/api/lqi`
- `/api/rf/heatmap` y `/api/rf/noise`
- `/api/airtime/stats`

No comprime configuración, claves, exportaciones, canales, mensajes, logs, docs,
WebSockets, teselas, errores, HEAD, respuestas parciales, datos ya codificados,
respuestas con cookies/ETag ni las que solicitan `Cache-Control: no-transform`.

El único trabajo admitido usa zlib nivel 1 fuera del event loop. Mide el tiempo
de CPU del hilo (`thread_time`) y el tiempo real (`monotonic`), trabaja en bloques
de 32 KiB y descansa en el worker hasta que el consumo acumulado de compresión
ocupa como máximo el 50% de un núcleo en el trabajo. Las peticiones concurrentes
se sirven sin comprimir; no forman una cola de compresión. Cancelar una petición
no libera el puesto mientras el worker sigue activo.

Este presupuesto regula el consumo medio del worker; un bloque puede producir
un pico breve antes del descanso. No equivale a una cuota instantánea del sistema
operativo ni limita el proceso bridge. El usuario acotó expresamente el 50% al
trabajo de compresión. La implementación no acredita consumo de CPU real ni
rendimiento en un SBC sin mediciones de carga autorizadas.

## Alcance de comprobación

La construcción y su comprobación verifican sintaxis parseable, artefactos,
hashes y gzip. La revisión estática revisa referencias y contratos; no acredita
layout de navegador, accesibilidad completa, interoperabilidad HTTP o rendimiento.
En esta entrega, 22 assets del catálogo local suman 1.940.079 bytes de fuentes,
1.674.827 bytes servidos minimizados y 324.289 bytes gzip (83,3% menos que las
fuentes). El catálogo incluye ambos temas y el CSS base; estas cifras no son una
medición de descarga inicial ni incluyen Leaflet, fuentes de iconos o teselas.
Se comprobaron sintaxis de 31 JS (fuentes y variantes), Ruff y mypy estricto sobre
los tres módulos Python modificados (`--follow-imports=silent`). La máquina de
QA disponible tiene Python 3.12; no se ejecutó el servicio ni se acredita aquí
runtime CPython 3.14.8. La dependencia de build se reutilizó de la caché local
esbuild 0.28.1; el lockfile conserva versión e integridades de paquetes npm.
pytest/Playwright y mediciones de carga requieren petición explícita según
[AGENTS.md](../AGENTS.md). No se inicia una estación ni se transmite por radio
para construir estos archivos.

## Login visual — 2026-10-12

La pantalla de acceso utiliza los tokens vigentes de `app.css`, un SVG decorativo local y un formulario con controles de 48 px. En móvil muestra una columna y mantiene scroll propio; el tema guardado se aplica antes del login mediante `core/theme.js`, compartido con la estación. El control de visibilidad de contraseña conserva 44 px, nombres accesibles y vuelve a ocultar la entrada después de un intento.

Se revisaron fuentes, IDs, traducciones y pares de contraste, y se regeneraron 31 activos: 1.963.214 bytes servidos y 400.692 bytes gzip. Build/check y sintaxis JS correctos. Las cifras son tamaños de build; no acreditan layout, rendimiento ni accesibilidad completos en navegador. La [revisión y propuesta de recuperación](LOGIN_DESIGN_AND_RECOVERY.md) distingue cambios de interfaz implementados de un CLI de recuperación todavía propuesto.
