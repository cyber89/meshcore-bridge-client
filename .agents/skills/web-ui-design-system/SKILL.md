---
name: web-ui-design-system
description: >-
  Diseño visual de interfaces de grado profesional: Sistema de tokens de diseño, paletas armónicas HSL,
  escala tipográfica fluida (clamp), grilla espacial de 8pt, contraste accesible WCAG 2.2 AA (>= 4.5:1),
  micro-animaciones y soporte responsivo desktop/mobile.
---

# Web UI & Design System Skill

Esta skill define las pautas estéticas, visuales y de interacción para construir aplicaciones web fluidas, modernas y de grado profesional sin dependencias pesadas.

## Principios de Diseño
1. **Paleta Armónica de Color (Espacio HSL)**:
   - Fondo Base: Tonos pizarra oscuro (`hsl(222, 47%, 7%)` - `#0b0f19`).
   - Superficies y Tarjetas: `hsl(217, 33%, 17%)` / `hsl(215, 28%, 23%)`.
   - Acentos Funcionales:
     - Cian Eléctrico (`#06b6d4` / `hsl(189, 94%, 43%)`) para acciones primarias e información activa.
     - Esmeralda (`#10b981`) para estado online, éxito y telemetría estable.
     - Ámbar (`#f59e0b`) para advertencias o enlaces de calidad media.
     - Rosa / Rubí (`#f43f5e`) para errores, caídas de conexión o paquetes corruptos.
   - Contraste WCAG 2.2 AA estricto ($\ge 4.5:1$ en textos estándar, $\ge 3:1$ en encabezados y componentes interactivos).

2. **Sistema de Espaciado (Spatial Grid de 8pt)**:
   - Variables de espaciado: `4px` (xxs), `8px` (xs), `12px` (sm), `16px` (md), `24px` (lg), `32px` (xl).
   - Radio de esquinas consistente: `var(--radius-sm: 6px)`, `var(--radius-md: 10px)`, `var(--radius-lg: 16px)`.

3. **Tipografía Fluida y Legible**:
   - Pila de fuentes de sistema de alto rendimiento: `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`.
   - Escala tipográfica matemática: 0.75rem (badges/metadata), 0.85rem (cuerpo compacto/tablas), 0.95rem (lectura), 1.25rem (h3), 1.6rem (kpis/h2), 2.0rem (h1).
   - Letter-spacing ajustado: `-0.01em` en títulos para mayor solidez visual, `0.02em` en badges en mayúsculas.

4. **Micro-interacciones y Estados de Componentes**:
   - Todos los elementos interactivos (botones, pestañas, filas de tabla, chips) deben contar con estados `:hover`, `:active` y `:focus-visible`.
   - Transiciones suaves: `transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1)`.
   - Respeta `@media (prefers-reduced-motion: reduce)`.

## Referencias
Consultar [design_tokens_cheatsheet.md](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.agents/skills/web-ui-design-system/references/design_tokens_cheatsheet.md).
