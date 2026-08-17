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
2. **Variables CSS (Custom Properties)**:
   - Centralizar todas las dimensiones, colores, sombras y radios en `:root`.
3. **Respeto a Preferencias de Accesibilidad**:
   - `@media (prefers-reduced-motion: reduce)` desactivando animaciones agresivas.

## Estándares de JavaScript Moderno (ES6+)
1. **Asincronía y Control de Peticiones**:
   - `async/await` nativo para todas las llamadas asíncronas con manejo de errores `try/catch`.
   - Uso de `AbortController` para cancelar peticiones HTTP obsoletas o timeouts.
2. **WebSocket Resiliente**:
   - Patrón de reconexión con retroceso exponencial (*exponential backoff*) y buffer de reconexión.
3. **Manipulación Segura del DOM**:
   - Nunca interpolar variables sin sanitizar en `innerHTML`. Utilizar siempre `escapeHtml(value)` o `textContent`.

## Herramientas de Verificación
```bash
python .agents/skills/html-css-modern-js/scripts/lint_frontend_standards.py
```
