# Armonización visual de la estación web — 2026-10-17

Estado: implementación integrada y revisión visual virtual completada.

## Objetivo y alcance

Revisar toda la SPA y mejorar su coherencia visual: acceso y perfil, cabecera y
navegación, chat, nodos y contactos, mapa, analítica, ajustes locales,
administración de infraestructura, sniffer, logs y diálogos compartidos.
Conservar Bootstrap local, Vanilla CSS/JS, fuentes del sistema, iconos locales,
traducciones y los contratos REST/WebSocket existentes.

## Equipo y propiedad

- Diseño visual: auditoría global y cambios en `src/web/static/css/app.css`.
- Componentes web: `index.html`, `modules/nodes.js` y `modules/sniffer.js`;
  semántica de controles y tablas, nombres accesibles y estados de selección.
- Experiencia y revisión: inspección independiente y navegador aislado, sin
  editar fuentes de la aplicación.
- Principal: integración, módulos de mapa/analítica, documentación, build y Git.

## Plan de ejecución

1. **Auditoría.** Inventariar vistas, estilos estáticos y markup dinámico;
   identificar contrastes, densidades y puntos de ruptura inconsistentes.
2. **Sistema visual.** Centralizar colores semánticos para ambos temas, escala
   tipográfica, alturas de controles, espaciado y superficies. Reparar texto
   blanco sobre azul claro y cifras claras sobre tarjetas del tema claro.
3. **Componentes.** Armonizar botones, filtros, pestañas, tarjetas, tablas,
   formularios, popups y diálogos; conservar los selectores funcionales.
4. **Responsividad y accesibilidad.** Revisar overflow, textos largos, foco y
   áreas táctiles; añadir estados accesibles a filtros y nombres a acciones.
5. **Verificación.** Construir y comprobar los artefactos locales, revisar diff,
   referencias y contraste de pares explícitos. El usuario autorizó revisión
   visual de escritorio/móvil y ambos temas sobre estación virtual aislada.
6. **Entrega.** Corregir los hallazgos de integración, registrar evidencia y
   limitaciones, publicar sólo los archivos propios de esta tarea.

## Restricciones y aceptación

Los cambios son de presentación y semántica de controles. No añaden tráfico RF,
publicaciones MQTT, reintentos, timers ni cambios de parámetros de radio; el
checklist de nuevas transmisiones no aplica. Mantener exclusión LOCAL/REPEATER
de contactos y envío de chat, y las confirmaciones de administración existentes.

La aceptación requiere build/check reproducible, ausencia de regresiones
estáticas en IDs/imports, contraste medido en pares declarados y revisión visual
en el entorno autorizado. Los checks estáticos no certifican WCAG completa ni
rendimiento. No ejecutar la suite Python global por esta autorización de revisión
visual. No incluir modificaciones previas del usuario en documentación/pruebas.

## Registro de ejecución

- Auditoría inicial: los tokens vigentes están en `app.css`, aunque algunas
  skills antiguas mencionan `tokens.css`. La UI ya contiene modernizaciones
  anteriores que se conservan.
- Hallazgos iniciales: botones compactos y badges con blanco sobre azul claro;
  analítica con fallback blanco de `--text-bright` ausente; metadatos pequeños y
  controles táctiles con dimensiones discordantes; filtros sin estado accesible;
  popups del mapa con colores fijos que no siguen el tema.
- Sistema visual aplicado en las definiciones existentes de `app.css`: controles
  de 36/32 px en escritorio y 44 px con puntero táctil; metadatos de al menos
  12 px, fuentes locales, radios y superficies compartidos. Colores de texto
  semánticos separados de rellenos sólidos para ambos temas.
- Componentes: filtros con `aria-pressed` sincronizado, encabezados de tabla con
  `scope`, iconos locales y nombres contextuales de acciones. El ACK conserva
  icono y nombre accesible al pasar de cola a enviado/entregado. Popups de mapa y
  tarjetas compartidas siguen los colores del tema.
- Distribución: tarjetas de nodos con ancho mínimo y acciones que se redistribuyen
  sin cortar palabras; último anuncio en fila completa. Subpestañas móviles en una
  fila desplazable. Gráfica de tráfico con etiquetas SVG de 12 px, viewBox de
  640 unidades y scroll local accesible por teclado. Mapa acotado al área útil;
  diálogos con scroll propio, incluido el contenedor anidado de administración.
- Visor OpenAPI: misma familia visual y preferencia de tema guardada, aplicada
  mediante script local compatible con CSP; conserva carga manual y autorización.

## Evidencia y límites

- `npm --prefix tools/frontend run build` y `run check`: esbuild 0.28.1, 31 assets;
  fuentes, variantes mínimas, hashes y gzip verificados. Esbuild es dependencia
  local de construcción, sin cambios de dependencias de producción.
  Resultado final: 2.372.791 bytes de fuentes, 2.051.384 servidos y 418.697 gzip;
  son tamaños del catálogo de build, no mediciones de descarga o rendimiento.
- Revisión estructural: 648 IDs únicos preservados, marcadores de traducción
  existentes conservados, referencias ARIA resueltas, 41 imports locales
  existentes y sintaxis de 24 fuentes JS comprobados; diff sin errores de espacios.
- Contraste por fórmula de luminancia sRGB: blanco sobre rellenos primario
  6,16:1, éxito 5,87:1, peligro 6,47:1 e información 6,63:1. Texto principal,
  secundario y acentos declarados superan 4,5:1 sobre superficies de tarjeta y
  herramientas en ambos temas. No equivale a certificación WCAG de toda la SPA.
- Navegador: Python 3.12.10, Playwright 1.62.0 y Chromium 151; fixtures mantenidas
  con VirtualMeshAdapter, MQTT simulado, estado temporal y puerto loopback propio.
  Primera matriz de siete vistas, ES/EN y ambos temas en 1920×1080, 390×844,
  320×740, 844×390 y 768×1024: sin overflow global. Se añadieron pasadas de
  corrección y capturas enfocadas de nodos, gráfica, popovers, toasts, login,
  modales y visor OpenAPI con carga manual del contrato.
- La revisión detectó y corrigió tarjetas estrechas, acciones partidas,
  subpestañas móviles demasiado altas, iconos claros en tarjetas claras, etiquetas
  pequeñas de gráfica y nombres accesibles de ACK desactualizados. Las capturas
  de modales/toasts se repitieron esperando su transición completa; una captura
  prematura de backdrop no se aceptó como evidencia del contenido.
- Evidencia local no versionada: `tests/artifacts/visual-harmony/` (capturas,
  geometría y resultados). El script puntual está en
  `scratch/visual_harmony_audit.py`; no se incorpora como suite mantenida.
  `verified-final.json` registra la pasada enfocada; su cobertura del visor queda
  sustituida por `docs-verified-final.json`, que comprueba ancho, tema DOM y colores
  calculados en escritorio y móvil táctil. `passive-admin-final.json` verifica
  los seis paneles de administración por ambos temas en móvil táctil (12 casos),
  fondo alcanzable mediante scroll y ACK sintético con nombre/icono sincronizados.
  Las ejecuciones finales terminaron sin errores JS, consola ni HTTP; WebSocket
  conectado durante la inspección y cierre de navegador, servidor y adaptador.
  El desbloqueo visual administrativo se simuló sin transmisión RF. Las teselas
  de mapa de la fixture sustituyen los recursos externos; las capturas no evalúan
  la calidad cartográfica del proveedor.
- No se ejecutaron pytest global, cobertura, mypy ni Ruff: el cambio es de
  frontend y la autorización fue de inspección visual. No se operó una estación
  física ni un broker de producción. El comportamiento de hardware y el
  rendimiento en SBC quedan fuera de esta comprobación.
