# Auditoría de JavaScript, diálogos y notificaciones — 2026-10-18

Revisión del checkout integrado de la SPA, con inspección de código, regresiones
reproducibles y Chromium sobre estaciones virtuales aisladas. Se conservan los
cambios locales previos ajenos a esta tarea. El usuario autorizó expresamente
publicar también la fragmentación de chat que ya estaba añadida localmente,
junto con sus correcciones necesarias.

## Defectos reproducidos y corregidos

| Área | Comportamiento anterior | Corrección |
|---|---|---|
| Envío fragmentado | Cambiar de conversación podía redirigir los siguientes fragmentos a otro canal o DM | Captura inmutable del destino, canal y nombre; cada fragmento se guarda en su conversación original |
| Envíos concurrentes | Un segundo submit transmitía y borraba un nuevo borrador durante un envío pendiente | Una operación de envío a la vez; el nuevo borrador se conserva |
| Rechazo de un fragmento | Seguían enviándose los fragmentos siguientes; sólo se recuperaba una parte del texto | Se detiene la operación y se recupera únicamente el texto todavía no aceptado, sin sobrescribir un borrador nuevo |
| Contador y airtime | 320 B de texto UTF-8 podían formar tres paquetes y mostrar dos | Se cuentan los fragmentos reales y se suma su airtime estimado; tooltip ES/EN distingue mensaje y paquete |
| Preferencias locales | Un `SecurityError` de Web Storage podía interrumpir el arranque o los controles | Lectura/escritura opcional protegida; las preferencias de interfaz siguen funcionando en memoria |
| Prompts | Enter o Escape durante composición IME confirmaba o cancelaba el diálogo | No consumir teclas con `isComposing` |
| Tipos de toast | `constructor`, `toString` o `__proto__` se aceptaban como tipos y podían romper i18n | Sólo se aceptan propiedades propias del mapa de tipos; el resto usa información |
| Ciclo del toast | Varios cierres durante el fade encolaban callbacks sobre una instancia ya destruida | Un único cierre por notificación; sin modificar Bootstrap |
| Botón de cierre | Área de 32×32 px también en pantalla táctil | 44×44 px con `pointer: coarse` |
| Favoritos | Estado y aviso de éxito cambiaban antes del POST; errores HTTP se ignoraban | Actualizar únicamente tras confirmación del servidor y conservar estado al fallar |
| Copiar QR/HEX/JSON | Se anunciaba éxito antes de completar el portapapeles; rechazo o API ausente podían producir errores no tratados | Esperar `writeText`, controlar fallos y facilitar selección manual |
| Canal guardado | Nombres como `A&B` aparecían como `A&amp;B` en el toast | Escape centralizado en el sumidero, con nombres literales |
| Traceroute | Una respuesta del nodo A podía aparecer tras cerrar o abrir el nodo B | Descartar respuestas fuera de la generación/objetivo vigente |
| Heatmap | Una respuesta pendiente volvía a añadir capas y rearmar el refresco después de desactivarlo | Comprobar estado deseado y generación antes de pintar o rearmar |

Se conservan los bloqueos de mensajería hacia LOCAL y REPEATER y los contratos de
ACK, almacenamiento y estados fallidos. Se retiró una variable sin uso del
contador y una afirmación de 60 FPS sin medición del comentario del worker.

## Código sin uso y contratos

- Comprobación sintáctica de 22 archivos JS y resolución del grafo ESM de la
  entrada de la aplicación: 19 módulos, sin imports/exports rotos detectados.
- Los tres archivos fuera de ese grafo no son huérfanos: `i18n.js` y `qrcode.js`
  se cargan como scripts clásicos; `packet_worker.js` se instancia con `new Worker`.
- Los IDs literales revisados en los módulos y el núcleo tienen destino en el
  HTML. Las claves ES/EN y sus parámetros conservan paridad.
- No se eliminan APIs públicas, fallbacks ni fuentes de assets por no aparecer
  en una búsqueda textual. No se acredita ausencia exhaustiva de código muerto
  mediante análisis léxico, cobertura parcial o un grafo de imports.
- Se revisaron los scripts históricos de inspección antes de ejecutarlos.
  `check_frontend_health.py` y `audit_frontend_inspection.py` no se usaron como
  fixtures: contienen inicialización antigua y puertos fijos. La evidencia usa
  las fixtures mantenidas de `tests/conftest.py`.

## Impacto sobre LoRa

1. **Airtime:** una acción de usuario produce tantos paquetes como fragmentos
   UTF-8 reales, con el límite existente de 160 B por paquete. Se conserva la
   pausa existente de 300 ms entre fragmentos y el rate limiter del backend.
   La estimación mostrada es la suma del modelo existente por paquete; no es
   una medición RF ni incorpora necesariamente retransmisiones o todos los hops.
2. **Spam y bucles:** no se añaden consultas de radio, difusión MQTT ni reintentos
   automáticos. El bloqueo de envíos concurrentes y la parada ante rechazo
   reducen operaciones duplicadas. Las guardas de origen/rol se conservan.
3. **Timers y configuración:** no se añade un scheduler de radio ni se cambia
   un cooldown. Las correcciones de heatmap sólo protegen el refresco HTTP ya
   existente de datos pasivos, conservando su intervalo. No se modifica la
   persistencia de airtime ni de los timers de seguridad del backend.

No se eligieron límites o intervalos nuevos. La fragmentación previa se incluye
por autorización del usuario y conserva los parámetros que ya tenía.

## Verificación y evidencia

Las regresiones nuevas están en `test_js_dialog_regressions.py`,
`test_js_module_regressions.py` y `test_js_preference_helpers.py`.
Se observaron fallos antes de los parches y pases después, incluyendo controles
positivos para evitar arreglos que simplemente descarten todas las respuestas o
todas las copias.

La ejecución inicial amplia pasó 74 comprobaciones, pero registró dos errores de
JavaScript al cerrar toasts en los escenarios de administración remota en móvil
horizontal. Una regresión de tres cierres consecutivos reprodujo exactamente
`Cannot read properties of null (reading 'classList')` dentro de Bootstrap;
tras la guarda de ciclo de vida pasó sin `pageerror`.

Las verificaciones, capturas, grafo de módulos y reportes JUnit se guardan en
`tests/artifacts/js-review/`.

| Verificación | Resultado |
|---|---|
| Diálogos, estilos, módulos y preferencias (`final-ui.xml`) | 56 pases |
| Auditoría funcional, i18n, cancelaciones y carreras (`final-functions.xml`) | 121 pases |
| Revalidación final de chat y preferencias (`final-chat.xml`) | 25 pases; 25 casos fuera del filtro |
| Regresiones con selectores definitivos (`portable-selectors.xml`) | 32 pases; sin fallos ni errores |
| Casos distintos entre los tres reportes | 180; cero fallos, errores o skips |
| Ruff de las tres regresiones nuevas y `conftest.py` | Sin incidencias |
| mypy `--strict` de las tres regresiones nuevas | Sin incidencias |
| Auditoría estática de traducciones del checkout integrado | 1649 claves ES y 1649 EN; sin incidencias detectadas |
| Build del checkout integrado y `--check` | 31 assets coherentes |
| Regresiones sobre el contenido exacto del índice (`publication-final.xml`) | 32 pases en 214,44 s; sin fallos, errores o skips |
| Contenido seleccionado para publicar | Grafo de 19 módulos resuelto; sintaxis de 22 archivos y hashes/descompresión de los 31 assets verificados |

Los bloques amplios verifican el checkout integrado. La última revalidación de
chat se ejecutó después de corregir la parada ante rechazo y el cómputo UTF-8.
La preparación de publicación usa selectores de comportamiento (`data-toast-type`
y `data-bs-dismiss`) para que las regresiones no dependan de la maquetación local
previa que queda fuera del commit.

La fixture mantenida `tests/conftest.py` se actualiza, con autorización expresa
del usuario, para iniciar sesión y completar el cambio inicial de credenciales
en la estación virtual antes de abrir la SPA. La autenticación de producción ya
está en `main`; esta preparación no modifica sus contratos ni datos operativos.
La verificación del contenido exacto seleccionado se ejecuta en una copia
independiente de las fuentes de producción y pruebas guardadas en el índice Git.
Las 32 regresiones pasan en esa copia; la comparación binaria confirmó que sus
fuentes, assets y archivos de pruebas coinciden con el contenido seleccionado.

## Alcance y límites

Windows con CPython 3.12.14, pytest 9.1.1, Playwright 1.62.0 y Node.js 24.19.0;
se reutilizaron las herramientas locales. Ruff pasa en los tres módulos nuevos
y `conftest.py`; mypy estricto pasa en los tres módulos nuevos. Al ampliar mypy
a `conftest.py` aparecen ocho incidencias de tipado. La comparación con el archivo
de `HEAD` reproduce las mismas ocho: asignación al método MQTT y atributos de
servidor que no declara `WebServerProtocol`. No proceden de las 20 líneas añadidas
de autenticación; quedan registradas en `mypy-conftest-baseline.txt`.
No se acredita cobertura global de Python ni se cambian dependencias de producción.

Las pruebas usan datos temporales, radio virtual, puertos de loopback del SO,
peticiones aplazadas controladas y portapapeles simulado. No transmiten mediante
hardware ni consultan un broker operativo. El sandbox de Windows requiere
permiso de ejecución ampliado para los sockets locales de `asyncio`.

La evidencia de estilos cubre temas, tamaños y estados ensayados; no certifica
WCAG completo, lectores de pantalla, cartografía externa o rendimiento físico.
El commit excluye otros cambios locales previos de autenticación, backend,
diálogos/maquetación y documentación. Sus assets se generan exclusivamente desde
los contenidos seleccionados para publicar, manteniendo sus hashes coherentes.
Se normalizaron además metadatos de fuentes y el gzip del HTML que todavía
reflejaban CRLF de Windows en lugar de los bytes LF guardados por Git.
