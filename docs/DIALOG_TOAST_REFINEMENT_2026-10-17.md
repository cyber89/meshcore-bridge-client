# Diálogos y toast del sistema — 2026-10-17

## Plan

1. Auditar confirmaciones, alertas, prompts, perfil nativo y modales de
   formularios, QR, importación, traceroute, inspector y administración. Revisar
   también los cuatro tipos de toast y sus rutas de creación/cierre.
2. Armonizar superficies, iconos, títulos, jerarquía de acciones, radios y padding;
   toast neutros con severidad visible mediante icono, texto y acento.
3. Conservar alturas táctiles y foco visible, envolver títulos y mensajes largos,
   acotar pilas al viewport y mantener scroll de contenido sin ocultar acciones.
4. Verificar ambos temas e idiomas en escritorio, móvil estrecho y landscape;
   comprobar teclado, cierre, foco y diálogos anidados en estación virtual.
5. Revisar contratos, reconstruir assets, registrar resultados y publicar sólo
   archivos de esta tarea en `origin/main`.

## Equipo y límites

- Diseño: propiedad exclusiva de `src/web/static/css/app.css`.
- Componentes: markup estático en `src/web/static/index.html` y revisión cruzada.
- Experiencia/QA: scripts puntuales en `scratch/` y evidencia bajo
  `tests/artifacts/dialog-toast-audit/`; fixtures con estado temporal,
  VirtualMeshAdapter, MQTT simulado y loopback propio.
- Principal: `app.js`, traducciones, integración, documentación, build y Git;
  cambios de interacción sólo tras reproducción de la regresión.

Se mantienen contratos Promise de confirmación/alerta/prompt, validaciones y
duraciones configuradas de los avisos. No se añaden eventos automáticos, consultas
RF, reintentos ni schedulers. El checklist de nuevas transmisiones no aplica.
La autorización de navegador continúa en esta revisión; no se ejecuta pytest
global ni se utilizan instalaciones operativas. Los cambios previos en
documentación y pruebas quedan fuera del commit.

## Hallazgos y ejecución

- Toast con fondos de severidad completos y controles de cierre pequeños;
  falta acotar la altura de una pila larga.
- Región viva duplicada entre contenedor y cada toast, y etiquetas de cierre
  generadas sin binding de idioma.
- Clases de badge globales interfieren con los fondos suaves de los iconos de
  diálogos de sistema. Cabeceras/footers requieren contratos de tamaño comunes.
- Toasts: superficie neutra, título traducible e icono/acento de severidad;
  mensaje de varias líneas, cierre de 44 px, pila acotada al viewport y scroll
  hacia el nuevo aviso cuando el usuario no está interactuando con la pila.
  Los anuncios pertenecen a cada toast, sin región viva duplicada en el padre.
- Diálogos: clases `tone-*` independientes de badges, tarjeta del sistema
  centrada, cabeceras/claves que envuelven y espaciado compartido. Orden visual de
  acciones igual al DOM; márgenes de footers anidados derivados del mismo
  padding. Perfil con scroll y QR con ancho propio en el contenedor Bootstrap.
- Interacción: reproducción previa en estación virtual de dos fallos reales:
  Ctrl+K abría la paleta detrás de Perfil nativo y el fallback sin Bootstrap
  generaba toast oculto, sin cierre útil y borraba avisos persistentes. Los dos
  tests nuevos fallaron por esas causas antes del parche. Correcciones: ceder
  teclado/foco al diálogo nativo y alinear fallback con el contrato de Bootstrap
  (`durationMs > 0` autohide; cero/negativo persistente). Se dispone la instancia
  de Bootstrap cuando el toast termina de cerrarse.

## Verificación

- Build/check de esbuild 0.28.1: 31 assets, 2.379.413 bytes de fuentes,
  2.056.779 bytes servidos y 419.642 gzip. Son tamaños de build, no mediciones
  de rendimiento.
- 648 IDs únicos conservados, traducciones previas y referencias ARIA
  preservadas; sintaxis de las fuentes JS y diff comprobados.
- Contraste de iconos sobre los fondos efectivos de diálogo: claro
  4,74–6,85:1 y oscuro 8,69–9,84:1. Iconos de toast sobre su superficie mezclada:
  claro 5,08–5,50:1 y oscuro 6,22–8,03:1. Esto no certifica WCAG de toda la SPA.
- Pendiente durante ejecución: resultado de regresiones y aceptación visual final.
