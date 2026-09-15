---
name: html-css-modern-js
description: >-
  Estándares de frontend moderno: HTML5 semántico (header, nav, main, section, aside),
  CSS moderno (Flexbox, CSS Grid, Custom Properties, clamp()), y JavaScript ES6-ES2024
  (async/await, AbortController, WebSocket auto-reconnect, CustomEvents, sanitización DOM).
---

# Modern HTML5, CSS3 & JavaScript Skill

Esta skill define las mejores prácticas de desarrollo web moderno utilizando tecnologías nativas sin dependencias pesadas para asegurar máxima velocidad de renderizado (< 50ms) y bajo consumo de memoria.

## Estándares de HTML5 Semántico
1. **Estructura Jerárquica y Accesible**:
   - Usar `<header>`, `<nav>`, `<main>`, `<section>`, `<article>`, `<aside>` y `<footer>`.
   - Uso de un único `<h1>` por página con jerarquía coherente de `<h2>`, `<h3>`.
   - Elementos interactivos nativos (`<button>`, `<input>`, `<select>`) en lugar de `<div>` con `onclick`.
   - Atributos ARIA cuando los componentes lo requieran (`role="tablist"`, `role="tab"`, `aria-selected`, `aria-live="polite"`).

## Estándares de CSS3 Moderno
1. **Maquetación con Flexbox y CSS Grid**:
   - `display: flex` para alineaciones unidimensionales (barras de herramientas, chips, burbujas de chat).
   - `display: grid` con `grid-template-columns: repeat(auto-fit, minmax(280px, 1fr))` para tableros de tarjetas responsivas sin necesidad de media queries complejas.
   - `gap` nativo para separación consistente de elementos.
2. **Variables CSS (Custom Properties) y Tipografía Fluida**:
   - Centralizar todas las dimensiones, colores, sombras y radios en `:root`.
   - Tipografía adaptativa con `font-size: clamp(0.875rem, 1vw + 0.5rem, 1.125rem)`.
3. **Respeto a Preferencias de Accesibilidad**:
   - Contraste de color WCAG 2.2 AA (relación mínima 4.5:1 para texto normal, 3:1 para controles UI).
   - `@media (prefers-reduced-motion: reduce)` desactivando animaciones agresivas.
   - Navegación por teclado visible con `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }`.

## Estándares de Componentes e Interacción
1. **Interruptores Toggle Switch Semánticos**:
   - Implementar con `<input type="checkbox" role="switch" id="..." aria-checked="...">` y `<label>` asociado.
   - Estado visual activo/inactivo claro con tokens CSS sin recurrir a librerías de terceros.
2. **Formularios y Validaciones**:
   - Mensajes de error claros e informativos vinculados al campo con `aria-describedby`.
   - Estado de carga y deshabilitación durante peticiones de red activas.

## Estándares de JavaScript Moderno (ES6-ES2024)
1. **Asincronía y Control de Peticiones**:
   - `async/await` nativo para todas las llamadas asíncronas con manejo de errores `try/catch`.
   - Uso de `AbortController` para cancelar peticiones HTTP obsoletas o timeouts.
2. **WebSocket Resiliente y Desacoplado**:
   - Patrón de reconexión con retroceso exponencial (*exponential backoff* con jitter aleatorio).
   - Event-driven: Despacho de eventos internos con `window.dispatchEvent(new CustomEvent('mesh-event', { detail: payload }))`.
3. **Manipulación Segura del DOM y Prevención XSS**:
   - Nunca interpolar variables sin sanitizar en `innerHTML`. Utilizar siempre `escapeHtml(value)` o `textContent`.

## Herramientas de Verificación
```bash
python .agents/skills/html-css-modern-js/scripts/lint_frontend_standards.py
python scripts/inspect_web.py
```

