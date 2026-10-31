# ADR 0027: Endurecimiento de CSP y Desacoplamiento de session_startup.js

- **Estado**: Aceptado
- **Fecha**: 2026-10-31
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: `src/web/asgi_security.py`, `src/web/static/index.html`, `src/web/static/js/session_startup.js`, `src/web/static/js/core/auth.js`, `tests/test_auth_startup_browser.py`

---

## Contexto y Problema

Como parte del endurecimiento integral de seguridad de **MeshCore Bridge v3.0** (alineado con OWASP Top 10 A03:2021 — Injection), la cabecera `Content-Security-Policy` (CSP) gestionada por `AsgiSecurityMiddleware` en `src/web/asgi_security.py` requería la eliminación estricta de la directiva `'unsafe-inline'` en `script-src`.

Históricamente, la plantilla `src/web/static/index.html` contenía un bloque `<script>` en línea dentro del elemento `<head>`. Su propósito era:
1. Leer `localStorage.getItem("meshcore_theme")` o evaluar la preferencia del sistema operativo (`prefers-color-scheme: light`).
2. Configurar el atributo `data-bs-theme` y la hoja de estilos de Bootswatch (`bootstrap-zephyr.local.min.css`) antes de que el navegador dibujase la interfaz, evitando un molesto destello de tema blanco (*flash of unstyled/incorrect theme*).

Sin embargo, mantener este bloque obligaba a declarar `'unsafe-inline'` o a generar nonces criptográficos por solicitud HTTP. El uso de nonces dinámicos invalidaba el cacheado estático inmutable con `ETag` / `gzip` del archivo `index.html` servido por `AsgiAssetHandler`.

Al migrar inicialmente la lógica a un archivo externo `/js/session_startup.js`, se introdujo con la etiqueta `<script src="/js/session_startup.js"></script>` sin atributos asíncronos. Esto generó un bloqueo sincrónico del analizador HTML del navegador (*parser blocking*): el evento `DOMContentLoaded` no se disparaba hasta que el script se descargaba y ejecutaba completamente, provocando congelamientos y *timeouts* en suites de pruebas de navegador y en dispositivos cliente con conectividad restringida.

---

## Factores de Decisión

1. **Eliminación Total de `'unsafe-inline'` en `script-src`**:
   - Garantizar que ningún script en línea o inyectado por terceros pueda ejecutarse en el contexto de la aplicación, cerrando vectores de Cross-Site Scripting (XSS).
2. **Compatibilidad con Caché Estático Inmutable**:
   - Evitar nonces por solicitud en `index.html` para permitir que el servidor ASGI devuelva respuestas HTTP 304 Not Modified y compresión `gzip` estática precalculada.
3. **Arranque Asíncrono sin Bloqueo del DOM**:
   - La inicialización del tema y la consulta temprana de la sesión de autenticación (`/api/auth/session`) no deben bloquear el análisis del DOM ni retrasar el evento `DOMContentLoaded`.
4. **Prevención de Destellos de Interfaz (*FOUC* / *Login Flash*)**:
   - Un usuario con una cookie de sesión válida no debe observar momentáneamente el formulario de inicio de sesión durante la comprobación de credenciales.

---

## Decisión

Se implementa una arquitectura desacoplada de arranque y seguridad compuesta por tres pilares:

### 1. Política CSP Estricta sin `'unsafe-inline'`
En `src/web/asgi_security.py`, la directiva de scripts se fija estrictamente a orígenes propios:
```text
script-src 'self';
```
Queda prohibido el uso de `'unsafe-inline'` o `'unsafe-eval'`. Todos los scripts de la SPA deben servirse como recursos locales independientes.

### 2. Desacoplamiento Asíncrono en `session_startup.js`
En `src/web/static/index.html`, la carga se realiza de manera explícitamente asíncrona:
```html
<script async src="/js/session_startup.js"></script>
```
El archivo `/js/session_startup.js`:
- Aplica inmediatamente las clases de densidad compacta y el tema guardado en `localStorage`.
- Inicia en paralelo la promesa de consulta de autenticación antes de que el grafo de módulos ES de `app.js` termine de parsearse:
  ```javascript
  if (Object.hasOwn(window, "meshcoreSessionStartup")) return;
  window.meshcoreSessionStartup = fetch("/api/auth/session", {
    credentials: "same-origin",
    cache: "no-store",
  }).catch(() => null);
  ```
- Al cargarse como `async`, no detiene la construcción del DOM y permite que `app.js` reutilice el resultado del `fetch` en vuelo sin emitir peticiones duplicadas.

### 3. Estado de Autenticación Pendiente en CSS
El elemento `<body>` incluye la clase `auth-pending` por defecto en `index.html`:
- Oculta el formulario de login y la interfaz de la aplicación mientras `session_startup.js` y `BrowserAuthentication` validan la sesión.
- Si la sesión es válida, se remueve la clase y se muestra `#app`; si no hay sesión, se oculta el splash de carga `#authStartup` y se muestra `#loginForm` de forma limpia.

---

## Consecuencias

### Positivas
- **Máxima Protección XSS**: La política CSP rechaza cualquier inyección de script no autorizado.
- **Rendimiento Óptimo**: `index.html` se entrega pre-comprimido con `gzip` y cabeceras `Cache-Control` deterministas.
- **Sin Bloqueo de DOM**: El navegador procesa la estructura semántica y recursos en paralelo.
- **Compatibilidad con Pruebas E2E**: Las pruebas de Playwright (`test_auth_startup_browser.py`) verifican tanto cargas instantáneas como retrasos inducidos de scripts sin bloqueos de tiempo de espera.

### Negativas / Restricciones
- Cualquier código JavaScript futuro debe residir en archivos estáticos `.js` dentro de `src/web/static/js/` y ser registrado en el manifiesto de activos (`scripts/build_frontend.cjs`).
- No se admiten manipulaciones de atributos `onclick="..."` en el HTML; todos los manejadores de eventos deben enlazarse mediante `addEventListener()` en sus respectivos módulos.

---

## Trazabilidad de Código y Verificación

- **Implementación**:
  - `src/web/asgi_security.py`
  - `src/web/static/index.html`
  - `src/web/static/js/session_startup.js`
  - `src/web/static/js/core/auth.js`
- **Suites de Verificación**:
  - `tests/test_web_security_and_maps.py` (Validación de cabeceras CSP y ausencia de `'unsafe-inline'`).
  - `tests/test_auth_startup_browser.py` (Verificación de arranque asíncrono, ausencia de flash de login y reutilización de fallback de módulo).
