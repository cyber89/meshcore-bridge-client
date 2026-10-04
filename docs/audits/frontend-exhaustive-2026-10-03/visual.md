# Auditoría visual especializada — 2026-10-03

## Alcance y plan

Inspección de `tokens.css` y `admin.css`, contrastada con los consumidores HTML y JavaScript de la SPA. Skills utilizadas: `web-ui-design-system` y `html-css-modern-js`. La propiedad de cambios queda limitada a esas dos hojas y este anexo; el dirigente integra los hallazgos de HTML, JS y demás hojas, y coordina Chromium sobre una estación virtual aislada.

1. Conservar evidencia de la vista de logs antes de editar.
2. Corregir la mezcla de colores del tema claro y los contratos CSS/DOM de logs y traceroute.
3. Revisar datos largos y metadatos en móvil, colores semánticos y focos de consola.
4. Retirar únicamente CSS sin consumidores comprobados, conservando las clases de salida de terminal activas.
5. Integrar verificación renderizada y regresiones con el dirigente; registrar límites reales.

## Hallazgos de partida

Las líneas siguientes corresponden a la versión de entrada `942ccd8`; cambian al retirar reglas.

| ID | Evidencia de partida | Problema y solución |
|---|---|---|
| VIS-01 | `tokens.css:215–221`, `admin.css:1909`, `1956`, `2001` | El tema claro fuerza `.system-logs-box` a `#0B192C`, pero los mensajes y fechas usan los tokens oscuros del tema claro. El mensaje `#273a41` sobre ese fondo alcanza sólo **1,49:1** y el tiempo `#4b6069` **2,67:1**, calculados con luminancia relativa sRGB. Retirar la excepción oscura y conservar lienzo/textos semánticos. |
| VIS-02 | `sniffer.js:751–753`, `admin.css:1995–2020` | El renderizador emite `.log-mod` y `.log-trace`; el CSS declara `.log-source` y `.log-traceback`, sin consumidores. Alinear clases, envolver el logger y colocar la excepción en una fila completa. |
| VIS-03 | `admin.css:1924–1932`, `1869–1892` | Fila flex sin estructura para la excepción; metadatos y filtro tienen mínimos que no garantizan lectura de logs reales largos en móvil. Adaptar columnas y mínimos, envolver cadenas largas y filtros. La geometría requiere comprobación renderizada. |
| VIS-04 | `map.js:490/508/516`, `admin.css:3350–3374` | JS añade estados `running/success/error`; CSS espera `trace-measuring/trace-success/trace-error`. Alinear los tres estados con su DOM real y sus tokens. |
| VIS-05 | `admin.css:3376`, `2461–2476`, `2527–2544` | Fondo de traceroute y dumps hex/JSON conservan colores oscuros fijos. El grafo mezcla ese fondo con textos definidos por el tema claro. Utilizar tokens de superficie y acento en diagnósticos. |
| VIS-06 | `admin.css:3594–3623/3655–3665`, `3853–3865/4154` | Consola oscura usa texto de sistema `#64748b` y placeholder `#475569`; estados claros usan colores fijos en lugar de los tokens ya medidos. Uniformar metadatos, placeholders y estados con tokens del tema. |
| VIS-07 | `tokens.css:215–216`; `admin.css:807–881`, `3390–3460`, `4065–4076` | Selectores antiguos de terminal y grafo sin consumidores en `src`/`tests` fuera del CSS; además algunas reglas `.term-*` duplican reglas vigentes posteriores. Retirar sólo esos bloques verificados; conservar estilos vigentes de consola y nodos de traceroute. |
| VIS-08 | `admin.css:1024`, `1787`; capturas de partida del dirigente | El encabezado de subpestañas se comprime por `flex-shrink` frente a un subpanel grande y los botones generales carecen del estilo que sólo existía dentro del repetidor. Los botones llegan a verse como una franja recortada. Se protege la barra contra contracción y se aplican botones del tema con wrap, 44 px y foco visible. |

Se derivan al dirigente otras tres superficies oscuras inline de `index.html`: `#localMapsStatusCard` (1333) y dumps del inspector (2335/2343). La selección manual de cartografía oscura/radar y los colores decorativos de marcadores no constituyen por sí mismos errores del tema claro; se conservan.

## Correcciones implementadas

- Se elimina la excepción oscura de logs. El feed usa `--bg-canvas` y `--text-main`; fechas, logger y niveles usan sus tokens semánticos. Las filas RF/IP/seguridad tienen fondos semánticos coherentes en ambos temas.
- Las filas son grid con cuatro columnas en escritorio y metadatos más mensaje completo en móvil. `.log-trace` ocupa todas las columnas; logger, mensaje y excepción envuelven cadenas largas. Se conserva el contenido escapado por el renderizador.
- El feed tiene altura `clamp(350px, 55dvh, 720px)` para mantener scroll interno con muchos registros. El contenedor exterior también puede desplazarse para alcanzar filtros y feed en pantallas bajas. Se mantienen filtros y campos dentro de su ancho disponible.
- Las subpestañas generales ya usan superficies, textos y estados del tema, permiten varias filas y tienen foco visible. Tanto barra como subpanel evitan la contracción que ocultaba controles.
- Traceroute usa `running/success/error`, fondo de lienzo, nodos que no se aplastan y alineación inicial que permite acceder al inicio de una ruta ancha. Se retira el modelo de grafo antiguo que no usa el renderizador vigente.
- Vista previa hex clara, dumps de paquetes y texto de consola/placeholder pasan a tokens. WARN y CRITICAL mantienen las mismas familias de estilos que WARNING y ERROR, respectivamente.

La limpieza retira **159 líneas** de tres bloques obsoletos o duplicados: 72 de la terminal antigua, 74 del modelo antiguo de nodos/enlaces de traceroute y 13 del selector `.trace-visual-graph` sin consumidor. Se conserva el modelo real `.linux-term-*` / `.trace-node-item` y la única definición vigente de las clases compartidas `.term-*`.

Puntos del código resultante: `admin.css:1024` (subpestañas), `1754` (vista logs), `1887` (feed), `1904` (grid), `1977` (logger), `1991` (excepción), `3352` (traceroute). En `tokens.css` se elimina la regla defectuosa; la vista previa hex queda en la línea 222.

Comprobación estática tras los cambios y el ajuste móvil adicional: `git diff --check` sin errores; 598 llaves de apertura/cierre en `admin.css`; no quedan `.log-source`, `.log-traceback`, terminal legacy ni grafo legacy. El equilibrio de llaves es una señal parcial, no un parser ni prueba de layout.

### Contrastes de colores declarados, tema claro

| Contenido | Color / fondo | Ratio |
|---|---|---|
| Mensaje | `#273a41` / `#dce3e4` | 9,14:1 |
| Tiempo | `#4b6069` / `#dce3e4` | 5,08:1 |
| Logger | `#1d4ed8` / `#dce3e4` | 5,15:1 |
| INFO | `#035f91` / `#d5e5e9` | 5,32:1 |
| DEBUG | `#7130ce` / `#e4ddec` | 5,26:1 |
| WARNING/WARN | `#92400e` / `#ece1c8` | 5,46:1 |
| ERROR/CRITICAL y excepción | `#b91c1c` / `#eedbd9` | 4,86:1 |

Estos ratios emplean los colores declarados para cada pareja. La regresión del dirigente mide los estilos computados del DOM, incluido el cambio de temas y geometría.

## Evidencia y límites

`rg` busca consumidores en `src` y `tests`, excluyendo CSS para detectar referencias activas. Las conclusiones de ausencia se limitan al checkout; no equivalen a análisis general de todas las clases generadas posibles. La aritmética de contraste de partida demuestra la mezcla concreta de logs, sin certificar WCAG completo.

No se conectan dispositivos, no se inicia una estación operativa ni se transmiten paquetes. Las comprobaciones y capturas de navegador son responsabilidad del dirigente para evitar duplicar procesos y resultados.

El dirigente reproduce VIS-01 en ambas resoluciones, 390 y 1920, con estilos computados: mensajes **1,486:1**, fecha **2,670:1**, fondo `rgb(11, 25, 44)`. Los PNG y JSON de partida se guardan en `tests/artifacts/frontend-exhaustive/baseline/`. La reproducción no es una certificación de todos los estados de la vista.

## Segunda revisión visual

La captura corregida `tests/artifacts/frontend-exhaustive/final/logs-light-390.png` permite detectar una incoherencia adicional: el contador de paquetes `10` se parte en `1`/`0` y la subpestaña de monitor queda reducida a cinco líneas estrechas. Se corrige el selector real `#snifferPacketsBadge` con `flex-shrink: 0`, ancho intrínseco y `white-space: nowrap`; por debajo de 640 px las dos subpestañas de `#tab-logs` ocupan filas completas, con iconos sin contracción y texto alineado al inicio. Esta regla está limitada a logs y no modifica las tres columnas de pestañas de administración remota.

El dirigente vuelve a comprobar las vistas/logs después de esta corrección. La captura que motivó este ajuste es una revisión intermedia y no evidencia del ajuste final.
