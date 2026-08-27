# TODO2 - Hallazgos Adicionales de Auditoría (Post-Reporte Inicial)

> **Fecha de análisis**: 2026-08-24
> **Alcance**: Código fuente completo de MeshCore Bridge (`src/`, `tests/`, `config.py`)
> **Metodología**: Revisión manual exhaustiva del código, comparación cruzada con `TODO.md` y `Report.md` existentes
> **Objetivo**: Identificar errores, vulnerabilidades y deficiencias **NO documentadas** en auditorías previas

---

## Categorías de Hallazgos

| Categoría | Nuevos | Severidad |
|-----------|--------|-----------|
| Seguridad (SEC) | 5 | CRITICAL/HIGH |
| Concurrencia (CONC) | 3 | MEDIUM/HIGH |
| Calidad (QUAL) | 5 | MEDIUM/LOW |
| Robustez (ROB) | 4 | MEDIUM/HIGH |
| Frontend (FE) | 2 | LOW/MEDIUM |

---

## Seguridad (SEC)

### SEC-007: Autenticación ausente en TCP Companion Server
- **Ubicación**: `src/tcp_companion_server.py:43-59`
- **Severidad**: CRITICAL
- **Descripción**: El servidor TCP en el puerto 5000 acepta conexiones de cualquier cliente de la red sin autenticación. Cualquier dispositivo en la LAN puede enviar comandos de radio arbitrarios.
- **Impacto**: Acceso no autorizado a la radio LoRa, posibilidad de inyectar comandos maliciosos.
- **Recomendación**: Implementar autenticación por token o handshake con credenciales pre-compartidas.

### SEC-008: CORS wildcard permite solicitudes cross-origin desde cualquier dominio
- **Ubicación**: `src/web/http_server.py:197-207`
- **Severidad**: HIGH
- **Descripción**: `Access-Control-Allow-Origin: *` en la respuesta CORS preflight permite que cualquier sitio web haga solicitudes a la API del bridge.
- **Impacto**: Un sitio web malicioso podría ejecutar comandos admin o transmitir mensajes vía el bridge desde el navegador de un usuario en la misma LAN.
- **Recomendación**: Restringir el origen a configuraciones específicas o implementar autenticación CORS estricta.

### SEC-009: WebSocket handshake sin validación de Origin
- **Ubicación**: `src/web/http_server.py:233-264`
- **Severidad**: HIGH
- **Descripción**: El handshake WebSocket no valida el header `Origin`, permitiendo conexiones WebSocket cross-origin.
- **Impacto**: Sitios web maliciosos podrían establecer conexiones WebSocket persistentes para recibir datos en tiempo real o inyectar comandos.
- **Recomendación**: Validar el header `Origin` contra una lista blanca de orígenes permitidos.

### SEC-010: Variables de entorno sensibles potencialmente visibles en logs
- **Ubicación**: `config.py:49-53`
- **Severidad**: MEDIUM
- **Descripción**: `MQTT_PASSWORD` se carga desde `.env` y se almacena en variables de entorno del proceso. En entornos con acceso a `/proc/<pid>/environ`, las credenciales MQTT serían visibles.
- **Impacto**: Exposición de credenciales MQTT en entornos multi-tenant.
- **Recomendación**: No store passwords in env vars; usar archivos de configuración con permisos restrictivos o vault de secretos.

### SEC-011: Path traversal en WebSocket upgrade potencial
- **Ubicación**: `src/web/http_server.py:156-159`
- **Severidad**: MEDIUM
- **Descripción**: La detección de WebSocket upgrade ocurre antes de la validación de path traversal. Un atacante podría enviar una solicitud de upgrade con path malicioso para potencialmente acceder a recursos no autorizados.
- **Impacto**: El bypass de la validación de archivos estáticos podría permitir lectura de archivos arbitrarios.
- **Recomendación**: Mover la validación de WebSocket upgrade después de la validación de path.

---

## Concurrencia (CONC)

### CONC-010: PacketDeduplicator sin sincronización thread-safe
- **Ubicación**: `src/deduplicator.py:13-64`
- **Severidad**: MEDIUM
- **Descripción**: `PacketDeduplicator` usa `collections.OrderedDict` sin locks. Los métodos `is_duplicate` y `is_duplicate_sync` pueden ser llamados desde el hilo de paho-mqtt y desde asyncio simultáneamente.
- **Impacto**: Posibles condiciones de carrera que podrían causar pérdida de deduplicación o corrupción del OrderedDict.
- **Recomendación**: Usar `threading.Lock` o implementar la deduplicación completamente en el event loop de asyncio.

### CONC-011: `_background_tasks` set puede crecer indefinidamente
- **Ubicación**: `src/bridge_core.py:151`
- **Severidad**: MEDIUM
- **Descripción**: `_background_tasks: set[asyncio.Task[Any]]` se usa para mantener tareas en background, pero las tareas completadas solo se eliminan mediante `add_done_callback`. Si una tarea falla sin completarse, puede permanecer en el set indefinidamente.
- **Impacto**: Fuga de memoria gradual por acumulación de referencias a tareas completadas.
- **Recomendación**: Implementar limpieza periódica del set o usar un mecanismo de timeout para tareas staled.

### CONC-012: Race condition en `tx_count` y `tx_error_count`
- **Ubicación**: `src/bridge_core.py:529,545,564,576`
- **Severidad**: MEDIUM
- **Descripción**: Los contadores `tx_count` y `tx_error_count` se incrementan sin sincronización explícita. Aunque CPython tiene el GIL, operaciones como `self.tx_count += 1` no son atómicas en presencia de `await`.
- **Impacto**: Conteo inexacto de métricas bajo alta carga.
- **Recomendación**: Usar `asyncio.Lock` o contadores atómicos para métricas críticas.

---

## Calidad (QUAL)

### QUAL-011: Código duplicado masivo en `_handle_mesh_channel_msg` y `_handle_mesh_direct_msg`
- **Ubicación**: `src/rx_router.py:621-765` vs `src/rx_router.py:767-906`
- **Severidad**: MEDIUM
- **Descripción**: Los métodos `_handle_mesh_channel_msg` y `_handle_mesh_direct_msg` contienen ~145 líneas de código casi idéntico (extracción de telemetría, detección de comandos, publicación MQTT, broadcasting WebSocket).
- **Impacto**: Dificultad de mantenimiento, riesgo de inconsistencias al modificar un método sin actualizar el otro.
- **Recomendación**: Extraer la lógica común a un método privado `_handle_mesh_msg_common(msg, event_type_str)`.

### QUAL-012: `_route_logs` importa módulos dentro del método
- **Ubicación**: `src/web/api_router.py:796,836,846`
- **Severidad**: LOW
- **Descripción**: `from src.diagnostics import DiagnosticManager` se ejecuta dentro del método `_route_logs` en múltiples puntos. Aunque Python cachea imports, esto añade overhead innecesario y dificulta la lectura.
- **Impacto**: Rendimiento marginal reducido, código menos legible.
- **Recomendación**: Mover el import al nivel de módulo.

### QUAL-013: Fallback a index.html para archivos estáticos inexistentes
- **Ubicación**: `src/web/http_server.py:386-404`
- **Severidad**: LOW
- **Descripción**: Cuando un archivo estático no existe, el servidor sirve `index.html` como fallback. Esto ocurre incluso para requests a paths como `/api/noexiste` que no deberían servir HTML.
- **Impacto**: Comportamiento confuso para clientes que esperan 404 en rutas inexistentes.
- **Recomendación**: Servir fallback solo para paths de SPA (sin extensión), no para todos los archivos inexistentes.

### QUAL-014: Variable `_SENDER_PREFIX_RE` no está optimizada para compilación
- **Ubicación**: `src/rx_router.py:36`
- **Severidad**: LOW
- **Descripción**: La expresión regular `_SENDER_PREFIX_RE` se compila al nivel de módulo, lo cual es correcto, pero el patrón `re.DOTALL` puede causar comportamiento inesperado con saltos de línea en textos de radio.
- **Impacto**: Posible extracción incorrecta de nombres con mensajes multilínea.
- **Recomendación**: Evaluar si `re.DOTALL` es necesario o si `re.MULTILINE` sería más apropiado.

### QUAL-015: `_safe_int` y `_safe_float` en config.py no validan rangos
- **Ubicación**: `config.py:30-42`
- **Severidad**: LOW
- **Descripción**: Las funciones `_safe_int` y `_safe_float` solo validan que el valor sea convertible, pero no validan rangos lógicos (ej: `BAUD_RATE` negativo, `LORA_DEFAULT_SF` fuera de 7-12, `WEB_PORT` fuera de 1-65535).
- **Impacto**: Configuraciones inválidas podrían causar comportamientos erráticos en runtime.
- **Recomendación**: Agregar validación de rangos para parámetros críticos.

---

## Robustez (ROB)

### ROB-008: `broadcast_companion_frame` no maneja backpressure
- **Ubicación**: `src/tcp_companion_server.py:85-116`
- **Severidad**: MEDIUM
- **Descripción**: El método `broadcast_companion_frame` escribe a todos los clientes sin verificar si el buffer de escritura está saturado. Un cliente lento podría causar acumulación de datos en memoria.
- **Impacto**: Fuga de memoria si un cliente TCP no consume datos lo suficientemente rápido.
- **Recomendación**: Implementar límite de tamaño de buffer por cliente o usar `await writer.drain()` con timeout.

### ROB-009: `_watchdog_loop` es un stub sin funcionalidad real
- **Ubicación**: `src/bridge_core.py:486-489`
- **Severidad**: LOW
- **Descripción**: El método `_watchdog_loop` solo duerme `WATCHDOG_INTERVAL_SEC` segundos en un loop infinito sin hacer ninguna verificación real. Es un stub de compatibilidad con tests.
- **Impacto**: Confusión sobre la funcionalidad real del watchdog.
- **Recomendación**: Eliminar o marcar explícitamente como deprecated.

### ROB-010: `_force_serial_reconnect` incrementa contador sin await de la reconexión
- **Ubicación**: `src/bridge_core.py:474-484`
- **Severidad**: MEDIUM
- **Descripción**: `_force_serial_reconnect` incrementa `serial_reconnect_count` pero no espera a que la reconexión se complete realmente. El método `disconnect()` es await pero `connect()` no se llama.
- **Impacto**: El contador de reconexiones se incrementa sin que la reconexión realmente ocurra.
- **Recomendación**: Agregar `await self.serial_adapter.connect()` después de `disconnect()`.

### ROB-011: `MeshcoreFrame.serialize()` calcula CRC con `struct.pack(">H")` (big-endian)
- **Ubicación**: `src/protocol_types.py:386`
- **Severidad**: MEDIUM
- **Descripción**: El CRC se serializa en big-endian (`>H`) pero el header se serializa en little-endian (`<BBHHBH`). Aunque el CRC se calcula correctamente, la diferencia de endianness entre header y CRC podría causar confusión y errores en implementaciones futuras.
- **Impacto**: Riesgo de bugs si se modifica el formato CRC sin entender la asimetría.
- **Recomendación**: Documentar explícitamente la convención de endianness para CRC vs header.

---

## Frontend (FE)

### FE-006: WebSocket no implementa ping/pong desde el servidor
- **Ubicación**: `src/web/http_server.py:284-297`
- **Severidad**: LOW
- **Descripción**: El servidor WebSocket solo responde a pings del cliente, pero no envía pings propios para detectar conexiones muertas.
- **Impacto**: Conexiones WebSocket zombi podrían acumularse sin ser detectadas.
- **Recomendación**: Implementar ping periódico desde el servidor y cerrar conexiones que no respondan.

### FE-007: Métricas WebSocket enviadas sin compresión
- **Ubicación**: `src/web/http_server.py:83-91,265-282`
- **Severidad**: LOW
- **Descripción**: Las actualizaciones de métricas (cada 2 segundos) envían payloads JSON completos sin compresión ni deltagging.
- **Impacto**: Consumo de ancho de banda innecesario en conexiones con múltiples clientes.
- **Recomendación**: Implementar WebSocket permessage-deflate o enviar solo deltas de métricas.

---

## Priorización Recomendada

| Prioridad | IDs | Acción |
|-----------|-----|--------|
| **Inmediata** | SEC-007, SEC-008, SEC-009 | Implementar autenticación TCP, restringir CORS, validar Origin en WebSocket |
| **Corto plazo** | CONC-010, ROB-008, ROB-010 | Agregar locks al deduplicador, manejar backpressure TCP, corregir reconexión |
| **Mediano plazo** | QUAL-011, SEC-010, CONC-011 | Refactorizar código duplicado, mejorar manejo de secretos, limpiar background tasks |
| **Bajo** | Resto | Corregir calidad de código, mejorar tests, optimizar frontend |

---

## Notas

- Estos hallazgos son **adicionales** a los documentados en `TODO.md` (SEC-001–006, CONC-001–009, QUAL-001–010, ROB-001–007, FE-001–005).
- Se recomienda integrar estos hallazgos en el `TODO.md` principal tras su revisión.
- Los tests existentes cubren la mayoría de los flujoshappy path pero no cubren los edge cases de concurrencia y seguridad identificados aquí.
