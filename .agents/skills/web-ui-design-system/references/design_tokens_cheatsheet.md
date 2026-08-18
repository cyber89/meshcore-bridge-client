# Guía Rápida de Tokens de Diseño (Design Tokens CheatSheet)

## 1. Variables CSS Universales

```css
:root {
  /* Fondos y Superficies (Dark Theme) */
  --bg-app: #0b0f19;          /* Fondo base profundo */
  --bg-surface: #111827;      /* Barras, paneles laterales y cabeceras */
  --bg-card: #1e293b;         /* Tarjetas, bloques interactivos */
  --bg-card-hover: #273549;   /* Estado hover */
  --border-subtle: #334155;   /* Bordes separadores */
  --border-focus: #06b6d4;    /* Foco visible */

  /* Textos */
  --text-primary: #f8fafc;    /* Texto principal (Contraste > 12:1) */
  --text-secondary: #94a3b8;  /* Texto secundario / subtítulos */
  --text-muted: #8494a8;      /* Metadatos y marcas de tiempo (WCAG AA 4.5:1) */

  /* Acentos Semánticos */
  --accent-cyan: #06b6d4;     /* Primario / RF / Acciones */
  --accent-emerald: #10b981;  /* Éxito / Online / Batería OK */
  --accent-amber: #f59e0b;    /* Advertencia / Retransmisión */
  --accent-rose: #f43f5e;     /* Error / Caída de enlace */
  --accent-purple: #a855f7;   /* Sensores / Telemetría */

  /* Geometría y Elevación */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --shadow-card: 0 4px 12px rgba(0, 0, 0, 0.3);
  --transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
```

## 2. Puntos de Quiebre Responsivos (Breakpoints)
- **Mobile Vertical**: `< 640px` (Columna única, navegación inferior o colapsable, tarjetas a 100% ancho).
- **Tablet / Mobile Horizontal**: `640px - 1024px` (Barra lateral compacta, grillas de 2 columnas).
- **Desktop**: `> 1024px` (Layout completo de 3 paneles: navegación, contenido principal y visor lateral).
