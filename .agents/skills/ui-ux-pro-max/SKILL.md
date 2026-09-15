---
name: ui-ux-pro-max
description: >-
  Inteligencia de diseño UI/UX para web, móvil y escritorio. Sistema integral de diseño con 79 estilos (50 activos),
  192 paletas de color con perfiles de razonamiento, 74 emparejamientos tipográficos, 119 reglas de experiencia de usuario (UX),
  105 iconos curados, 17 presets de animación y 25 tipos de gráficos sin dependencias pesadas.
---

# UI/UX Pro Max - Inteligencia de Diseño y Experiencia de Usuario

Esta skill provee directrices formales de diseño visual, accesibilidad (WCAG 2.2 AA), ergonomía de interfaces y sistemas de diseño para clientes web nativos.

## Cuándo Aplicar
Usar esta skill en tareas relacionadas con:
- Estructura visual de páginas, jerarquía de contenido y diagramación.
- Creación y refactorización de componentes de interfaz de usuario.
- Selección armónica de paletas de color, tokens CSS y variables semánticas.
- Tipografía fluida (`clamp()`), escala espacial de 8pt y legibilidad.
- Accesibilidad: contraste de color mínimo de 4.5:1, etiquetas ARIA, navegación por teclado (`:focus-visible`).
- Micro-interacciones táctiles (mínimo 44x44px) y feedback de carga.

## Matriz de Prioridad de Reglas

| Prioridad | Categoría | Impacto | Verificaciones Clave | Anti-patrones a Evitar |
|---|---|---|---|---|
| 1 | Accesibilidad | CRÍTICO | Contraste >= 4.5:1, etiquetas aria-label, foco visible, navegación completa por teclado | Ocultar contorno de foco, botones de solo icono sin texto accesible |
| 2 | Interacción Táctil | CRÍTICO | Área táctil >= 44x44px, separación >= 8px, estado de pulsación visible | Dependencia exclusiva de hover, respuestas instantáneas sin feedback (0ms) |
| 3 | Rendimiento Visual | ALTO | Cero layout shifts (CLS < 0.1), renderizado nativo en < 50ms | Layout thrashing, frameworks CSS masivos que bloqueen SBCs |
| 4 | Consistencia de Estilo | ALTO | Tokens de diseño centralizados en `:root`, iconos SVG limpios | Mezclar estilos planos con esqueumórficos, usar emojis como iconos |
| 5 | Responsividad | ALTO | Diseño Mobile-First, flexbox y grid fluido con `repeat(auto-fit, minmax(...))` | Anchos fijos en píxeles que generen scroll horizontal no deseado |
| 6 | Tipografía | MEDIO | Tamaño base 16px (1rem), altura de línea 1.4-1.6, jerarquía h1-h4 clara | Textos menores a 12px, gris claro sobre fondo gris |
| 7 | Animación y Movimiento| MEDIO | `prefers-reduced-motion: reduce`, transiciones suaves (150-250ms) | Animaciones largas que retrasen la interactividad del usuario |
| 8 | Formularios y Feedback| MEDIO | Etiquetas visibles, validación cerca del campo, mensajes de error legibles | Solo placeholders sin labels permanentes, errores genéricos |

## Herramientas y Scripts Locales
Para buscar estilos y tokens específicos del catálogo:
```bash
python .agents/skills/ui-ux-pro-max/scripts/search.py "<termino>" --domain <ux|style|color|typography>
```
