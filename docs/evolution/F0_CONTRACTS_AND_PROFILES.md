# F0 — Contratos, Perfiles e Invariantes de MeshCore Bridge

**Fecha:** 2026-10-21  
**Estado:** Canónico (Fase F0 del Plan de Evolución `nuevo.md`)  
**Autor:** Agente Lead Orchestrator & System Architect  

---

## 1. Inventario de Consumidores y Contratos Actuales

El análisis del código fuente en producción identifica cinco familias de consumidores con contratos explícitos:

### 1.1 Endpoints REST (`/api/*`)
- **Canales (`src/web/controllers/channels_controller.py`)**:
  - `GET /api/channels`: Lista de canales configurados.
  - `POST /api/channels`: Creación / actualización de canal.
  - `DELETE /api/channels/{idx}`: Eliminación de canal por índice.
  - `POST /api/channels/sync`: Solicitud de sincronización de canales desde la radio física.
- **Mensajería y Chat (`src/web/controllers/chat_controller.py`, `messages_controller.py`)**:
  - `GET /api/chat/history`: Consulta paginada con cursor temporal y límite.
  - `POST /api/chat/send`: Envío de mensaje (canal público, canal secundario o mensaje directo).
- **Contactos y Nodos (`src/web/controllers/contacts_controller.py`, `nodes_controller.py`)**:
  - `GET /api/contacts`: Lista de contactos de usuario (exclusivamente roles `CLIENT`/`ROOM`/`SENSOR`, nunca `REPEATER`).
  - `GET /api/nodes`: Lista unificada de todos los nodos de la malla (incluyendo repetidores).
- **Administración y Telemetría (`src/web/controllers/admin_controller.py`, `system_controller.py`)**:
  - `POST /api/admin/ping_zero`: Ping hop 0 a repetidor.
  - `POST /api/admin/traceroute`: Traceroute hacia nodo destino.
  - `POST /api/admin/command`: Ejecución de comandos remotos en repetidores.
  - `GET /api/system/status`, `GET /api/system/health`: Telemetría y estado operativo de la estación.

### 1.2 Eventos WebSocket (`src/web/asgi_ws_hub.py`)
- Flujo en tiempo real sobre `/ws`:
  - `chat_message`: Nuevo mensaje de chat recibido por radio (con LQI, SNR, RSSI).
  - `chat_delivery_update`: Actualización de estado de entrega (`queued`, `sent`, `delivered`, `failed`).
  - `node_discovered`: Anuncio o beacon recibido de un nodo en la malla.
  - `telemetry_update`: Lectura de telemetría o estado de canal.
  - `admin_event`: Respuesta a comando administrativo o traceroute.

### 1.3 Tópicos MQTT (Local y Comunitario / Externo)
- **Tópicos Derivados del Prefijo (`src/mqtt_client.py:87–94`)**:
  - Estado y LWT: `{prefix}/bridge/state` (`online`/`offline` retenido).
  - Salud: `{prefix}/bridge/health`.
  - Transmisión saliente (Suscripción): `{prefix}/tx`.
  - Confirmación de transmisión (Publicación): `{prefix}/tx/status`.
  - Comandos administrativos generales (Suscripción): `{prefix}/admin/cmd`.
  - Respuestas administrativas (Publicación): `{prefix}/admin/status`.
  - Comandos por repetidor (Suscripción): `{prefix}/admin/repeater/+/cmd`.
- **Tópicos Históricamente Cableados con Constantes Globales (Hallazgo H3)**:
  - `TOPIC_RX_PUBLIC` (`src/rx_router.py:1100`).
  - `TOPIC_RX_CHANNEL` (`src/rx_router.py:1102`).
  - `TOPIC_RX_DIRECT` (`src/rx_router.py:1122`).
  - `TOPIC_TX_STATUS` (`src/bridge_core.py:1121`).
  - `TOPIC_ADMIN_STAT` (`src/admin/*`).
  - `TOPIC_ADMIN_REPEATER` (`src/admin/*`).
  - *Mitigación F1.3*: Centralización en un resolvedor único `MqttTopics`.

### 1.4 Servidor Proxy TCP Companion (`src/tcp_companion_server.py`)
- Puerto por defecto `5000` (configurable con `TCP_SERVER_PORT`).
- Framing binario oficial MeshCore: `<` (`0x3C`, App a Radio) y `>` (`0x3E`, Radio a App) + uint16 LE length + payload.
- Tamaño máximo de trama: `MAX_FRAME_SIZE = 300` bytes (alineado al parser oficial `meshcore_py 2.3.14`).
- Arbitraje transaccional: Las respuestas de comandos (`opcode < 0x80`) se dirigen exclusivamente al `response_owner` que envió la orden. Los paquetes asíncronos de RF / eventos (`opcode >= 0x80`) se difunden en broadcast a todos los clientes conectados.

---

## 2. Matriz de Perfiles y Propietarios de Recursos

| Perfil | Componentes Esenciales | Componentes Opcionales | Propietario de Tareas y Colas |
|---|---|---|---|
| **`core`** | Serial Driver, SDK Adapter, `TxRateLimiter`, `AirtimeTracker`, `StationDatabase` (SQLite), `NodeRegistry`. | Ninguno. Modo headless puro sin red IP expuesta. | `MeshCoreBridge._background_tasks`, worker de escritura SQLite. |
| **`web`** | `core` + FastAPI / Uvicorn ASGI, `AsgiWsHub`, SPA estática, controladores REST. | Servidor proxy TCP Companion. | Event loop ASGI, `AsgiWsHub._connections`. |
| **`companion`** | `core` + `MeshCoreCompanionServer` (TCP 5000). | Servidor web ASGI. | `MeshCoreCompanionServer._client_tasks`, `_writer_tasks`. |
| **`mqtt`** | `core` + `MeshCoreMqttClient` (local) y/o `ExternalMqttClient` (comunitario). | Servidor web ASGI, proxy Companion. | `MeshCoreMqttClient._loop`, `MqttDispatcher._inbound_tasks`. |
| **Combinado** | Unión de las capacidades habilitadas. | Cada subsistema se inicia solo si su flag (`*_ENABLED`) es verdadero. | `ServicesManager` supervisa la salud y recarga con rollback. |

---

## 3. Invariantes Inmutables del Sistema

1. **Exclusión Estricta de Repetidores (`REPEATER` / `ROUTER`)**:
   - Nunca aparecen en la libreta de contactos (`/api/contacts`).
   - Bloqueo total de mensajería de chat (broadcast o DM) hacia nodos de tipo repetidor. La interacción es únicamente administrativa (ping 0, telemetría, traceroute, configuración remota).
2. **Exclusión Estricta del Nodo Local (`LOCAL`)**:
   - Nunca se incluye en contactos ni en vecinos de la malla.
   - Prohibido el envío de mensajes dirigidos a la clave pública propia (prevención de bucle infinito).
3. **Autoridad Única de Radio y Cola TX**:
   - Solo un proceso puede abrir el transceptor serie USB.
   - Toda transmisión debe pasar por `TxRateLimiter` para arbitraje de prioridad y control de airtime.
4. **Autoridad Transaccional de SQLite**:
   - SQLite con WAL es la única autoridad de persistencia (chat, ACK monotónico, airtime, contactos, sesiones).
   - Los archivos JSON previos son únicamente origen de migración histórica.
5. **Monotonicidad de Estados de Chat**:
   - Prohibida la regresión de estado: una confirmación `delivered` nunca puede ser degradada a `sent` o `queued` por un evento tardío o fuera de orden.

---

## 4. Decisiones Registradas del Usuario (Sesión 2026-10-21)

1. **Consumidores MQTT y n8n Remotos en LAN**:
   - El broker local Mosquitto gestionado por los instaladores (`install.sh`, `install.ps1`) NO utilizará acceso anónimo ni escuchará sin control.
   - Se configurará bind explícito en la interfaz LAN o `0.0.0.0` con autenticación obligatoria mediante usuario y contraseña (`allow_anonymous false`) y listas de control de acceso (ACL).
2. **Política de `command_id` en Workflows MQTT (Idempotencia)**:
   - **Modo Legado**: Órdenes sin `command_id` o `id` se aceptan con garantías limitadas (sin deduplicación), emitiendo advertencia estructurada en logs.
   - **Modo Idempotente**: Órdenes con `command_id` son registradas atómicamente en un ledger persistido en SQLite antes de su despacho a la radio. Solicitudes con el mismo ID y misma huella semántica devuelven el estado registrado sin retransmitir por RF. Solicitudes con el mismo ID pero diferente huella producen conflicto (`CONFLICT`).
3. **Retención del Ledger de Comandos**:
   - No se añadirá ningún timer periódico ni hilo de limpieza en segundo plano (prevención de fugas y cumplimiento de la regla de timers).
   - Se aplicará un tope estricto de **10 000 filas** verificado y podado en el momento de la inserción transaccional (`DELETE FROM command_ledger WHERE id IN (SELECT id FROM command_ledger ORDER BY created_at ASC LIMIT MAX(0, count - 10000))`).
4. **Colas y Presupuestos de Memoria**:
   - Se conservan estrictamente los límites vigentes en el código (`MAX_MQTT_INBOUND_TASKS = 50`, `MQTT_MAX_PAYLOAD_BYTES = 128 KiB`, timeout de drenado de 2 segundos, presupuestos de cola TX y airtime).

---

## 5. Procedimiento de Respaldo y Rollback de SQLite (WAL-Consistent)

Antes de cualquier migración de esquema en `src/station_database.py`:
1. **Respaldo Consistente en Caliente**:
   - Debido a que SQLite opera en modo `PRAGMA journal_mode=WAL`, copiar simplemente `meshcore.sqlite3` sin los archivos `-wal` y `-shm` produce corrupción de transacciones pendientes.
   - Se utilizará la API nativa `sqlite3.Connection.backup()`:
     ```python
     def backup_database(src_conn: sqlite3.Connection, backup_path: Path) -> None:
         backup_path.parent.mkdir(parents=True, exist_ok=True)
         with sqlite3.connect(backup_path) as dst_conn:
             src_conn.backup(dst_conn)
     ```
2. **Reversión de Esquema**:
   - Cada migración debe estar versionada (`PRAGMA user_version`).
   - Si la inicialización detecta una versión superior a la soportada por el código actual, el arranque debe abortar inmediatamente con error explícito de incompatibilidad hacia abajo (*fail-closed*), sin reescribir ni truncar la base de datos.

---

## 6. Decisiones Pendientes (Para Fases Posteriores F4–F6)

- Definición del hardware y SBC objetivo (Raspberry Pi Zero 2W, Pi 4, Orange Pi) para las mediciones de latencia de F5.
- Posible ampliación a webhook HTTP directo para n8n sin broker MQTT intermedio.
- Criterios cuantitativos para evaluar la separación física del backend web en un proceso independiente (F6).
