# Evaluación y opciones de diseño del frontend

Fecha: 2026-10-19. Base revisada: `33b5fab` en `main`.

Estado: **evaluación y propuesta; ninguna de las mejoras propuestas se implementa en esta entrega**. Se inspeccionaron código, estilos, manifiesto y documentación; no se arrancó una estación, no se ejecutaron suites ni navegador y no se midió rendimiento de ejecución.

## 1. Dictamen del equipo y alcance

La SPA puede mostrar más contenido en celular y aprovechar mejor el escritorio. La intervención recomendada combina **espaciado sin duplicaciones, configuración organizada por tareas y densidad adaptable**. El texto actual ya es relativamente pequeño: reducirlo globalmente ofrece menos margen que reorganizar los componentes.

En entrega de recursos, ya existen módulos ES, minificación y gzip previo. Primero conviene corregir la correspondencia entre URLs y manifiesto; después separar el arranque de autenticación y cargar vistas costosas cuando se necesiten. CSS crítico, precargas y Brotli son opciones condicionadas a evidencia; no son requisitos universales ni ganancias demostradas aquí.

El team leader integró tres revisiones paralelas con propiedad exclusiva de los documentos finales. Los especialistas trabajaron en modo lectura:

| Responsabilidad | Revisión realizada | Entregable integrado |
| --- | --- | --- |
| Team leader / integración | Contraste directo con fuentes, dependencias, documentación oficial y prioridades | Este documento, trazabilidad y secuencia de implementación |
| Especialista de diseño visual y UX | Jerarquía, temas, tipografía, tarjetas, ayudas y configuración | Tres direcciones visuales y riesgos de legibilidad |
| Especialista de maquetación responsive | Ancho, altura, puntero, densidad, cabecera, formularios y diálogos | Matriz por pantalla y criterios de aceptación |
| Especialista de entrega y rendimiento | Grafo JS, build, fuentes, CSS, compresión y caché | Inventario estático y opciones de carga/compilación |

La aplicación conserva Vanilla JS/CSS y Bootstrap local. No se propone introducir React, Vue, Tailwind, fuentes remotas ni dependencias nuevas de producción. Esta evaluación complementa el [plan de modernización](docs/FRONTEND_MODERNIZATION_PLAN.md) y la [entrega del frontend](docs/FRONTEND_DELIVERY.md); sus registros históricos no sustituyen el código actual.

## 2. Evidencia local y límites

Las líneas son referencias del checkout indicado; pueden desplazarse en futuras ediciones. «Confirmado» significa observado en fuentes o archivos. Un riesgo de layout o una consecuencia de red inferida del código requiere aceptación posterior en navegador/HTTP.

| ID | Evidencia | Resultado relevante |
| --- | --- | --- |
| E01 | [app.css](src/web/static/css/app.css), líneas 166–237, 398–432 | Tokens: controles comunes 36 px y pequeños 32 px; cuerpo `0.875rem`, etiquetas `0.8125rem`, metadatos `0.78125rem`; padding de tarjeta `1rem`, gap `0.75rem`. Son valores declarados, no dimensiones calculadas de cada control. |
| E02 | [app.css](src/web/static/css/app.css), 3696–3795 y 3850–3940 | Ajustes, tarjetas, pila con máximo `56rem`, grillas de dos/tres columnas y campos. |
| E03 | [app.css](src/web/static/css/app.css), 4480–4490, 5345–5623 | Algunos márgenes ya se anulan en grillas; cabecera móvil de varias filas; campos móviles 16 px; mínimos táctiles 44 px mediante `pointer: coarse`. |
| E04 | [index.html](src/web/static/index.html), 1602–1706 y 1747–2007 | Seguridad y servicios usan pilas verticales; existen formularios extensos de MQTT y conexión. `settings-content-layout` y `settings-cards-col` no tienen reglas propias encontradas en `app.css`. |
| E05 | [app.css](src/web/static/css/app.css), 240–342, 638–653, 2494–2503 | Temas, foco y movimiento reducido; nodos ya usan padding 12 px y gap 8 px específicos. |
| E06 | [index.html](src/web/static/index.html), 12–21 y 3099–3102; [session_startup.js](src/web/static/js/session_startup.js) | Sesión con script `async`; Leaflet/Bootstrap/QR/i18n con `defer`; aplicación con `type="module"`; cuatro hojas CSS iniciales. |
| E07 | [app.js](src/web/static/js/app.js), 6–22, 70–120 y 1069–1072 | Importación estática de todos los módulos de vistas; construcción de aplicación tras autenticación; inicialización conjunta de módulos y WebSocket. |
| E08 | [map.js](src/web/static/js/modules/map.js), 30–44 y 190–249; [analytics.js](src/web/static/js/modules/analytics.js), 29–49 | Inicialización de mapa y consulta inicial de analítica; proveedores de teselas locales y externos. |
| E09 | [build_frontend.cjs](scripts/build_frontend.cjs), 65–127; [package.json](tools/frontend/package.json) | `esbuild.transform` por archivo, esbuild 0.28.1, gzip nivel 9 y manifiesto versión 1; sin bundling del grafo. |
| E10 | [asgi_assets.py](src/web/asgi_assets.py), 181, 238–261 y 294–327 | Selección por clave fuente del manifiesto, hashes y gzip verificados; ETag, `Vary`, HTML sin almacenamiento y otros estáticos con 300 s. |
| E11 | [asgi_compression.py](src/web/asgi_compression.py), 19–31, 70–128 y 130–203 | Gzip dinámico solo en métricas autorizadas; trabajo fuera del event loop con presupuesto existente. |
| E12 | [theme.js](src/web/static/js/core/theme.js), 1–24; [auth.js](src/web/static/js/core/auth.js), inicio | Preferencia local de tema; cambio a Zephyr derivado local. El arranque de autenticación aún depende del grafo de `app.js`. |
| E13 | [Bootstrap Icons](src/web/static/css/bootstrap-icons.min.css), línea 5; [manifiesto](src/web/static/asset-manifest.json) | Iconos locales WOFF2/WOFF y `font-display:block`; las fuentes no forman parte de las entradas del manifiesto. |

Con raíz habitual de 16 px, los roles tipográficos de E01 equivalen a 14/13/12,5 px. La raíz y el zoom deben seguir respetando las preferencias del navegador. Los registros históricos mencionan botones 32/30 px y tarjetas 14 px; el checkout actual declara 36/32 px y 16 px generales, con excepciones por componente. No se toma una cifra histórica como medida vigente.

La skill de diseño cita `tokens.css`, que no existe en este checkout. Los tokens actuales están en `app.css`; el plan previo ya registra esta discrepancia. Este documento no crea una segunda fuente de tokens.

### Inventario de bytes, sin medición de navegación

Se leyeron las 32 entradas del manifiesto y sus archivos: hashes SHA-256 de fuentes, destinos y gzip coinciden; cada gzip se descomprime a los bytes del destino. Esto acredita consistencia del catálogo, no qué representación recibió un navegador.

| Recurso o conjunto | Fuente, bytes | Destino, bytes | Gzip disponible, bytes |
| --- | ---: | ---: | ---: |
| Catálogo completo, 32 entradas | 2.389.678 | 2.064.798 | 422.343 |
| HTML principal | 244.012 | 244.012 | 43.821 |
| CSS propio `app.css` | 162.730 | 130.631 | 23.097 |
| Entrada `app.js` | 46.044 | 27.592 | 8.071 |
| Diccionarios y código `i18n.js` | 232.435 | 191.399 | 57.484 |
| Leaflet JS | 147.552 | 154.798 | 43.846 |
| Leaflet CSS | 14.145 | 11.036 | 2.677 |
| Zephyr, derivado sin import remoto | 236.596 | 236.506 | 31.634 |

El WOFF2 de iconos mide **134.012 bytes**; el fallback WOFF, **180.288 bytes**. Son alternativas, no una descarga simultánea asumida. El catálogo incluye recursos que no necesariamente se piden al inicio, ambos temas y módulos; sus totales **no son el peso inicial, una medición de transferencia ni un ahorro de tiempo**. Tampoco gzip disponible equivale a gzip seleccionado: véase la incidencia de URLs en la sección 11.

El grafo estático inspeccionado de `app.js` alcanza 19 módulos ES y suma 436.729 bytes de destinos, con 113.700 bytes gzip disponibles en el manifiesto. Son tamaños de archivos del grafo, sin incluir scripts clásicos, CSS, HTML o cabeceras HTTP; tampoco acreditan tiempos de parseo o descarga.

## 3. Opciones de estilo visual

| Opción | Diseño y comportamiento | Ventaja | Coste o limitación |
| --- | --- | --- | --- |
| A. Evolución compacta | Mantener identidad azul, claro/oscuro y tarjetas; unificar espaciado, jerarquía y acciones; añadir densidad Normal/Compacta | Entrega gradual y continuidad con la estación actual | Hay que migrar cada familia; un cambio de escala global no resuelve la organización |
| B. Consola técnica | Superficies más planas, filas, separadores, números alineados y tablas en pantallas amplias | Alta densidad para diagnósticos y operadores frecuentes | Exige resúmenes adaptados al móvil y preservar lectura y foco |
| C. Configuración por tareas | Resumen, campos habituales y detalles «Avanzado» dentro de grupos comprensibles | Reduce longitud aparente y carga de lectura | Cambia navegación/textos; requiere mapear las siete secciones actuales y las seis del administrador remoto |

**Recomendación integrada:** A como base; incorporar de C la divulgación progresiva de ayuda y parámetros avanzados. Aplicar B selectivamente a analítica, sniffer y tablas técnicas.

Conservar colores de estado con texto/icono, foco visible, estados ocupado/deshabilitado y contraste de ambos temas. Simplificar sombras y niveles de fondo anidados en configuración; usar el acento principal para selección y acciones destacadas. No añadir transparencia, blur o animaciones costosas como requisito estético. No se declara cumplimiento WCAG integral con esta inspección.

## 4. Densidad y adaptación por pantalla

### Reglas de decisión

1. Ajustar por **espacio disponible del componente**, altura útil y capacidad de interacción. El ancho de pantalla no identifica por sí solo un dispositivo ni su puntero.
2. Reducir primero contenedores anidados, márgenes duplicados, decoración y ayudas siempre expandidas; después evaluar tamaños de glifos y controles de escritorio.
3. Conservar campos móviles a 16 px y mínimos táctiles actuales de 44 px. Un icono visual más pequeño puede vivir dentro de un botón tocable de 44 px sin solaparse con otros.
4. Mantener crecimiento por traducción, zoom, nombres/claves largos y mensajes de error. Evitar alturas fijas de tarjeta y truncado como única forma de acceder a un valor.
5. No usar `transform: scale`, `zoom` global, raíz menor ni bloqueo del zoom para hacer caber contenido.

WCAG 2.2 AA establece 24 × 24 CSS px o condiciones de separación/excepciones para objetivos; 44 px es aquí una decisión conservadora del producto, no el mínimo universal AA. La adaptación debe permitir reflujo a 320 CSS px, con desplazamiento local cuando una tabla o mapa requiere dos dimensiones. Referencias: [tamaño de objetivos](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) y [reflujo](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).

### Matriz propuesta, pendiente de aceptación visual

Los rangos son candidatos por ancho CSS disponible; se ajustarán donde el contenido real deje de caber. No son detección de modelos de teléfono.

| Contexto | Estructura propuesta | Densidad y comportamiento |
| --- | --- | --- |
| 320–479 px, teléfono estrecho | Una columna; dos solo para campos cortos que mantengan etiqueta y valor completos | Padding 8–12 px; gap entre grupos 8 px; cabecera breve; acciones secundarias en menú |
| 480–767 px, teléfono ancho o horizontal | Una o dos columnas intrínsecas; no forzar parejas de campos largos | Priorizar altura útil y teclado; detalles extensos desplegables |
| 768–1023 px, tableta o ventana mediana | Dos columnas donde quepan; navegación lateral contraíble | Separación 12 px; objetivos de 44 px cuando el puntero sea grueso |
| 1024–1439 px, escritorio | Dos o tres columnas de campos; tarjetas relacionadas en dos columnas | Controles Compacta de 32 px comunes y 30 px pequeños como candidatos; Normal conserva 36/32 px |
| Desde 1440 px, pantalla amplia | Dos o tres zonas de trabajo; formularios largos con ancho de lectura controlado | Distribuir secciones independientes; no estirar todos los inputs ni alargar párrafos |
| Cualquier ancho, altura corta o teclado abierto | Cuerpo desplazable; acciones y campo enfocado accesibles | Reducir decoración/cabecera; usar altura disponible y evitar barras superpuestas |
| Pantalla táctil amplia o dispositivo híbrido | Distribución por ancho y objetivos por capacidad de interacción | Compacta no puede anular los mínimos táctiles; evaluar también entrada mixta |

| Rol | Actual habitual | Candidato de diseño |
| --- | --- | --- |
| Texto principal | 14 px | Conservar 14 px; permitir Normal más cómodo donde haya lectura extensa |
| Etiqueta de campo | 13 px | Conservar; simplificar texto antes de reducir |
| Texto auxiliar | 12,5 px | Conservar o ampliar si es difícil de leer; evitar nuevas letras de 10–11 px |
| Entrada en teléfono | 16 px | Conservar |
| Título de sección | Aproximadamente 16 px, según componente | 16–18 px; jerarquía por peso y separación |
| Padding de tarjeta genérica | 16 px | 12 px en Compacta; 8–12 px en móvil según contenido |
| Gap de tarjeta | 12 px | 8 px en Compacta |
| Separación entre grupos de campo | Puede sumar gap 12 px y margen 12 px | Una sola separación de 8–12 px en formularios migrados |

La preferencia Normal/Compacta podría guardarse en LocalStorage siguiendo el patrón del tema, con fallback si el almacenamiento falla. Se aplicaría antes de mostrar la interfaz para evitar saltos. No existe hoy ese selector; su implementación debe decidir si la preferencia es global o por estación y usar una clave explícita y documentada. No alteraría la configuración de radio.

## 5. Configuración y cobertura de vistas

En `.settings-form`, los hijos `.form-group` pueden acumular el gap del padre, su margen inferior y el margen de etiqueta. Las grillas de dos/tres columnas y `.form-row-2col` ya anulan parte de esos márgenes: no corresponde aplicar una corrección indiscriminada a todos los formularios (E02–E03).

Seguridad y servicios mantienen pilas con máximo `56rem` y contenedores sin reglas propias de distribución (E04). Proponer una grilla de tarjetas cortas para escritorio, con MQTT y conexión en ancho completo cuando lo necesiten. Evitar masonry/orden visual que difiera del DOM y del recorrido de teclado.

Conservar las siete secciones locales y los IDs/eventos actuales durante una primera fase. Introducir dentro de cada sección un resumen con valores actuales, campos habituales y «Avanzado». Mantener siempre visibles errores, avisos de RF, estado de conexión, cambios pendientes y consecuencias de guardar. Las ayudas extensas pueden contraerse; las advertencias críticas no deben depender de un tooltip.

| Vista o familia | Intervención a evaluar | Contrato que se conserva |
| --- | --- | --- |
| Acceso y cuenta | Separar carga mínima; reducir decoración cuando falte altura | Ocultación hasta autenticar, errores legibles y controles accesibles |
| Cabecera y navegación | Presupuesto de altura menor en móvil; menú de acciones secundarias | Estado de radio, acceso a cuenta/tema/idioma y sección activa |
| Chat/canales/DM | Barra de herramientas compacta y panel de canales adaptativo | Historial y eventos aunque la vista esté oculta; popovers ya consideran `visualViewport` |
| Nodos y contactos | Alineación de herramientas, densidad por familia y detalles desplegables | Nombres/claves completos y restricciones CLIENT/REPEATER/LOCAL; nodos ya tienen padding/gap menores |
| Mapa | Controles/leyenda compactos; carga de biblioteca y estilos al entrar | Atribución, capas locales, geografía y acceso a trazas administrativas |
| Analítica | KPIs alineados y tablas/gráficos con detalle progresivo | Estado desconocido/stale/error, unidades y desplazamiento técnico local |
| Sniffer/logs | Filas compactas en escritorio y columnas prioritarias en móvil | Acceso al paquete completo, filtros y límites actuales |
| Configuración local | Grupos por tarea, espacios sin duplicación y columnas por contenido | Formularios, validación, persistencia y efectos de guardado actuales |
| Administración remota y diálogos | Separar resumen/avanzado y revisar cuerpo/acciones en altura corta | Foco, Escape, confirmaciones, busy states y operaciones manuales |
| Visor OpenAPI | Coherencia visual básica y tipografía legible | Su política propia de seguridad, carga manual y ausencia de ejecución de operaciones |

Las pestañas locales móviles ya son una tira horizontal desplazable. Mejorar la indicación de continuidad y mantener visible la selección es una opción más incremental que sustituirlas por otro control. Si se elige selector de sección, preservar semántica, foco y navegación de teclado.

## 6. Optimización de tipografías web e iconos

**Ya implementado:** el cuerpo usa fuentes del sistema; la variante local de Zephyr elimina el import de Google Fonts. No hay que añadir una fuente web para optimizar una descarga de texto que hoy se evita (E01, E09, E12).

La oportunidad específica es Bootstrap Icons: se conserva el catálogo completo, WOFF2/WOFF y `font-display:block` (E13). Comparar estas opciones:

| Opción | Aplicación propuesta | Consideraciones |
| --- | --- | --- |
| Mantener fuente local | Primera fase, sin cambio de iconografía | Medir aparición de iconos y transferencia; texto de acciones debe funcionar sin glifos |
| Subconjunto de iconos | Generar solo glifos usados por HTML y JS | Inventariar clases dinámicas y ambos idiomas/estados; actualizar hashes, licencia y procedencia |
| Sprite SVG local | Migrar familias de controles progresivamente | Reservar dimensiones, marcar decoración y conservar nombres accesibles; más trabajo de sustitución |
| Nueva fuente de texto local | Solo si existe una necesidad de identidad explícita | WOFF2, pesos/idiomas necesarios y fallback compatible; añade descarga y mantenimiento |

No aplicar `font-display:swap` a iconos de forma mecánica: un fallback puede mostrar símbolos incorrectos. Evitar incrustar fuentes completas en base64. Si se incorpora una fuente de texto, evaluar `swap`/`optional` y estabilidad de métricas. [Buenas prácticas de fuentes](https://web.dev/articles/font-best-practices).

Consolidar los roles tipográficos existentes, usar monospace para contenido técnico y números tabulares para medidas comparables. `--font-fluid-body` existe, pero `body` usa `--font-body`; decidir qué rol será realmente fluido antes de añadir más tokens. No atribuir una ganancia de rendimiento al mero uso de `clamp()`.

## 7. Incrustación de CSS crítico

**Actual:** cuatro hojas enlazadas en el encabezado: Slate, iconos, CSS propio y Leaflet. El CSS del mapa se solicita aunque la primera pantalla sea el acceso (E06). El HTML contiene también las vistas y diálogos; dividir CSS no elimina ese DOM.

| Alternativa | Uso en este proyecto | Decisión propuesta |
| --- | --- | --- |
| Mantener CSS externo y aplazar mapa | Menos cambios, caché independiente y orden de cascada conocido | Primera opción |
| Extraer CSS pequeño de arranque en archivo | Autenticación, estado inicial y tema, separado del resto | Comparar con la anterior antes de incrustar |
| Incrustar CSS crítico generado en HTML | Solo acceso/arranque y estructura inicialmente visible; resto diferido de forma controlada | Experimento posterior si las mediciones muestran bloqueo relevante |

El CSS crítico elimina una petición para esas reglas, pero incrementa el HTML y exige mantener sincronización y cascada. La técnica necesita especial cuidado con distintas pantallas/estados. [CSS crítico](https://web.dev/articles/extract-critical-css).

En esta SPA deben permanecer desde el primer render las reglas `.auth-pending`, `[hidden]`, foco y estructura de autenticación; diferirlas puede mostrar secciones antes de tiempo. Generar el bloque desde una única fuente de estilos, cubrir tema claro/oscuro y ES/EN y regenerar gzip/manifiesto. No copiar reglas manualmente en dos lugares.

Antes de incrustar estilos o usar manejadores inline para cargar CSS, revisar la política efectiva de la SPA y el plan de CSP. `_DOC_CONTENT_SECURITY_POLICY` en `asgi_security.py` pertenece al visor documental, no acredita una política equivalente para la SPA. Si corresponde autorizar un bloque inline, preferir hashes o nonces coordinados; no relajar una política mediante `unsafe-inline` por conveniencia.

## 8. JavaScript: carga diferida, `defer`, `async` y arranque

**Actual:** `session_startup.js` ya usa `async` para adelantar una lectura de sesión independiente. Leaflet, Bootstrap, QR e i18n usan `defer`. `app.js` es un módulo y sus imports de vistas son estáticos (E06–E08). No se encontró `import()` en las fuentes propias inspeccionadas.

`defer` conserva orden entre scripts clásicos diferidos y espera al fin del parseo. Los módulos se difieren por defecto; añadirles `defer` no los vuelve más rápidos. `async` ejecuta en cuanto está disponible, sin garantizar orden entre dependencias. [Semántica de script](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/script).

| Recurso | Tratamiento propuesto | Motivo específico |
| --- | --- | --- |
| Comprobación de sesión | Conservar `async` y su guarda compartida | Ya adelanta trabajo independiente sin duplicar la consulta |
| Tema y acceso | Entrada mínima, con pocas dependencias | `BrowserAuthentication` se inicia desde `app.js`; sus imports actuales incluyen todas las vistas antes de ejecutar esa entrada |
| Bootstrap | Conservar orden controlado o cargar explícitamente antes de sus consumidores | Diálogos y otros controles dependen de su API global |
| QR | Carga bajo demanda al abrir funciones que generan códigos | Conservar una promesa compartida, error visible y cancelación segura |
| Leaflet + CSS | Carga conjunta al necesitar el mapa | No promover ambos al arranque de un usuario que permanece en chat |
| Traducciones | Mantener disponibilidad antes de pintar; estudiar diccionarios por idioma | El archivo actual incluye ES y EN; no intercambiar idioma mediante descarga sin fallback |
| Analítica y sniffer | Módulo visual bajo demanda tras separar sus responsabilidades | Reducir evaluación y construcción iniciales sin perder eventos ni estado |

La aplicación se construye después de autenticar; eso no evita la descarga/evaluación previa del grafo importado por su entrada. Diferir un script tampoco equivale a cargarlo solo cuando se abre una pestaña. No convertir todos los scripts a `async`: rompería supuestos de orden y globals.

El HTML solicita Slate primero y el tema claro guardado se aplica durante la inicialización de autenticación. La posible descarga de ambos temas y el posible destello visual deben confirmarse con waterfall/filmstrip; seleccionar el tema temprano es un candidato de mejora, no un defecto visual reproducido aquí. Sniffer también crea su worker al inicializarse ([sniffer.js](src/web/static/js/modules/sniffer.js), 82–95), por lo que debe entrar en el inventario de trabajo inicial.

## 9. Directivas de recursos

No se encontraron `preload`, `modulepreload`, `preconnect` ni `dns-prefetch` en el HTML principal inspeccionado. Su ausencia no es por sí misma un defecto.

| Directiva | Posible aplicación | Evitar |
| --- | --- | --- |
| `preload` | Una fuente de iconos o CSS crítico externo solo si el waterfall demuestra descubrimiento tardío | Precargar todos los temas, mapas, fuentes alternativas o recursos ya descubiertos temprano |
| `modulepreload` | Entrada mínima y dependencias críticas concretas que sigan siendo necesarias | Precargar todas las vistas y anular la carga diferida |
| `preconnect` | Origen externo de teselas realmente elegido, al activar mapa online | Añadir Google Fonts o CDNs inexistentes en la ruta actual; conexiones extra al mismo origen |
| `dns-prefetch` | Resolución anticipada de un proveedor externo probable, de menor prioridad | Resolver preventivamente todos los proveedores o usarlos en modo local |

`preload` necesita destino `as`, tipo y modo de credenciales coherentes; una fuente se precarga con `crossorigin` y la misma URL efectiva. `modulepreload` es la directiva específica para módulos. [Preload](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/rel/preload), [modulepreload](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/rel/modulepreload).

`preconnect` anticipa establecimiento de conexión y `dns-prefetch` solo DNS; no aportan ese beneficio para el mismo origen ya conectado. El mapa contiene proveedores externos y una opción local: activar hints debe respetar la capa elegida y el uso offline. [Carga especulativa](https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/Speculative_loading).

## 10. Eficiencia de código, empaquetado, minificación y división

### Minificación y tree shaking

**Actual:** esbuild transforma/minifica cada archivo propio por separado; conserva imports relativos y globals clásicos. No hay bundling del grafo ni tree shaking entre módulos. El HTML se comprime con gzip, pero no se minifica en ese script (E09).

Conservar el build reproducible y la frontera fuente/vendor. Leaflet es un caso para revisar: transformar su JS produce un destino de 154.798 bytes frente a 147.552 de origen; «minificado» no garantiza un archivo menor. Comparar bytes crudos y comprimidos antes de elegir tratamiento, sin eliminar licencias ni cambiar contratos del global `L`.

Tree shaking elimina declaraciones que pueden descartarse; su eficacia depende de exports, imports y efectos laterales. Tener módulos ES no demuestra que ya esté ocurriendo. [API de esbuild](https://esbuild.github.io/api/#tree-shaking).

Auditar listeners globales, registros en el bus y creación de instancias antes de marcar código como libre de efectos. No añadir `sideEffects:false` o anotaciones de pureza para forzar eliminación sin demostrar que son correctas. Para CSS, el análisis de uso debe incluir clases construidas desde JS, temas, idiomas, Leaflet, estados de error y diálogos; un escaneo del HTML inicial no permite borrar reglas con seguridad.

### Opciones de bundling

| Estrategia | Ventaja potencial | Coste/riesgo en MeshCore Bridge |
| --- | --- | --- |
| ESM por archivo actual | Caché y depuración sencillas; URLs existentes | Más descubrimientos encadenados; no evita imports iniciales de vistas ocultas |
| Un único bundle de aplicación | Menos peticiones y análisis entre módulos | Descargaría vistas no usadas; invalidación de todo el paquete y mayor evaluación inicial |
| Entrada mínima + chunks por función | Aísla acceso y permite cargar mapa/analítica/QR cuando se usan | Necesita ciclo de vida explícito, manejo de fallos de carga y manifiesto de chunks |

**Preferencia:** evolucionar hacia la tercera opción si las mediciones confirman su utilidad. Primero separar fuentes CSS por responsabilidad y producir un único CSS general equivalente; separar archivos fuente no obliga a servir muchas hojas. Después evaluar CSS por vista costosa, manteniendo orden de cascada. No introducir `@layer` mecánicamente: hay que resolver su precedencia frente al CSS vendor existente.

### Code splitting y contratos de estado

La carga bajo demanda puede introducirse con `import()` nativo manteniendo el build por archivo actual. Si se eligen bundles con chunks compartidos, esbuild ofrece `splitting` mediante su API de construcción con salida ESM. Debe revisarse la compatibilidad de la versión fijada antes de migrar. [División de código en esbuild](https://esbuild.github.io/api/#splitting).

Propuesta de separación propia del proyecto:

1. **Arranque:** tema, idioma mínimo, comprobación de sesión y formulario de acceso.
2. **Núcleo autenticado:** store, bus, WebSocket, límites de autorización, historial y coordinación de acciones.
3. **Vistas:** chat/directorios/configuración, activadas con contrato explícito.
4. **Funciones costosas:** mapa/Leaflet, gráficos de analítica, QR e inspector, según necesidad.

Mantener estado y recepción de eventos en el núcleo aunque una vista nunca se haya cargado. El [bus actual](src/web/static/js/core/eventbus.js), 17–29, usa `EventTarget` sin replay: suscribirse tarde no recupera eventos anteriores. Las referencias cruzadas actuales de `context` a mapa, chat, nodos y configuración requieren adaptadores o un coordinador que resuelva la carga; canales/configuración deben quedar disponibles para chat aunque no se haya abierto Ajustes. No sustituir simplemente cada import por `import()`.

Definir `load/activate/deactivate/dispose`, una promesa por carga, deduplicación de listeners y rechazo de respuestas obsoletas. Un fallo de chunk debe dejar reintento manual y contexto comprensible sin duplicar envíos. Preservar cancelación, foco, idioma/tema y autenticación de respuestas. No añadir timers de precarga ni nuevos reintentos de radio.

Para chunks con hash, actualizar build, manifiesto, resolución de rutas y empaquetado Python. El adaptador actual reconoce manifiesto versión 1: un nuevo esquema requiere migración coordinada y fallback. Publicar chunks antes del HTML/manifiesto que los referencia y conservar archivos de versiones aún en uso según una política explícita. Solo recursos con URL inmutable por contenido podrían recibir caché larga; `app.js` no puede convertirse en `immutable` manteniendo la misma URL mutable.

## 11. Compresión de texto: gzip y Brotli

### Gzip existente y prioridad de correspondencia de URLs

Ya se genera gzip nivel 9 en build; el servidor no lo recalcula por petición. Valida hashes, negocia aceptación, añade `Vary: Accept-Encoding` y usa ETag por representación (E09–E10).

**Hallazgo estático P1:** ciertas URLs solicitan directamente destinos derivados, pero el manifiesto se indexa por fuente:

| URL solicitada | Clave del manifiesto | Consecuencia del flujo de código actual |
| --- | --- | --- |
| `/js/leaflet.min.js` | `js/leaflet.js` | No encuentra entrada por esa URL; no valida/selecciona el sidecar gzip |
| `/css/leaflet.min.css` | `css/leaflet.css` | Mismo recorrido sin gzip seleccionado |
| `/css/bootstrap-zephyr.local.min.css` | `css/bootstrap-zephyr.min.css` | Afecta al tema claro elegido desde `theme.js` |

`_select_asset` busca la clave solicitada y devuelve `gzip_verified=False` si falta; `_static` exige esa verificación. Esta consecuencia se deduce del código y del manifiesto presente; no se reprodujo mediante una petición HTTP en esta tarea.

Opciones: unificar URLs canónicas y consumidores, o incorporar aliases/índice inverso validados para destinos. La segunda debe conservar verificación de fuente/destino/gzip, contención de rutas, invalidación y ETag correcto. Para Zephyr, mantener siempre el derivado local sin import de Google Fonts, incluso en fallback; no cambiar a una URL cuyo fallback reintroduzca una dependencia remota. **No resolverlo sirviendo cualquier `.gz` por su fecha o existencia.**

### Brotli como ampliación opcional

| Opción | Alcance | Evaluación |
| --- | --- | --- |
| Mantener gzip | Reparar selección y aplazar recursos innecesarios | Menor coste y prioridad inmediata |
| Brotli previo en build | Añadir `.br` para HTML/CSS/JS, conservar gzip y original | Candidato posterior; medir reducción real y coste de build/almacenamiento |
| Brotli en proxy existente | Usar capacidades del despliegue cuando estén configuradas | Documentar responsabilidad, caché, cabeceras y ausencia de doble compresión |
| Brotli dinámico general | Comprimir cada respuesta al vuelo | No recomendado como cambio inicial: afecta CPU, latencia y perímetro de datos |

Brotli y gzip son codificaciones negociadas mediante `Accept-Encoding`; la respuesta declara `Content-Encoding`. Se deben respetar calidades `q`, negativas explícitas y variantes de caché, sin elegir `br` solo porque aparezca en la cabecera. [Accept-Encoding](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Accept-Encoding) y [Content-Encoding](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Encoding).

La opción de Brotli previo exige generador reproducible, digest y bytes por representación, validación de descompresión, negociación `br/gzip/identity`, ETags separados, `Vary`, HEAD/304 y fallback cuando falte o esté corrupto un sidecar. No implica instalar Brotli en el SBC si se distribuyen artefactos preconstruidos.

Conservar los límites de la compresión dinámica existente: solo métricas GET autorizadas, exclusión de secretos/configuración/chat, trabajo fuera de asyncio y presupuesto de CPU actual. No cambiar su presupuesto, umbrales o concurrencia en una tarea de diseño. No recomprimir WOFF2, imágenes ni respuestas ya codificadas como estrategia general. No prometer un porcentaje de ahorro de Brotli sin generar y medir los mismos contenidos.

## 12. Prioridades, dependencia y propiedad para una implementación futura

| Orden | Trabajo | Valor esperado, por comprobar | Complejidad relativa | Propietario propuesto |
| --- | --- | --- | --- | --- |
| P1-1 | Alinear URLs y manifiesto para gzip | Usar representaciones que ya existen | Media | Entrega/build, con revisión del líder y adaptador Python |
| P1-2 | Corregir separación de campos y organizar seguridad/servicios | Más contenido útil sin reducir texto | Baja–media | Maquetación CSS/HTML |
| P1-3 | Densidad Normal/Compacta y cabecera móvil | Ajuste por espacio y preferencia | Media | Diseño y maquetación, un único dueño de archivos compartidos |
| P1-4 | Medición aislada de carga y render | Decidir qué optimizaciones compensan | Media | QA, cuando se solicite ejecución |
| P2-1 | Entrada mínima de acceso y tema | Menor grafo previo a autenticación; revisar posible carga de ambos temas | Media–alta | Arquitectura frontend |
| P2-2 | Carga por función de Leaflet/QR/analítica | Menos recursos y trabajo iniciales para vistas no usadas | Alta | Arquitectura frontend + build |
| P2-3 | Inventario/subconjunto o SVG de iconos; diccionarios por idioma | Evitar catálogos completos innecesarios | Media | Diseño/iconografía + i18n/build |
| P3-1 | CSS crítico y hints seleccionados | Mejorar descubrimiento/render solo si existe cuello de botella | Media–alta | Entrega + diseño |
| P3-2 | Brotli previo y caché de chunks con hash | Menor transferencia potencial y caché segura | Media–alta | Build + adaptador estático |

P1-1 y P1-2 pueden desarrollarse por especialistas distintos con propiedad de archivos acordada. Cambios a `index.html`, `app.js`, `app.css`, build y manifiesto necesitan un propietario único por fase y revisión de integración. No optimizar simultáneamente todas las capas: comparar cada entrega con una base reproducible.

## 13. Plan de comprobación pendiente

Estos son criterios para una futura tarea con ejecución autorizada; no son resultados de esta entrega.

| Dimensión | Casos mínimos propuestos | Evidencia a registrar |
| --- | --- | --- |
| Pantallas | 320/360/390/480/768/1024/1440/1920/2560 CSS px; 767/768 y 991/992 por transiciones existentes | Capturas y medidas de cabecera, controles, columnas y scroll |
| Altura e interacción | Vertical/horizontal, altura útil de 500 px o menos, teclado móvil, puntero fino/grueso e híbrido | Campo enfocado y acciones accesibles, sin superposición |
| Accesibilidad | Teclado, foco, zoom 200% y reflujo 320 CSS px; lector cuando corresponda | Orden de lectura, nombres de controles, contraste renderizado y áreas táctiles |
| Contenido | ES/EN, ambos temas, nombres/claves largos, tablas grandes, ayudas expandidas | Sin recortes irrecuperables ni desplazamiento horizontal global injustificado |
| Estado | Carga/vacío/error/stale/offline, cambios de cuenta y rechazo 401/403 | Sin mezcla de datos protegidos ni respuestas obsoletas |
| Recursos | Caché fría/caliente, tema guardado claro/oscuro y primera vista diferente | HAR, peticiones, bytes transferidos/descomprimidos y cadena de imports |
| Experiencia | Acceso, primer contenido útil, primera interacción y primera apertura de vista diferida | FCP/LCP/CLS, tareas largas e interacción, con navegador/red/dispositivo documentados |
| Compresión | URL fuente/alias, gzip aceptado/rechazado; br si se añade; HEAD/304 y sidecar inválido | Cabeceras y cuerpo coherentes, fallback y separación de ETags |
| Estado y chunks | Mensajes antes de abrir una vista, retorno a pestaña, chunk fallido, cambio de idioma | Sin pérdida de historial/eventos, duplicación de listeners o envíos |

Usar una estación virtual propia, puertos de loopback asignados y datos temporales; nunca asumir que un servicio ya abierto es una fixture. Conservar trazas comparables y documentar equipo/SBC, navegador, carga y red. El porcentaje de contenido visible y el tiempo ganado se calcularán solo después de medir el mismo contenido en los mismos escenarios.

La validación estática de esta entrega se limita a lectura cruzada, referencias locales, consistencia de artefactos y revisión de diff. No se ejecutaron pytest, cobertura, mypy, ruff, Playwright ni pruebas de carga por esta solicitud de evaluación documental. No se acredita interoperabilidad HTTP, accesibilidad completa, rendimiento ni aspecto renderizado.

## 14. Impacto y límites de la propuesta

En esta entrega: **cero paquetes RF, cero notificaciones automáticas, cero timers nuevos y cero cambios a parámetros de radio o presupuesto de compresión**. No se leen datos de una instalación operativa ni se modifican referencias oficiales.

Las mejoras de presentación y entrega deberán conservar endpoints, selectores, roles, control de origen propio, cooldowns, validaciones, SQLite y límites de autorización. Separar vistas no autoriza cambiar consultas activas de radio ni rearme de schedulers. Cualquier implementación que añada tráfico RF, notificaciones, reintentos o timers debe resolver antes el checklist de [AGENTS.md](AGENTS.md) con los intervalos que elija el usuario.

El resultado es una base de decisión para mejorar densidad y carga sin confundir propuestas con capacidades implementadas. La selección visual recomendada es **A + configuración progresiva de C**, con prioridad a espacios/columnas y a la selección correcta de gzip antes de acometer cambios mayores de empaquetado.
