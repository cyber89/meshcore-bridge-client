# ADR 0012: Reestructuración Integral de la Web SPA con Bootstrap 5.3 y Bootstrap Icons

- **Estado**: Aprobado / En Planificación
- **Fecha**: 2026-10-09
- **Autores**: Lead Orchestrator, Frontend Architect Agent, Usuario (mediante sesión de alineación `/grill-me`)
- **Base**: `fcaf89b` y árbol de trabajo consolidado en FastAPI ASGI

## Contexto y Problema

MeshCore Bridge opera una Single Page Application (SPA) para monitorización y administración de radioenlaces LoRa y repetidores. Hasta la fecha, la interfaz dependía de aproximadamente 209 KB de CSS artesanal distribuido en seis archivos (`tokens.css`, `components.css`, `admin.css`, `chat.css`, `nodes.css`, `app.css`), junto con un generador de iconos SVG incrustados en JavaScript (`icons.js`) y componentes modales/tabs manuales.

Tras culminar con éxito la consolidación del backend en FastAPI ASGI y retirar el servidor HTTP legacy, se acordó con el usuario evolucionar y modernizar la interfaz hacia un framework CSS estándar, potente, robusto y popular, que proporcione un sistema de diseño canónico y accesible sin dependencias pesadas.

## Factores de Decisión

1. **Operación 100% Offline y Embebida**: El bridge opera habitualmente en estaciones base aisladas, repetidores en cumbres y entornos sin acceso a Internet. Todos los recursos CSS, JS y fuentes de iconos deben residir localmente en `src/web/static/` sin depender de CDNs externas ni requerir compiladores Node.js/npm en el host objetivo (Raspberry Pi/Linux).
2. **Framework Moderno y Sobrio**: Adopción de **Bootstrap 5.3**, aprovechando su sistema de variables CSS, Flexbox/Grid responsivo y soporte nativo de modo oscuro (`data-bs-theme="dark"`).
3. **Eliminación Total de CSS Artesanal**: Retirar el 100% de las hojas de estilo manuales previas (`tokens.css`, `components.css`, `admin.css`, `chat.css`, `nodes.css`, `app.css`) para evitar deuda técnica y reglas CSS en conflicto, resolviendo todo el diseño mediante componentes y utilidades nativas de Bootstrap 5.3.
4. **Iconografía Oficial Estandarizada**: Adoptar **Bootstrap Icons (BI)** localmente (`bootstrap-icons.min.css` y archivos `.woff2`), sustituyendo la generación manual de SVGs en `icons.js`.
5. **Componentes Nativos y JS Unificado**: Adaptar los controladores de la SPA (`app.js`, `nodes.js`, `repeater.js`, etc.) para emplear los componentes interactivos nativos de Bootstrap (`bootstrap.Modal`, `bootstrap.Tab`, `bootstrap.Toast`), conservando todos los endpoints REST, WebSockets y la invariante de exclusión de repetidores/nodo local en la libreta de contactos.

## Decisión

1. **Assets Estáticos Locales**: Alojar en `src/web/static/`:
   - `css/bootstrap.min.css` (Bootstrap 5.3.3 compilado)
   - `css/bootstrap-icons.min.css` y directorio `fonts/` (Bootstrap Icons 1.11.3)
   - `js/bootstrap.bundle.min.js` (Bootstrap 5.3.3 con motor Popper.js integrado)
2. **Reestructuración Completa Inmediata de `index.html`**:
   - Etiqueta raíz con `<html lang="es" data-bs-theme="dark">`.
   - **Navbar Superior Fijo (`navbar navbar-expand-lg bg-body-tertiary border-bottom sticky-top`)**: Identidad, indicador de estado de radio LoRa, selector de idioma y chips de métricas globales (`badge bg-secondary`, `badge bg-success`).
   - **Barra Lateral Responsiva (Sidebar con `nav-pills`)**: Menú vertical de pestañas (`#tab-chat`, `#tab-contacts`, `#tab-nodes`, `#tab-map`, `#tab-analytics`, `#tab-logs`, `#tab-settings`), convertible en panel deslizante `offcanvas-start` para dispositivos móviles.
   - **Modales Nativos (`modal fade`)**: Reestructurar los 6 modales existentes (Repetidores, Detalles de Nodo, Contactos, Traceroute, Búsqueda Global Ctrl+K, Código QR) bajo la jerarquía canónica de Bootstrap (`modal-dialog`, `modal-content`, `modal-header`, `modal-body`, `modal-footer` y botón `btn-close`).
   - **Tablas de Datos**: Migrar todas las tablas de nodos, analítica, sniffer y logs a `<div class="table-responsive"><table class="table table-dark table-hover table-striped table-sm align-middle">`.
   - **Notificaciones Flotantes**: Estandarizar alertas y avisos de airtime mediante `<div class="toast-container position-fixed bottom-0 end-0 p-3">` y componentes `toast` nativos.
3. **Limpieza de Archivos Obsoletos**:
   - Eliminar `tokens.css`, `components.css`, `admin.css`, `chat.css`, `nodes.css`, `app.css` y `icons.js`.
4. **Adaptación de Scripts Frontend**:
   - Actualizar los módulos JS para instanciar `bootstrap.Modal.getOrCreateInstance()`, `bootstrap.Tab.getOrCreateInstance()` y `bootstrap.Toast.getOrCreateInstance()`, emitiendo `<i class="bi bi-..."></i>` en lugar de plantillas SVG manuales.

## Consecuencias

- **Positivas**:
  - Código HTML/CSS estándar, mantenible, accesible (WCAG 2.2 AA) y con soporte responsive fluido entre móvil y escritorio.
  - Eliminación de ~209 KB de CSS manual fragmentado y sin dependencias externas en tiempo de ejecución.
  - Compatibilidad total con la suite REST y WebSocket de FastAPI.
- **Riesgos y Mitigación**:
  - *Ruptura de selectores DOM en JS*: Se mantiene un mapa estricto de IDs en `index.html` para asegurar que las referencias existentes (`document.getElementById(...)`) sigan resolviendo los mismos nodos del DOM.
  - *Impacto en Airtime LoRa*: Cero paquetes RF adicionales. Esta reestructuración es puramente de capa cliente (Web SPA) y no afecta la tasa de envío ni el consumo de canal de la radio.
