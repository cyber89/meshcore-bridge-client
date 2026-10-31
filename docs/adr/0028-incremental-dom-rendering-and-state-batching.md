# ADR 0028: Renderizado Incremental y Procesamiento en Lotes del Estado DOM

- **Estado**: Aceptado
- **Fecha**: 2026-10-31
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: `src/web/static/js/core/store.js`, `src/web/static/js/core/eventbus.js`, `src/web/static/js/modules/nodes.js`, `tests/test_frontend_ui_audit.py`, `tests/test_palette_live_nodes_browser.py`

---

## Contexto y Problema

En redes de malla LoRa con densidad media-alta (decenas o cientos de nodos cliente, repetidores y beacons de telemetría emitiendo periódicamente), la interfaz web de MeshCore Bridge recibía ráfagas continuas de eventos a través del WebSocket (`node_discovered`, `node_updated`, `telemetry_updated`).

El módulo de nodos (`NodesModule` en `src/web/static/js/modules/nodes.js`) presentaba dos deficiencias críticas de rendimiento:

1. **Destrucción y Reconstrucción Masiva del DOM**:
   - Cada evento entrante invocaba `renderNodes()`, el cual ejecutaba `container.innerHTML = ""` y reconstruía completamente la cuadrícula HTML para todos los nodos registrados.
   - En topologías con más de 50 dispositivos, esto provocaba *Layout Thrashing*, saturación del hilo principal de JavaScript (*Long Tasks* superiores a 150 ms) y pérdida del foco de teclado/accesibilidad.
2. **Propagación Desincronizada en el Almacén de Estado**:
   - Cada actualización individual en `Store` emitía un evento síncrono e independiente hacia todos sus suscriptores.
   - Al recibir paquetes de ráfaga o sincronizaciones de historial, los módulos ejecutaban ciclos de renderizado redundantes para datos que cambiaban casi simultáneamente.
3. **Ausencia de Desuscripción en EventBus**:
   - `EventBus` carecía de un mecanismo canónico para remover escuchadores (`off()`), aumentando el riesgo de fugas de memoria al desmontar vistas o regenerar controladores.

---

## Factores de Decisión

1. **Rendimiento UI y Eliminación de Bloqueos (60 FPS)**:
   - Mantener el tiempo de procesamiento de eventos UI por debajo del umbral perceptible (menos de 16 ms), garantizando fluidez en navegadores móviles y hardware de recursos limitados.
2. **Mutaciones Atómicas Agrupadas (*State Batching*)**:
   - Permitir que múltiples modificaciones de colecciones o estados se agrupen y emitan una única notificación consolidada.
3. **Preservación del Estado Visual del DOM (*In-Place Updates*)**:
   - No destruir tarjetas existentes. Actualizar únicamente las etiquetas y valores modificados (LQI, batería, estado online/offline, timestamp de último contacto).
4. **Ordenamiento Inteligente Diferido (*Debounced Sort*)**:
   - Desacoplar la recepción de datos del ordenamiento visual en pantalla mediante un temporizador amortiguado (*debounce*).

---

## Decisión

Se implementa una solución de optimización reactiva basada en tres componentes:

### 1. Desuscripción Segura en `EventBus.off()`
En `src/web/static/js/core/eventbus.js`, se incorpora el método `off(event, handler)` para remover manejadores registrados de forma idempotente, facilitando la limpieza de escuchadores transitorios.

### 2. Procesamiento en Lotes con `Store.batch()`
En `src/web/static/js/core/store.js`, se introduce el mecanismo de agrupamiento:
```javascript
batch(updater) {
  this._batchDepth++;
  try {
    updater();
  } finally {
    this._batchDepth--;
    if (this._batchDepth === 0 && this._pendingNotifications.size > 0) {
      this._flushPendingNotifications();
    }
  }
}
```
Durante la ejecución de `updater`, las notificaciones a los observadores quedan encoladas. Al salir del bloque más externo, se ejecuta una única emisión por cada clave de estado modificada, eliminando re-renderizados espurios en cascada.

### 3. Renderizado Incremental y Debounce en `NodesModule`
En `src/web/static/js/modules/nodes.js`:
- **Actualización en el Lugar (*In-Place Patching*)**:
  Al actualizar un nodo, se localiza su tarjeta mediante su selector identificador (`#node-card-${cssSafePubkey}`). Si existe, se modifican exclusivamente los elementos secundarios correspondientes (texto de SNR, barra de batería, badge de LQI) sin tocar el contenedor padre.
- **Inserción Atómica con `DocumentFragment`**:
  Nuevos nodos se renderizan en memoria y se insertan en el DOM mediante fragmentos documentales para minimizar los recálculos de reflujo (*reflow*).
- **Ordenamiento con Debounce de 400 ms**:
  Las solicitudes de reordenamiento de la cuadrícula no se ejecutan de inmediato; se acumulan y procesan tras 400 ms de inactividad de eventos, evitando saltos visuales erráticos durante ráfagas de paquetes LoRa.

---

## Consecuencias

### Positivas
- **Cero Bloqueo de Interfaz**: Se eliminan las pausas perceptibles y los *Long Tasks* en la vista de Nodos.
- **Preservación de Selección y Scroll**: El usuario puede interactuar con una tarjeta o leer telemetría mientras entran nuevos paquetes en la malla sin perder la posición ni el foco de teclado.
- **Menor Consumo de CPU y Batería**: Disminución sustancial de recálculos de estilo en dispositivos móviles y clientes remotos.

### Negativas / Restricciones
- La lógica de renderizado requiere selectores DOM consistentes y funciones de actualización granular, lo que exige mayor disciplina en la plantilla de tarjetas frente al enfoque ingenuo de reemplazo total.

---

## Trazabilidad de Código y Verificación

- **Implementación**:
  - `src/web/static/js/core/eventbus.js`
  - `src/web/static/js/core/store.js`
  - `src/web/static/js/modules/nodes.js`
- **Suites de Verificación**:
  - `tests/test_frontend_ui_audit.py` (Inspección de rendimiento DOM y estructura de tarjetas).
  - `tests/test_palette_live_nodes_browser.py` (Actualización en vivo de nodos sin pérdida de foco).
  - `tests/test_e2e_playwright.py` (Navegación fluida y verificación de la cuadrícula unificada de nodos).
