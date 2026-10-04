# Calidad y coherencia CSS: componentes, chat y nodos

Auditoría del 2026-10-03 sobre `942ccd80b6d8af1d9c22cb9eef91c2cd75aa5702`. Responsable: agente CSS Quality. Skills: `html-css-modern-js`, `web-ui-design-system` y `clean-code-solid`. Propiedad de cambios: `src/web/static/css/components.css`, `chat.css` y `nodes.css`.

## Plan ejecutado

1. Leer las reglas del proyecto, el orden real de importación de `app.css` y los selectores producidos por HTML/JS.
2. Contrastar los estados normal, hover, foco, disabled y móvil, en ambos temas; identificar contradicciones de cascada y contrastes calculables.
3. Corregir los defectos reproducibles y consolidar estilos compartidos. Conservar selectores dinámicos y evitar borrados basados sólo en búsquedas literales.
4. Revisar el diff y entregar al agente dirigente los escenarios que necesitan comprobación renderizada en estación virtual.

## Defectos y soluciones aplicadas

| ID | Problema reproducible | Causa | Solución |
|---|---|---|---|
| CSS-01 | En tema claro, pasar el cursor sobre una tarjeta de switch oscurece su fondo y deja el texto oscuro ilegible. Afecta tanto `.toggle-field-group` como `.toggle-field-inline`. | Los hover fijaban `rgba(30,41,59,.85/.9)` independientemente del tema. | Ambos fondos usan `--bg-surface-hover`. El título de la tarjeta calculado pasa de 1.570:1 a 10.491:1. |
| CSS-02 | Los datos de un nodo/contacto offline tienen menos contraste que la misma tarjeta online. | `.node-card-offline,.contact-card-offline {opacity:.82}` seguía activa más abajo, pese al comentario previo que decía preservar legibilidad. El nodo sólo recuperaba opacity1 con hover. | Se elimina la opacidad global y el hover compensatorio; la disponibilidad se comunica por badge y borde punteado en ambas tarjetas. Texto muted calculado: 4.041:1 → 5.917:1. |
| CSS-03 | Un diálogo de acción destructiva tiene texto blanco de bajo contraste en el extremo claro del botón. | Degradado `#ef4444→#b91c1c` fijo y separado de la paleta semántica. | Usa `--danger-fill→--danger-fill-hover`, con `--on-danger`; hover usa danger-fill-hover. Extremo menos favorable: 3.763:1 → 6.470:1. |
| CSS-04 | El control de switch mantiene pista gris oscura y perilla blanca en el tema claro, ajenas a sus capas y con poca distinción de la perilla cuando se homogeniza el fondo. | Colores hex fijos en la pista y perilla. | La pista y borde usan bg-surface-hover/border-control; perilla usa text-bright en reposo y text-inverse cuando está marcada. Se conservan variantes azul, violeta y éxito. |
| CSS-05 | El área clicable de switches es de 48×26px o 36×20px en pantallas táctiles. | La etiqueta mide igual que la pista visual; la regla global táctil sólo cubría botones. | Bajo pointer:coarse la etiqueta mide al menos44×44; la pista permanece centrada y conserva sus dimensiones visuales26/20px. |
| CSS-06 | Un título largo del diálogo de sistema puede imponer un mínimo intrínseco dentro de la cabecera flexible. | El h3 no permitía reducir su ancho ni partir cadenas largas. | `min-width:0` y `overflow-wrap:anywhere`; los controles de cierre conservan tamaño. Validar títulos largos en320px y paisaje. |
| CSS-07 | Los botones compartidos dependen de importar el módulo de chat y el botón peligro tiene definiciones base contradictorias. | Buttons generales en chat.css; btn-danger sólido en components.css sobreescrito por el transparente de chat.css, por orden de importación. | Los botones generales se trasladan a components.css y se elimina la base peligro redundante. Se conserva la apariencia efectiva y la transformación hover. Las variantes de diálogo mantienen mayor especificidad. |
| CSS-08 | Código CSS redundante aumenta el coste de mantenimiento sin añadir comportamiento. | Siete overrides de texto del tema claro repetían la regla normal o aliases que ya resuelven dentro del tema. La toolbar de contactos tenía una base repetida completamente sobreescrita. | Se retiran esos siete bloques; se conservan las diferencias reales de fondo, borde y sombra. Se retiran dos declaraciones repetidas del fondo de mensajes y la toolbar inicial redundante. El indicador de tarjeta local usa accent-primary en vez de azul fijo. |

| CSS-09 | En844×390 la cabecera fuerza scrollWidth1057 y expulsa el botón de tema fuera de pantalla. | Las métricas ocupan446px sin reducirse y el modo compacto sólo se activaba hasta768px; el centro de búsqueda tenía mínimo intrínseco. | Se extiende la cabecera compacta hasta1200px: métricas duplicadas ocultas, logo/estado truncables y botones tema/idioma conservados. La paleta de comandos permanece accesible mediante icono44px en móvil y tablet hasta1200px. El centro/hint permiten reducir ancho y truncar en desktop. |

## Evidencia y alcance

[css-quality-static.json](css-quality-static.json) contiene el baseline, tokens leídos, seis cálculos sRGB y conteos antes/después. Se calcularon los contrastes con la fórmula de luminancia relativa y composición alfa; para offline se asumió tarjeta sobre canvas y para hover superficie elevada. Son escenarios concretos de análisis estático, no una certificación WCAG completa ni una medida de antialiasing del navegador.

- Diff revisado; `git diff --check` sin errores (Git sólo advierte normalización LF→CRLF).
- Llaves equilibradas en los tres módulos: components380/380, chat132/132, nodes139/139. El equilibrio es una señal léxica parcial, no valida toda la gramática CSS.
- Cambio neto final tras CSS-09:11 líneas menos entre los tres módulos, incluyendo las nuevas correcciones;141 líneas de estilos comunes se trasladan entre módulos.
- No se borraron selectores por la ausencia de coincidencias literales. Se mantienen estilos de tramas, ACK, ping, airtime, navegación y nodos dinámicos.
- No se modifican comandos RF, APIs, límites, timers, dependencias ni datos de una estación operativa.

## Comprobación renderizada para integración

El agente dirigente centraliza navegador/suites. Debe comprobar ambos temas con ancho320/390/768/1920, el hover de switchgroup e inline, tarjeta offline, botones destructivos normal/hover, perillas normal/marcada, switches táctiles compactos y títulos largos de diálogo. Comparar también los botones de la cabecera, directorios y formularios tras mover la base compartida. Esta sección enumera escenarios, no afirma ejecuciones que el agente CSS no realizó.

## Reproducción renderizada de CSS-09

El dirigente detectó el fallo en Chromium real en ambos temas con844×390 mientras recorría los seis paneles de administración remota. La tarjeta remota cabía; `document.documentElement.scrollWidth` era1057 y `.header-right` llegaba a1057.1875px. Capturas y geometría baseline: `tests/artifacts/frontend-exhaustive/final/remote-overflow-light-844.json/png` (tambiéndark). La corrección aborda la cabecera, sin ocultar controles de tema o idioma ni aplicar overflow:hidden para encubrir el problema. El dirigente añadirá844,900,1024 al reflow y verificará los controles visibles; resultados finales centralizados en su informe. Los conteos del JSON anterior describen el primer lote CSS, anterior aCSS-09.

La paleta de comandos también permanece visible como botón de44px en teléfonos: se elimina el display:none anterior hasta768px. Esta affordance hace accesible la búsqueda sin depender de Ctrl+K en un dispositivo táctil. La última matriz debe confirmar320/390px en ambos idiomas, además de769/844/900/1024/1201px, con métricas y status largos y el fallback Courier empleado por las pruebas mantenidas.
