# Revisión de frontend, diseño e idiomas — 2026-10-03

## Estado de los errores registrados

Las correcciones iniciales de esta revisión están aplicadas en el commit `80007ce`,
publicado en `origin/main`. El seguimiento de los errores restantes se detalla
en la sección siguiente. El error de teardown descrito más abajo pertenece
a una ejecución intermedia; la ejecución final terminó sin ese error.

| Error registrado | Estado | Corrección y evidencia |
| --- | --- | --- |
| Anidación de chat, CSS duplicado y controles sin nombre accesible | Corregido | `index.html`: cierre del layout, una hoja maestra CSS y controles/etiquetas nativos. |
| Navegación y foco inconsistentes en pestañas y diálogos | Corregido | `app.js`: tabulación, flechas/Home/End, foco de modales y restauración; casos de navegador aprobados. |
| Nombres sin escapar y selección de chat para repetidores/local | Corregido | Paleta con nombres escapados y guardas de destino; clasificación de nodos por rol, sin heurísticas de nombre. |
| DEBUG que no alternaba, errores HTTP/portapapeles y pérdida de duty cycle | Corregido | Alternancia INFO/DEBUG, comprobación HTTP, manejo de portapapeles y combinación de eventos parciales en `app.js`. |
| Contraste, alias de tema y distribución móvil incoherentes | Corregido | Tokens por tema, alias resueltos, compositor y modales responsive; 48 pares de contraste y matriz de tamaños aprobados. |
| Textos sin traducir o cambio de idioma que alteraba datos visibles | Corregido | Catálogos ES/EN, interpolación y refresco desde caché; auditoría sin incidencias y casos de idioma aprobados. |
| `ERR_ABORTED` de un mosaico retirado tratado como fallo de QA | Corregido | Fixture que distingue esa cancelación, comprobación de carga de mosaicos visibles y ejecución final sin errores de teardown. |

Las limitaciones de verificación se conservan al final del informe.

## Seguimiento: correcciones adicionales solicitadas

La revisión independiente encontró mensajes de error propios de la UI que el
auditor anterior no detectaba. Su salida inicial sin candidatos no demostraba que
esas ramas estuvieran traducidas. También encontró resultados obsoletos en la
paleta y una excepción demasiado amplia en la fixture cartográfica.

| Hallazgo adicional | Corrección |
| --- | --- |
| Errores de guardar/exportar/eliminar canales, añadir contactos, radio/identidad y descargar logs permanecían en español | Mensajes e interpolaciones del catálogo ES/EN en settings y sniffer; los detalles originales del error se conservan y escapan al renderizar. |
| Selección de repetidor, fallo de ping, aceptación/actualización de contactos y fallbacks de analítica sin traducción | Catálogo para mensajes propios; añadida la clave de actualización de contactos que antes podía mostrarse literalmente. |
| Textos redundantes de chat, batería y nombres de canal predeterminados | Uso directo del catálogo e interpolación; nombres proporcionados por usuarios conservados. |
| Buscar por «repetidor» o «cliente» no encontraba los roles canónicos en español | La paleta compara el rol original y su traducción. |
| Cambiar ES/EN con una búsqueda abierta mantenía resultados ocultos del filtro previo | Se recalcula el filtro conservando consulta y foco; se restaura la opción seleccionada si continúa presente. |
| El auditor ignoraba líneas mixtas con `I18n.t`, errores sin tildes y mensajes de terminal; los candidatos no hacían fallar el comando | Inspección léxica de argumentos, templates, errores y terminales; candidatos bloqueantes y regresiones con casos positivos/negativos. |
| QA cartográfica reemplazaba cualquier imagen externa y toleraba cualquier cancelación de imagen externa | URLs exactas de Leaflet 1.9.4 y rutas de mosaicos OSM/Esri permitidas; otras dependencias fallan. Sólo cancelaciones de mosaicos esperados se toleran. |

Catálogo del seguimiento: 1.249 claves por idioma, 1.111 referencias y 132 reglas
de selectores. Auditor ampliado sin hallazgos ni candidatos; siete fallbacks
exactos del catálogo listados individualmente con su motivo. La inspección sigue
siendo léxica y no demuestra por sí sola todos los flujos de ejecución.

Regresiones: nueve operaciones fallidas en ambos idiomas conservando detalles
literales, búsqueda/refresco de la paleta, política de URLs cartográficas y 13
casos del auditor. Los fallos se inyectan en `fetch` del navegador; no se realizan
guardados ni consultas por RF. Artefactos del seguimiento en
`tests/artifacts/frontend-followup-verified.json`, `frontend-i18n-followup-final.json`
y `frontend-followup-coverage.xml`.

Resultado final del seguimiento: **77 pruebas aprobadas**, sin skips ni errores
de teardown, en 105.37 s; 57 casos de navegador y 20 de auditor/política de recursos.
Ruff y validación documental aprobados. Mypy conserva el resultado de 59 archivos
de producción: este seguimiento no modifica código Python de `src`.
Cobertura Python de esta selección: 36.68% (4.896 de 13.347 líneas de `src`),
parcial y separada de los casos de navegador/JavaScript.

Reproducción de la matriz del seguimiento:

```powershell
# UTF-8 permite conservar también mensajes de error Unicode en Windows.
$env:PYTHONUTF8 = '1'
python scripts/run_quality_checks.py --only-tests --report tests/artifacts/frontend-followup-verified.json -- tests/test_frontend_followup.py tests/test_frontend_i18n_audit.py tests/test_frontend_ui_audit.py tests/test_e2e_playwright.py tests/test_playwright_e2e_simulation.py -q --tb=short --cov-report=xml:tests/artifacts/frontend-followup-coverage.xml
node scripts/audit_frontend_i18n.cjs
```

La primera ejecución del seguimiento aprobó 26 casos y falló dos al intentar
operar el input oculto de un switch. La regresión ahora hace clic en su etiqueta
visible y comprueba el estado nativo; el comportamiento de producción no se
relajó. El JSON intermedio preserva el fallo aunque la consola Windows del runner
no pudo imprimir un carácter Unicode; la ejecución final usa UTF-8.

## Plan y responsabilidades

Solicitud: revisar errores e incongruencias del frontend, traducciones de toda la
interfaz y diseño responsive en temas claro y oscuro; aplicar mejoras justificadas.

| Responsable | Propiedad | Skills |
| --- | --- | --- |
| Agente diseño | `src/web/static/css/**` | web-ui-design-system, ui-ux-pro-max |
| Agente HTML/JS | `index.html`, `app.js`, `js/core/**` | html-css-modern-js, contract-openapi-sync |
| Agente traducciones | `i18n.js`, `js/modules/**`, auditoría i18n | html-css-modern-js |
| Principal | integración, pruebas de navegador e informe | web-browser-inspection, bridge-test-runner, python-patterns-typing |

Los agentes trabajan en archivos separados. El principal revisa los contratos y
diffs e integra la evidencia antes de publicar según AGENTS.md.

## Criterios de aceptación

- Mantener Vanilla HTML/CSS/JS y los contratos REST/WebSocket existentes.
- Corregir errores observables de estructura, interacción y escape de datos.
- Aplicar una paleta coherente de azul/pizarra con superficies claras y oscuras,
  texto legible, foco visible y controles táctiles adecuados.
- Revisar claves ES/EN, interpolaciones, textos/atributos estáticos y contenido
  dinámico; conservar nombres, mensajes, claves, logs y respuestas del dispositivo.
- Comprobar las siete vistas y seis subpestañas de ajustes en 320, 390, 768 y
  1920 px con ambos temas e idiomas. Revisar capturas desktop/mobile.
- Probar persistencia del idioma, cambio con modal abierto, conservación de
  borradores/iconos, navegación y restricciones de contactos/mensajería.

Referencia de contraste: [WCAG 2.2, contraste mínimo](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum/),
4.5:1 para texto normal y 3:1 para texto grande. Una auditoría parcial de tokens y
capturas no acredita conformidad WCAG completa.

## Aislamiento y alcance RF

Se reutilizan las fixtures mantenidas de `tests/conftest.py`: `VirtualMeshAdapter`,
MQTT simulado, persistencia temporal y HTTP loopback con puerto asignado por el SO.
No se modifica la política de radio, reintentos ni schedulers. Los cambios visuales
y de traducción no generan paquetes adicionales ni rearman timers de configuración.
Los casos de envío existentes se ejecutan exclusivamente en la radio virtual.

## Evidencia

La primera ejecución de las pruebas existentes de navegador registró 19 aprobadas.
La ejecución final integrada aprobó los 37 casos de navegador, sin skips ni errores
de teardown, en 78.84 s (`frontend-browser-verified.json`). Capturas y JSON de
geometría/contraste se guardan en `tests/artifacts/frontend-ui/`, ignorado en Git.
La fixture bloquea recursos externos; la comprobación cartográfica adicional
sirve Leaflet desde una caché verificada y usa mosaicos virtuales.

## Correcciones implementadas

- Cierre ausente de `chat-layout`, carga duplicada de hojas CSS, campos/botones
  sin nombre accesible y ayudas de consola construidas como elementos no nativos.
- Pestañas con selección ARIA y tabulación coherentes; navegación con flechas,
  Home/End, gestión/restauración de foco y Escape en diálogos.
- Escape de nombres de nodos en la paleta, acceso al mapa de nodos vigente y
  exclusión de LOCAL/REPEATER al seleccionar conversaciones. La clasificación por
  alias `R-`, `REP-` o texto `REPEATER` fue eliminada: el nombre no determina el rol.
- Paleta INFO/DEBUG consistente, tratamiento de fallos HTTP/portapapeles y
  conservación del duty cycle al recibir eventos parciales de cutoff.
- Texto principal/secundario/tenue, badges, estados seleccionados, placeholders,
  ACK, paneles de telemetría y popups con colores semánticos para cada tema.
  Alias CSS ausentes o heredados del tema oscuro ahora resuelven los colores
  del tema activo, incluidos paneles que usan estilos inline.
- Compositor móvil en dos filas; búsquedas sin altura accidental de 240 px;
  modales con viewport dinámico y contenido desplazable; lista del mapa situada
  debajo de los controles en móvil. Objetivos táctiles de 44 px según contexto.
- 573 claves nuevas para texto HTML y cobertura de títulos, metadescripción,
  placeholders, etiquetas accesibles, tooltips, modales, ayudas y estados vivos.
  El catálogo final contiene 1.236 claves en español y 1.236 en inglés.
- Refresco de idioma desde cachés de los módulos, sin consultas RF adicionales,
  conservación de formularios/contadores/nombres y parámetros de interpolación
  asociados a las etiquetas dinámicas. Estados y roles traducidos, incluidos
  singular/plural en los contadores de saltos.
  La paleta de búsqueda traduce etiquetas y roles mientras está abierta,
  sin alterar ni interpretar como HTML los nombres del usuario.

## Verificación inicial y límites

`node scripts/audit_frontend_i18n.cjs` revisa 1.097 referencias y 132 reglas de
selectores: cero duplicados, referencias ausentes, incompatibilidades entre
parámetros o candidatos directos en español detectados. Los candidatos se buscan
mediante heurísticas y no equivalen a una demostración de cobertura total.

La verificación de estructura HTML, sintaxis JS y los chequeos de presencia de
estándares son estáticos. La afirmación «100%» del linter auxiliar sólo describe
sus reglas sintácticas; no certifica accesibilidad ni funcionamiento completo.

Mypy estricto: 59 archivos de producción sin errores. Ruff: `src`, `tests` y
`scripts` sin errores. Validación documental: 55 documentos sin incidencias.

Se midieron 48 combinaciones de ocho tokens de texto/acento sobre tres superficies
en ambos temas: todas superan 4.5:1; mínimo observado 4.96:1. También se comprueba
que los cuatro alias CSS compartidos resuelven el valor del tema activo.

Las pruebas seleccionadas producen una cobertura del 37% del código Python total
(`src`): es cobertura parcial de esta tarea, no el resultado de la suite completa
del backend. Entorno: Windows, Python 3.12.14, Playwright 1.62.0 y Chromium incluido
por Playwright; se mantiene compatibilidad de código Python con 3.10.

Una ejecución intermedia terminó con 37 casos aprobados y un error de teardown:
Chromium notificó `ERR_ABORTED` cuando Leaflet retiró un mosaico obsoleto.
La fixture inicial distinguía cancelaciones de imágenes externas; el seguimiento
restringe la excepción a mosaicos de rutas esperadas. Siguen fallando las
peticiones locales, recursos externos inesperados, otros errores HTTP/red y
errores de consola/JavaScript. El caso cartográfico exige que todos los mosaicos
visibles terminen de cargar. Los resultados intermedios se conservan en artefactos.

Comandos y evidencia reproducible:

- Navegador: `python scripts/run_quality_checks.py --only-tests --report tests/artifacts/frontend-browser-verified.json -- tests/test_frontend_ui_audit.py tests/test_e2e_playwright.py tests/test_playwright_e2e_simulation.py --tb=short -q --cov-report=xml:tests/artifacts/frontend-coverage.xml`.
- Catálogo: `node scripts/audit_frontend_i18n.cjs`; salida en `tests/artifacts/frontend-i18n-final.json`.
- Mypy/Ruff/documentación: `scripts/run_quality_checks.py` con `--only-types`, `--only-lint` y `--only-docs`; JSON separados en artefactos.

La prueba cartográfica adicional usa los archivos Leaflet 1.9.4 fijados por la
app, guardados sólo en los artefactos de QA y verificados con sus hashes SRI.
Se sirve la librería localmente y se interceptan imágenes con mosaicos neutros:
se comprueban controles, marcadores y superposiciones, sin acreditar disponibilidad
de proveedores de mapas, relieve real o descargas MBTiles. Se omite en un checkout
sin esa caché y comunica el motivo.

Los nombres de usuario/nodos/canales, mensajes, JSON/hex, registros operativos,
diagnósticos de backend, respuestas de firmware, opcodes y unidades conservan
su contenido original. Los controles y etiquetas de la interfaz se traducen.
No se ejercitan todos los errores posibles de dispositivos o brokers reales,
ni se afirma conformidad WCAG completa o interoperabilidad RF física.
