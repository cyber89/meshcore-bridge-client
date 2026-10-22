# ADR 0020: Extracción de Servicios de Aplicación y Desacoplamiento de Canales (`ChannelService`)

- **Estado**: Aceptado
- **Fecha**: 2026-10-21
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: Fase F3.1 del Plan de Evolución `nuevo.md`, `src/application/channels.py`, `src/web/controllers/channels_controller.py`, `src/bridge_core.py`

---

## Contexto y Problema

Históricamente, el estado de los canales de la estación LoRa (índice, nombre, clave secreta / PSK, hash) residía dentro del controlador web `ChannelsController` (`src/web/controllers/channels_controller.py`).
Esta arquitectura acoplaba el núcleo de la estación a la presencia del servidor web HTTP:
1. `src/bridge_core.py:888–900` accedía directamente a `self.web_server.router.channels_ctrl` y a sus variables privadas `_mutation_lock`, `_write_task`, `_dirty` para auto-importar canales al arrancar el hardware.
2. Si la estación se ejecutaba en modo headless (`WEB_ENABLED=false`), la importación de canales fallaba o se omitía por completo.
3. `src/routers/system_handler.py:164–169` mutaba directamente el diccionario en memoria `router_ctx.web_server.router.channels`.
4. El material criptográfico (claves secretas de canal / PSK) se almacenaba en la misma estructura expuesta a la interfaz web, arriesgando fugas accidentales si no se redactaba explícitamente en cada serialización.

## Factores de Decisión

1. **Monolito Modular e Independencia Web**: El estado de la estación, los canales y la sincronización con el hardware deben funcionar con o sin interfaz web.
2. **Seguridad y Principio de Menor Privilegio**: Las vistas públicas de canales (`ChannelPublicView`) deben redactar o excluir las claves privadas por diseño, permitiendo el acceso a la PSK únicamente en operaciones administrativas expresamente autorizadas.
3. **Persistencia Transaccional y Bloqueo Concurrente**: Las mutaciones de canales requieren confirmación atómica en hardware (transceptor LoRa) antes de persistirse en SQLite (`channels`), garantizando que un fallo de hardware no deje un canal fantasma guardado en base de datos.

## Decisión

Se decide extraer la lógica de gestión de canales a un servicio de aplicación desacoplado: **`ChannelService`** en `src/application/channels.py`:
1. **Responsabilidades de `ChannelService`**:
   - Poseer la tabla de canales, los bloqueos de mutación asíncronos (`asyncio.Lock`), el seguimiento de eliminaciones (*tombstones*) y la persistencia atómica en SQLite / JSON fallback.
   - Proveer métodos públicos tipados: `get_channel_snapshots()`, `get_channel()`, `update_channel()`, `delete_channel()`, `sync_from_radio()`.
   - Separar el modelo de dominio interno (`ChannelRecord`) del modelo de vista pública (`ChannelPublicSnapshot`), donde `secret_key` / `psk` se omiten o redactan a menos que se solicite expresamente con privilegios.
2. **Refactorización de Consumidores**:
   - `MeshCoreBridge` construye y posee la instancia de `ChannelService`.
   - `ChannelsController` se convierte en un adaptador delgado que delega todas las consultas y mutaciones a `ChannelService`.
   - `SystemHandler` y el auto-bootstrap de radio en `MeshCoreBridge` consumen exclusivamente la API pública de `ChannelService`.

## Consecuencias

- **Positivas**:
  - La estación puede inicializar, persistir y sincronizar canales LoRa en modo estrictamente headless (`WEB_ENABLED=false`).
  - Eliminación del acceso a campos y locks privados (`_mutation_lock`, `_dirty`, `_write_task`) desde orquestadores externos.
  - Protección robusta contra fugas de material criptográfico de canales en endpoints y logs.
- **Negativas / Compensaciones**:
  - Requiere actualizar todos los puntos de acceso a canales en backend y controladores para consumir la nueva interfaz de servicio.
